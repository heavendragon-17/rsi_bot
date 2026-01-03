# RSI Bot

A Python bot that sends RSI-based alerts to Telegram.

---

## Quick Start

### Create environment file

Create a file named `env.txt` in the project root:

```txt
TELEGRAM_BOT_TOKEN=PASTE_YOUR_TOKEN_HERE
TARGET_CHAT_ID=PASTE_YOUR_CHAT_ID_HERE
```

---

### Run setup

#### Linux / macOS / Git Bash / WSL

```bash
source setup.sh
```

#### Windows (PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

This will:

-   Create a virtual environment
-   Load environment variables
-   Activate the virtual environment
-   Install dependencies

---

## Run the bot

Make sure the virtual environment is active, then run:

```bash
python main.py
```

---

## Environment Variables

| Variable           | Description        |
| ------------------ | ------------------ |
| TELEGRAM_BOT_TOKEN | Telegram bot token |
| TARGET_CHAT_ID     | Telegram chat ID   |

> ⚠️ Do NOT commit `env.txt` to version control.

---

## Requirements

-   Python **3.9+**
-   Telegram Bot Token
-   Telegram Chat ID
