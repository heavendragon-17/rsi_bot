import asyncio
import logging
import os

from telegram_chatbot import create_application, Chatbot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auto-notifier")

COIN_NAME = "Bitcoin"
INTERVAL_SECONDS = 2
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
if not TARGET_CHAT_ID:
    raise RuntimeError("Missing TARGET_CHAT_ID env var.")

async def auto_notify(app, interval: int, coin: str, chat_id: int):
    chatbot: Chatbot = app.bot_data["chatbot"]
    while True:
        await asyncio.sleep(interval)
        await chatbot.send_crypto_notification(chat_id, coin)
        logger.info(f"Auto notification sent for {coin}")


async def main():
    app = create_application()
    await app.initialize()
    await app.start()

    asyncio.create_task(auto_notify(app, INTERVAL_SECONDS, COIN_NAME, TARGET_CHAT_ID))

    logger.info("Bot running with repeating auto-notification enabled...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
