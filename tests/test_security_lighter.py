import sys
import os
import logging
import pytest
import asyncio
from unittest.mock import MagicMock, patch

# 1. Mock the 'lighter' library and its submodules BEFORE importing the adapter
mock_lighter = MagicMock()
sys.modules["lighter"] = mock_lighter
sys.modules["lighter.api"] = MagicMock()

# Now we can import the adapter
from app.services.execution.dex.lighter_adapter import LighterAdapter

class TestLighterSecurity:

    @pytest.fixture
    def secret_key(self):
        return "SUPER_SECRET_PRIVATE_KEY_12345"

    @pytest.fixture
    def mock_env(self, secret_key):
        return {
            "LIGHTER_SECRET_KEY": secret_key,
            "LIGHTER_API_KEY_INDEX": "2",
            "LIGHTER_ACCOUNT_INDEX": "10",
            "LIGHTER_L1_ADDRESS": "0x123",
            "LIGHTER_BASE_URL": "https://testnet.example.com"
        }

    def test_create_order_logs_leak_secret(self, mock_env, secret_key, caplog):
        """
        Verify if create_order leaks the secret key in logs when an exception occurs
        that contains the secret key.
        """
        # Setup logging to capture everything
        caplog.set_level(logging.ERROR)

        # Patch environment variables
        with patch.dict(os.environ, mock_env):
            adapter = LighterAdapter(config={"bot": {"mode": "paper"}})

            error_msg = f"API Error with key: {secret_key}"

            # Setup Mock Client
            mock_client_instance = MagicMock()
            # Needed for context manager in _cleanup_client if it was one, but it's not.
            # But api_client.close is awaited.
            mock_client_instance.api_client.close = MagicMock(side_effect=lambda: asyncio.sleep(0))

            mock_lighter.SignerClient.return_value = mock_client_instance

            # Setup async failure for create_order
            async def async_raise(*args, **kwargs):
                raise ValueError(error_msg)

            mock_client_instance.create_order.side_effect = async_raise

            # Trigger create_order
            # This calls internal _create which catches exception and logs it
            with pytest.raises(Exception):
                adapter.create_order(
                    symbol="BTC/USDT",
                    order_type="limit",
                    side="buy",
                    amount=1,
                    price=10000
                )

            # Check logs
            found_secret = False
            for record in caplog.records:
                if secret_key in record.message:
                    found_secret = True
                    break

            assert not found_secret, "Security Fix Failed: Secret key FOUND in logs!"
