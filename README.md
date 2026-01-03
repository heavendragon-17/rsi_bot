# RSI Bot

## Setting up environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Setting environment variables

**Windows:**

```cmd
$env:TELEGRAM_BOT_TOKEN="PASTE_YOUR_TOKEN_HERE"
$env:TARGET_CHAT_ID="PASTE_YOUR_CHAT_ID_HERE"
```

**Linux/macOS:**

```bash
export TELEGRAM_BOT_TOKEN="PASTE_YOUR_TOKEN_HERE"
export TARGET_CHAT_ID="PASTE_YOUR_CHAT_ID_HERE"
```

## Running the bot

Activate your virtual environment if not already active, then run:

```bash
python main.py
```