import httpx
from typing import Optional, Dict, Any


class AdminClient:
    def __init__(self, base_url: str, api_key: str = "", transport: Optional[httpx.BaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.Client(base_url=self.base_url, headers=headers, transport=transport)

    def upsert_account(self, payload: Dict[str, Any]) -> None:
        resp = self.client.post("/admin/accounts", json=payload)
        if resp.status_code == 400 and "exists" in resp.text:
            email = payload["email"]
            self.client.delete(f"/admin/accounts/{email}")
            resp = self.client.post("/admin/accounts", json=payload)
        resp.raise_for_status()

    def list_accounts(self) -> list[Dict[str, Any]]:
        resp = self.client.get("/admin/accounts")
        resp.raise_for_status()
        return resp.json()
