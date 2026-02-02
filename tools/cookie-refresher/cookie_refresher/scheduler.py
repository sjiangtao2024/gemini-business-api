from datetime import datetime
from typing import List, Dict, Any


def select_due_accounts(accounts: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    due: List[Dict[str, Any]] = []
    for acc in accounts:
        expires_at = acc.get("expires_at")
        if not expires_at:
            continue
        if now >= datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
            due.append(acc)
    return due
