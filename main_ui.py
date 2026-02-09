import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ui.bridge import BacktestUI

def main():
    parser = argparse.ArgumentParser(description="Backtest UI Launcher")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--test", action="store_true", help="Test mode (init only)")
    args = parser.parse_args()

    if args.test:
        try:
            ui = BacktestUI(debug=args.debug)
            print("Test mode: BacktestUI initialized successfully")
        except Exception as e:
            print(f"Test mode: BacktestUI initialization failed: {e}")
            sys.exit(1)
        return

    ui = BacktestUI(debug=args.debug)
    ui.start()

if __name__ == "__main__":
    main()
