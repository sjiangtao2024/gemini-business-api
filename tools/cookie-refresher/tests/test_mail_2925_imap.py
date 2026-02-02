from cookie_refresher.mail_2925 import Mail2925Handler


def test_imap_fetches_latest_code(monkeypatch):
    calls = []

    class FakeIMAP:
        def __init__(self, host, port):
            calls.append(("init", host, port))

        def login(self, user, password):
            calls.append(("login", user, password))
            return "OK", []

        def select(self, mailbox):
            calls.append(("select", mailbox))
            return "OK", []

        def search(self, charset, criteria):
            calls.append(("search", criteria))
            return "OK", [b"1 2"]

        def fetch(self, msg_id, _):
            calls.append(("fetch", msg_id))
            body = b"Subject: Code\n\nYour verification code is 123456."
            return "OK", [(None, body)]

        def close(self):
            calls.append(("close",))

        def logout(self):
            calls.append(("logout",))

    monkeypatch.setattr("imaplib.IMAP4_SSL", FakeIMAP)

    handler = Mail2925Handler("imap.2925.com", 993, "user", "pass")
    code = handler.get_verification_code()

    assert code == "123456"
    assert ("init", "imap.2925.com", 993) in calls
    assert ("login", "user", "pass") in calls
