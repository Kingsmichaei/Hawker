# Hawker

**An AI sales assistant for small online sellers that chats with buyers, builds their cart, and closes the sale with PayPal — inside the conversation.**

Built for the [PayPal AI Hackathon 2026](https://paypalaihackathon.devpost.com/).

## The problem

Millions of small sellers — artisans, home brands, Instagram and WhatsApp shops — sell through chat. A buyer asks "do you have this in blue?", waits hours for a reply, then gets a bank account number to pay into. Sales die in that gap, and buyers abroad often can't pay at all.

## What Hawker does

- **Buyers** chat with the shop like they would with a person: "a gift for my mum under $30". The agent searches the real catalogue, recommends up to three items with reasons, adds what the buyer wants to the cart, and opens a **PayPal checkout right in the chat**.
- **The agent can negotiate**, but only inside a limit the seller sets (e.g. max 10% off). The server enforces the limit; the model can't talk its way past it.
- **Sellers** get a dashboard: paid orders from PayPal, revenue, how many chats turned into sales, and the full chat behind each order so they can see *why* someone bought (or got a discount).
- **Sellers add products in their own words** ("small indigo pouch with zip") and the AI writes the listing.

The demo shop is *Adire Lane*, a hand-dyed textile and natural-beauty shop selling to buyers anywhere.

## How PayPal and AI are used

| Part | What it does |
|---|---|
| **Gemini function calling** | The agent has six tools: `search_products`, `get_product`, `update_cart`, `view_cart`, `offer_discount`, `start_checkout`. It decides when to call them across a multi-step loop. |
| **PayPal Orders v2 API** | `start_checkout` makes the PayPal button appear; the server builds the order from the database cart (itemised, with discount breakdown) and creates it with an idempotency key. |
| **PayPal JS SDK** (`@paypal/react-paypal-js`) | Renders the PayPal button inline in the chat; the buyer approves in PayPal. |
| **Capture + verification** | The server captures the order and checks the captured amount matches what it expected before marking it paid, cutting stock and clearing the cart. |
| **PayPal webhooks** | Optional `PAYMENT.CAPTURE.COMPLETED` handler with signature verification, as a backup if the buyer closes the tab mid-payment. |

### Guardrails (in code, not just the prompt)

- The model never supplies prices. Every price in a PayPal order comes from the database.
- Discounts are clamped to the seller's `max_discount_pct`.
- Stock is checked when items are added and again when the PayPal order is created.
- The agent can show the PayPal button, but **only the buyer can approve a payment**. The agent never asks for card or bank details.
- Capturing twice is harmless, and double clicks on "Pay" reuse the same PayPal request id.

## Architecture

```
Buyer chat (React) ──► FastAPI ──► Gemini (tool calls)
       │                  │  └──► SQLite: products, carts, conversations, orders
       │                  └──► PayPal Orders v2 (create / capture), webhooks
       └── PayPal button (JS SDK) ── buyer approves in PayPal
Seller dashboard (React) ──► FastAPI /api/seller/*
```

- `backend/app/agent.py` — the agent loop, tools and guardrails
- `backend/app/paypal.py` — PayPal REST client (OAuth, orders, capture, webhook verification)
- `backend/app/main.py` — API routes and order completion
- `frontend/src/Shop.jsx` — buyer chat with inline PayPal checkout
- `frontend/src/Seller.jsx` — seller dashboard

## Run it locally

You need Python 3.11+, Node 20+, a free [PayPal Developer](https://developer.paypal.com) sandbox app, and a free Gemini key from [Google AI Studio](https://aistudio.google.com/).

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env        # then fill in PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 for the shop and http://localhost:5173/seller for the dashboard (token = `SELLER_TOKEN` in `.env`).

To pay, log in to the PayPal popup with a **sandbox personal account** from developer.paypal.com > Testing Tools > Sandbox Accounts.

The demo catalogue is created automatically on first start. Delete `backend/hawker.db` to reset.

### Try this conversation

1. "I want a gift for my mum, under $30"
2. "The scarf looks nice. Add two."
3. "Can you do a better price?"
4. "OK I'm ready to pay" → PayPal button appears → approve with a sandbox buyer
5. Open `/seller` and click **Read chat** on the new order.

## Tests

```bash
cd backend && pytest
```

The suite runs the full sale (chat → cart → PayPal order → capture → seller dashboard) with a scripted model and mocked PayPal, plus tests for the discount cap, stock limits, wrong capture amounts, LLM failures and the Gemini request format.

## Deploy

`render.yaml` deploys backend and built frontend as one web service on Render. Set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` and `GEMINI_API_KEY` in the Render dashboard, and set `CORS_ORIGINS` to your site URL.

## Limits and next steps

- One store per deployment today; the data model already keys everything by `store_id` for multi-seller.
- Simple keyword search; swapping in vector search (e.g. Elastic) would help large catalogues.
- Next: a WhatsApp channel using the same agent, and PayPal shipping callbacks for real delivery quotes.

## License

MIT
