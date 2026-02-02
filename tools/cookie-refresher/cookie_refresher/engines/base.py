from typing import Dict, Any, List
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta


def extract_session_info(url: str, cookies: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    parsed = urlparse(url)
    parts = url.split("/cid/")
    team_id = parts[1].split("?")[0].split("/")[0] if len(parts) > 1 else ""
    csesidx = parse_qs(parsed.query).get("csesidx", [""])[0]
    return {
        "team_id": team_id,
        "csesidx": csesidx,
        "secure_c_ses": cookies.get("__Secure-C_SES", {}).get("value", ""),
        "host_c_oses": cookies.get("__Host-C_OSES", {}).get("value", ""),
    }


def build_account_payload(url: str, cookies: List[Dict[str, Any]], user_agent: str) -> Dict[str, str]:
    cookie_map = {c.get("name", ""): c for c in cookies}
    session_info = extract_session_info(url, cookie_map)
    ses_cookie = cookie_map.get("__Secure-C_SES", {})
    expiry = ses_cookie.get("expiry")
    if expiry:
        expires_at = datetime.fromtimestamp(expiry, tz=timezone.utc) - timedelta(hours=12)
        expires_at_iso = expires_at.isoformat()
    else:
        expires_at_iso = None
    return {
        **session_info,
        "user_agent": user_agent,
        "expires_at": expires_at_iso,
    }
