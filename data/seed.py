"""
Database and embedding initialization script.
Run once: python data/seed.py

Generates:
- data/demo.db (SQLite with orders, customers, products, complaints)
- data/documents/complaints.json (100+ unstructured complaint documents for RAG)
- data/documents/feedback.json (50+ feedback documents for RAG)
"""

import sqlite3
import random
import json
import os
from datetime import datetime, timedelta

random.seed(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "demo.db")
DOCS_DIR = os.path.join(BASE_DIR, "documents")

# ─── Constants ───────────────────────────────────────────────────────────────

CITIES = [
    ("Delhi", "Delhi"),
    ("Mumbai", "Maharashtra"),
    ("Bangalore", "Karnataka"),
    ("Chennai", "Tamil Nadu"),
    ("Kolkata", "West Bengal"),
    ("Hyderabad", "Telangana"),
    ("Pune", "Maharashtra"),
    ("Jaipur", "Rajasthan"),
    ("Lucknow", "Uttar Pradesh"),
    ("Ahmedabad", "Gujarat"),
]

CITY_TO_REGION = {
    "Delhi": "North", "Lucknow": "North", "Jaipur": "North",
    "Mumbai": "West", "Pune": "West", "Ahmedabad": "West",
    "Bangalore": "South", "Chennai": "South", "Hyderabad": "South",
    "Kolkata": "East",
}

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Ananya", "Diya", "Myra", "Sara", "Aadhya", "Isha",
    "Kiara", "Riya", "Priya", "Neha", "Amit", "Raj", "Suresh", "Vikram",
    "Deepak", "Rahul", "Pooja", "Meera", "Kavita", "Nisha", "Rohan", "Karan",
    "Manish", "Vishal", "Sanjay", "Arun", "Sneha", "Divya", "Swati", "Anjali",
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Gupta", "Singh", "Kumar", "Mehta", "Joshi",
    "Reddy", "Nair", "Iyer", "Shah", "Malhotra", "Chopra", "Kapoor", "Das",
    "Bose", "Chatterjee", "Pillai", "Rao", "Agarwal", "Pandey", "Mishra",
    "Saxena", "Tiwari",
]

SEGMENTS = ["regular"] * 60 + ["premium"] * 30 + ["enterprise"] * 10

PRODUCTS_DATA = {
    "Electronics": {
        "subcategories": ["Smartphones", "Laptops", "Tablets", "Headphones", "Smartwatches",
                          "Cameras", "Speakers", "Chargers", "Cables", "Power Banks"],
        "names": [
            "ProMax Phone 15", "UltraBook Laptop", "SlimTab 10", "BassBoost Headphones",
            "SmartWatch Pro", "DigitalCam X200", "SoundBar Elite", "TurboChrg 65W",
            "USB-C Premium Cable", "PowerVault 20K",
        ],
        "price_range": (2000, 50000),
        "margin_pct": (0.15, 0.35),
    },
    "Clothing": {
        "subcategories": ["T-Shirts", "Jeans", "Shirts", "Dresses", "Jackets",
                          "Kurtas", "Sarees", "Trousers", "Sweaters", "Activewear"],
        "names": [
            "Classic Cotton Tee", "SlimFit Denim", "Oxford Formal Shirt", "Floral Maxi Dress",
            "WindBreaker Jacket", "Silk Kurta Set", "Banarasi Saree", "Chino Trousers",
            "Merino Wool Sweater", "DryFit Running Set",
        ],
        "price_range": (500, 8000),
        "margin_pct": (0.30, 0.55),
    },
    "Home": {
        "subcategories": ["Bedding", "Kitchen", "Decor", "Furniture", "Lighting",
                          "Storage", "Bath", "Cleaning", "Garden", "Tools"],
        "names": [
            "Egyptian Cotton Bedsheet", "Non-Stick Cookware Set", "Ceramic Vase Trio",
            "Ergonomic Office Chair", "LED Desk Lamp", "Stackable Storage Bins",
            "Bamboo Towel Set", "Robot Vacuum Mini", "Terracotta Planter Set",
            "Multi-Tool Kit Pro",
        ],
        "price_range": (800, 25000),
        "margin_pct": (0.25, 0.45),
    },
    "Food": {
        "subcategories": ["Snacks", "Beverages", "Spices", "Organic", "Supplements",
                          "Dry Fruits", "Sweets", "Ready-to-Eat", "Tea & Coffee", "Honey"],
        "names": [
            "Premium Trail Mix", "Cold Brew Coffee Pack", "Kashmiri Saffron 5g",
            "Organic Quinoa 1kg", "Whey Protein Isolate", "Cashew Combo Box",
            "Artisan Chocolate Box", "Dal Makhani Ready Meal", "Darjeeling First Flush",
            "Wild Forest Honey 500g",
        ],
        "price_range": (200, 3000),
        "margin_pct": (0.20, 0.40),
    },
    "Beauty": {
        "subcategories": ["Skincare", "Haircare", "Makeup", "Fragrance", "Men's Grooming",
                          "Sunscreen", "Face Masks", "Serums", "Lip Care", "Nail Care"],
        "names": [
            "Vitamin C Serum 30ml", "Argan Oil Shampoo", "Matte Lipstick Set",
            "Oud Eau de Parfum", "Beard Grooming Kit", "SPF50 Sunscreen Gel",
            "Charcoal Face Mask Pack", "Retinol Night Serum", "Tinted Lip Balm Trio",
            "Gel Nail Polish Set",
        ],
        "price_range": (300, 5000),
        "margin_pct": (0.40, 0.65),
    },
}

CHANNELS = ["online", "retail", "wholesale"]
CHANNEL_WEIGHTS = [0.55, 0.30, 0.15]

STATUSES = ["completed", "pending", "cancelled", "returned"]
STATUS_WEIGHTS = [0.72, 0.12, 0.10, 0.06]

COMPLAINT_CATEGORIES = ["delivery", "quality", "pricing", "service", "refund"]
SEVERITIES = ["low", "medium", "high", "critical"]

DELIVERY_COMPLAINT_TEMPLATES = [
    "Ordered {product} on {date}, delivery was promised in 3 days but arrived after {delay} days. Very frustrated with the delay.",
    "Package for order #{order_id} was delivered to wrong address. Had to contact support multiple times to get it redirected. {region} region logistics seem broken.",
    "My {product} order arrived with damaged packaging. The box was completely crushed. {region} warehouse packing quality is terrible.",
    "Delivery partner marked my order as delivered but I never received it. Order #{order_id} from {region} region. Had to file a dispute.",
    "Waited {delay} days for my {product}. Tracking showed it stuck at {region} sorting facility for over a week. Unacceptable delays.",
    "Order #{order_id} was supposed to arrive by {date} but still showing 'in transit'. {region} region deliveries have been consistently late.",
    "Received someone else's order instead of my {product}. Mix-up at {region} warehouse. Now have to return and wait again.",
    "Delivery was rescheduled 3 times for my {product} order. Each time I stayed home and waited. {region} logistics is unreliable.",
    "My {product} was left at the doorstep in rain without any protection. Entire packaging was soaked. {region} delivery partners need training.",
    "Partial delivery - received only 1 of 3 items from order #{order_id}. {region} warehouse seems to have inventory issues.",
]

QUALITY_COMPLAINT_TEMPLATES = [
    "The {product} I received looks nothing like the pictures on the website. Quality is much lower than expected for ₹{amount}.",
    "My {product} stopped working after just 2 weeks. For the price of ₹{amount}, I expected better durability.",
    "Color of {product} is completely different from what was shown. This feels like false advertising.",
    "Received a damaged {product} - there was a visible scratch on the surface. Quality control needs improvement.",
    "{product} material quality is poor. Feels cheap and flimsy despite being marketed as premium.",
]

PRICING_COMPLAINT_TEMPLATES = [
    "I was charged ₹{amount} but the listed price was much lower. Pricing discrepancy in order #{order_id}.",
    "Found the same {product} at ₹{lower_amount} on another platform right after purchasing at ₹{amount}. Where is the price match guarantee?",
    "Hidden charges added to my {product} order. Final amount ₹{amount} was 15% more than shown at checkout.",
]

SERVICE_COMPLAINT_TEMPLATES = [
    "Called customer support 5 times about order #{order_id}. Each time I had to explain the issue from scratch. No resolution yet.",
    "Chat support disconnected mid-conversation while resolving my {product} issue. No follow-up callback received.",
    "Customer support promised a callback within 24 hours regarding my order #{order_id}. It's been 4 days, still waiting.",
    "Rude behavior from support agent when I called about my {product} return. Very unprofessional experience.",
]

REFUND_COMPLAINT_TEMPLATES = [
    "Returned my {product} 2 weeks ago but haven't received refund of ₹{amount} yet. Order #{order_id}.",
    "Refund for order #{order_id} was processed but only ₹{lower_amount} was credited instead of full ₹{amount}.",
    "Been waiting for 20 days for my refund on {product}. Support says it's 'being processed'. ₹{amount} is a significant amount.",
]

POSITIVE_FEEDBACK_TEMPLATES = [
    "Absolutely love my {product}! Delivered ahead of schedule to {city}. Quality exceeded expectations. Will definitely order again.",
    "Great experience with order #{order_id}. {product} was exactly as described and arrived well-packaged. {region} delivery was swift!",
    "Customer support was incredibly helpful when I had a question about my {product}. Issue resolved in one call. Impressed!",
    "The {product} is fantastic value for ₹{amount}. Build quality is premium and it works perfectly. Highly recommend.",
    "Smooth ordering experience. {product} delivered to {city} in just 2 days. Tracking updates were accurate throughout.",
    "Returning customer here. Always satisfied with the quality. My latest {product} purchase was no exception. Keep it up!",
    "Best online shopping experience. {product} packaging was eco-friendly and the product itself is top-notch.",
    "Upgraded from a competitor's product to {product} and the difference is night and day. Worth every rupee of ₹{amount}.",
]


# ─── Helper functions ────────────────────────────────────────────────────────

def random_date(start: datetime, end: datetime) -> str:
    """Generate a random date string between start and end."""
    delta = end - start
    random_days = random.randint(0, delta.days)
    dt = start + timedelta(days=random_days)
    return dt.strftime("%Y-%m-%d")


def generate_email(first, last):
    """Generate a realistic email address."""
    domains = ["gmail.com", "yahoo.co.in", "outlook.com", "hotmail.com", "protonmail.com"]
    sep = random.choice([".", "_", ""])
    num = random.choice(["", str(random.randint(1, 99))])
    return f"{first.lower()}{sep}{last.lower()}{num}@{random.choice(domains)}"


# ─── Data Generation ─────────────────────────────────────────────────────────

def create_tables(conn):
    """Create all database tables."""
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT,
            city TEXT,
            state TEXT,
            join_date DATE,
            segment TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT,
            subcategory TEXT,
            price REAL,
            cost REAL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
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
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_id INTEGER,
            complaint_text TEXT,
            category TEXT,
            severity TEXT,
            created_date DATE,
            resolved BOOLEAN,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)
    
    conn.commit()


def generate_customers(conn):
    """Generate 200 customers across 10 cities."""
    cursor = conn.cursor()
    customers = []
    
    for i in range(1, 201):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = generate_email(first, last)
        city, state = random.choice(CITIES)
        join_date = random_date(datetime(2023, 1, 1), datetime(2024, 12, 31))
        segment = random.choice(SEGMENTS)
        
        customers.append((i, name, email, city, state, join_date, segment))
    
    cursor.executemany(
        "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", customers
    )
    conn.commit()
    print(f"  ✓ Generated {len(customers)} customers")
    return customers


def generate_products(conn):
    """Generate 50 products across 5 categories."""
    cursor = conn.cursor()
    products = []
    pid = 1
    
    for category, info in PRODUCTS_DATA.items():
        for j in range(10):
            name = info["names"][j]
            subcategory = info["subcategories"][j]
            price = round(random.uniform(*info["price_range"]), 2)
            margin = random.uniform(*info["margin_pct"])
            cost = round(price * (1 - margin), 2)
            
            products.append((pid, name, category, subcategory, price, cost))
            pid += 1
    
    cursor.executemany(
        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)", products
    )
    conn.commit()
    print(f"  ✓ Generated {len(products)} products")
    return products


def generate_orders(conn, customers, products):
    """Generate 2000+ orders from Jan 2024 to Mar 2025.
    
    Key data patterns:
    - North is largest region (~35% revenue)
    - Electronics is ~40% revenue
    - South region has revenue drop in Feb-Mar 2025 (~30% reduction)
    """
    cursor = conn.cursor()
    orders = []
    
    # Build product lookup by category
    electronics_ids = [p[0] for p in products if p[2] == "Electronics"]
    other_ids = [p[0] for p in products if p[2] != "Electronics"]
    product_lookup = {p[0]: p for p in products}
    
    # Customer-to-city mapping for region determination
    customer_cities = {c[0]: c[3] for c in customers}
    
    # Region weights: North ~35%, West ~25%, South ~25%, East ~15%
    region_customers = {"North": [], "South": [], "East": [], "West": []}
    for c in customers:
        region = CITY_TO_REGION[c[3]]
        region_customers[region].append(c[0])
    
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2025, 3, 31)
    
    order_id = 1
    current = start_date
    
    while current <= end_date:
        month_str = current.strftime("%Y-%m")
        
        # Determine daily order count (base ~5 per day, growing slightly)
        months_elapsed = (current.year - 2024) * 12 + current.month - 1
        base_daily = 5 + months_elapsed * 0.3  # Slight growth
        daily_orders = max(3, int(random.gauss(base_daily, 1.5)))
        
        for _ in range(daily_orders):
            # Pick region with weights
            region = random.choices(
                ["North", "South", "East", "West"],
                weights=[0.35, 0.25, 0.15, 0.25]
            )[0]
            
            # Pick customer from that region
            if not region_customers[region]:
                region = "North"
            customer_id = random.choice(region_customers[region])
            
            # Pick product — Electronics gets ~40% weight
            if random.random() < 0.40:
                product_id = random.choice(electronics_ids)
            else:
                product_id = random.choice(other_ids)
            
            product = product_lookup[product_id]
            price = product[4]
            
            quantity = random.choices([1, 2, 3, 4, 5], weights=[50, 25, 15, 7, 3])[0]
            amount = round(price * quantity, 2)
            
            # Apply South region revenue drop in Feb-Mar 2025
            is_south_drop_period = (
                region == "South" and 
                current >= datetime(2025, 2, 1) and 
                current <= datetime(2025, 3, 31)
            )
            if is_south_drop_period:
                amount = round(amount * 0.70, 2)  # 30% reduction
                # Also increase cancellation rate in South during this period
                status = random.choices(
                    STATUSES, weights=[0.55, 0.15, 0.20, 0.10]
                )[0]
            else:
                status = random.choices(STATUSES, STATUS_WEIGHTS)[0]
            
            channel = random.choices(CHANNELS, CHANNEL_WEIGHTS)[0]
            order_date = current.strftime("%Y-%m-%d")
            
            orders.append((
                order_id, customer_id, product_id, amount,
                quantity, status, region, channel, order_date
            ))
            order_id += 1
        
        current += timedelta(days=1)
    
    cursor.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", orders
    )
    conn.commit()
    print(f"  ✓ Generated {len(orders)} orders")
    return orders


def generate_complaints(conn, orders, products):
    """Generate 300 complaints with South region delivery spike in Feb-Mar 2025."""
    cursor = conn.cursor()
    complaints = []
    product_lookup = {p[0]: p for p in products}
    
    # Select orders that can have complaints (completed, returned, or cancelled)
    eligible_orders = [o for o in orders if o[5] in ("completed", "returned", "cancelled")]
    
    # ── South region Feb-Mar 2025 delivery complaints (~80 complaints) ──
    south_feb_mar = [
        o for o in eligible_orders 
        if o[6] == "South" and o[8] >= "2025-02-01" and o[8] <= "2025-03-31"
    ]
    
    complaint_id = 1
    
    # Generate concentrated South delivery complaints
    south_sample_size = min(80, len(south_feb_mar))
    south_complaint_orders = random.sample(south_feb_mar, south_sample_size) if south_feb_mar else []
    
    for order in south_complaint_orders:
        product = product_lookup[order[2]]
        product_name = product[1]
        delay = random.randint(5, 18)
        
        # 70% delivery, 30% other categories
        if random.random() < 0.70:
            cat = "delivery"
            template = random.choice(DELIVERY_COMPLAINT_TEMPLATES)
        else:
            cat = random.choice(["quality", "service", "refund"])
            if cat == "quality":
                template = random.choice(QUALITY_COMPLAINT_TEMPLATES)
            elif cat == "service":
                template = random.choice(SERVICE_COMPLAINT_TEMPLATES)
            else:
                template = random.choice(REFUND_COMPLAINT_TEMPLATES)
        
        text = template.format(
            product=product_name, date=order[8], delay=delay,
            order_id=order[0], region="South", amount=int(order[3]),
            lower_amount=int(order[3] * 0.85), city="Chennai"
        )
        
        severity = random.choices(SEVERITIES, weights=[0.10, 0.25, 0.40, 0.25])[0]
        
        # Complaint date is 1-10 days after order
        order_dt = datetime.strptime(order[8], "%Y-%m-%d")
        complaint_dt = order_dt + timedelta(days=random.randint(1, 10))
        created_date = complaint_dt.strftime("%Y-%m-%d")
        
        resolved = random.random() < 0.40  # Low resolution rate during crisis
        
        complaints.append((
            complaint_id, order[1], order[0], text, cat,
            severity, created_date, resolved
        ))
        complaint_id += 1
    
    # ── General complaints for other regions/periods (~220 complaints) ──
    remaining_needed = 300 - len(complaints)
    other_orders = [o for o in eligible_orders if o not in south_complaint_orders]
    general_sample = random.sample(other_orders, min(remaining_needed, len(other_orders)))
    
    for order in general_sample:
        product = product_lookup[order[2]]
        product_name = product[1]
        
        cat = random.choices(
            COMPLAINT_CATEGORIES, weights=[0.30, 0.25, 0.15, 0.20, 0.10]
        )[0]
        
        if cat == "delivery":
            template = random.choice(DELIVERY_COMPLAINT_TEMPLATES)
        elif cat == "quality":
            template = random.choice(QUALITY_COMPLAINT_TEMPLATES)
        elif cat == "pricing":
            template = random.choice(PRICING_COMPLAINT_TEMPLATES)
        elif cat == "service":
            template = random.choice(SERVICE_COMPLAINT_TEMPLATES)
        else:
            template = random.choice(REFUND_COMPLAINT_TEMPLATES)
        
        delay = random.randint(3, 14)
        text = template.format(
            product=product_name, date=order[8], delay=delay,
            order_id=order[0], region=order[6], amount=int(order[3]),
            lower_amount=int(order[3] * 0.85), city="Mumbai"
        )
        
        severity = random.choices(SEVERITIES, weights=[0.25, 0.35, 0.25, 0.15])[0]
        
        order_dt = datetime.strptime(order[8], "%Y-%m-%d")
        complaint_dt = order_dt + timedelta(days=random.randint(1, 14))
        created_date = complaint_dt.strftime("%Y-%m-%d")
        
        resolved = random.random() < 0.65
        
        complaints.append((
            complaint_id, order[1], order[0], text, cat,
            severity, created_date, resolved
        ))
        complaint_id += 1
    
    cursor.executemany(
        "INSERT INTO complaints VALUES (?, ?, ?, ?, ?, ?, ?, ?)", complaints
    )
    conn.commit()
    print(f"  ✓ Generated {len(complaints)} complaints")
    return complaints


def generate_complaint_documents(orders, products):
    """Generate 100+ unstructured complaint documents for RAG."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    
    product_lookup = {p[0]: p for p in products}
    documents = []
    
    # ── South region delivery complaints (60 docs concentrated in Feb-Mar 2025) ──
    south_delivery_texts = [
        "Ordered a laptop on March 2, delivery was promised in 3 days but arrived after 2 weeks. Packaging was damaged. South region warehouse seems to have major issues.",
        "South region deliveries have been terrible since February. My electronics order took 12 days instead of the usual 3. Multiple friends have similar complaints.",
        "Third delayed delivery this month from the South warehouse. My SmartWatch Pro order was stuck in Chennai sorting facility for 8 days. Something is seriously wrong.",
        "Delivery partner in Bangalore couldn't find my address despite clear landmarks. Order was returned to warehouse and I had to wait another week. South region needs better trained partners.",
        "Received a completely damaged package from South warehouse. The box looked like it was thrown around. My Headphones were broken inside. This is the second time this happened.",
        "South region supply chain appears to be broken. Spoke to other customers in my apartment complex - everyone is facing delivery delays since February 2025.",
        "My order from Chennai warehouse has been showing 'in transit' for 10 days. Customer support says there's a 'temporary logistics issue' in the South region. Very vague response.",
        "Hyderabad delivery hub seems overwhelmed. All my recent orders are delayed by at least a week. Previously, same-day delivery was common in this area.",
        "Placed 3 orders in March, all from South warehouse. Two were delayed by over a week, one was delivered damaged. The logistics quality has dropped significantly.",
        "Multiple returns and re-deliveries for my Bangalore address. South region courier partners are consistently late and sometimes don't show up at all.",
        "The delivery situation in South India has become unbearable since February. My colleague's expensive electronics order was lost in transit between warehouses.",
        "Delivery tracking for South region orders is extremely inaccurate. Shows 'out for delivery' for 3 days straight. My UltraBook Laptop finally arrived after 11 days.",
        "South region warehouse appears to be understaffed. Orders are being dispatched much later than usual. My March orders all shipped 4-5 days after placement.",
        "Filed 4 complaints this month alone about delivery delays from South region. Each time told 'it will be escalated'. No actual improvement seen.",
        "Chennai warehouse seems to have storage issues. Received a product with warehouse damage (dents and scratches) that clearly happened during storage, not transit.",
        "South region express delivery is a joke now. Paid extra for 1-day delivery of my tablet, received it after 6 days. No refund of delivery charges offered.",
        "Our company ordered bulk electronics from South warehouse. Half the shipment arrived damaged. The other half was delayed by 2 weeks. Switching to North fulfillment.",
        "Bangalore last-mile delivery has deteriorated since their logistics partner changed. My ProMax Phone order was handed to me in a torn poly bag.",
        "Consistent pattern of South region delays since mid-February. Spoke to customer service who admitted they're 'aware of regional challenges'. Not reassuring.",
        "My parents in Hyderabad have stopped ordering online because of repeated delivery failures. South region has lost customer trust in just 2 months.",
        "Order marked delivered but left at security gate in rain. South region delivery agents don't follow safe delivery protocols anymore.",
        "Tracking shows my order bouncing between South region hubs for 5 days. Chennai → Bangalore → Chennai again. Clear logistics routing issues.",
        "Premium customer here with 3 years of loyalty. South region delivery has never been this bad. Considering switching to competitor platforms.",
        "South warehouse sent wrong item twice for the same order. Had to return and reorder. Total time wasted: 3 weeks. Absolutely unacceptable.",
        "Delivery agent in Chennai was rude when I pointed out the delayed delivery. Started arguing instead of apologizing. Poor training in South region.",
        "February and March have been nightmare months for South region customers. Every order I place takes 10+ days. Something systemic is going on.",
        "The cardboard quality used for packaging at South warehouse has clearly been downgraded. Products arriving with more damage than ever before.",
        "Group complaint from our residential society in Bangalore: 15 residents have experienced delivery delays in March alone. All South warehouse orders.",
        "My March order for kitchen appliances arrived broken. South warehouse packing team used no bubble wrap or protective material. ₹15,000 product wasted.",
        "South region customer service can't even track orders properly. They give different ETAs every time I call. Internal systems seem to be in chaos.",
    ]
    
    doc_id = 1
    for i, text in enumerate(south_delivery_texts):
        # Spread across Feb-Mar 2025
        if i < 10:
            month, day_range = "02", (10, 28)
        else:
            month, day_range = "03", (1, 28)
        
        day = random.randint(*day_range)
        date = f"2025-{month}-{day:02d}"
        
        documents.append({
            "id": doc_id,
            "text": text,
            "category": "delivery",
            "region": "South",
            "date": date,
        })
        doc_id += 1
    
    # ── South region quality complaints (15 docs) ──
    south_quality = [
        "Products from South warehouse arrive in poor condition. My new electronics had visible scratches that weren't there in unboxing videos of the same product.",
        "Quality control at Chennai fulfillment center needs a complete overhaul. Receiving expired food products and damaged electronics regularly.",
        "South warehouse seems to be shipping refurbished items as new. My 'new' laptop had signs of previous use and different serial number than invoice.",
        "Clothing orders from South region arrive wrinkled and sometimes with a musty smell. Storage conditions at the warehouse seem subpar.",
        "Received a Beauty product from Hyderabad warehouse that was clearly tampered with. Seal was broken and product was half used.",
        "South region product quality has dropped since Feb 2025. Suspect they changed suppliers or are cutting corners on storage.",
        "Multiple items from South warehouse had damaged barcodes and labels. Looks like water damage in the storage facility.",
        "Electronics from South fulfillment show higher failure rates. My community forum has 20+ reports of DOA products this month alone.",
        "The product I received from South warehouse was outdated model despite ordering the latest version. Either inventory mix-up or deliberate.",
        "South region cosmetics arrived melted. Clearly not stored in temperature-controlled conditions. ₹3,000 worth of products ruined.",
        "Repeated quality issues with South warehouse: wrong sizes in clothing, dented electronics boxes, expired supplements. Pattern is clear.",
        "Ordered premium headphones from South warehouse, received a cheap knockoff. Packaging was resealed. This is fraud.",
        "South warehouse food items arrived past expiry date. This is a health hazard. Filing a formal complaint with consumer forum.",
        "The sewing on clothing items from South region is consistently poor. Had to return 3 out of 5 shirts. Other regions are fine.",
        "South warehouse is shipping items without proper protective packaging. Even 'fragile' marked items arrive in plain boxes with no padding.",
    ]
    
    for text in south_quality:
        day = random.randint(1, 28)
        month = random.choice(["02", "03"])
        documents.append({
            "id": doc_id,
            "text": text,
            "category": "quality",
            "region": "South",
            "date": f"2025-{month}-{day:02d}",
        })
        doc_id += 1
    
    # ── General complaints from other regions (55+ docs) ──
    general_complaints = [
        ("North region delivery was slightly delayed but product arrived in perfect condition. Minor inconvenience.", "delivery", "North", "2025-01-15"),
        ("Mumbai delivery is generally reliable. Had one delayed order this week but support resolved quickly.", "delivery", "West", "2025-02-10"),
        ("East region customer service was helpful when I reported a pricing discrepancy. Refund processed same day.", "pricing", "East", "2025-01-22"),
        ("Delhi warehouse packing quality is excellent. Never had a damaged delivery from North region.", "quality", "North", "2025-02-05"),
        ("Kolkata deliveries are fine except during festivals when everything gets delayed. Understandable.", "delivery", "East", "2025-03-01"),
        ("Pune office received bulk order on time. West region B2B fulfillment works well.", "delivery", "West", "2025-01-18"),
        ("Had a pricing issue with an Electronics order in January. Support in North region was responsive and credited the difference.", "pricing", "North", "2025-01-28"),
        ("Jaipur delivery partner is excellent. Always calls before delivery and handles packages carefully.", "service", "North", "2025-02-14"),
        ("Mumbai warehouse processed my return within 2 days. Refund was fast. Good experience with West region.", "refund", "West", "2025-03-05"),
        ("East region delivery times have improved compared to last year. Kolkata now gets 2-day delivery consistently.", "delivery", "East", "2025-02-20"),
        ("Quality of electronics from North warehouse is consistently high. All my gadgets arrived in mint condition.", "quality", "North", "2025-03-10"),
        ("West region food delivery maintains cold chain well. Supplements and perishables always arrive fresh.", "quality", "West", "2025-01-30"),
        ("Ahmedabad customer here - delivery is prompt and packaging is secure. No complaints about West region.", "delivery", "West", "2025-02-25"),
        ("Delhi same-day delivery actually delivered same day! Impressed with North region speed.", "delivery", "North", "2025-03-15"),
        ("Had a minor service issue in East region but it was resolved with one call. Support agent was professional.", "service", "East", "2025-01-12"),
        ("Lucknow delivery took 4 days for a product that should come in 2. North region express isn't always express.", "delivery", "North", "2025-02-08"),
        ("Quality issue with clothing from West warehouse. Stitching came apart after 2 washes. Decent refund process though.", "quality", "West", "2025-03-20"),
        ("Mumbai return pickup was seamless. West region logistics handles returns much better than pickups.", "refund", "West", "2025-01-05"),
        ("North region has best packaging I've seen. Double-boxed my fragile order with extra bubble wrap.", "quality", "North", "2025-02-15"),
        ("East region customer support speaks Bengali which was helpful. Resolved my complaint about wrong product quickly.", "service", "East", "2025-03-08"),
        ("Pricing error on website showed ₹500 instead of ₹5000. West region honored the lower price. Great policy!", "pricing", "West", "2025-01-25"),
        ("Jaipur electronics delivery arrived with original manufacturer seal intact. North warehouse handles products well.", "quality", "North", "2025-03-12"),
        ("Kolkata home appliance delivery included free installation. East region service is improving steadily.", "service", "East", "2025-02-28"),
        ("Delhi next-day delivery for premium members works flawlessly. North region logistics is top tier.", "delivery", "North", "2025-03-18"),
        ("West region beauty products always arrive with samples. Nice touch from Mumbai warehouse team.", "quality", "West", "2025-01-20"),
        ("Had a refund issue with North region order. Took 10 days but eventually resolved. Should be faster.", "refund", "North", "2025-02-22"),
        ("East region wholesale orders are well-handled. Bulk pricing was transparent with no hidden fees.", "pricing", "East", "2025-03-03"),
        ("Mumbai warehouse accidentally shipped 2 of the same item. Reported it and was told to keep both. Excellent service!", "service", "West", "2025-01-08"),
        ("North region handles festival rush better than other regions. Diwali orders all arrived on time.", "delivery", "North", "2024-11-15"),
        ("Pune order tracking is accurate and updates in real-time. West region tech infrastructure is solid.", "delivery", "West", "2025-02-12"),
        ("East region express delivery launched in Kolkata. First order arrived in 4 hours. Impressive improvement.", "delivery", "East", "2025-03-25"),
        ("Quality complaint about Home category product from North. Table arrived with one leg shorter. Manufacturing defect.", "quality", "North", "2025-01-14"),
        ("West region subscription service works perfectly. Monthly deliveries arrive on the same date every month.", "service", "West", "2025-02-01"),
        ("North region food items: all organic products were genuine with proper certification. Trust established.", "quality", "North", "2025-03-22"),
        ("Kolkata customer service needs more English-speaking agents. Had difficulty explaining my issue.", "service", "East", "2025-01-18"),
        ("West region price matching with competitors: submitted evidence and got ₹2000 discount. Fair policy.", "pricing", "West", "2025-02-07"),
        ("Delhi warehouse fire sale items arrived in perfect condition despite 70% discount. North QC is maintained even for sales.", "quality", "North", "2025-03-05"),
        ("East region refund for defective electronics took 15 days. Acceptable but not great.", "refund", "East", "2025-01-28"),
        ("North region loyalty program benefits are actually useful. Got free express delivery and early access to sales.", "service", "North", "2025-02-18"),
        ("West region started eco-friendly packaging. Love the initiative. Products still well-protected.", "quality", "West", "2025-03-15"),
    ]
    
    for text, cat, region, date in general_complaints:
        documents.append({
            "id": doc_id,
            "text": text,
            "category": cat,
            "region": region,
            "date": date,
        })
        doc_id += 1
    
    filepath = os.path.join(DOCS_DIR, "complaints.json")
    with open(filepath, "w") as f:
        json.dump(documents, f, indent=2)
    
    print(f"  ✓ Generated {len(documents)} complaint documents → {filepath}")
    return documents


def generate_feedback_documents(orders, products):
    """Generate 50+ positive/mixed feedback documents for RAG."""
    product_lookup = {p[0]: p for p in products}
    feedbacks = []
    doc_id = 1
    
    # Pick random completed orders for positive feedback
    completed_orders = [o for o in orders if o[5] == "completed"]
    sample = random.sample(completed_orders, min(55, len(completed_orders)))
    
    for order in sample:
        product = product_lookup[order[2]]
        template = random.choice(POSITIVE_FEEDBACK_TEMPLATES)
        
        # Get city from region
        region_city = {
            "North": random.choice(["Delhi", "Jaipur", "Lucknow"]),
            "South": random.choice(["Bangalore", "Chennai", "Hyderabad"]),
            "East": "Kolkata",
            "West": random.choice(["Mumbai", "Pune", "Ahmedabad"]),
        }
        
        text = template.format(
            product=product[1],
            order_id=order[0],
            region=order[6],
            amount=int(order[3]),
            city=region_city[order[6]],
        )
        
        feedbacks.append({
            "id": doc_id,
            "text": text,
            "sentiment": random.choices(
                ["positive", "neutral"], weights=[0.85, 0.15]
            )[0],
            "region": order[6],
            "date": order[8],
        })
        doc_id += 1
    
    filepath = os.path.join(DOCS_DIR, "feedback.json")
    with open(filepath, "w") as f:
        json.dump(feedbacks, f, indent=2)
    
    print(f"  ✓ Generated {len(feedbacks)} feedback documents → {filepath}")
    return feedbacks


def print_summary(conn):
    """Print data summary statistics."""
    cursor = conn.cursor()
    
    print("\n📊 Database Summary:")
    print("=" * 60)
    
    cursor.execute("SELECT COUNT(*) FROM customers")
    print(f"  Customers:  {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM products")
    print(f"  Products:   {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    print(f"  Orders:     {total_orders}")
    
    cursor.execute("SELECT COUNT(*) FROM complaints")
    print(f"  Complaints: {cursor.fetchone()[0]}")
    
    print("\n📈 Revenue by Region:")
    cursor.execute("""
        SELECT region, 
               ROUND(SUM(amount), 0) as revenue,
               COUNT(*) as orders
        FROM orders 
        WHERE status = 'completed'
        GROUP BY region 
        ORDER BY revenue DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]:6s}: ₹{row[1]:>12,.0f}  ({row[2]} orders)")
    
    print("\n📈 Revenue by Category:")
    cursor.execute("""
        SELECT p.category, 
               ROUND(SUM(o.amount), 0) as revenue,
               ROUND(SUM(o.amount) * 100.0 / (SELECT SUM(amount) FROM orders WHERE status='completed'), 1) as pct
        FROM orders o 
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status = 'completed'
        GROUP BY p.category 
        ORDER BY revenue DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]:12s}: ₹{row[1]:>12,.0f}  ({row[2]}%)")
    
    print("\n📉 South Region Monthly Revenue (showing drop):")
    cursor.execute("""
        SELECT strftime('%Y-%m', order_date) as month, 
               ROUND(SUM(amount), 0) as revenue,
               COUNT(*) as orders
        FROM orders 
        WHERE region = 'South' AND status = 'completed'
          AND order_date >= '2024-10-01'
        GROUP BY month 
        ORDER BY month
    """)
    for row in cursor.fetchall():
        marker = " ⚠️" if row[0] in ("2025-02", "2025-03") else ""
        print(f"  {row[0]}: ₹{row[1]:>10,.0f}  ({row[2]} orders){marker}")
    
    print("\n📋 Complaints by Category (South in Feb-Mar 2025):")
    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM complaints 
        WHERE complaint_id IN (
            SELECT c.complaint_id FROM complaints c
            JOIN orders o ON c.order_id = o.order_id
            WHERE o.region = 'South' 
              AND c.created_date >= '2025-02-01'
              AND c.created_date <= '2025-03-31'
        )
        GROUP BY category 
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]:10s}: {row[1]}")
    
    print("\n" + "=" * 60)
    print("✅ Database ready at:", DB_PATH)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("🚀 Initializing Talk to Data demo database...")
    print()
    
    # Remove existing DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"  ✗ Removed existing {DB_PATH}")
    
    # Create fresh database
    conn = sqlite3.connect(DB_PATH)
    
    print("📦 Creating tables...")
    create_tables(conn)
    
    print("\n👥 Generating data...")
    customers = generate_customers(conn)
    products = generate_products(conn)
    orders = generate_orders(conn, customers, products)
    complaints = generate_complaints(conn, orders, products)
    
    print("\n📄 Generating documents for RAG...")
    generate_complaint_documents(orders, products)
    generate_feedback_documents(orders, products)
    
    print_summary(conn)
    conn.close()


if __name__ == "__main__":
    main()
