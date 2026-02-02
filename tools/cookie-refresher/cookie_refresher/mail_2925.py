import re

CODE_PATTERNS = [
    r"verification code is[:\s]+([A-Z0-9]{6})",
    r"验证码[：:\s]+([A-Z0-9]{6})",
    r"([A-Z0-9]{6})\s+is your verification code",
]


def extract_verification_code(body: str) -> str:
    for pattern in CODE_PATTERNS:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(1)
    raise ValueError("verification code not found")
