"""Runnable signal-only composition for the Core V2.1 coordinator."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from app.notification.telegram_bot import TelegramBot
from app.signal.core_v2_1.buffer import ClosedCandleBuffer
from app.signal.core_v2_1.coordinator import (
    BootstrapStatus,
    CoreV21SignalCoordinator,
)
from app.signal.core_v2_1.core_adapter import (
    RUNTIME_STRATEGY_VERSION,
    CoreV21RuntimeEvaluator,
)
from app.signal.core_v2_1.hyperliquid_export import (
    DEFAULT_DATA_DIR,
    PUMP_FILENAME,
    PUMP_KEY,
    HyperliquidExportError,
    load_anchored_pump_m15_seed,
)
from app.signal.core_v2_1.market_data import (
    DEFAULT_FINALIZATION_DELAY,
    BinancePublicCandleSource,
    CompositeMarketDataRouter,
    HyperliquidPublicCandleSource,
    ReconnectingClosedCandlePoller,
)
from app.signal.core_v2_1.market_plan import build_core_v2_1_market_plan
from app.signal.core_v2_1.models import MarketPlan, ensure_utc
from app.signal.core_v2_1.outbox import (
    ConfirmingNotificationSink,
    DurableOutboxDispatcher,
    DurableOutboxWorker,
    TelegramOutboxSink,
)
from app.signal.core_v2_1.state_store import CoreV21StateStore

logger = structlog.get_logger(__name__)


class RuntimeReadinessError(RuntimeError):
    """Mandatory point-in-time history is incomplete; live mode stays off."""


@dataclass(frozen=True)
class RuntimeStartResult:
    hydrated_candles: int
    bootstrap: BootstrapStatus


@dataclass(frozen=True)
class RuntimeHealth:
    started: bool
    coordinator_ready: bool
    poller_alive: bool
    poller_ready: bool
    poller_last_error: str | None
    poller_last_success_at: datetime | None
    outbox_counts: Mapping[str, int]


class CoreV21LiveSignalRuntime:
    """Hydrate → recover → poll → evaluate → durable Telegram outbox.

    The object owns only public market-data clients and notification delivery.
    It deliberately has no exchange execution adapter and cannot place orders.
    """

    def __init__(
        self,
        *,
        state_database: str | Path,
        market_router: CompositeMarketDataRouter,
        notification_sink: ConfirmingNotificationSink,
        market_plan: MarketPlan | None = None,
        topic_by_symbol: Mapping[str, int | None] | None = None,
        poll_interval_seconds: float = 15.0,
        clock: Callable[[], datetime] | None = None,
        finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
        bootstrap_data_dir: str | Path | None = None,
    ) -> None:
        if finalization_delay < timedelta(0):
            raise ValueError("finalization_delay cannot be negative")
        self._clock = clock
        self._finalization_delay = finalization_delay
        self._plan = market_plan or build_core_v2_1_market_plan()
        # Recursive indicators are seeded from the stable persisted anchor;
        # a moving in-memory cap would change EMA/RSI/ATR after restart.
        self._buffer = ClosedCandleBuffer(max_candles_per_market=None)
        self._store = CoreV21StateStore(state_database)
        self._coordinator = CoreV21SignalCoordinator(
            strategy_version=RUNTIME_STRATEGY_VERSION,
            market_plan=self._plan,
            buffer=self._buffer,
            store=self._store,
            evaluator=CoreV21RuntimeEvaluator(),
            topic_by_symbol=topic_by_symbol,
        )
        self._router = market_router
        self._bootstrap_data_dir = (
            Path(bootstrap_data_dir).expanduser().resolve()
            if bootstrap_data_dir is not None
            else None
        )
        self._poller = ReconnectingClosedCandlePoller(
            market_router,
            self._plan.all_keys,
            self._coordinator.on_closed_candle,
            poll_interval_seconds=poll_interval_seconds,
            clock=self._clock,
            finalization_delay=finalization_delay,
        )
        self._dispatcher = DurableOutboxDispatcher(
            self._store,
            notification_sink,
        )
        self._outbox_worker = DurableOutboxWorker(self._dispatcher)
        self._started = False
        self._lifecycle_lock = threading.Lock()

    @classmethod
    def with_public_venues_and_telegram(
        cls,
        *,
        state_database: str | Path,
        telegram_chat_id: str | int,
        topic_by_symbol: Mapping[str, int | None] | None = None,
        poll_interval_seconds: float = 15.0,
        clock: Callable[[], datetime] | None = None,
        finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
        bootstrap_data_dir: str | Path | None = DEFAULT_DATA_DIR,
    ) -> CoreV21LiveSignalRuntime:
        """Build the production public-data/Telegram composition.

        ``TelegramBot`` reads only its bot token from the environment here;
        Binance and Hyperliquid data sources require no API credentials.
        """

        router = CompositeMarketDataRouter(
            (
                BinancePublicCandleSource(
                    clock=clock,
                    finalization_delay=finalization_delay,
                ),
                HyperliquidPublicCandleSource(
                    clock=clock,
                    finalization_delay=finalization_delay,
                ),
            )
        )
        sink = TelegramOutboxSink(
            TelegramBot(token_env="TELEGRAM_BOT_TOKEN"),
            chat_id=telegram_chat_id,
        )
        return cls(
            state_database=state_database,
            market_router=router,
            notification_sink=sink,
            topic_by_symbol=topic_by_symbol,
            poll_interval_seconds=poll_interval_seconds,
            clock=clock,
            finalization_delay=finalization_delay,
            bootstrap_data_dir=bootstrap_data_dir,
        )

    @property
    def coordinator(self) -> CoreV21SignalCoordinator:
        return self._coordinator

    def start(self, *, through: datetime | None = None) -> RuntimeStartResult:
        with self._lifecycle_lock:
            if self._started:
                raise RuntimeError("Core V2.1 live signal runtime is already started")
            if through is not None:
                boundary = ensure_utc(through, field_name="runtime start time")
            elif self._clock is not None:
                server_now = ensure_utc(
                    self._clock(),
                    field_name="runtime server clock",
                )
                boundary = server_now - self._finalization_delay
            else:
                boundary = self._router.finalized_through(
                    venues={key.venue for key in self._plan.all_keys},
                    finalization_delay=self._finalization_delay,
                )
            self._seed_anchored_pump_history(boundary)
            hydrated = self._coordinator.hydrate(self._router, through=boundary)
            bootstrap = self._coordinator.bootstrap(through=boundary)
            if not bootstrap.ready:
                details = "; ".join(bootstrap.missing_or_blocked)
                raise RuntimeReadinessError(
                    f"Core V2.1 startup failed closed: {details}"
                )

            for key in self._plan.all_keys:
                latest = self._buffer.latest_close(key)
                if latest is None:
                    raise RuntimeReadinessError(
                        f"Core V2.1 startup has no cursor for {key.storage_id}"
                    )
                self._poller.seed_cursor(key, latest)

            # Pending restart-catch-up advisories are durable before either
            # worker starts.  Delivery and market polling can now run safely.
            self._outbox_worker.start()
            try:
                self._poller.start()
            except Exception:
                self._outbox_worker.stop()
                raise
            self._started = True
            return RuntimeStartResult(
                hydrated_candles=hydrated,
                bootstrap=bootstrap,
            )

    def _seed_anchored_pump_history(self, through: datetime) -> None:
        """Import the canonical PUMP M15 prefix on an empty live database."""

        if self._bootstrap_data_dir is None or PUMP_KEY not in self._plan.all_keys:
            return
        if self._store.load_market_candles(PUMP_KEY):
            return
        seed_path = self._bootstrap_data_dir / PUMP_FILENAME
        if not seed_path.is_file():
            # A fresh venue fetch remains valid while the locked anchor is
            # still retained.  Once it is not, hydration fails closed with the
            # venue's explicit retention error.
            return
        try:
            candles = load_anchored_pump_m15_seed(
                self._bootstrap_data_dir,
                through=through,
            )
            inserted = self._store.persist_market_candles(candles)
        except HyperliquidExportError as exc:
            raise RuntimeReadinessError(
                f"Core V2.1 PUMP bootstrap failed closed: {exc}"
            ) from exc
        logger.info(
            "core_v2_pump_seed_imported",
            path=str(seed_path),
            candles=len(candles),
            inserted=inserted,
            venue=PUMP_KEY.venue.value,
            instrument=PUMP_KEY.instrument,
        )

    def stop(self) -> None:
        with self._lifecycle_lock:
            if not self._started:
                return
            self._poller.stop()
            # Best-effort immediate delivery of rows already due.  Anything
            # still retrying remains durable for the next process start.
            try:
                self._dispatcher.dispatch_due()
            finally:
                self._outbox_worker.stop()
                self._started = False

    def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            started=self._started,
            coordinator_ready=self._coordinator.is_ready,
            poller_alive=self._poller.is_alive,
            poller_ready=self._poller.is_ready,
            poller_last_error=self._poller.last_error,
            poller_last_success_at=self._poller.last_success_at,
            outbox_counts=self._store.outbox_counts(),
        )
