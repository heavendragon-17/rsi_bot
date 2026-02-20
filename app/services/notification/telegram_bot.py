from __future__ import annotations

import json
import os
from typing import Optional

import requests

import logging




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
        self.logger = logging.getLogger("rsi_bot")

        if not self.token:
            raise RuntimeError(f"Missing {token_env} env var.")

    def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        button_text: Optional[str] = None,
        button_url: Optional[str] = None,
        disable_web_preview: bool = True,
    ) -> bool:
        """
        Send a Telegram message.

        Args:
            message: Plain text (no icons/emojis added automatically).
            chat_id: Overrides TELEGRAM_CHAT_ID if provided.
            button_text: If provided with button_url, adds an inline URL button.
            button_url: Target URL for the inline button.
            disable_web_preview: Avoid URL previews.

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
        }

        # Add an inline URL button if requested
        if button_text and button_url:
            payload["reply_markup"] = json.dumps(
                {
                    "inline_keyboard": [
                        [{"text": str(button_text), "url": str(button_url)}]
                    ]
                }
            )

        try:
            resp = requests.post(url, data=payload, timeout=5)

            if resp.status_code == 200:
                self.logger.info(
                    "Telegram message sent (chat_id=%s, button=%s)",
                    target_chat_id,
                    "yes" if (button_text and button_url) else "no",
                )
                return True

            # Telegram returns JSON error details; log it for debugging
            self.logger.warning(
                "Telegram send failed (status=%s): %s",
                resp.status_code,
                resp.text,
            )
            return False

        except Exception:
            # Never crash the trading engine
            self.logger.exception("Telegram send exception")
            return False

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
