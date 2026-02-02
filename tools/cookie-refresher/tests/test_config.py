from cookie_refresher.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.admin_base_url == "http://localhost:8000"
