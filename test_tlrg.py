import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not found in .env files")
    exit(1)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
try:
    response = requests.get(url).json()
    print("--- RAW RESPONSE FROM TELEGRAM ---")
    print(json.dumps(response, indent=2))
    print("----------------------------------")
    
    print("\n--- PARSED CHAT IDs ---")
    for update in response.get("result", []):
        # A message could be under 'message', 'channel_post', 'edited_message', etc.
        for key in ["message", "channel_post", "edited_message", "edited_channel_post", "my_chat_member"]:
            if key in update:
                chat = update[key].get("chat", {})
                if chat:
                    print(f"Found via '{key}': Title: {chat.get('title', 'N/A')}, Type: {chat.get('type', 'N/A')}, ID: {chat.get('id')}")
except Exception as e:
    print(f"Failed to fetch updates: {e}")
