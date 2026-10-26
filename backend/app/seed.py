"""Demo store: a small artisan shop selling handmade goods to buyers anywhere."""
from sqlmodel import Session, select

from .models import Product, Store

DEMO_PRODUCTS = [
    ("Indigo Adire Scarf", "Hand-dyed cotton scarf in deep indigo, tie-and-dye pattern made by hand. About 180 x 70 cm, soft and light.", "scarf,adire,indigo,cotton,gift,accessory", 2800, 14),
    ("Adire Fabric — 2 yards", "Two yards of hand-dyed adire cotton fabric, ready for sewing a top, skirt or cushion covers.", "fabric,adire,cotton,sewing,material", 3500, 20),
    ("Ankara Tote Bag", "Roomy tote in bright ankara print with a lined inside pocket. Fits a laptop up to 14 inches.", "bag,tote,ankara,laptop,gift,accessory", 3200, 9),
    ("Beaded Bracelet Set (3)", "Three stackable glass-bead bracelets on stretch cord. One size fits most wrists.", "bracelet,beads,jewelry,jewellery,gift,accessory", 1800, 25),
    ("Raw Shea Butter — 250 g", "Unrefined shea butter from northern Nigeria. Good for dry skin and hair. Nut-based product.", "shea,butter,skincare,hair,natural,beauty", 1500, 30),
    ("Black Soap Bar — 3 pack", "Traditional plantain-ash black soap, three 100 g bars, unscented.", "soap,black soap,skincare,natural,beauty", 1600, 18),
    ("Woven Raffia Coasters (6)", "Six handwoven raffia coasters, 10 cm across, natural and dyed colours.", "coasters,raffia,home,kitchen,gift", 1400, 12),
    ("Aso-Oke Throw Pillow Cover", "Handwoven aso-oke cushion cover, 45 x 45 cm, zip closure. Insert not included.", "pillow,cushion,aso-oke,home,decor", 2600, 7),
    ("Kids' Ankara Bucket Hat", "Reversible bucket hat in ankara print for ages 3-8.", "hat,kids,children,ankara,accessory", 1200, 10),
]


def seed_if_empty(session: Session) -> Store:
    store = session.exec(select(Store)).first()
    if store:
        return store
    store = Store(
        name="Adire Lane",
        tagline="Handmade adire, ankara and natural beauty from Abeokuta",
        currency="USD",
        max_discount_pct=10,
        policies=(
            "We ship worldwide in 5-9 business days; shipping is included in the price. "
            "Returns within 14 days if unused. Be warm and a little playful. "
            "Mention that every item is handmade, so patterns vary slightly."
        ),
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    for name, desc, tags, price, stock in DEMO_PRODUCTS:
        session.add(Product(store_id=store.id, name=name, description=desc, tags=tags, price_cents=price, stock=stock))
    session.commit()
    return store
