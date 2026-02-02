from typing import Dict, Any
from urllib.parse import urlparse, parse_qs


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
