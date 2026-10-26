"""Cart and pricing. Prices always come from the database, never from the model."""
from sqlmodel import Session, select

from .models import CartItem, Conversation, Product, Store


class CartError(Exception):
    pass


def product_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "price_cents": p.price_cents,
        "stock": p.stock,
        "image_url": p.image_url,
        "tags": [t.strip() for t in p.tags.split(",") if t.strip()],
    }


def get_cart(session: Session, convo: Conversation) -> dict:
    rows = session.exec(select(CartItem).where(CartItem.conversation_id == convo.id)).all()
    items = []
    subtotal = 0
    for row in rows:
        p = session.get(Product, row.product_id)
        if not p:
            continue
        line = p.price_cents * row.qty
        subtotal += line
        items.append(
            {
                "product_id": p.id,
                "name": p.name,
                "qty": row.qty,
                "unit_cents": p.price_cents,
                "line_cents": line,
                "image_url": p.image_url,
            }
        )
    discount = subtotal * convo.discount_pct // 100
    store = session.get(Store, convo.store_id)
    return {
        "items": items,
        "subtotal_cents": subtotal,
        "discount_pct": convo.discount_pct,
        "discount_cents": discount,
        "total_cents": subtotal - discount,
        "currency": store.currency if store else "USD",
    }


def set_qty(session: Session, convo: Conversation, product_id: int, qty: int) -> dict:
    """Set the quantity of a product in the cart (0 removes it)."""
    p = session.get(Product, product_id)
    if not p or not p.active or p.store_id != convo.store_id:
        raise CartError(f"No product with id {product_id}")
    if qty < 0:
        raise CartError("Quantity can't be negative")
    if qty > p.stock:
        raise CartError(f"Only {p.stock} of {p.name} in stock")
    row = session.exec(
        select(CartItem).where(CartItem.conversation_id == convo.id, CartItem.product_id == product_id)
    ).first()
    if qty == 0:
        if row:
            session.delete(row)
    elif row:
        row.qty = qty
        session.add(row)
    else:
        session.add(CartItem(conversation_id=convo.id, product_id=product_id, qty=qty))
    session.commit()
    return get_cart(session, convo)


def clear_cart(session: Session, convo: Conversation) -> None:
    for row in session.exec(select(CartItem).where(CartItem.conversation_id == convo.id)).all():
        session.delete(row)
    session.commit()
