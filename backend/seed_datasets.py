"""
DataMind AI — Seed Script
Generates 4 realistic demo datasets and uploads them via the API.

Usage:
    python seed_datasets.py

Requires the backend to be running (default: http://localhost:8001).
"""

import os
import sys
import io
import requests
import numpy as np
import pandas as pd
import random
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE = os.getenv("API_BASE", "http://localhost:8001")
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "admin@datamind.ai")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Admin@DataMind2026")

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_token() -> str:
    """Login and return access token."""
    # Try demo-login first (fastest)
    r = requests.post(f"{API_BASE}/api/auth/demo-login", timeout=10)
    if r.status_code == 200:
        token = r.json().get("access_token")
        if token:
            print("  Logged in via demo-login")
            return token

    # Fallback: regular login with superadmin credentials
    r = requests.post(
        f"{API_BASE}/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("No access_token in login response")
    print(f"  Logged in as {DEMO_EMAIL}")
    return token


def upload_csv(token: str, name: str, description: str, df: pd.DataFrame) -> dict:
    """Upload a DataFrame as CSV to the datasets endpoint."""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode()

    r = requests.post(
        f"{API_BASE}/api/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (f"{name.lower().replace(' ', '_')}.csv", csv_bytes, "text/csv")},
        data={"name": name, "description": description},
        timeout=60,
    )
    if r.status_code not in (200, 201):
        print(f"  ERROR uploading '{name}': {r.status_code} — {r.text[:300]}")
        return {}
    result = r.json()
    print(f"  Uploaded '{name}' => id={result.get('id')} rows={result.get('row_count')}")
    return result


# ── Dataset Generators ────────────────────────────────────────────────────────

def make_sales_data() -> pd.DataFrame:
    """200-row monthly sales data (2022–2024)."""
    rng = np.random.default_rng(42)
    random.seed(42)

    regions = ["North", "South", "East", "West", "Central"]
    products = ["Enterprise Suite", "Pro License", "Starter Pack", "Data Module", "Analytics Add-on"]
    reps = [
        "Alice Johnson", "Bob Martinez", "Carol Lee", "David Kim",
        "Emma Wilson", "Frank Chen", "Grace Patel", "Henry Brown",
    ]

    rows = []
    start = datetime(2022, 1, 1)
    for i in range(200):
        # Spread across 36 months
        month_offset = i % 36
        date = (start + timedelta(days=int(month_offset * 30 + rng.integers(0, 28)))).date()
        region = random.choice(regions)
        product = random.choice(products)
        rep = random.choice(reps)

        base_revenue = {"Enterprise Suite": 45000, "Pro License": 18000,
                        "Starter Pack": 5500, "Data Module": 12000, "Analytics Add-on": 8000}[product]
        seasonal_factor = 1.0 + 0.15 * np.sin(2 * np.pi * date.month / 12)
        revenue = int(rng.normal(base_revenue * seasonal_factor, base_revenue * 0.15))
        revenue = max(1000, revenue)
        cost_pct = rng.uniform(0.45, 0.65)
        cost = int(revenue * cost_pct)
        profit = revenue - cost
        units = max(1, int(rng.normal(revenue / 800, 3)))

        rows.append({
            "date": str(date),
            "region": region,
            "product": product,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "units_sold": units,
            "sales_rep": rep,
        })

    return pd.DataFrame(rows)


def make_hr_employees() -> pd.DataFrame:
    """150-row HR employee dataset."""
    rng = np.random.default_rng(7)
    random.seed(7)

    departments = ["Engineering", "Sales", "Marketing", "Finance", "Operations", "HR", "Product"]
    dept_salary = {
        "Engineering": 110000, "Sales": 75000, "Marketing": 80000,
        "Finance": 95000, "Operations": 70000, "HR": 68000, "Product": 105000,
    }

    rows = []
    for emp_id in range(1001, 1151):
        dept = random.choice(departments)
        hire_year = rng.integers(2015, 2024)
        hire_month = rng.integers(1, 13)
        hire_day = rng.integers(1, 28)
        hire_date = datetime(int(hire_year), int(hire_month), int(hire_day)).date()
        tenure = round((datetime(2024, 12, 31).date() - hire_date).days / 365.25, 1)

        base = dept_salary[dept]
        salary = int(rng.normal(base * (1 + tenure * 0.03), base * 0.12))
        salary = max(45000, min(220000, salary))

        perf = round(float(rng.normal(3.5, 0.6)), 1)
        perf = max(1.0, min(5.0, perf))

        # Attrition more likely with low perf + long tenure + low salary
        attrition_prob = 0.05 + (0.1 if perf < 3.0 else 0) + (0.05 if tenure > 5 else 0)
        attrition = int(rng.random() < attrition_prob)

        rows.append({
            "employee_id": emp_id,
            "department": dept,
            "hire_date": str(hire_date),
            "salary": salary,
            "performance_score": perf,
            "tenure_years": tenure,
            "attrition": attrition,
        })

    return pd.DataFrame(rows)


def make_ecommerce_orders() -> pd.DataFrame:
    """300-row e-commerce orders dataset."""
    rng = np.random.default_rng(99)
    random.seed(99)

    categories = ["Electronics", "Clothing", "Home & Garden", "Sports", "Books", "Beauty", "Toys"]
    payment_methods = ["Credit Card", "PayPal", "Debit Card", "Apple Pay", "Google Pay", "Bank Transfer"]
    statuses = ["completed", "completed", "completed", "shipped", "processing", "refunded", "cancelled"]
    countries = ["USA", "UK", "Canada", "Germany", "France", "Australia", "Netherlands", "Sweden"]

    cat_amounts = {
        "Electronics": (80, 800), "Clothing": (20, 150), "Home & Garden": (30, 400),
        "Sports": (25, 300), "Books": (8, 60), "Beauty": (15, 120), "Toys": (10, 200),
    }

    rows = []
    start = datetime(2023, 1, 1)
    for i in range(300):
        order_date = (start + timedelta(days=int(rng.integers(0, 730)))).date()
        category = random.choice(categories)
        lo, hi = cat_amounts[category]
        amount = round(float(rng.uniform(lo, hi)), 2)
        rows.append({
            "order_id": f"ORD-{10000 + i}",
            "date": str(order_date),
            "customer_id": f"CUST-{rng.integers(1000, 5000)}",
            "product_category": category,
            "amount": amount,
            "payment_method": random.choice(payment_methods),
            "status": random.choice(statuses),
            "country": random.choice(countries),
        })

    return pd.DataFrame(rows)


def make_financial_metrics() -> pd.DataFrame:
    """36-row monthly P&L (Jan 2022 – Dec 2024)."""
    rng = np.random.default_rng(13)

    rows = []
    base_rev = 1_200_000
    growth_rate = 0.008  # ~10% annual

    for i in range(36):
        year = 2022 + i // 12
        month = i % 12 + 1
        month_label = f"{year}-{month:02d}"

        # Seasonal + trend revenue
        seasonal = 1.0 + 0.12 * np.sin(2 * np.pi * (month - 3) / 12)
        revenue = int(base_rev * (1 + growth_rate) ** i * seasonal * rng.uniform(0.97, 1.03))

        cogs_pct = rng.uniform(0.38, 0.45)
        cogs = int(revenue * cogs_pct)
        gross_profit = revenue - cogs

        opex = int(revenue * rng.uniform(0.28, 0.35))
        ebitda = gross_profit - opex
        net_income = int(ebitda * rng.uniform(0.72, 0.85))  # after tax/interest

        growth_pct = round(((revenue / (base_rev * (1 + growth_rate) ** max(i - 12, 0) * seasonal)) - 1) * 100, 1) if i >= 12 else None

        rows.append({
            "month": month_label,
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "opex": opex,
            "ebitda": ebitda,
            "net_income": net_income,
            "growth_pct": growth_pct,
        })

    return pd.DataFrame(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

DATASETS = [
    {
        "name": "sales_data",
        "description": "Monthly sales performance data (2022–2024): region, product, revenue, cost, profit, and sales rep.",
        "generator": make_sales_data,
    },
    {
        "name": "hr_employees",
        "description": "HR employee records: department, hire date, salary, performance scores, tenure, and attrition flag.",
        "generator": make_hr_employees,
    },
    {
        "name": "ecommerce_orders",
        "description": "E-commerce order history (2023–2024): order ID, customer, category, amount, payment method, status, and country.",
        "generator": make_ecommerce_orders,
    },
    {
        "name": "financial_metrics",
        "description": "Monthly P&L statement (Jan 2022–Dec 2024): revenue, COGS, gross profit, OpEx, EBITDA, net income, and YoY growth.",
        "generator": make_financial_metrics,
    },
]


def main():
    print("\n=== DataMind AI — Seed Datasets ===\n")

    # 1. Authenticate
    print("[1/5] Authenticating...")
    try:
        token = get_token()
    except Exception as e:
        print(f"  FAILED to authenticate: {e}")
        print(f"  Make sure the backend is running at {API_BASE}")
        sys.exit(1)

    # 2. Generate + upload datasets
    print(f"\n[2/5] Generating & uploading {len(DATASETS)} datasets...")
    sample_data_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    os.makedirs(sample_data_dir, exist_ok=True)

    results = []
    for ds in DATASETS:
        print(f"\n  >> {ds['name']}")
        df = ds["generator"]()
        print(f"     Generated: {len(df)} rows × {len(df.columns)} columns")

        # Save locally to sample_data/
        local_path = os.path.join(sample_data_dir, f"{ds['name']}.csv")
        df.to_csv(local_path, index=False)
        print(f"     Saved locally: {local_path}")

        # Upload to running backend
        result = upload_csv(token, ds["name"], ds["description"], df)
        results.append(result)

    # 3. Summary
    print("\n[3/5] Summary")
    successful = [r for r in results if r.get("id")]
    print(f"  {len(successful)}/{len(DATASETS)} datasets uploaded successfully\n")

    for ds, result in zip(DATASETS, results):
        status = "OK" if result.get("id") else "FAILED"
        print(f"  [{status}] {ds['name']}: {result.get('row_count', 'N/A')} rows, id={result.get('id', 'N/A')}")

    print("\nDone! Refresh the DataMind AI platform to see your datasets.\n")


if __name__ == "__main__":
    main()
