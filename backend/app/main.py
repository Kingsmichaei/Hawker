"""Hawker API — an AI sales agent that closes the sale with PayPal."""
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import agent
from .cart import clear_cart, get_cart, product_dict
from .config import settings
from .db import get_session, init_db
from .llm import LLMError, get_provider
from .models import Conversation, Order, Product, Store, now
from .paypal import LineItem, PayPalClient, PayPalError, build_order_body, money
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app):
    init_db()
    from .db import engine

    with Session(engine) as s:
        seed_if_empty(s)
    yield


app = FastAPI(title="Hawker", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

_paypal = PayPalClient()


def get_paypal() -> PayPalClient:
    return _paypal


def get_store(session: Session) -> Store:
    store = session.exec(select(Store)).first()
    if not store:
        raise HTTPException(500, "No store configured")
    return store


def require_seller(x_seller_token: str = Header(default="")) -> None:
    if x_seller_token != settings.seller_token:
        raise HTTPException(401, "Seller token required")


def get_convo(session: Session, convo_id: str) -> Conversation:
    convo = session.get(Conversation, convo_id)
    if not convo:
        raise HTTPException(404, "Conversation not found")
    return convo


# ---------- public ----------


@app.get("/api/health")
def health(paypal: PayPalClient = Depends(get_paypal)):
    return {"ok": True, "paypal_configured": paypal.configured, "llm_configured": bool(settings.gemini_api_key)}


@app.get("/api/config")
def public_config(session: Session = Depends(get_session)):
    store = get_store(session)
    return {
        "paypal_client_id": settings.paypal_client_id,
        "currency": store.currency,
        "store": {"name": store.name, "tagline": store.tagline},
    }


@app.get("/api/products")
def list_products(session: Session = Depends(get_session)):
    store = get_store(session)
    rows = session.exec(select(Product).where(Product.store_id == store.id, Product.active == True)).all()  # noqa: E712
    return [product_dict(p) for p in rows]


@app.post("/api/conversations")
def start_conversation(session: Session = Depends(get_session)):
    store = get_store(session)
    greeting = f"Hi! Welcome to {store.name}. What are you shopping for today?"
    convo = Conversation(
        store_id=store.id,
        history_json=json.dumps([{"role": "model", "parts": [{"text": greeting}]}]),
        transcript_json=json.dumps([{"role": "agent", "text": greeting}]),
    )
    session.add(convo)
    session.commit()
    return {"id": convo.id, "greeting": greeting, "cart": get_cart(session, convo)}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/api/conversations/{convo_id}/messages")
async def send_message(convo_id: str, body: MessageIn, session: Session = Depends(get_session)):
    convo = get_convo(session, convo_id)
    return await agent.respond(session, convo, body.text.strip(), get_provider())


@app.get("/api/conversations/{convo_id}/cart")
def view_cart(convo_id: str, session: Session = Depends(get_session)):
    return get_cart(session, get_convo(session, convo_id))


@app.post("/api/conversations/{convo_id}/paypal/order")
async def create_paypal_order(
    convo_id: str, session: Session = Depends(get_session), paypal: PayPalClient = Depends(get_paypal)
):
    """Create a PayPal order from the server-side cart. The browser never sends prices."""
    convo = get_convo(session, convo_id)
    store = get_store(session)
    cart = get_cart(session, convo)
    if not cart["items"]:
        raise HTTPException(400, "Cart is empty")
    for item in cart["items"]:
        p = session.get(Product, item["product_id"])
        if not p or p.stock < item["qty"]:
            raise HTTPException(409, f"Not enough stock for {item['name']}")

    line_items = [LineItem(i["name"], i["unit_cents"], i["qty"], sku=str(i["product_id"])) for i in cart["items"]]
    body = build_order_body(line_items, cart["discount_cents"], cart["currency"], convo.id[:32], store.name)
    # Same cart contents => same request id, so double clicks don't create duplicate orders.
    fingerprint = "-".join(f"{i['product_id']}x{i['qty']}" for i in cart["items"])
    digest = hashlib.sha256(f"{convo.id}|{fingerprint}|{cart['total_cents']}".encode()).hexdigest()[:24]
    request_id = f"hawker-{digest}"
    try:
        result = await paypal.create_order(body, request_id)
    except PayPalError as e:
        raise HTTPException(502, f"PayPal: {e}")

    order = session.exec(select(Order).where(Order.paypal_order_id == result["id"])).first()
    if not order:
        order = Order(
            store_id=store.id,
            conversation_id=convo.id,
            paypal_order_id=result["id"],
            subtotal_cents=cart["subtotal_cents"],
            discount_cents=cart["discount_cents"],
            total_cents=cart["total_cents"],
            currency=cart["currency"],
            items_json=json.dumps(cart["items"]),
        )
        session.add(order)
        session.commit()
    return {"id": result["id"], "status": result.get("status")}


def _complete_order(session: Session, order: Order, capture_data: dict) -> None:
    """Mark an order paid, decrement stock and clear the cart. Safe to call twice."""
    if order.status == "COMPLETED":
        return
    pu = (capture_data.get("purchase_units") or [{}])[0]
    captures = (pu.get("payments") or {}).get("captures") or []
    capture = captures[0] if captures else {}
    amount = (capture.get("amount") or {}).get("value")
    if capture.get("status") != "COMPLETED" or amount != money(order.total_cents):
        raise HTTPException(402, "Payment was not completed for the expected amount")

    payer = capture_data.get("payer") or {}
    name = payer.get("name") or {}
    order.status = "COMPLETED"
    order.capture_id = capture.get("id", "")
    order.payer_email = payer.get("email_address", "")
    order.payer_name = " ".join(x for x in [name.get("given_name"), name.get("surname")] if x)
    order.captured_at = now()
    session.add(order)
    for item in json.loads(order.items_json):
        p = session.get(Product, item["product_id"])
        if p:
            p.stock = max(0, p.stock - item["qty"])
            session.add(p)

    convo = session.get(Conversation, order.conversation_id)
    if convo:
        clear_cart(session, convo)
        convo.discount_pct = 0
        note = f"Payment of {order.currency} {money(order.total_cents)} received via PayPal (order {order.paypal_order_id})."
        history = json.loads(convo.history_json)
        history.append({"role": "user", "parts": [{"text": f"[Store notice] {note} The cart is now empty."}]})
        history.append({"role": "model", "parts": [{"text": "Thank you! Your payment went through."}]})
        transcript = json.loads(convo.transcript_json)
        transcript.append({"role": "system", "text": note})
        convo.history_json = json.dumps(history)
        convo.transcript_json = json.dumps(transcript)
        session.add(convo)
    session.commit()


@app.post("/api/paypal/orders/{paypal_order_id}/capture")
async def capture_paypal_order(
    paypal_order_id: str, session: Session = Depends(get_session), paypal: PayPalClient = Depends(get_paypal)
):
    order = session.exec(select(Order).where(Order.paypal_order_id == paypal_order_id)).first()
    if not order:
        raise HTTPException(404, "Unknown order")
    if order.status != "COMPLETED":
        try:
            data = await paypal.capture_order(paypal_order_id)
        except PayPalError as e:
            issue = ((e.details.get("details") or [{}])[0]).get("issue", "")
            if issue == "ORDER_ALREADY_CAPTURED":
                data = await paypal.get_order(paypal_order_id)
            else:
                raise HTTPException(502, f"PayPal: {e} {issue}".strip())
        _complete_order(session, order, data)
    return {"status": order.status, "order": order_dict(order)}


@app.post("/api/paypal/webhook")
async def paypal_webhook(
    request: Request, session: Session = Depends(get_session), paypal: PayPalClient = Depends(get_paypal)
):
    """Backup path: if the browser closes before capture finishes, the webhook still marks the order paid."""
    event = await request.json()
    if not settings.paypal_webhook_id:
        raise HTTPException(503, "Webhook not configured")
    if not await paypal.verify_webhook(dict(request.headers), event, settings.paypal_webhook_id):
        raise HTTPException(400, "Invalid signature")
    if event.get("event_type") == "PAYMENT.CAPTURE.COMPLETED":
        resource = event.get("resource") or {}
        order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
        order = session.exec(select(Order).where(Order.paypal_order_id == order_id)).first() if order_id else None
        if order and order.status != "COMPLETED":
            _complete_order(session, order, await paypal.get_order(order_id))
    return {"ok": True}


# ---------- seller ----------


def order_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "paypal_order_id": o.paypal_order_id,
        "status": o.status,
        "subtotal_cents": o.subtotal_cents,
        "discount_cents": o.discount_cents,
        "total_cents": o.total_cents,
        "currency": o.currency,
        "items": json.loads(o.items_json),
        "payer_name": o.payer_name,
        "payer_email": o.payer_email,
        "conversation_id": o.conversation_id,
        "created_at": o.created_at.isoformat(),
        "captured_at": o.captured_at.isoformat() if o.captured_at else None,
    }


@app.get("/api/seller/summary", dependencies=[Depends(require_seller)])
def seller_summary(session: Session = Depends(get_session)):
    store = get_store(session)
    orders = session.exec(select(Order).where(Order.store_id == store.id).order_by(Order.created_at.desc())).all()
    convos = session.exec(select(Conversation).where(Conversation.store_id == store.id)).all()
    paid = [o for o in orders if o.status == "COMPLETED"]
    return {
        "store": store.model_dump(),
        "stats": {
            "conversations": len(convos),
            "orders_paid": len(paid),
            "revenue_cents": sum(o.total_cents for o in paid),
            "discounts_cents": sum(o.discount_cents for o in paid),
            "conversion_pct": round(100 * len({o.conversation_id for o in paid}) / len(convos), 1) if convos else 0,
        },
        "orders": [order_dict(o) for o in orders[:50]],
    }


class StoreUpdate(BaseModel):
    name: str | None = None
    tagline: str | None = None
    max_discount_pct: int | None = Field(default=None, ge=0, le=50)
    policies: str | None = Field(default=None, max_length=2000)


@app.patch("/api/seller/store", dependencies=[Depends(require_seller)])
def update_store(body: StoreUpdate, session: Session = Depends(get_session)):
    store = get_store(session)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(store, k, v)
    session.add(store)
    session.commit()
    return store.model_dump()


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    tags: list[str] = []
    price_cents: int = Field(gt=0)
    stock: int = Field(ge=0)
    image_url: str = ""


@app.get("/api/seller/products", dependencies=[Depends(require_seller)])
def seller_products(session: Session = Depends(get_session)):
    store = get_store(session)
    return [product_dict(p) | {"active": p.active} for p in session.exec(select(Product).where(Product.store_id == store.id)).all()]


@app.post("/api/seller/products", dependencies=[Depends(require_seller)])
def create_product(body: ProductIn, session: Session = Depends(get_session)):
    store = get_store(session)
    p = Product(store_id=store.id, **body.model_dump(exclude={"tags"}), tags=",".join(body.tags))
    session.add(p)
    session.commit()
    return product_dict(p)


@app.put("/api/seller/products/{product_id}", dependencies=[Depends(require_seller)])
def update_product(product_id: int, body: ProductIn, session: Session = Depends(get_session)):
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude={"tags"}).items():
        setattr(p, k, v)
    p.tags = ",".join(body.tags)
    session.add(p)
    session.commit()
    return product_dict(p)


@app.delete("/api/seller/products/{product_id}", dependencies=[Depends(require_seller)])
def archive_product(product_id: int, session: Session = Depends(get_session)):
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Not found")
    p.active = False  # keep history for old orders
    session.add(p)
    session.commit()
    return {"ok": True}


class DraftIn(BaseModel):
    notes: str = Field(min_length=3, max_length=1000)


@app.post("/api/seller/products/draft", dependencies=[Depends(require_seller)])
async def draft_product(body: DraftIn):
    try:
        return await agent.draft_listing(body.notes, get_provider())
    except (LLMError, ValueError) as e:
        raise HTTPException(502, f"Could not draft listing: {e}")


@app.get("/api/seller/conversations/{convo_id}", dependencies=[Depends(require_seller)])
def conversation_transcript(convo_id: str, session: Session = Depends(get_session)):
    convo = get_convo(session, convo_id)
    return {
        "id": convo.id,
        "created_at": convo.created_at.isoformat(),
        "discount_reason": convo.discount_reason,
        "transcript": json.loads(convo.transcript_json),
    }


# ---------- serve the built frontend (single URL deploys, e.g. Render) ----------

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = DIST / path
        if path and file.is_file():
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
