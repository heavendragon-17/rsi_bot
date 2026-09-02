"""SignalRunner — multi-strategy signal-bot orchestrator.

Wires together the pieces from slices 1-6:
  * resolver builds ``StrategyInstanceConfig`` per active strategy (slice 4)
    plus the optional ``btc_rsi_cross_alert`` component via
    :func:`resolve_signal_runtime_config`
  * ``TimeframeMultiplexer`` fans out per-``(sym, tf)`` closes (slice 1)
  * ``BinanceStreamManager`` multi-TF path feeds the multiplexer (slice 2)
    and fires ``history_complete_callback`` after REST hydration
  * ``VirtualPositionStore`` holds the advisory positions (slice 5)
  * ``StrategyWorker`` per strategy runs analyze + exit monitor (slice 6)
  * ``BtcRsiCrossAlertWorker`` evaluates BTC M5 alignments / M15 crosses against
    native H1/H4 context and alerts Telegram-only (no orders, no virtual positions)
  * ``NotificationService`` carries every message (slice 3) including the
    SIGTERM shutdown broadcast formatted here (slice 6's
    :func:`format_shutdown_broadcast`).

Lifecycle:
    runner = SignalRunner(raw_config, notification_service)
    runner.start()
    runner.wait()   # blocks on SIGINT/SIGTERM
"""

from __future__ import annotations

import signal as signal_module
import threading
import time
from collections.abc import Callable

import structlog

from app.core.constants import SIGNAL_SHUTDOWN_JOIN_SECONDS
from app.core.events import Candle
from app.data.multiplexer import TimeframeMultiplexer
from app.data.stream_manager import BinanceStreamManager
from app.notification.notification_service import NotificationService
from app.signal.btc_rsi_cross_alert.config import BtcRsiCrossAlertConfig
from app.signal.btc_rsi_cross_alert.worker import BtcRsiCrossAlertWorker
from app.signal.signal_formatter import format_shutdown_broadcast
from app.signal.strategy_config import (
    StrategyInstanceConfig,
    resolve_signal_runtime_config,
)
from app.signal.strategy_worker import StrategyWorker
from app.signal.virtual_position import VirtualPositionStore
from app.trading.strategy.loader import load_strategy_instance

logger = structlog.get_logger()


class SignalRunner:
    """Orchestrates the signal bot's lifecycle."""

    def __init__(
        self,
        raw_config: dict,
        notification_service: NotificationService,
        *,
        history_limit: int = 300,
        install_signal_handlers: bool = True,
    ) -> None:
        self._raw = raw_config
        self._notifier = notification_service
        self._history_limit = history_limit
        self._install_signal_handlers = install_signal_handlers

        self._instance_cfgs: list[StrategyInstanceConfig] = []
        self._alert_cfgs: tuple[BtcRsiCrossAlertConfig, ...] = ()
        self._workers: list[StrategyWorker] = []
        self._alert_workers: list[BtcRsiCrossAlertWorker] = []
        self._threads: list[threading.Thread] = []
        self._alert_threads: list[threading.Thread] = []
        self._multiplexer: TimeframeMultiplexer | None = None
        self._stream: BinanceStreamManager | None = None
        self._vp_store = VirtualPositionStore()
        self._debug_topic_id: int = 0
        self._max_candles_per_tf: dict[str, int] = {}

        self._running = threading.Event()
        self._stop_event = threading.Event()
        self._started = False

    @property
    def vp_store(self) -> VirtualPositionStore:
        """Expose the VP store so the StatusWriter can snapshot open VPs."""
        return self._vp_store

    @property
    def strategies(self) -> list[StrategyInstanceConfig]:
        """Resolved active ordinary strategies (populated after start).

        Deliberately limited to ordinary single-frame strategy configs so
        ``/test_signal`` never fabricates a virtual-position card for the
        BTC RSI cross alert component.
        """
        return list(self._instance_cfgs)

    @property
    def alert_components(self) -> tuple[BtcRsiCrossAlertConfig, ...]:
        """Active typed alert-only signal components (defensive copy)."""
        return tuple(self._alert_cfgs)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Build + start every component. Idempotent after a first success."""
        if self._started:
            logger.debug("signal_runner_start_noop")
            return

        runtime_cfg = resolve_signal_runtime_config(self._raw)
        self._instance_cfgs = list(runtime_cfg.strategies)
        self._alert_cfgs = (
            (runtime_cfg.btc_rsi_cross_alert,)
            if runtime_cfg.btc_rsi_cross_alert is not None
            else ()
        )
        self._debug_topic_id = runtime_cfg.debug_topic_id
        if not self._instance_cfgs and not self._alert_cfgs:
            logger.warning("signal_runner_no_active_strategies")
            # Set the stop event so ``wait()`` returns immediately rather
            # than blocking forever on a never-started runner.
            self._stop_event.set()
            return

        data_cfg = self._raw.get("data") or {}
        self._max_candles_per_tf = dict(
            data_cfg.get("max_candles_per_timeframe") or {}
        )

        union = runtime_cfg.targets

        # Set the running flag AND register signal handlers BEFORE spawning
        # any threads or opening the WebSocket. If SIGTERM arrives during the
        # ramp-up window, the handler's ``stop()`` must see _running set (so
        # it proceeds past the idempotency guard) and any None-valued
        # attributes (stream, notifier) must be handled by ``stop()``.
        self._running.set()
        self._started = True
        if self._install_signal_handlers:
            signal_module.signal(signal_module.SIGINT, self._signal_handler)
            signal_module.signal(signal_module.SIGTERM, self._signal_handler)

        self._multiplexer = TimeframeMultiplexer(
            targets=set(union),
            max_candles_per_tf=self._max_candles_per_tf or None,
        )

        self._build_workers()

        self._stream = BinanceStreamManager(
            targets=set(union),
            multiplexer=self._multiplexer,
            history_limit=self._history_limit,
            history_complete_callback=self._notify_history_complete,
        )
        self._stream.start()

        logger.info(
            "signal_runner_started",
            strategies=[c.name for c in self._instance_cfgs],
            alert_components=[c.name for c in self._alert_cfgs],
            targets=sorted(union),
        )

    def stop(self) -> None:
        """Shut down in reverse dependency order. Safe to call repeatedly."""
        if not self._running.is_set():
            return
        self._running.clear()
        self._stop_event.set()
        logger.info("signal_runner_stopping")

        # 1. Stop the stream so no more candles arrive.
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                logger.exception("signal_runner_stream_stop_failed")

        # 2. Broadcast shutdown per strategy (only strategies with open VPs).
        # Wrapped: a failure here must not skip the worker-join and notifier-drain
        # phases that follow.
        try:
            self._send_shutdown_broadcasts()
        except Exception:
            logger.exception("signal_runner_shutdown_broadcast_failed")

        # 3. Request stop on every worker (clears its event + unblocks waits).
        for strategy_worker in self._workers:
            strategy_worker.request_stop()
        for alert_worker in self._alert_workers:
            alert_worker.request_stop()

        # 4. Join worker threads with a bounded timeout (ordinary + alert).
        for thread in self._threads + self._alert_threads:
            thread.join(timeout=SIGNAL_SHUTDOWN_JOIN_SECONDS)
            if thread.is_alive():
                logger.warning("signal_runner_worker_join_timeout", thread=thread.name)

        # 5. Drain the notification queue (waits up to NotificationWorker's own
        # 30 s timeout) — shutdown broadcast must flush before the process exits.
        try:
            self._notifier.stop()
        except Exception:
            logger.exception("signal_runner_notifier_stop_failed")

        logger.info("signal_runner_stopped")

    def wait(self) -> None:
        """Block until :meth:`stop` is invoked (typically by a signal).

        Uses ``_stop_event.wait(timeout=1)`` — shutdown unblocks immediately
        when :meth:`stop` sets the event, vs. sleeping out the full second.
        """
        last_heartbeat = 0
        reported_dead_threads: set[str] = set()
        all_threads = lambda: self._threads + self._alert_threads  # noqa: E731
        while not self._stop_event.wait(timeout=1):
            threads = all_threads()
            for thread in threads:
                if not thread.is_alive() and thread.name not in reported_dead_threads:
                    reported_dead_threads.add(thread.name)
                    logger.error(
                        "signal_runner_worker_not_alive",
                        thread=thread.name,
                    )
                    self._report_worker_failure(
                        "signal_runner_worker_liveness",
                        reason=(
                            f"{thread.name} stopped while the signal runner "
                            "was still active"
                        ),
                    )
            now = int(time.time())
            if now - last_heartbeat >= 60:
                alive = sum(1 for t in threads if t.is_alive())
                logger.info(
                    "signal_runner_heartbeat",
                    workers_alive=alive,
                    total=len(threads),
                )
                last_heartbeat = now

    def _report_worker_failure(self, operation: str, *, reason: str) -> None:
        """Report worker liveness failures without using the send queue."""

        reporter = getattr(self._notifier, "report_notification_failure", None)
        if not callable(reporter):
            logger.error(
                "signal_runner_failure_unreportable",
                operation=operation,
                error=reason,
            )
            return
        try:
            reporter(operation, topic_id=self._debug_topic_id, reason=reason)
        except Exception:
            logger.exception(
                "signal_runner_failure_report_failed",
                operation=operation,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _notify_history_complete(self) -> None:
        """Stream-manager hook: arm every alert worker after REST hydration.

        Runs exactly once after all fetch attempts return, before the
        WebSocket loop starts. Ordinary StrategyWorkers need no hook — their
        startup behavior is unchanged.
        """
        for worker in self._alert_workers:
            try:
                worker.on_history_complete()
            except Exception:
                logger.exception("btc_rsi_cross_history_ready_failed")

    def _build_workers(self) -> None:
        assert self._multiplexer is not None
        for strategy_cfg in self._instance_cfgs:
            # load_strategy_instance reads config["strategy"] (set by
            # as_legacy_dict) to pick the concrete class from STRATEGY_MAP.
            # Using the factory keeps the abstract/concrete type dance inside
            # the loader.
            strategy = load_strategy_instance(strategy_cfg.as_legacy_dict())
            strategy_worker = StrategyWorker(
                instance_cfg=strategy_cfg,
                strategy=strategy,
                multiplexer=self._multiplexer,
                vp_store=self._vp_store,
                notifier=self._notifier,
                debug_topic_id=self._debug_topic_id,
            )
            self._multiplexer.register_close_callback(
                _make_filtered_callback(strategy_worker)
            )
            thread = threading.Thread(
                target=strategy_worker.run,
                name=f"signal-worker-{strategy_cfg.name}",
                daemon=True,
            )
            self._workers.append(strategy_worker)
            self._threads.append(thread)
            thread.start()
            logger.info(
                "signal_worker_spawned",
                strategy=strategy_cfg.name,
                topic_id=strategy_cfg.telegram_topic_id,
                targets=sorted(strategy_cfg.targets),
            )

        for alert_cfg in self._alert_cfgs:
            alert_worker = BtcRsiCrossAlertWorker(
                config=alert_cfg,
                multiplexer=self._multiplexer,
                notifier=self._notifier,
                debug_topic_id=self._debug_topic_id,
            )
            self._multiplexer.register_close_callback(
                _make_alert_callback(alert_worker)
            )
            thread = threading.Thread(
                target=alert_worker.run,
                name=f"signal-alert-worker-{alert_cfg.name}",
                daemon=True,
            )
            self._alert_workers.append(alert_worker)
            self._alert_threads.append(thread)
            thread.start()
            logger.info(
                "signal_alert_worker_spawned",
                component=alert_cfg.name,
                topics=alert_cfg.telegram_topic_ids,
                targets=sorted(alert_cfg.targets),
            )

    def _send_shutdown_broadcasts(self) -> None:
        grouped = self._vp_store.all_open_by_strategy()
        for cfg in self._instance_cfgs:
            vps = grouped.get(cfg.name, [])
            if not vps:
                continue
            self._notifier.send_message(
                format_shutdown_broadcast(cfg.name, vps),
                topic_id=cfg.telegram_topic_id,
            )

    def _signal_handler(self, signum, frame) -> None:
        logger.info("signal_runner_received_signal", signum=signum)
        self.stop()


def _make_filtered_callback(
    worker: StrategyWorker,
) -> Callable[[str, str, Candle], None]:
    """One closure per worker: route only events for that worker's targets."""
    targets = worker.instance_cfg.targets

    def cb(symbol: str, timeframe: str, candle: Candle) -> None:
        if (symbol, timeframe) in targets:
            worker.enqueue(symbol, timeframe, candle)

    return cb


def _make_alert_callback(
    worker: BtcRsiCrossAlertWorker,
) -> Callable[[str, str, Candle], None]:
    """One closure for the BTC alert worker.

    The worker itself routes H1/H4 closes to synchronous confirmation and
    M5/M15 closes to its evaluation queue.
    """

    def cb(symbol: str, timeframe: str, candle: Candle) -> None:
        worker.handle_closed_candle(symbol, timeframe, candle)

    return cb
