from datetime import datetime, timezone
from cookie_refresher.policy import compute_expires_at, should_refresh


def test_expires_at_is_cookie_expiry_minus_12h():
    expiry = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    expires_at = compute_expires_at(expiry)
    assert expires_at == datetime(2026, 2, 2, 0, 0, tzinfo=timezone.utc)


def test_should_refresh_when_expired():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    assert should_refresh(now, now) is True
