
import os
import sys
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

print("--- FETCH LIGHTER ACCOUNT INDEX ---")

public_address = input("Please enter your Public Wallet Address (L1 default address): ").strip()
if not public_address or not public_address.startswith("0x"):
    print("Invalid address. It should start with '0x'.")
    sys.exit(1)

try:
    import lighter
    from lighter.api_client import ApiClient
    from lighter.configuration import Configuration
    from lighter.api import AccountApi
except ImportError as e:
    print(f"\nCRITICAL: Could not import lighter SDK: {e}")
    sys.exit(1)

async def async_main():
    base_url = os.getenv("LIGHTER_BASE_URL", "https://testnet.zklighter.elliot.ai")
    print(f"Connecting to: {base_url}")
    
    try:
        conf = Configuration(host=base_url)
        api_client = ApiClient(conf)
        account_api = AccountApi(api_client)
            
        print(f"Querying account for address: {public_address}...")
        
        # Try finding the method dynamically
        method_name = 'get_account_by_l1_address'
        if hasattr(account_api, 'accounts_by_l1_address'):
            method_name = 'accounts_by_l1_address'
        elif not hasattr(account_api, method_name):
            print("Method not found. Available methods:")
            print([m for m in dir(account_api) if not m.startswith('_')])
            await api_client.close()
            return
            
        method = getattr(account_api, method_name)
        
        # Execute Query
        import inspect
        if inspect.iscoroutinefunction(method):
            acc = await method(public_address)
        else:
            acc = method(public_address)
            if inspect.iscoroutine(acc):
                acc = await acc

        # --- INSPECTION START ---
        print("\n--- OBJECT INSPECTION ---")
        print(f"Type: {type(acc)}")
        
        # Helper to dump object
        def dump_obj(obj):
            if hasattr(obj, 'to_dict'):
                return obj.to_dict()
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            return str(obj)

        data = dump_obj(acc)
        print(f"Data: {data}")
        print("-------------------------")
        
        # Try to extract index from known patterns
        index = None
        
        # Case 1: Direct index
        if isinstance(data, dict):
            index = data.get('index') or data.get('account_index') or data.get('id')
            
            # Case 2: SubAccounts / List wrapper
            # User reported data is wrapped in 'sub_accounts'
            sub_accounts = data.get('sub_accounts') or data.get('accounts')
            if not index and sub_accounts:
                if isinstance(sub_accounts, list) and len(sub_accounts) > 0:
                    print(f"Found {len(sub_accounts)} sub-accounts.")
                    first = sub_accounts[0]
                    # recursively check first account
                    first_data = dump_obj(first)
                    print(f"First Account: {first_data}")
                    if isinstance(first_data, dict):
                        index = first_data.get('index') or first_data.get('account_index') or first_data.get('id')

        if index is not None:
            print(f"\n>>> FOUND ACCOUNT INDEX: {index} <<<")
            print(f"Please update your .env file with:")
            print(f"LIGHTER_ACCOUNT_INDEX={index}")
        else:
            print("\nCOULD NOT IDENTIFY INDEX AUTOMATICALLY.")
            print("Please check the 'Data' output above look for 'index' or 'id'.")
        
        await api_client.close()

    except Exception as e:
        print(f"API Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_main())
    finally:
        loop.close()

if __name__ == "__main__":
    main()
