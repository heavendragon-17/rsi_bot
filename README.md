# RSI Bot System

A cryptocurrency trading bot designed to trade based on RSI and WMA signals. This system includes a modular architecture with a central core, market data management, strategy execution, and order management.

## Prerequisites

-   **Python 3.10+**: Ensure Python is installed and added to your PATH.
-   **Git**: Version control system to clone the repository.

## Installation (Windows)

1.  **Clone the repository:**

    ```powershell
    git clone https://github.com/heavendragon-17/rsi_bot.git
    ```

2.  **Run the setup script:**
    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\setup.ps1
    ```

## Configuration

### 1. Environment Variables (.env)

Create a `.env` file in the root directory to store your sensitive keys. You can duplicate the example file:

```powershell
copy .env.example .env
```

Open `.env` with a text editor (Notepad, VS Code) and fill in your API keys:

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here
TELEGRAM_TOKEN=your_telegram_bot_token
```

### 2. Bot Configuration (config.yaml)

Modify `config.yaml` to adjust the bot's behavior:

```yaml
bot:
    active: true
    mode: 'paper' # Set to "live" for real trading (RISKY!)

exchange:
    name: 'binance'

timeframe: '5m'
symbols:
    - 'BTC/USDT'
    - 'ETH/USDT'
```

## Running the Bot

Make sure your virtual environment is activated, then run:

```powershell
python main.py
```

The bot will initialize the database (`trades.db`), fetch historical data, and start listening to market streams.

## Troubleshooting

-   **'python' is not recognized**: Ensure you checked "Add Python to PATH" during installation.
-   **ImportError**: Make sure you activated the virtual environment (`.\venv\Scripts\activate`) before running the bot.
-   **Service unavailable / 451 Error**: If you are in a restricted region (like the US), Binance.com API may be blocked. You may need to use a VPN or switch to a supported exchange.
-   **Unit Tests**:

```
pytest tests/test_config_validation.py
```
