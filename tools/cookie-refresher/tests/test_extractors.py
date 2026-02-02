from cookie_refresher.engines.base import extract_session_info


def test_extract_session_info_from_url_and_cookies():
    url = "https://business.gemini.google/cid/abc123?csesidx=999"
    cookies = {
        "__Secure-C_SES": {"value": "ses"},
        "__Host-C_OSES": {"value": "oses"},
    }
    info = extract_session_info(url, cookies)
    assert info["team_id"] == "abc123"
    assert info["csesidx"] == "999"
