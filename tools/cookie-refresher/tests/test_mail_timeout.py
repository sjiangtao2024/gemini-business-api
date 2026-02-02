import pytest
from cookie_refresher.mail_2925 import Mail2925Handler


def test_mail_timeout_raises():
    class FakeIMAP:
        def __init__(self, host, port):
            pass

        def login(self, *_):
            return "OK", []

        def select(self, *_):
            return "OK", []

        def search(self, *_):
            return "OK", [b""]

        def close(self):
            pass

        def logout(self):
            pass

    import imaplib
    original = imaplib.IMAP4_SSL
    imaplib.IMAP4_SSL = FakeIMAP
    try:
        handler = Mail2925Handler("imap.2925.com", 993, "user", "pass")
        with pytest.raises(ValueError, match="verification code not found"):
            handler.get_verification_code()
    finally:
        imaplib.IMAP4_SSL = original
