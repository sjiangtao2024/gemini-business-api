from cookie_refresher.config import Settings


def test_settings_reads_tokens(monkeypatch):
    monkeypatch.setenv("XSRF_TOKEN", "xsrf")
    monkeypatch.setenv("GRECAPTCHA_TOKEN", "gcap")
    settings = Settings()
    assert settings.xsrf_token == "xsrf"
    assert settings.grecaptcha_token == "gcap"
