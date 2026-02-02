def run_with_fallback(primary, fallback, email: str):
    try:
        return primary.login_and_extract(email)
    except Exception:
        return fallback.login_and_extract(email)
