"""The sales agent: an LLM with tools for searching the catalogue, editing the cart,
offering a capped discount and opening PayPal checkout.

Guardrails live here in code, not in the prompt:
- the model only ever sees prices that come from the database
- discounts are clamped to the seller's max_discount_pct
- stock is checked on every cart change
- the model can open checkout, but only the buyer can approve the payment in PayPal
"""
import json
import re

from sqlmodel import Session, select

from .cart import CartError, get_cart, product_dict, set_qty
from .llm import LLMError, LLMProvider
from .models import Conversation, Product, Store

MAX_STEPS = 6
MAX_HISTORY = 40

TOOLS = [
    {
        "name": "search_products",
        "description": "Search the store catalogue. Use an empty query to list popular items. "
        "Always call this before recommending or quoting a price.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the buyer is looking for"},
                "max_price_cents": {"type": "integer", "description": "Optional budget in cents"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product",
        "description": "Get full details for one product by id.",
        "parameters": {
            "type": "object",
            "properties": {"product_id": {"type": "integer"}},
            "required": ["product_id"],
        },
    },
    {
        "name": "update_cart",
        "description": "Set how many of a product are in the buyer's cart. qty=0 removes it. "
        "Only do this when the buyer has said they want the item.",
        "parameters": {
            "type": "object",
            "properties": {"product_id": {"type": "integer"}, "qty": {"type": "integer", "minimum": 0}},
            "required": ["product_id", "qty"],
        },
    },
    {
        "name": "view_cart",
        "description": "See what is in the cart and the totals.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "offer_discount",
        "description": "Apply a percentage discount to the whole cart. Use only when the buyer asks for a "
        "better price or is hesitating on price. The store enforces a maximum; the result tells you "
        "what was actually applied.",
        "parameters": {
            "type": "object",
            "properties": {
                "percent": {"type": "integer", "minimum": 1, "maximum": 100},
                "reason": {"type": "string", "description": "Short reason, shown to the seller"},
            },
            "required": ["percent", "reason"],
        },
    },
    {
        "name": "start_checkout",
        "description": "Show the PayPal payment button to the buyer for the current cart. "
        "Call this when the buyer is ready to pay.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def system_prompt(store: Store) -> str:
    return f"""You are the sales assistant for "{store.name}"{f" — {store.tagline}" if store.tagline else ""}.
You chat with shoppers, help them find the right product, build their cart and get them to checkout.

How you work:
- Use your tools. Never invent products, prices, stock or discounts; only state what a tool returned.
- Prices from tools are in cents of {store.currency}. Show them to the buyer as normal money, e.g. $24.00.
- Ask at most one short question at a time when you need to know more (size, budget, who it's for).
- Recommend at most 3 products at once and say why each fits.
- Only add things to the cart when the buyer clearly wants them. Confirm what you added.
- If the buyer pushes on price, you may use offer_discount. Start small. Never promise a discount
  before the tool confirms it.
- When the buyer is ready, call start_checkout. Payment happens in the PayPal button that appears;
  never ask for card numbers, passwords or bank details.
- Keep replies short and friendly, like a good shop assistant on WhatsApp. No markdown tables.

Store policies from the seller (follow them, they override your defaults on tone and shipping info):
{store.policies or "None given."}"""


def search(session: Session, store_id: int, query: str, max_price_cents: int | None = None, limit: int = 6) -> list[Product]:
    products = session.exec(
        select(Product).where(Product.store_id == store_id, Product.active == True)  # noqa: E712
    ).all()
    if max_price_cents:
        products = [p for p in products if p.price_cents <= max_price_cents]
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    if not words:
        return sorted(products, key=lambda p: -p.stock)[:limit]

    def score(p: Product) -> float:
        name, tags, desc = p.name.lower(), p.tags.lower(), p.description.lower()
        s = 0.0
        for w in words:
            stem = w.rstrip("s") or w
            if stem in name:
                s += 3
            if stem in tags:
                s += 2
            if stem in desc:
                s += 1
        return s

    ranked = [(score(p), p) for p in products]
    ranked = [x for x in ranked if x[0] > 0]
    ranked.sort(key=lambda x: (-x[0], x[1].price_cents))
    return [p for _, p in ranked[:limit]]


class Turn:
    """What happened during one buyer message, for the UI."""

    def __init__(self):
        self.products: dict[int, dict] = {}
        self.cart_changed = False
        self.checkout = False
        self.tool_calls: list[dict] = []


def run_tool(session: Session, convo: Conversation, store: Store, name: str, args: dict, turn: Turn) -> dict:
    try:
        if name == "search_products":
            found = search(session, store.id, str(args.get("query", "")), _int(args.get("max_price_cents")))
            for p in found:
                turn.products[p.id] = product_dict(p)
            return {"results": [_brief(p) for p in found], "count": len(found)}

        if name == "get_product":
            p = session.get(Product, _int(args.get("product_id")))
            if not p or p.store_id != store.id or not p.active:
                return {"error": "No such product"}
            turn.products[p.id] = product_dict(p)
            return {"product": product_dict(p)}

        if name == "update_cart":
            cart = set_qty(session, convo, _int(args.get("product_id")), _int(args.get("qty")) or 0)
            turn.cart_changed = True
            return {"cart": cart}

        if name == "view_cart":
            return {"cart": get_cart(session, convo)}

        if name == "offer_discount":
            requested = max(0, _int(args.get("percent")) or 0)
            applied = min(requested, store.max_discount_pct)
            if applied <= convo.discount_pct:
                return {
                    "applied_percent": convo.discount_pct,
                    "note": "That is already the best discount available."
                    if convo.discount_pct >= store.max_discount_pct
                    else "Existing discount is already equal or higher.",
                    "cart": get_cart(session, convo),
                }
            convo.discount_pct = applied
            convo.discount_reason = str(args.get("reason", ""))[:200]
            session.add(convo)
            session.commit()
            turn.cart_changed = True
            result = {"applied_percent": applied, "cart": get_cart(session, convo)}
            if applied < requested:
                result["note"] = f"Capped at the store maximum of {store.max_discount_pct}%."
            return result

        if name == "start_checkout":
            cart = get_cart(session, convo)
            if not cart["items"]:
                return {"error": "Cart is empty. Add something first."}
            turn.checkout = True
            turn.cart_changed = True
            return {"status": "PayPal button shown to buyer", "cart": cart}

        return {"error": f"Unknown tool {name}"}
    except CartError as e:
        return {"error": str(e)}


def _brief(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "price_cents": p.price_cents,
        "stock": p.stock,
        "summary": p.description[:160],
    }


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def trim_history(contents: list[dict]) -> list[dict]:
    """Keep recent history, cutting only at a plain user text turn so tool call/response pairs stay intact."""
    if len(contents) <= MAX_HISTORY:
        return contents
    for i in range(len(contents) - MAX_HISTORY, len(contents)):
        c = contents[i]
        if c["role"] == "user" and all("text" in p for p in c.get("parts", [])):
            return contents[i:]
    return contents[-1:]


async def respond(session: Session, convo: Conversation, text: str, llm: LLMProvider) -> dict:
    store = session.get(Store, convo.store_id)
    history = json.loads(convo.history_json)
    history.append({"role": "user", "parts": [{"text": text}]})
    transcript = json.loads(convo.transcript_json)
    transcript.append({"role": "buyer", "text": text})

    turn = Turn()
    reply = ""
    for _ in range(MAX_STEPS):
        try:
            content = await llm.generate(system_prompt(store), trim_history(history), TOOLS)
        except LLMError as e:
            reply = "Sorry, I'm having trouble thinking right now. Please try again in a moment."
            transcript.append({"role": "system", "text": f"LLM error: {e}"[:300]})
            break
        history.append(content)
        calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
        texts = [p["text"] for p in content.get("parts", []) if p.get("text") and not p.get("thought")]
        if not calls:
            reply = "\n".join(texts).strip()
            break
        responses = []
        for call in calls:
            name, args = call.get("name", ""), call.get("args") or {}
            result = run_tool(session, convo, store, name, args, turn)
            turn.tool_calls.append({"name": name, "args": args, "ok": "error" not in result})
            responses.append({"functionResponse": {"name": name, "response": result}})
        history.append({"role": "user", "parts": responses})
    else:
        reply = "Let me know how you'd like to continue."

    if not reply:
        reply = "Done! Anything else I can help with?"
    transcript.append({"role": "agent", "text": reply, "tools": [c["name"] for c in turn.tool_calls]})
    if not history or history[-1]["role"] != "model":
        history.append({"role": "model", "parts": [{"text": reply}]})

    convo.history_json = json.dumps(trim_history(history))
    convo.transcript_json = json.dumps(transcript)
    session.add(convo)
    session.commit()

    return {
        "reply": reply,
        "products": list(turn.products.values())[:3] if not turn.checkout else [],
        "cart": get_cart(session, convo),
        "checkout": turn.checkout,
        "tools": turn.tool_calls,
    }


async def draft_listing(notes: str, llm: LLMProvider) -> dict:
    """Seller helper: turn rough notes into a product name, description and tags."""
    prompt = (
        "Turn these rough seller notes into a product listing. Reply with JSON only, keys: "
        'name (short), description (2-3 friendly sentences, no made-up specs), tags (list of 3-6 lowercase words).\n\n'
        f"Notes: {notes}"
    )
    content = await llm.generate("You write honest, clear product listings.", [{"role": "user", "parts": [{"text": prompt}]}], [])
    text = "".join(p.get("text", "") for p in content.get("parts", []) if not p.get("thought"))
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise LLMError("Could not read listing from model")
    data = json.loads(match.group(0))
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    return {
        "name": str(data.get("name", ""))[:120],
        "description": str(data.get("description", ""))[:1000],
        "tags": [str(t).lower()[:30] for t in tags][:6],
    }
