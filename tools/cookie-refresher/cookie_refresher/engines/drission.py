from typing import Any, Callable, Dict, Optional

from cookie_refresher.engines.base import build_account_payload


class DrissionEngine:
    def __init__(
        self,
        code_provider: Callable[[], str],
        page_factory: Optional[Callable[[], Any]] = None,
        login_url: str = "https://auth.business.gemini.google/login",
    ):
        self.code_provider = code_provider
        self.page_factory = page_factory or self._default_page_factory
        self.login_url = login_url

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
            cookies = page.get_cookies()
            user_agent = page.run_js("return navigator.userAgent")
            return build_account_payload(page.url, cookies, user_agent)
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _login(self, page, email: str) -> None:
        page.get(self.login_url)
        try:
            email_input = page.ele('input[type="email"]')
            email_input.input(email)
            code = self.code_provider()
            code_input = page.ele('input[name="code"]')
            code_input.input(code)
        except Exception as exc:
            raise RuntimeError("login timeout") from exc
