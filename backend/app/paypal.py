"""Thin async client for the PayPal REST APIs we use (sandbox by default).

- OAuth2 client-credentials token (cached until shortly before expiry)
- Orders v2: create + capture
- Webhook signature verification
"""
import time
from dataclasses import dataclass

import httpx

from .config import settings


class PayPalError(Exception):
    def __init__(self, message: str, status: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def money(cents: int) -> str:
    """Format integer cents as the decimal string PayPal expects ("12.50")."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


@dataclass
class LineItem:
    name: str
    unit_cents: int
    qty: int
    sku: str = ""


def build_order_body(
    items: list[LineItem], discount_cents: int, currency: str, reference_id: str, brand: str
) -> dict:
    item_total = sum(i.unit_cents * i.qty for i in items)
    total = item_total - discount_cents
    if total <= 0:
        raise PayPalError("Order total must be positive")
    breakdown = {"item_total": {"currency_code": currency, "value": money(item_total)}}
    if discount_cents:
        breakdown["discount"] = {"currency_code": currency, "value": money(discount_cents)}
    return {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference_id,
                "description": f"Order from {brand}"[:127],
                "amount": {
                    "currency_code": currency,
                    "value": money(total),
                    "breakdown": breakdown,
                },
                "items": [
                    {
                        "name": i.name[:127],
                        "sku": i.sku[:127],
                        "quantity": str(i.qty),
                        "unit_amount": {"currency_code": currency, "value": money(i.unit_cents)},
                        "category": "PHYSICAL_GOODS",
                    }
                    for i in items
                ],
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": brand[:127],
                    "shipping_preference": "GET_FROM_FILE",
                    "user_action": "PAY_NOW",
                }
            }
        },
    }


class PayPalClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        http: httpx.AsyncClient | None = None,
    ):
        self.client_id = client_id if client_id is not None else settings.paypal_client_id
        self.client_secret = client_secret if client_secret is not None else settings.paypal_client_secret
        self.base_url = (base_url or settings.paypal_base_url).rstrip("/")
        self._http = http
        self._token: str | None = None
        self._token_expiry = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30)
        return self._http

    async def access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        if not self.configured:
            raise PayPalError("PayPal credentials are not set (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET)")
        r = await self._client().post(
            f"{self.base_url}/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            raise PayPalError("Could not get PayPal access token", r.status_code, _json(r))
        data = r.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 3000))
        return self._token

    async def _request(self, method: str, path: str, json: dict | None = None, request_id: str | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {await self.access_token()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:  # PayPal idempotency key: safe to retry the same call
            headers["PayPal-Request-Id"] = request_id
        r = await self._client().request(method, f"{self.base_url}{path}", json=json, headers=headers)
        if r.status_code >= 400:
            body = _json(r)
            raise PayPalError(body.get("message") or f"PayPal error {r.status_code}", r.status_code, body)
        return _json(r)

    async def create_order(self, body: dict, request_id: str) -> dict:
        return await self._request("POST", "/v2/checkout/orders", json=body, request_id=request_id)

    async def get_order(self, order_id: str) -> dict:
        return await self._request("GET", f"/v2/checkout/orders/{order_id}")

    async def capture_order(self, order_id: str) -> dict:
        return await self._request(
            "POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=f"capture-{order_id}"
        )

    async def verify_webhook(self, headers: dict, event: dict, webhook_id: str) -> bool:
        h = {k.lower(): v for k, v in headers.items()}
        body = {
            "auth_algo": h.get("paypal-auth-algo"),
            "cert_url": h.get("paypal-cert-url"),
            "transmission_id": h.get("paypal-transmission-id"),
            "transmission_sig": h.get("paypal-transmission-sig"),
            "transmission_time": h.get("paypal-transmission-time"),
            "webhook_id": webhook_id,
            "webhook_event": event,
        }
        data = await self._request("POST", "/v1/notifications/verify-webhook-signature", json=body)
        return data.get("verification_status") == "SUCCESS"


def _json(r: httpx.Response) -> dict:
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}
