import argparse
import time

from cookie_refresher.admin_client import AdminClient
from cookie_refresher.config import Settings
from cookie_refresher.engines.drission import DrissionEngine
from cookie_refresher.engines.selenium_uc import SeleniumUCEngine
from cookie_refresher.mail_2925 import Mail2925Handler
from cookie_refresher.orchestrator import run_with_fallback
from cookie_refresher.service import refresh_due_accounts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemini Business cookie refresher")
    parser.add_argument("--once", action="store_true", help="Run one refresh cycle and exit")
    parser.add_argument("--schedule", action="store_true", help="Run in scheduled loop")
    parser.add_argument("--interval-seconds", type=int, default=3600, help="Schedule interval")
    return parser


def _build_engine(settings: Settings):
    mail_handler = Mail2925Handler(
        settings.imap_host,
        settings.imap_port,
        settings.imap_user,
        settings.imap_pass,
    )

    def code_provider():
        return mail_handler.get_verification_code()

    primary = SeleniumUCEngine(code_provider)
    fallback = DrissionEngine(code_provider)

    class OrchestratedEngine:
        def login_and_extract(self, email: str):
            return run_with_fallback(primary, fallback, email)

    return OrchestratedEngine()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings()
    admin_client = AdminClient(settings.admin_base_url, settings.admin_api_key)
    engine = _build_engine(settings)

    if args.once:
        refresh_due_accounts(admin_client, engine)
        return 0

    if args.schedule:
        while True:
            refresh_due_accounts(admin_client, engine)
            time.sleep(args.interval_seconds)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
