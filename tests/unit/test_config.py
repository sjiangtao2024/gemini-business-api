"""
Unit tests for ConfigLoader

Tests JSON configuration loading and validation.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import ConfigLoader
from app.models.account import Account


@pytest.fixture
def valid_config():
    """Valid configuration data"""
    now = datetime.now(timezone.utc)
    return {
        "accounts": [
            {
                "email": "test1@example.com",
                "team_id": "team-1",
                "secure_c_ses": "ses-1",
                "host_c_oses": "oses-1",
                "csesidx": "111111",
                "user_agent": "ua-1",
                "created_at": now.isoformat(),
            },
            {
                "email": "test2@example.com",
                "team_id": "team-2",
                "secure_c_ses": "ses-2",
                "host_c_oses": "oses-2",
                "csesidx": "222222",
                "user_agent": "ua-2",
                "created_at": now.isoformat(),
                "expires_at": (now).isoformat(),
            },
        ],
        "settings": {
            "account_expiry_days": 30,
            "expiry_warning_days": 3,
        },
    }


@pytest.fixture
def temp_config_file(valid_config):
    """Create temporary config file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(valid_config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


class TestConfigLoaderInit:
    """Test ConfigLoader initialization"""

    def test_init_sets_path(self):
        """Init should set config path"""
        loader = ConfigLoader("test/path.json")

        assert loader.config_path == Path("test/path.json")

    def test_init_default_path(self):
        """Init should use default path"""
        loader = ConfigLoader()

        assert loader.config_path == Path("config/accounts.json")

    def test_init_empty_settings(self):
        """Init should have empty settings"""
        loader = ConfigLoader()

        assert loader.settings == {}


class TestLoadAccounts:
    """Test load_accounts method"""

    def test_load_valid_config(self, temp_config_file):
        """Load valid configuration file"""
        loader = ConfigLoader(temp_config_file)
        accounts = loader.load_accounts()

        assert len(accounts) == 2
        assert all(isinstance(a, Account) for a in accounts)

    def test_load_sets_account_fields(self, temp_config_file):
        """Loaded accounts should have correct fields"""
        loader = ConfigLoader(temp_config_file)
        accounts = loader.load_accounts()

        account = accounts[0]
        assert account.email == "test1@example.com"
        assert account.team_id == "team-1"
        assert account.secure_c_ses == "ses-1"

    def test_load_sets_settings(self, temp_config_file):
        """Load should set settings"""
        loader = ConfigLoader(temp_config_file)
        loader.load_accounts()

        assert loader.settings["account_expiry_days"] == 30
        assert loader.settings["expiry_warning_days"] == 3

    def test_load_nonexistent_file_raises(self):
        """Loading nonexistent file should raise FileNotFoundError"""
        loader = ConfigLoader("nonexistent.json")

        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            loader.load_accounts()

    def test_load_invalid_json_raises(self):
        """Loading invalid JSON should raise ValueError"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json")
            temp_path = f.name

        try:
            loader = ConfigLoader(temp_path)

            with pytest.raises(ValueError, match="Invalid JSON"):
                loader.load_accounts()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_empty_accounts_raises(self):
        """Loading config with no accounts should raise ValueError"""
        config = {"accounts": [], "settings": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            temp_path = f.name

        try:
            loader = ConfigLoader(temp_path)

            with pytest.raises(ValueError, match="No accounts found"):
                loader.load_accounts()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_missing_required_field_raises(self):
        """Loading account with missing required field should raise ValueError"""
        now = datetime.now(timezone.utc)
        config = {
            "accounts": [
                {
                    "email": "test@example.com",
                    # Missing team_id
                    "secure_c_ses": "ses",
                    "host_c_oses": "oses",
                    "csesidx": "123",
                    "user_agent": "ua",
                    "created_at": now.isoformat(),
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            temp_path = f.name

        try:
            loader = ConfigLoader(temp_path)

            with pytest.raises(ValueError, match="Missing required fields"):
                loader.load_accounts()
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestGetSetting:
    """Test get_setting method"""

    def test_get_existing_setting(self, temp_config_file):
        """Get existing setting value"""
        loader = ConfigLoader(temp_config_file)
        loader.load_accounts()

        value = loader.get_setting("account_expiry_days")

        assert value == 30

    def test_get_nonexistent_setting_returns_default(self, temp_config_file):
        """Get nonexistent setting should return default"""
        loader = ConfigLoader(temp_config_file)
        loader.load_accounts()

        value = loader.get_setting("nonexistent", "default_value")

        assert value == "default_value"

    def test_get_setting_before_load_returns_default(self):
        """Get setting before load should return default"""
        loader = ConfigLoader()

        value = loader.get_setting("key", "default")

        assert value == "default"


class TestValidateConfig:
    """Test validate_config method"""

    def test_validate_valid_config(self, temp_config_file):
        """Validate valid configuration"""
        loader = ConfigLoader(temp_config_file)

        assert loader.validate_config() is True

    def test_validate_invalid_config_raises(self):
        """Validate invalid configuration should raise ValueError"""
        loader = ConfigLoader("nonexistent.json")

        with pytest.raises(ValueError, match="Configuration validation failed"):
            loader.validate_config()


class TestCreateAccount:
    """Test _create_account method"""

    def test_create_account_with_all_fields(self):
        """Create account with all required fields"""
        now = datetime.now(timezone.utc)
        data = {
            "email": "test@example.com",
            "team_id": "team-123",
            "secure_c_ses": "ses",
            "host_c_oses": "oses",
            "csesidx": "123456",
            "user_agent": "Mozilla/5.0",
            "created_at": now.isoformat(),
        }

        loader = ConfigLoader()
        account = loader._create_account(data)

        assert isinstance(account, Account)
        assert account.email == "test@example.com"
        assert account.team_id == "team-123"

    def test_create_account_with_optional_expires_at(self):
        """Create account with optional expires_at field"""
        now = datetime.now(timezone.utc)
        data = {
            "email": "test@example.com",
            "team_id": "team-123",
            "secure_c_ses": "ses",
            "host_c_oses": "oses",
            "csesidx": "123456",
            "user_agent": "Mozilla/5.0",
            "created_at": now.isoformat(),
            "expires_at": now.isoformat(),
        }

        loader = ConfigLoader()
        account = loader._create_account(data)

        assert account.expires_at is not None

    def test_create_account_missing_email_raises(self):
        """Create account without email should raise ValueError"""
        now = datetime.now(timezone.utc)
        data = {
            # Missing email
            "team_id": "team-123",
            "secure_c_ses": "ses",
            "host_c_oses": "oses",
            "csesidx": "123456",
            "user_agent": "Mozilla/5.0",
            "created_at": now.isoformat(),
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="Missing required fields"):
            loader._create_account(data)
