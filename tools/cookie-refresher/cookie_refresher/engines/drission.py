from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

from cookie_refresher.engines.base import build_account_payload


class DrissionEngine:
    def __init__(
        self,
        code_provider: Callable[[], str],
        page_factory: Optional[Callable[[], Any]] = None,
        login_url: str = "https://auth.business.gemini.google/login",
        xsrf_token: str = "",
        grecaptcha_token: str = "",
    ):
        self.code_provider = code_provider
        self.page_factory = page_factory or self._default_page_factory
        self.login_url = login_url
        self.xsrf_token = xsrf_token
        self.grecaptcha_token = grecaptcha_token

    def _default_page_factory(self):
        from DrissionPage import ChromiumPage, ChromiumOptions

        options = ChromiumOptions()
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-gpu")
        return ChromiumPage(options)

    def login_and_extract(self, email: str) -> Dict[str, str]:
        page = self.page_factory()
        try:
            self._login(page, email)
            if self._is_signin_error(page.url):
                raise RuntimeError("signin error")
            if self._is_challenge(page.url):
                raise RuntimeError("challenge detected")
            if self._is_verification_failed(page.url):
                raise RuntimeError("verification failed")
            cookies = page.get_cookies()
            user_agent = page.run_js("return navigator.userAgent")
            return build_account_payload(page.url, cookies, user_agent)
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _login(self, page, email: str) -> None:
        if self.xsrf_token:
            page.get("https://auth.business.gemini.google/")
            self.prepare_auth_cookies(page, self.xsrf_token, self.grecaptcha_token)
            page.get(self.build_login_url(email, self.xsrf_token))
        else:
            page.get(self.login_url)
        try:
            email_input = page.ele('input[type="email"]')
            email_input.input(email)
            code = self.code_provider()
            code_input = page.ele('input[name="code"]')
            code_input.input(code)
        except Exception as exc:
            raise RuntimeError("login timeout") from exc

    @staticmethod
    def _is_challenge(url: str) -> bool:
        lowered = url.lower()
        return "challenge" in lowered or "denied" in lowered or "blocked" in lowered

    @staticmethod
    def _is_signin_error(url: str) -> bool:
        return "signin-error" in url.lower()

    @staticmethod
    def _is_verification_failed(url: str) -> bool:
        return "verify-oob-code" in url.lower()

    def build_login_url(self, email: str, xsrf_token: str) -> str:
        login_hint = quote(email, safe="")
        return (
            "https://auth.business.gemini.google/login/email"
            f"?continueUrl=https%3A%2F%2Fbusiness.gemini.google%2F&loginHint={login_hint}"
            f"&xsrfToken={xsrf_token}"
        )

    def prepare_auth_cookies(self, page, xsrf_token: str, grecaptcha_token: str) -> None:
        if xsrf_token:
            page.set.cookies({
                "name": "__Host-AP_SignInXsrf",
                "value": xsrf_token,
                "url": "https://auth.business.gemini.google/",
                "path": "/",
                "secure": True,
            })
        if grecaptcha_token:
            page.set.cookies({
                "name": "_GRECAPTCHA",
                "value": grecaptcha_token,
                "url": "https://google.com",
                "path": "/",
                "secure": True,
            })
