
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())

from app.services.execution.dex.lighter_adapter import LighterAdapter

from dotenv import load_dotenv, find_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Force load from root .env
    env_path = os.path.join(os.getcwd(), '.env')
    print(f"Loading .env from: {env_path}")
    load_dotenv(dotenv_path=env_path, override=True)
    
    print("--- TESTING LIGHTER ADAPTER ---")
    print(f"Loaded LIGHTER_ACCOUNT_INDEX: {os.getenv('LIGHTER_ACCOUNT_INDEX')}")
    
    # Mock Config
    config = {
        "bot": {"mode": "paper"},
        "exchange": {"name": "lighter"}
    }
    
    try:
        print("Initializing Adapter...")
        adapter = LighterAdapter(config)
        print("Adapter Initialized.")
        
        print("\n1. Fetching Balance...")
        balance = adapter.fetch_balance()
        print(f"Balance: {balance}")
        
        print("\n2. Fetching Positions...")
        positions = adapter.fetch_positions()
        print(f"Positions: {positions}")
        
        print("\n--- TEST COMPLETE ---")
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
