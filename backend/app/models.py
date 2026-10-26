"""Database models. All money is stored as integer cents to avoid float errors."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Store(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    tagline: str = ""
    currency: str = "USD"
    # The agent may offer a discount, but the server never lets it exceed this.
    max_discount_pct: int = 10
    # Extra instructions from the seller ("we ship in 2 days", "be playful").
    policies: str = ""


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    store_id: int = Field(foreign_key="store.id", index=True)
    name: str
    description: str = ""
    tags: str = ""  # comma separated, used for search
    price_cents: int
    stock: int = 0
    image_url: str = ""
    active: bool = True


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    store_id: int = Field(foreign_key="store.id", index=True)
    created_at: datetime = Field(default_factory=now)
    discount_pct: int = 0
    discount_reason: str = ""
    # Full model history (Gemini "contents" format) as JSON text.
    history_json: str = "[]"
    # Human-readable transcript for the seller dashboard, JSON list of {role, text}.
    transcript_json: str = "[]"


class CartItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    product_id: int = Field(foreign_key="product.id")
    qty: int


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    store_id: int = Field(foreign_key="store.id", index=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    paypal_order_id: str = Field(index=True, unique=True)
    status: str = "CREATED"  # CREATED -> COMPLETED
    subtotal_cents: int
    discount_cents: int = 0
    total_cents: int
    currency: str = "USD"
    items_json: str = "[]"
    payer_name: str = ""
    payer_email: str = ""
    capture_id: str = ""
    created_at: datetime = Field(default_factory=now)
    captured_at: Optional[datetime] = None
