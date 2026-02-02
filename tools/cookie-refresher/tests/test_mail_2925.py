from cookie_refresher.mail_2925 import extract_verification_code


def test_extract_verification_code():
    body = "Your verification code is 123456."
    assert extract_verification_code(body) == "123456"
