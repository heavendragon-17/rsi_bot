"""SignalRunner — multi-strategy signal-bot orchestrator.

Wires together the pieces from slices 1-6:
  * resolver builds ``StrategyInstanceConfig`` per active strategy (slice 4)
  * ``TimeframeMultiplexer`` fans out per-``(sym, tf)`` closes (slice 1)
  * ``BinanceStreamManager`` multi-TF path feeds the multiplexer (slice 2)
  * ``VirtualPositionStore`` holds the advisory positions (slice 5)
  * ``StrategyWorker`` per strategy runs analyze + exit monitor (slice 6)
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
from app.signal.signal_formatter import format_shutdown_broadcast
from app.signal.strategy_config import (
    StrategyInstanceConfig,
    resolve_strategy_configs,
    validate_telegram_config,
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
        self._workers: list[StrategyWorker] = []
        self._threads: list[threading.Thread] = []
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Build + start every component. Idempotent after a first success."""
        if self._started:
            logger.debug("signal_runner_start_noop")
            return

        self._instance_cfgs = resolve_strategy_configs(self._raw)
        if not self._instance_cfgs:
            logger.warning("signal_runner_no_active_strategies")
            # Set the stop event so ``wait()`` returns immediately rather
            # than blocking forever on a never-started runner.
            self._stop_event.set()
            return

        self._debug_topic_id = validate_telegram_config(self._raw)

        data_cfg = self._raw.get("data") or {}
        self._max_candles_per_tf = dict(
            data_cfg.get("max_candles_per_timeframe") or {}
        )

        union = frozenset().union(*(cfg.targets for cfg in self._instance_cfgs))

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
        )
        self._stream.start()

        logger.info(
            "signal_runner_started",
            strategies=[c.name for c in self._instance_cfgs],
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

        # 3. Request stop on every worker (clears its event + enqueues sentinel).
        for worker in self._workers:
            worker.request_stop()

        # 4. Join worker threads with a bounded timeout.
        for thread in self._threads:
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
        while not self._stop_event.wait(timeout=1):
            now = int(time.time())
            if now - last_heartbeat >= 60:
                alive = sum(1 for t in self._threads if t.is_alive())
                logger.info(
                    "signal_runner_heartbeat",
                    workers_alive=alive,
                    total=len(self._threads),
                )
                last_heartbeat = now

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_workers(self) -> None:
        assert self._multiplexer is not None
        for cfg in self._instance_cfgs:
            # load_strategy_instance reads config["strategy"] (set by
            # as_legacy_dict) to pick the concrete class from STRATEGY_MAP.
            # Using the factory keeps the abstract/concrete type dance inside
            # the loader.
            strategy = load_strategy_instance(cfg.as_legacy_dict())
            worker = StrategyWorker(
                instance_cfg=cfg,
                strategy=strategy,
                multiplexer=self._multiplexer,
                vp_store=self._vp_store,
                notifier=self._notifier,
                debug_topic_id=self._debug_topic_id,
            )
            self._multiplexer.register_close_callback(
                _make_filtered_callback(worker)
            )
            thread = threading.Thread(
                target=worker.run,
                name=f"signal-worker-{cfg.name}",
                daemon=True,
            )
            self._workers.append(worker)
            self._threads.append(thread)
            thread.start()
            logger.info(
                "signal_worker_spawned",
                strategy=cfg.name,
                topic_id=cfg.telegram_topic_id,
                targets=sorted(cfg.targets),
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
