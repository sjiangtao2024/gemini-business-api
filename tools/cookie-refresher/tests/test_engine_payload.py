from datetime import datetime, timezone, timedelta
from cookie_refresher.engines.base import build_account_payload


def test_build_account_payload_sets_expires_at():
    url = "https://business.gemini.google/cid/team123?csesidx=777"
    cookies = [
        {"name": "__Secure-C_SES", "value": "ses", "expiry": 1738492800},  # 2025-02-02 00:00 UTC
        {"name": "__Host-C_OSES", "value": "oses"},
    ]
    payload = build_account_payload(url, cookies, "UA")
    assert payload["team_id"] == "team123"
    assert payload["csesidx"] == "777"
    assert payload["secure_c_ses"] == "ses"
    assert payload["host_c_oses"] == "oses"
    expected = datetime.fromtimestamp(1738492800, tz=timezone.utc) - timedelta(hours=12)
    assert payload["expires_at"] == expected.isoformat()
