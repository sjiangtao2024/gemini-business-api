from cookie_refresher.engines.selenium_uc import SeleniumUCEngine
from cookie_refresher.engines.drission import DrissionEngine


def test_selenium_sets_auth_cookies():
    cookies = []

    class FakeDriver:
        def get(self, _):
            pass

        def add_cookie(self, cookie):
            cookies.append(cookie)

        def find_element(self, *_):
            class Fake:
                def send_keys(self, _):
                    pass
            return Fake()

        def quit(self):
            pass

    engine = SeleniumUCEngine(lambda: "123456", driver_factory=lambda: FakeDriver())
    engine.prepare_auth_cookies(FakeDriver(), "token", "grecaptcha")

    names = {c["name"] for c in cookies}
    assert "__Host-AP_SignInXsrf" in names
    assert "_GRECAPTCHA" in names


def test_drission_sets_auth_cookies():
    cookies = []

    class FakeSetter:
        def cookies(self, cookie):
            cookies.append(cookie)

    class FakePage:
        set = FakeSetter()

        def get(self, _):
            pass

        def ele(self, *_):
            class Fake:
                def input(self, _):
                    pass
            return Fake()

        def close(self):
            pass

    engine = DrissionEngine(lambda: "123456", page_factory=lambda: FakePage())
    engine.prepare_auth_cookies(FakePage(), "token", "grecaptcha")

    names = {c["name"] for c in cookies}
    assert "__Host-AP_SignInXsrf" in names
    assert "_GRECAPTCHA" in names
