from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from html import escape

import requests  # type: ignore[import-untyped]
import structlog


class TelegramBot:
    """
    Simple Telegram notification sender using Telegram HTTP API (requests).
    """

    def __init__(
        self,
        token_env: str = "TELEGRAM_BOT_TOKEN",
        chat_id_env: str = "TELEGRAM_CHAT_ID",
        *,
        failure_topic_id: int | None = None,
        failure_chat_id: str | int | None = None,
    ):
        # Read env vars
        self.token = os.getenv(token_env)
        self.default_chat_id = os.getenv(chat_id_env)

        # Logger (uses your existing logger.py)
        # Fix for duplicate logs: Use the existing 'rsi_bot' logger instead of initializing a new one or using root
        self.logger = structlog.get_logger("rsi_bot")

        if not self.token:
            raise RuntimeError(f"Missing {token_env} env var.")

        self._callbacks: dict[str, Callable[[str], None]] = {}
        self._update_observer: Callable[[dict], None] | None = None
        self._polling_thread: threading.Thread | None = None
        self._stop_polling = threading.Event()
        self._failure_topic_id = failure_topic_id
        self._failure_chat_id = str(failure_chat_id) if failure_chat_id is not None else None
        self._failure_report_lock = threading.Lock()
        self._last_failure_report_at = 0.0
        self._suppressed_failure_reports = 0

    FAILURE_REPORT_COOLDOWN_SECONDS = 60.0

    def send_message(
        self,
        message: str,
        chat_id: str | None = None,
        button_text: str | None = None,
        button_url: str | None = None,
        disable_web_preview: bool = True,
        message_thread_id: int | None = None,
    ) -> bool:
        """
        Send a Telegram message.

        Args:
            message: Plain text (no icons/emojis added automatically).
            chat_id: Overrides TELEGRAM_CHAT_ID if provided.
            button_text: If provided with button_url, adds an inline URL button.
            button_url: Target URL for the inline button.
            disable_web_preview: Avoid URL previews.
            message_thread_id: Forum-topic id. When set, the message is
                posted to that thread in the target supergroup.

        Returns:
            True if request succeeded (HTTP 200), False otherwise.
        """
        target_chat_id = chat_id or self.default_chat_id
        if not target_chat_id:
            self.logger.warning("TELEGRAM_CHAT_ID is not set; message skipped.")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        payload = {
            "chat_id": target_chat_id,
            "text": message,
            "disable_web_page_preview": bool(disable_web_preview),
            "parse_mode": "HTML",
        }

        if message_thread_id is not None:
            payload["message_thread_id"] = str(message_thread_id)

        # Add an inline URL button if requested
        if button_text and button_url:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": [[{"text": str(button_text), "url": str(button_url)}]]}
            )

        succeeded, reason = self._post_payload(url, payload)
        if not succeeded:
            self._report_delivery_failure(
                target_chat_id=target_chat_id,
                attempted_topic_id=message_thread_id,
                operation="send_message",
                reason=reason or "Telegram returned an unsuccessful response",
            )
        return succeeded

    def report_failure(
        self,
        operation: str,
        *,
        topic_id: int | None = None,
        reason: str,
    ) -> None:
        """Send a rate-limited developer alert for an upstream failure.

        This method deliberately bypasses the notification queue.  It is used
        when that queue is full or a notifier callback itself raised, so the
        error path cannot disappear behind the same failed mechanism.
        """

        self._report_delivery_failure(
            target_chat_id=self.default_chat_id,
            attempted_topic_id=topic_id,
            operation=operation,
            reason=reason,
        )

    def _post_payload(self, url: str, payload: dict) -> tuple[bool, str | None]:
        """Post once, including the safe plain-text retry for bad HTML."""

        try:
            response = requests.post(url, data=payload, timeout=5)
            if response.status_code == 400 and "can't parse entities" in response.text:
                # Telegram refuses the HTML parse (e.g. a raw '<' reached the
                # text). Resend without parse_mode so the message is delivered
                # unformatted instead of being silently dropped.
                self.logger.warning(
                    "Telegram rejected HTML entities; retrying as plain text",
                    error=response.text[:300],
                )
                plain_payload = {
                    key: value for key, value in payload.items() if key != "parse_mode"
                }
                retry = requests.post(url, data=plain_payload, timeout=5)
                if retry.status_code == 200:
                    self.logger.info(
                        "Telegram message sent as plain text after entity rejection",
                        chat_id=payload.get("chat_id"),
                    )
                    return True, None
                return False, (
                    f"HTML parse rejected, plain-text retry returned HTTP "
                    f"{retry.status_code}: {retry.text[:300]}"
                )

            if response.status_code == 200:
                self.logger.info("Telegram message sent", chat_id=payload.get("chat_id"))
                return True, None

            self.logger.warning(
                "Telegram send failed",
                status=response.status_code,
                error=response.text[:500],
            )
            return False, f"HTTP {response.status_code}: {response.text[:300]}"
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            self.logger.warning("Telegram send network error", error=str(exc))
            return False, f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            # Never crash the trading engine, but preserve the reason for the
            # direct developer alert below.
            self.logger.exception("Telegram send exception", error=str(exc))
            return False, f"{type(exc).__name__}: {exc}"

    def _report_delivery_failure(
        self,
        *,
        target_chat_id: str | None,
        attempted_topic_id: int | None,
        operation: str,
        reason: str,
    ) -> None:
        now = time.monotonic()
        with self._failure_report_lock:
            if now - self._last_failure_report_at < self.FAILURE_REPORT_COOLDOWN_SECONDS:
                self._suppressed_failure_reports += 1
                self.logger.warning(
                    "telegram_delivery_failure_alert_suppressed",
                    operation=operation,
                    topic_id=attempted_topic_id,
                    suppressed=self._suppressed_failure_reports,
                )
                return
            suppressed = self._suppressed_failure_reports
            self._suppressed_failure_reports = 0
            self._last_failure_report_at = now

        alert_chat_id = self._failure_chat_id or target_chat_id
        if not alert_chat_id:
            self.logger.error(
                "telegram_delivery_failure_unreportable",
                operation=operation,
                topic_id=attempted_topic_id,
                error=reason,
            )
            return

        alert_topic_id = self._failure_topic_id
        if alert_topic_id == attempted_topic_id:
            # A debug-topic failure must fall back to the chat's main thread.
            alert_topic_id = None
        suppressed_line = (
            f"\nSuppressed duplicate failures: {suppressed}" if suppressed else ""
        )
        text = (
            "🚨 <b>Telegram delivery failure</b>\n"
            "The original notification was not delivered.\n"
            f"Operation: <code>{escape(operation)}</code>\n"
            f"Target topic: <code>{escape(str(attempted_topic_id or 'main chat'))}</code>\n"
            f"Reason: <pre>{escape(reason[:700])}</pre>"
            f"{suppressed_line}\n"
            "Check the bot service logs and Telegram permissions."
        )
        alert_payload = {
            "chat_id": alert_chat_id,
            "text": text,
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        }
        if alert_topic_id is not None:
            alert_payload["message_thread_id"] = str(alert_topic_id)

        sent, alert_reason = self._post_payload(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            alert_payload,
        )
        if sent:
            self.logger.error(
                "telegram_delivery_failure_alert_sent",
                operation=operation,
                topic_id=attempted_topic_id,
                alert_topic_id=alert_topic_id,
            )
            return

        # If the configured debug topic itself is invalid, make one bounded
        # attempt in the chat's main thread before conceding that Telegram is
        # unavailable.
        if alert_topic_id is not None:
            alert_payload.pop("message_thread_id", None)
            fallback_sent, fallback_reason = self._post_payload(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                alert_payload,
            )
            if fallback_sent:
                self.logger.error(
                    "telegram_delivery_failure_alert_sent",
                    operation=operation,
                    topic_id=attempted_topic_id,
                    alert_topic_id=None,
                    fallback=True,
                )
                return
            alert_reason = fallback_reason or alert_reason

        self.logger.error(
            "telegram_delivery_failure_alert_failed",
            operation=operation,
            topic_id=attempted_topic_id,
            error=alert_reason or "unknown error",
        )

    def start_polling(
        self,
        callbacks: dict[str, Callable[[str], None]],
        *,
        update_observer: Callable[[dict], None] | None = None,
    ) -> None:
        """
        Start a background thread to long-poll for incoming commands.

        Args:
            callbacks: A dictionary mapping command strings (e.g. "/status") to
                       callback functions. The callbacks receive the chat_id string.
        """
        if self._polling_thread and self._polling_thread.is_alive():
            self.logger.warning("Telegram polling is already running.")
            return

        self._callbacks = callbacks
        self._update_observer = update_observer
        self._stop_polling.clear()
        self._polling_thread = threading.Thread(target=self._poll_updates, name="telegram-polling", daemon=True)
        self._polling_thread.start()
        self.logger.info("Telegram command polling started.")

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        self._stop_polling.set()
        if self._polling_thread:
            self._polling_thread.join(timeout=5)

    def _poll_updates(self) -> None:
        """Long-polling loop for fetching Telegram updates."""
        offset = 0
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"

        while not self._stop_polling.is_set():
            try:
                # Use a timeout of 30 seconds for true long-polling
                payload = {"offset": offset, "timeout": 30}

                # set request timeout slightly larger than long-poll timeout
                resp = requests.get(url, params=payload, timeout=35)

                if resp.status_code != 200:
                    self.logger.error(f"Telegram getUpdates failed: {resp.status_code} - {resp.text}")
                    time.sleep(5)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    self.logger.error(f"Telegram getUpdates returned ok=False: {data}")
                    time.sleep(5)
                    continue

                for update in data.get("result", []):
                    update_id = update.get("update_id")
                    offset = update_id + 1  # acknowledge this update

                    message = update.get("message")
                    if not message:
                        continue

                    if self._update_observer is not None:
                        try:
                            self._update_observer(update)
                        except Exception:
                            # Observability must never prevent command
                            # handling or stop the polling loop.
                            self.logger.exception("Telegram update observer failed")

                    text = message.get("text", "").strip()
                    chat_id = str(message.get("chat", {}).get("id"))

                    if not text:
                        continue

                    # Match command
                    for cmd, callback in self._callbacks.items():
                        if text.startswith(cmd):
                            try:
                                callback(chat_id)
                            except Exception:
                                self.logger.exception(f"Error executing callback for {cmd} from chat {chat_id}")
                            break

            except requests.exceptions.Timeout:
                # Normal for long-polling
                continue
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                self.logger.warning(f"Telegram polling network error: {e}")
                time.sleep(5)
            except Exception:
                self.logger.exception("Telegram polling loop error")
                time.sleep(5)

    # ------------------------------------------------------------
    # Helpers for building trade URLs (optional convenience)
    # ------------------------------------------------------------
    @staticmethod
    def binance_spot_url(symbol: str) -> str:
        """
        Build a Binance Spot trade URL from symbol.

        Accepts:
          - "BTC/USDT" -> BTC_USDT
          - "BTCUSDT"  -> BTC_USDT (best-effort)
        """
        s = symbol.replace("/", "").upper()

        # Best-effort parsing for common quote assets
        for quote in ("USDT", "BUSD", "USDC", "FDUSD", "BTC", "ETH"):
            if s.endswith(quote) and len(s) > len(quote):
                base = s[: -len(quote)]
                return f"https://www.binance.com/en/trade/{base}_{quote}"

        # Fallback: just try raw symbol with underscore
        return f"https://www.binance.com/en/trade/{symbol.replace('/', '_')}"

    @staticmethod
    def binance_futures_url(symbol: str) -> str:
        """
        Build a Binance Futures URL from symbol.

        Accepts:
          - "BTC/USDT" -> BTCUSDT
          - "BTCUSDT"  -> BTCUSDT
        """
        s = symbol.replace("/", "").upper()
        return f"https://www.binance.com/en/futures/{s}"
