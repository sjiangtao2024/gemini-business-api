from cookie_refresher.config import Settings


def test_settings_reads_imap_user(monkeypatch):
    monkeypatch.setenv("IMAP_USER", "user")
    monkeypatch.setenv("IMAP_PASS", "pass")
    monkeypatch.setenv("GEMINI_LOGIN_EMAIL", "login@example.com")
    settings = Settings()
    assert settings.imap_user == "user"
    assert settings.imap_pass == "pass"
    assert settings.login_email == "login@example.com"
