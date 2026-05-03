"""
Kalshi authenticated REST client.

Replaces the kalshi_py SDK dependency. Uses RSA-PSS signing as required by
Kalshi's API (PKCS1v15 padding will be rejected with 401).

Auth header format (per Kalshi docs):
  KALSHI-ACCESS-KEY        : API key UUID
  KALSHI-ACCESS-TIMESTAMP  : ms since epoch (string)
  KALSHI-ACCESS-SIGNATURE  : base64(RSA-PSS-SHA256(ts + METHOD + url_path))
"""

import base64
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.padding import PSS, MGF1


class KalshiAuthenticatedClient:
    def __init__(self, access_key_id: str, private_key_pem: str, base_url: str):
        self.access_key_id = access_key_id
        self.base_url = base_url.rstrip('/')
        self._base_path = urlparse(self.base_url).path  # e.g. "/trade-api/v2"
        pem_bytes = private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem
        self._private_key = serialization.load_pem_private_key(pem_bytes, password=None)

    def _auth_headers(self, method: str, endpoint: str) -> dict:
        ts = str(int(datetime.now().timestamp() * 1000))
        full_path = self._base_path + endpoint  # "/trade-api/v2/portfolio/balance"
        msg = (ts + method.upper() + full_path).encode('utf-8')
        sig = self._private_key.sign(
            msg,
            PSS(mgf=MGF1(hashes.SHA256()), salt_length=PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            'KALSHI-ACCESS-KEY': self.access_key_id,
            'KALSHI-ACCESS-TIMESTAMP': ts,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'Content-Type': 'application/json',
        }

    def _get(self, endpoint: str, params: dict = None) -> dict:
        r = requests.get(
            self.base_url + endpoint,
            headers=self._auth_headers('GET', endpoint),
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint: str, body: dict) -> dict:
        r = requests.post(
            self.base_url + endpoint,
            headers=self._auth_headers('POST', endpoint),
            json=body,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def get_balance(self) -> dict:
        return self._get('/portfolio/balance')

    def get_positions(self, limit: int = 100) -> dict:
        return self._get('/portfolio/positions', params={'limit': limit})

    def create_order(self, ticker: str, side: str, count: int, yes_price: int,
                     action: str = 'buy',
                     type: str = 'limit',
                     time_in_force: str = 'ioc') -> dict:
        return self._post('/portfolio/orders', {
            'ticker': ticker,
            'action': action,
            'side': side,
            'count': count,
            'yes_price': yes_price,
            'type': type,
            'time_in_force': time_in_force,
        })
