import requests
import os

class TelegramBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    def send_message(self, message):
        if not self.token or not self.chat_id:
            # Silent fail or log if needed, avoid crashing
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {'chat_id': self.chat_id, 'text': message}
        try:
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
