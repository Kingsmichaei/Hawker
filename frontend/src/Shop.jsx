import { useEffect, useRef, useState } from "react";
import { PayPalButtons, PayPalScriptProvider } from "@paypal/react-paypal-js";
import { api, fmt } from "./lib";
import Swatch from "./Swatch";

const STARTERS = ["A gift under $30", "Something for dry skin", "I need fabric to sew a top"];
const KEY = "hawker.conversation";

function load(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function save(key, value) {
  try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch { /* storage blocked */ }
}

export default function Shop() {
  const [config, setConfig] = useState(null);
  const [convo, setConvo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [cart, setCart] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [cartOpen, setCartOpen] = useState(false);
  const started = useRef(false);
  const endRef = useRef(null);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api("/config").then(setConfig).catch((e) => setError(e.message));
    newChat(load(KEY));
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  async function newChat(existing) {
    setError("");
    if (existing) {
      try {
        const c = await api(`/conversations/${existing}/cart`);
        setConvo(existing);
        setCart(c);
        setMessages([{ role: "agent", text: "Welcome back! Your cart is still here. What else can I find for you?" }]);
        return;
      } catch { save(KEY, null); }
    }
    try {
      const c = await api("/conversations", { method: "POST" });
      save(KEY, c.id);
      setConvo(c.id);
      setCart(c.cart);
      setMessages([{ role: "agent", text: c.greeting }]);
    } catch (e) {
      setError(`Couldn't reach the shop: ${e.message}`);
    }
  }

  async function send(text) {
    const t = text.trim();
    if (!t || busy || !convo) return;
    setInput("");
    setMessages((m) => [...m, { role: "buyer", text: t }]);
    setBusy(true);
    try {
      const r = await api(`/conversations/${convo}/messages`, { method: "POST", body: { text: t } });
      setCart(r.cart);
      setMessages((m) => [...m, { role: "agent", text: r.reply, products: r.products, checkout: r.checkout, tools: r.tools }]);
      if (r.checkout) setCartOpen(false);
    } catch (e) {
      setMessages((m) => [...m, { role: "system", text: `Message not sent: ${e.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  function onPaid(order) {
    setCart({ ...cart, items: [], subtotal_cents: 0, discount_cents: 0, discount_pct: 0, total_cents: 0 });
    setMessages((m) => [...m, { role: "receipt", order }]);
  }

  const lastCheckout = messages.map((m) => m.checkout).lastIndexOf(true);
  const itemCount = cart?.items.reduce((n, i) => n + i.qty, 0) || 0;

  const body = (
    <div className="flex h-full flex-col">
      <header className="adire text-resist">
        <div className="mx-auto flex max-w-6xl items-end justify-between gap-4 px-4 pb-5 pt-6 sm:px-6">
          <div>
            <h1 className="font-display text-4xl font-extrabold leading-none tracking-tight sm:text-5xl">
              {config?.store.name || "Hawker"}
            </h1>
            <p className="mt-2 max-w-md text-sm text-indigo-wash">{config?.store.tagline}</p>
          </div>
          <button
            onClick={() => { save(KEY, null); newChat(null); }}
            className="shrink-0 rounded-full border border-white/30 px-3 py-1.5 text-sm hover:bg-white/10"
          >
            New chat
          </button>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-1 gap-6 overflow-hidden px-0 sm:px-6">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="no-scrollbar flex-1 space-y-4 overflow-y-auto px-4 py-6 sm:px-0" aria-live="polite">
            {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
            {messages.map((m, i) => (
              <Message key={i} m={m} convo={convo} config={config} live={i === lastCheckout && cart?.items.length > 0} onPaid={onPaid} onAsk={send} />
            ))}
            {busy && (
              <div className="typing ml-1 py-2" aria-label="The shop is typing"><span /><span /><span /></div>
            )}
            {messages.length === 1 && !busy && (
              <div className="flex flex-wrap gap-2 pt-1">
                {STARTERS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-indigo-dye/30 bg-resist px-3.5 py-1.5 text-sm text-indigo-dye hover:border-indigo-dye">
                    {s}
                  </button>
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="sticky bottom-0 flex gap-2 border-t border-indigo-wash bg-cotton px-4 py-3 sm:px-0"
          >
            <label htmlFor="msg" className="sr-only">Message the shop</label>
            <input
              id="msg"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about sizes, gifts, prices…"
              autoComplete="off"
              className="min-w-0 flex-1 rounded-xl border border-indigo-wash bg-resist px-4 py-3 outline-none focus:border-indigo-dye"
            />
            <button disabled={busy || !input.trim()} className="rounded-xl bg-indigo-dye px-5 font-semibold text-resist disabled:opacity-40">
              Send
            </button>
          </form>
        </main>

        <aside className="hidden w-80 shrink-0 py-6 lg:block">
          <CartPanel cart={cart} />
        </aside>
      </div>

      {/* Mobile cart bar */}
      <div className="lg:hidden">
        {cartOpen && (
          <div className="border-t border-indigo-wash bg-resist p-4"><CartPanel cart={cart} /></div>
        )}
        <button
          onClick={() => setCartOpen((o) => !o)}
          className="flex w-full items-center justify-between bg-indigo-night px-4 py-3 text-resist"
          aria-expanded={cartOpen}
        >
          <span>{itemCount ? `${itemCount} item${itemCount > 1 ? "s" : ""} in your cart` : "Cart is empty"}</span>
          <span className="font-semibold">{fmt(cart?.total_cents, cart?.currency)}</span>
        </button>
      </div>
    </div>
  );

  if (!config?.paypal_client_id) return body;
  return (
    <PayPalScriptProvider options={{ clientId: config.paypal_client_id, currency: config.currency, intent: "capture" }}>
      {body}
    </PayPalScriptProvider>
  );
}

function Message({ m, convo, config, live, onPaid, onAsk }) {
  if (m.role === "buyer") {
    return (
      <div className="msg-in flex justify-end">
        <p className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-indigo-dye px-4 py-2.5 text-resist">{m.text}</p>
      </div>
    );
  }
  if (m.role === "system") {
    return <p className="msg-in text-center text-sm text-red-700">{m.text}</p>;
  }
  if (m.role === "receipt") {
    const o = m.order;
    return (
      <div className="msg-in rounded-2xl border-2 border-indigo-dye bg-resist p-5">
        <p className="font-display text-2xl font-bold text-indigo-night">Paid. Thank you{o.payer_name ? `, ${o.payer_name.split(" ")[0]}` : ""}!</p>
        <p className="mt-1 text-sm text-ink/70">
          {fmt(o.total_cents, o.currency)} via PayPal. Order {o.paypal_order_id}. The shop has been notified and will ship soon.
        </p>
        <ul className="mt-3 space-y-1 text-sm">
          {o.items.map((i) => <li key={i.product_id}>{i.qty} × {i.name}</li>)}
        </ul>
      </div>
    );
  }
  return (
    <div className="msg-in space-y-3">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-md bg-resist px-4 py-2.5 shadow-[0_1px_0_#c9d3ee]">{m.text}</p>
      {m.products?.length > 0 && (
        <div className="no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          {m.products.map((p) => (
            <article key={p.id} className="w-52 shrink-0 overflow-hidden rounded-xl bg-resist ring-1 ring-indigo-wash">
              <Swatch name={p.name} image={p.image_url} className="h-28 w-full" />
              <div className="p-3">
                <h3 className="font-display text-[15px] font-bold leading-tight">{p.name}</h3>
                <p className="mt-1 text-sm text-indigo-dye">{fmt(p.price_cents, config?.currency)}</p>
                <button
                  onClick={() => onAsk(`Add the ${p.name} to my cart`)}
                  disabled={p.stock < 1}
                  className="mt-2 w-full rounded-lg border border-indigo-dye py-1.5 text-sm font-medium text-indigo-dye hover:bg-indigo-dye hover:text-resist disabled:opacity-40"
                >
                  {p.stock < 1 ? "Sold out" : "Add to cart"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {m.checkout && live && <Checkout convo={convo} config={config} onPaid={onPaid} />}
    </div>
  );
}

function Checkout({ convo, config, onPaid }) {
  const [err, setErr] = useState("");
  if (!config?.paypal_client_id) {
    return <p className="rounded-xl bg-resist p-4 text-sm">PayPal isn't set up on this server yet. Add PAYPAL_CLIENT_ID to the backend .env.</p>;
  }
  return (
    <div className="max-w-sm rounded-2xl bg-resist p-4 ring-1 ring-indigo-wash">
      <p className="mb-3 text-sm text-ink/70">Pay securely with PayPal. You'll confirm the amount before anything is charged.</p>
      <PayPalButtons
        style={{ layout: "vertical", shape: "rect", label: "pay", height: 44 }}
        createOrder={async () => {
          setErr("");
          const o = await api(`/conversations/${convo}/paypal/order`, { method: "POST" });
          return o.id;
        }}
        onApprove={async (data) => {
          const r = await api(`/paypal/orders/${data.orderID}/capture`, { method: "POST" });
          onPaid(r.order);
        }}
        onError={(e) => setErr(e?.message || "Payment didn't go through. Try again or use another PayPal funding source.")}
        onCancel={() => setErr("Payment cancelled. Your cart is still saved.")}
      />
      {err && <p className="mt-2 text-sm text-red-700">{err}</p>}
    </div>
  );
}

function CartPanel({ cart }) {
  if (!cart) return null;
  return (
    <div className="rounded-2xl bg-resist p-5 ring-1 ring-indigo-wash">
      <h2 className="font-display text-xl font-bold">Your cart</h2>
      {cart.items.length === 0 ? (
        <p className="mt-2 text-sm text-ink/60">Nothing here yet. Tell the shop what you're after and it will add items for you.</p>
      ) : (
        <>
          <ul className="mt-3 space-y-3">
            {cart.items.map((i) => (
              <li key={i.product_id} className="flex items-center gap-3">
                <Swatch name={i.name} image={i.image_url} className="h-11 w-11 shrink-0 rounded-md" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{i.name}</p>
                  <p className="text-xs text-ink/60">{i.qty} × {fmt(i.unit_cents, cart.currency)}</p>
                </div>
                <span className="text-sm">{fmt(i.line_cents, cart.currency)}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-4 space-y-1 border-t border-indigo-wash pt-3 text-sm">
            <div className="flex justify-between"><dt>Subtotal</dt><dd>{fmt(cart.subtotal_cents, cart.currency)}</dd></div>
            {cart.discount_cents > 0 && (
              <div className="flex justify-between text-ochre"><dt>Discount ({cart.discount_pct}%)</dt><dd>−{fmt(cart.discount_cents, cart.currency)}</dd></div>
            )}
            <div className="flex justify-between pt-1 text-base font-semibold"><dt>Total</dt><dd>{fmt(cart.total_cents, cart.currency)}</dd></div>
          </dl>
          <p className="mt-3 text-xs text-ink/60">Say “I'm ready to pay” in the chat to check out.</p>
        </>
      )}
    </div>
  );
}
