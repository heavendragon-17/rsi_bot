import os
import asyncio
import logging
from dataclasses import dataclass

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("crypto-bot")


@dataclass
class Chatbot:
    """
    A simple chatbot that sends notifications about cryptocurrencies.
    This version sends messages to Telegram chat(s) instead of printing.
    """
    app: Application

    async def send_crypto_notification(self, chat_id: int, crypto_type: str) -> None:
        crypto_type = crypto_type.strip()
        if not crypto_type:
            await self._send(chat_id, "Please provide a cryptocurrency name (e.g., Bitcoin).")
            return

        message = f"📢 Notification: There is an update about {crypto_type}"
        await self._send(chat_id, message)

    async def _send(self, chat_id: int, message: str) -> None:
        await self.app.bot.send_message(chat_id=chat_id, text=message)


# ================= NEW: chatid command =================
async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"📌 Your chat ID is:\n\n{chat_id}")
# ======================================================


async def text_as_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    bot: Chatbot = context.application.bot_data["chatbot"]

    crypto_type = (update.message.text or "").strip()
    await bot.send_crypto_notification(chat_id, crypto_type)


def create_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var.")

    app = Application.builder().token(token).build()

    chatbot = Chatbot(app=app)
    app.bot_data["chatbot"] = chatbot

    # Register handlers
    app.add_handler(CommandHandler("chatid", chatid))   # 👈 added
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_as_crypto))

    return app


def main() -> None:
    app = create_application()
    app.run_polling()


if __name__ == "__main__":
    main()
