import httpx
from cookie_refresher.admin_client import AdminClient


def test_list_accounts():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=[{"email": "a"}])
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = AdminClient("http://localhost:8000", transport=transport)
    accounts = client.list_accounts()
    assert accounts[0]["email"] == "a"
