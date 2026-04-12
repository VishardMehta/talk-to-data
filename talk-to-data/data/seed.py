"""
Seed script — run once to initialize the database and documents.
Usage: python data/seed.py
"""

import json
import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "demo.db"
DOCS_DIR = BASE / "documents"
DOCS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

CITIES = [
    "Delhi", "Mumbai", "Bangalore", "Chennai", "Kolkata",
    "Hyderabad", "Pune", "Jaipur", "Lucknow", "Ahmedabad",
]

CITY_REGION = {
    "Delhi": "North", "Jaipur": "North", "Lucknow": "North",
    "Mumbai": "West", "Pune": "West", "Ahmedabad": "West",
    "Bangalore": "South", "Chennai": "South", "Hyderabad": "South",
    "Kolkata": "East",
}

STATES = {
    "Delhi": "Delhi", "Jaipur": "Rajasthan", "Lucknow": "Uttar Pradesh",
    "Mumbai": "Maharashtra", "Pune": "Maharashtra", "Ahmedabad": "Gujarat",
    "Bangalore": "Karnataka", "Chennai": "Tamil Nadu", "Hyderabad": "Telangana",
    "Kolkata": "West Bengal",
}

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Priya", "Ananya", "Diya", "Pooja", "Neha", "Sneha", "Riya", "Meera",
    "Rahul", "Rohit", "Amit", "Suresh", "Rajesh", "Vikram", "Deepak", "Nikhil",
    "Kavya", "Divya", "Shruti", "Pallavi", "Swati", "Rekha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Singh", "Kumar", "Joshi", "Patel", "Mehta",
    "Reddy", "Nair", "Pillai", "Iyer", "Bose", "Das", "Chatterjee", "Roy",
    "Malhotra", "Kapoor", "Khanna", "Bhatia",
]

CATEGORIES = {
    "Electronics": ["Smartphone", "Laptop", "Tablet", "Headphones", "Smartwatch",
                    "Camera", "Speaker", "TV", "Keyboard", "Mouse"],
    "Clothing":    ["T-Shirt", "Jeans", "Kurta", "Saree", "Jacket",
                    "Dress", "Shorts", "Hoodie", "Blazer", "Leggings"],
    "Home":        ["Bed Sheet", "Pillow Set", "Curtains", "Wall Clock", "Lamp",
                    "Kitchen Set", "Storage Box", "Towel Set", "Cookware", "Vase"],
    "Food":        ["Organic Tea", "Coffee Blend", "Protein Bar", "Snack Pack", "Honey",
                    "Dry Fruits", "Olive Oil", "Spice Kit", "Muesli", "Juice Pack"],
    "Beauty":      ["Face Wash", "Moisturizer", "Shampoo", "Conditioner", "Serum",
                    "Lip Balm", "Sunscreen", "Body Lotion", "Eye Cream", "Perfume"],
}

CATEGORY_PRICE = {
    "Electronics": (5000, 50000),
    "Clothing":    (500,  5000),
    "Home":        (800,  8000),
    "Food":        (300,  2000),
    "Beauty":      (400,  3000),
}

CATEGORY_COST_RATIO = {
    "Electronics": 0.65,
    "Clothing":    0.40,
    "Home":        0.50,
    "Food":        0.45,
    "Beauty":      0.35,
}

START_DATE = date(2024, 1, 1)
END_DATE   = date(2025, 3, 31)


def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def rand_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


# ---------------------------------------------------------------------------
# Generate customers (200)
# ---------------------------------------------------------------------------

def gen_customers(n: int = 200) -> list[tuple]:
    rows = []
    segments = (["regular"] * 60 + ["premium"] * 30 + ["enterprise"] * 10)
    for i in range(1, n + 1):
        city = random.choice(CITIES)
        name = rand_name()
        email = f"{name.lower().replace(' ', '.')}{i}@example.com"
        segment = random.choice(segments)
        join_dt = rand_date(date(2022, 1, 1), date(2024, 6, 30))
        rows.append((i, name, email, city, STATES[city], str(join_dt), segment))
    return rows


# ---------------------------------------------------------------------------
# Generate products (50)
# ---------------------------------------------------------------------------

def gen_products() -> list[tuple]:
    rows = []
    pid = 1
    for cat, names in CATEGORIES.items():
        lo, hi = CATEGORY_PRICE[cat]
        ratio = CATEGORY_COST_RATIO[cat]
        # 2 subcategories per category
        subcat_map = {"Electronics": ["Mobile", "Computing", "Audio", "Accessories"],
                      "Clothing": ["Men", "Women", "Kids", "Sports"],
                      "Home": ["Bedroom", "Kitchen", "Décor", "Bath"],
                      "Food": ["Organic", "Packaged", "Beverages", "Snacks"],
                      "Beauty": ["Skin", "Hair", "Fragrance", "Body"]}
        subcats = subcat_map.get(cat, ["General"])
        for name in names:
            price = round(random.uniform(lo, hi), 2)
            cost  = round(price * ratio * random.uniform(0.9, 1.1), 2)
            subcat = random.choice(subcats)
            rows.append((pid, name, cat, subcat, price, cost))
            pid += 1
    return rows


# ---------------------------------------------------------------------------
# Generate orders (2000+)
# ---------------------------------------------------------------------------

def gen_orders(customers: list, products: list) -> list[tuple]:
    rows = []
    oid = 1

    # Build product lookup by category
    electronics = [p for p in products if p[2] == "Electronics"]
    non_electronics = [p for p in products if p[2] != "Electronics"]

    # Build customer → city → region map
    cust_region = {}
    for c in customers:
        city = c[3]
        cust_region[c[0]] = CITY_REGION[city]

    statuses = (
        ["completed"] * 70 + ["pending"] * 15 +
        ["cancelled"] * 10 + ["returned"] * 5
    )
    channels = ["online"] * 60 + ["retail"] * 30 + ["wholesale"] * 10

    target_orders = 2200
    for _ in range(target_orders):
        cust = random.choice(customers)
        cust_id = cust[0]
        region = cust_region[cust_id]

        # Electronics = ~40% of orders
        if random.random() < 0.40:
            prod = random.choice(electronics)
        else:
            prod = random.choice(non_electronics)

        prod_id = prod[0]
        price   = prod[4]
        qty     = random.randint(1, 3)
        amount  = round(price * qty, 2)

        # Deliberate revenue drop in South region Feb–Mar 2025
        order_dt = rand_date(START_DATE, END_DATE)
        if (region == "South"
                and order_dt >= date(2025, 2, 1)
                and order_dt <= date(2025, 3, 31)):
            amount = round(amount * random.uniform(0.60, 0.75), 2)

        # North is the largest region — slightly more orders
        if region == "North":
            # Accept this order
            pass
        elif region in ("East",) and random.random() < 0.15:
            # Thin out East a bit
            continue

        status  = random.choice(statuses)
        channel = random.choice(channels)

        rows.append((oid, cust_id, prod_id, amount, qty, status, region, channel, str(order_dt)))
        oid += 1

    return rows


# ---------------------------------------------------------------------------
# Generate complaints (300)
# ---------------------------------------------------------------------------

COMPLAINT_TEXTS = {
    "delivery": [
        "My order arrived 2 weeks late despite the promised 3-day delivery window.",
        "The package was delivered to the wrong address and I had to chase it.",
        "Delivery was delayed by 10 days with no communication from the courier.",
        "Item marked as delivered but I never received it. Huge inconvenience.",
        "The South region warehouse seems to be having major logistics issues.",
        "My parcel arrived damaged — the outer box was completely crushed.",
        "Wrong item delivered. I ordered a smartphone and got a keyboard.",
        "The courier attempted delivery at wrong time and left no notice.",
        "Package was left outside in the rain and contents were water damaged.",
        "Expected delivery on Monday. Item still not received by Friday.",
    ],
    "quality": [
        "Product quality is very poor. It broke within a week of use.",
        "The colour of the product is completely different from the website photo.",
        "There was a manufacturing defect — the zipper broke on day one.",
        "Received a counterfeit product. This is not the brand I ordered.",
        "The material feels very cheap compared to the product description.",
    ],
    "pricing": [
        "I was charged a different price than what was shown at checkout.",
        "Hidden delivery charges added at payment — very misleading.",
        "The discount coupon did not apply even though it was valid.",
        "Price changed between adding to cart and checkout.",
    ],
    "service": [
        "Customer service was completely unhelpful and rude.",
        "I raised a complaint 2 weeks ago and still have no response.",
        "The chat support disconnected three times without resolving my issue.",
        "No way to contact support on weekends — extremely frustrating.",
    ],
    "refund": [
        "Refund has not been processed even after 3 weeks.",
        "Was promised a refund in 7 days but it has been 21 days.",
        "Refund was processed but the amount is incorrect.",
        "Return was picked up but refund status still shows pending.",
    ],
}

SOUTH_DELIVERY_TEXTS = [
    "South region delivery completely broken in Feb 2025. 3 of my orders delayed.",
    "Ordered on Feb 5 from Bangalore. Arrived March 2. Unacceptable.",
    "Bangalore warehouse clearly has a staffing crisis. 2-week delays are the norm now.",
    "Third delayed delivery from Chennai this month. Switching to a competitor.",
    "Hyderabad orders consistently late since February. What is going on?",
    "My electronics order from Feb took 18 days. The South warehouse is a mess.",
    "Damaged goods received from South hub — packaging clearly inadequate.",
    "Feb 2025: Ordered from Chennai, tracking showed 'out for delivery' for 5 days.",
    "South supply chain issues are affecting everyone I know. Needs urgent fix.",
    "March 2025 delivery from Hyderabad — worst experience in 3 years of ordering.",
]


def gen_complaints(customers: list, orders: list) -> list[tuple]:
    rows = []
    cid = 1

    cust_region = {}
    order_lookup = {}
    for o in orders:
        order_lookup[o[0]] = o
        cust_region[o[1]] = o[6]  # region

    # Cluster: South delivery complaints in Feb–Mar 2025
    south_orders_feb_mar = [
        o for o in orders
        if o[6] == "South" and o[8] >= "2025-02-01" and o[8] <= "2025-03-31"
    ]

    # 120 South delivery complaints (the "smoking gun" for the demo)
    for i in range(min(120, len(south_orders_feb_mar))):
        o = south_orders_feb_mar[i % len(south_orders_feb_mar)]
        text = random.choice(SOUTH_DELIVERY_TEXTS + COMPLAINT_TEXTS["delivery"])
        severity = random.choice(["high", "critical", "medium"])
        created = rand_date(date(2025, 2, 1), date(2025, 3, 31))
        resolved = random.random() < 0.25
        rows.append((cid, o[1], o[0], text, "delivery", severity, str(created), int(resolved)))
        cid += 1

    # 180 general complaints spread across all categories
    all_cats = list(COMPLAINT_TEXTS.keys())
    for _ in range(180):
        cat = random.choice(all_cats)
        o = random.choice(orders)
        text = random.choice(COMPLAINT_TEXTS[cat])
        severity = random.choice(["low", "medium", "high", "critical"])
        created = rand_date(date(2024, 1, 1), date(2025, 3, 31))
        resolved = random.random() < 0.60
        rows.append((cid, o[1], o[0], text, cat, severity, str(created), int(resolved)))
        cid += 1

    random.shuffle(rows)
    # Re-number complaint_id
    rows = [(i + 1,) + row[1:] for i, row in enumerate(rows)]
    return rows


# ---------------------------------------------------------------------------
# Generate documents (complaints.json, feedback.json)
# ---------------------------------------------------------------------------

def gen_complaint_docs() -> list[dict]:
    docs = []
    doc_id = 1

    # South delivery heavy complaints Feb–Mar 2025
    for i in range(60):
        dt = rand_date(date(2025, 2, 1), date(2025, 3, 31))
        text = random.choice(SOUTH_DELIVERY_TEXTS + COMPLAINT_TEXTS["delivery"])
        docs.append({
            "id": doc_id, "text": text,
            "category": "delivery", "region": "South", "date": str(dt),
        })
        doc_id += 1

    # Other regions and categories
    all_cats = list(COMPLAINT_TEXTS.keys())
    regions = ["North", "East", "West", "South"]
    for _ in range(60):
        cat = random.choice(all_cats)
        region = random.choice(regions)
        dt = rand_date(date(2024, 1, 1), date(2025, 3, 31))
        text = random.choice(COMPLAINT_TEXTS[cat])
        docs.append({
            "id": doc_id, "text": text,
            "category": cat, "region": region, "date": str(dt),
        })
        doc_id += 1

    return docs


FEEDBACK_TEXTS = [
    "Really happy with my purchase. Fast delivery and great quality!",
    "The product exceeded my expectations. Will definitely order again.",
    "Good value for money. The Electronics category has great deals.",
    "Impressed with the packaging and the speed of delivery to North region.",
    "Customer service was helpful when I had a query. Resolved quickly.",
    "The Clothing range is stylish and fits well. Love the variety.",
    "Food items arrived fresh and well-packed. Great quality organic products.",
    "Easy returns process. Got my refund within 5 days. Very satisfied.",
    "North region delivery is consistently excellent. Never had an issue.",
    "Beauty products are authentic and well-priced. Highly recommended.",
    "The app is easy to use and the checkout process is smooth.",
    "Great discounts on Electronics. Got a laptop at 20% off list price.",
    "Same-day delivery in Delhi is a game-changer. Super impressed.",
    "Premium customer support. They proactively updated me on my order.",
    "Home category has excellent variety. My kitchen set was perfect.",
    "Fast and reliable. Five orders this month, all delivered on time.",
    "The loyalty points system is generous. Already redeemed twice.",
    "Loved the personalised recommendations. Discovered products I needed.",
    "West region distribution seems very efficient. Always early.",
    "Protein bars and organic snacks are great. Repeat buyer!",
]


def gen_feedback_docs() -> list[dict]:
    docs = []
    regions = ["North", "South", "East", "West"]
    for i, text in enumerate(FEEDBACK_TEXTS * 3, start=1):
        region = random.choice(regions)
        dt = rand_date(date(2024, 1, 1), date(2025, 3, 31))
        sentiment = "positive" if random.random() < 0.8 else "mixed"
        docs.append({
            "id": i, "text": text,
            "region": region, "date": str(dt), "sentiment": sentiment,
        })
    return docs[:60]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed():
    print("Seeding database...")

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT,
            city TEXT,
            state TEXT,
            join_date DATE,
            segment TEXT
        );

        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT,
            subcategory TEXT,
            price REAL,
            cost REAL
        );

        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            product_id INTEGER,
            amount REAL,
            quantity INTEGER,
            status TEXT,
            region TEXT,
            channel TEXT,
            order_date DATE,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE complaints (
            complaint_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_id INTEGER,
            complaint_text TEXT,
            category TEXT,
            severity TEXT,
            created_date DATE,
            resolved BOOLEAN,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
    """)

    print("  Generating customers...")
    customers = gen_customers(200)
    c.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?)", customers
    )

    print("  Generating products...")
    products = gen_products()
    c.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?,?)", products
    )

    print("  Generating orders...")
    orders = gen_orders(customers, products)
    c.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", orders
    )

    print("  Generating complaints...")
    complaints = gen_complaints(customers, orders)
    c.executemany(
        "INSERT INTO complaints VALUES (?,?,?,?,?,?,?,?)", complaints
    )

    conn.commit()

    # Print summary stats
    print("\n=== Database Summary ===")
    for table in ("customers", "products", "orders", "complaints"):
        count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")

    print("\n  Revenue by region:")
    for row in c.execute(
        "SELECT region, ROUND(SUM(amount),0) as rev FROM orders "
        "WHERE status='completed' GROUP BY region ORDER BY rev DESC"
    ):
        print(f"    {row[0]}: {row[1]:,.0f}")

    print("\n  Revenue by category:")
    for row in c.execute(
        "SELECT p.category, ROUND(SUM(o.amount),0) as rev "
        "FROM orders o JOIN products p ON o.product_id=p.product_id "
        "WHERE o.status='completed' GROUP BY p.category ORDER BY rev DESC"
    ):
        print(f"    {row[0]}: {row[1]:,.0f}")

    conn.close()

    # Documents
    print("\n  Writing complaint documents...")
    complaint_docs = gen_complaint_docs()
    with open(DOCS_DIR / "complaints.json", "w", encoding="utf-8") as f:
        json.dump(complaint_docs, f, indent=2)
    print(f"    {len(complaint_docs)} complaint documents written.")

    print("  Writing feedback documents...")
    feedback_docs = gen_feedback_docs()
    with open(DOCS_DIR / "feedback.json", "w", encoding="utf-8") as f:
        json.dump(feedback_docs, f, indent=2)
    print(f"    {len(feedback_docs)} feedback documents written.")

    print("\nSeed complete!")


if __name__ == "__main__":
    seed()
