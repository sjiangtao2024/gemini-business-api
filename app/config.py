"""
Configuration Loader - Load accounts from JSON with hot reload support

Loads account configuration from accounts.json and provides
hot reload capabilities for production use.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.models.account import Account

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Configuration loader for accounts.json"""

    def __init__(self, config_path: str = "config/accounts.json"):
        """
        Initialize Config Loader

        Args:
            config_path: Path to accounts.json file
        """
        self.config_path = Path(config_path)
        self.settings: Dict = {}

    def load_accounts(self) -> List[Account]:
        """
        Load accounts from JSON file

        Returns:
            List[Account]: List of Account instances

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If JSON is invalid or missing required fields
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please create config/accounts.json with your account credentials."
            )

        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {self.config_path}: {e}")

        # Load settings
        self.settings = config.get("settings", {})

        # Load accounts
        accounts_data = config.get("accounts", [])
        if not accounts_data:
            raise ValueError("No accounts found in configuration")

        accounts = []
        for idx, account_data in enumerate(accounts_data):
            try:
                account = self._create_account(account_data)
                accounts.append(account)
            except Exception as e:
                logger.error(f"Failed to load account #{idx + 1}: {e}")
                raise ValueError(f"Invalid account #{idx + 1}: {e}")

        logger.info(f"✅ Loaded {len(accounts)} account(s) from {self.config_path}")
        return accounts

    def _create_account(self, data: Dict) -> Account:
        """
        Create Account instance from configuration data

        Args:
            data: Account configuration dictionary

        Returns:
            Account: Account instance

        Raises:
            ValueError: If required fields are missing
        """
        required_fields = [
            "email",
            "team_id",
            "secure_c_ses",
            "host_c_oses",
            "csesidx",
            "user_agent",
            "created_at",
        ]

        # Check required fields
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        return Account(
            email=data["email"],
            team_id=data["team_id"],
            secure_c_ses=data["secure_c_ses"],
            host_c_oses=data["host_c_oses"],
            csesidx=data["csesidx"],
            user_agent=data["user_agent"],
            created_at=data["created_at"],
            expires_at=data.get("expires_at"),  # Optional
        )

    def get_setting(self, key: str, default=None):
        """
        Get setting value

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        return self.settings.get(key, default)

    def validate_config(self) -> bool:
        """
        Validate configuration file

        Returns:
            bool: True if valid

        Raises:
            ValueError: If validation fails
        """
        try:
            accounts = self.load_accounts()
            return len(accounts) > 0
        except Exception as e:
            raise ValueError(f"Configuration validation failed: {e}")
