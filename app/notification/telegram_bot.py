from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable

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
        self._polling_thread: threading.Thread | None = None
        self._stop_polling = threading.Event()

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

        try:
            resp = requests.post(url, data=payload, timeout=5)

            if resp.status_code == 400 and "can't parse entities" in resp.text:
                # Telegram refuses the HTML parse (e.g. a raw '<' reached the
                # text). Resend without parse_mode so the message is delivered
                # unformatted instead of being silently dropped.
                self.logger.warning(
                    "Telegram rejected HTML entities; retrying as plain text",
                    error=resp.text[:300],
                )
                plain_payload = {
                    key: value
                    for key, value in payload.items()
                    if key != "parse_mode"
                }
                resp = requests.post(url, data=plain_payload, timeout=5)
                if resp.status_code == 200:
                    self.logger.info(
                        "Telegram message sent as plain text after entity "
                        "rejection",
                        chat_id=target_chat_id,
                    )
                    return True

            if resp.status_code == 200:
                self.logger.info(
                    "Telegram message sent",
                    chat_id=target_chat_id,
                    button="yes" if (button_text and button_url) else "no",
                )
                return True

            # Telegram returns JSON error details; log it for debugging
            self.logger.warning(
                "Telegram send failed",
                status=resp.status_code,
                error=resp.text,
            )
            return False

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            self.logger.warning(f"Telegram send network error: {e}")
            return False
        except Exception as e:
            # Never crash the trading engine
            self.logger.exception("Telegram send exception: %s", e)
            return False

    def start_polling(self, callbacks: dict[str, Callable[[str], None]]) -> None:
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
