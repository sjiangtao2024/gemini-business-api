import httpx
from cookie_refresher.admin_client import AdminClient


def test_add_account_delete_then_add_on_400():
    calls = []
    post_count = {"count": 0}

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            post_count["count"] += 1
            if post_count["count"] == 1:
                return httpx.Response(400, json={"detail": "exists"})
            return httpx.Response(200, json={"message": "added"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"message": "deleted"})
        return httpx.Response(200, json={"message": "added"})

    transport = httpx.MockTransport(handler)
    client = AdminClient("http://localhost:8000", transport=transport)
    client.upsert_account({"email": "a@b.com"})
    assert calls[0] == ("POST", "/admin/accounts")
    assert calls[1] == ("DELETE", "/admin/accounts/a@b.com")
