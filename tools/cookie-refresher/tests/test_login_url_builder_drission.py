from cookie_refresher.engines.drission import DrissionEngine


def test_build_login_url_with_hint_and_xsrf():
    engine = DrissionEngine(lambda: "123456", page_factory=lambda: None)
    url = engine.build_login_url("user@example.com", "token")
    assert "login/email" in url
    assert "loginHint=user%40example.com" in url
    assert "xsrfToken=token" in url
