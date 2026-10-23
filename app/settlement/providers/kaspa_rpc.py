import os
import requests

class KaspaRPCClient:
    def __init__(self):
        host = os.getenv("KASPA_RPC_HOST")
        port = os.getenv("KASPA_RPC_PORT")

        if not host or not port:
            raise RuntimeError("KASPA_RPC_HOST or KASPA_RPC_PORT not set")

        self.url = f"http://{host}:{port}"

    def get_info(self):
        resp = requests.post(f"{self.url}/getInfo", json={})
        resp.raise_for_status()
        return resp.json()
