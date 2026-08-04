"""Safe analytics tools over the Latram Shop orders dataset.

Security posture: the LLM can only *choose* among these fixed, parameterized
functions — it never executes generated code. The CSV is read on every call,
so data edits are reflected immediately without re-indexing anything.
"""

from __future__ import annotations

import time

import pandas as pd
from langchain_core.tools import tool

from .config import ORDERS_CACHE_TTL, ORDERS_SOURCE_URL, SALES_CSV

VALID_DIMENSIONS = ("month", "country", "category", "payment_method",
                    "shipping_zone")

# In-process cache so a burst of tool calls doesn't hammer the live source.
_CACHE: dict = {"df": None, "ts": 0.0}


def _read_source() -> pd.DataFrame:
    """Live Google Sheet first (if configured), local CSV as safety net."""
    if ORDERS_SOURCE_URL:
        now = time.time()
        if _CACHE["df"] is not None and now - _CACHE["ts"] < ORDERS_CACHE_TTL:
            return _CACHE["df"].copy()
        try:
            df = pd.read_csv(ORDERS_SOURCE_URL,
                             dtype={"delivery_days": "object"})
            if {"order_id", "order_date", "total"}.issubset(df.columns):
                _CACHE["df"], _CACHE["ts"] = df, now
                return df.copy()
        except Exception:
            pass  # unreachable/malformed live source -> graceful fallback
    return pd.read_csv(SALES_CSV, dtype={"delivery_days": "object"})


def _load(start_date: str = "", end_date: str = "") -> pd.DataFrame:
    df = _read_source()
    # Sheets exports currency-formatted cells as "$39.99" — sanitize money
    # columns so human formatting in the live source never breaks the math.
    for c in ("unit_price", "total"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(r"[$,]", "",
                                                            regex=True),
                              errors="coerce")
    df["order_date"] = pd.to_datetime(df["order_date"], format="mixed")
    if start_date:
        df = df[df["order_date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["order_date"] <= pd.to_datetime(end_date)]
    return df


def _sales(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["order_status"] != "cancelled"]


@tool
def sales_overview(start_date: str = "", end_date: str = "") -> str:
    """Overall business snapshot: total revenue (USD), number of orders,
    average order value, and orders by status. Optional ISO dates
    (YYYY-MM-DD) to filter the period; leave empty for all time.
    Dataset range: 2025-07-01 to 2026-07-19."""
    df = _load(start_date, end_date)
    if df.empty:
        return "No orders in that period."
    s = _sales(df)
    status = ", ".join(f"{k}: {v}" for k, v in
                       df["order_status"].value_counts().items())
    return (f"Period: {df.order_date.min().date()} to {df.order_date.max().date()}. "
            f"Revenue: ${s.total.sum():,.2f} USD across {len(s):,} non-cancelled "
            f"orders (AOV ${s.total.mean():,.2f}). Order status — {status}.")


@tool
def top_products(n: int = 5, by: str = "revenue",
                 start_date: str = "", end_date: str = "") -> str:
    """Ranking of best-selling products. `by` is 'revenue' (USD) or 'units'.
    Optional ISO date filters (dataset spans 2025-07-01 to 2026-07-19,
    so e.g. Q1-2026 is start_date=2026-01-01, end_date=2026-03-31). If the
    user does not specify a metric, default to revenue and say so."""
    df = _sales(_load(start_date, end_date))
    if df.empty:
        return "No orders in that period."
    col, label = (("total", "$") if by != "units" else ("quantity", "u"))
    top = df.groupby(["product", "category"])[col].sum().nlargest(n)
    lines = [f"{i}. {p} ({c}): {label}{v:,.0f}"
             for i, ((p, c), v) in enumerate(top.items(), 1)]
    return f"Top {n} products by {by}:\n" + "\n".join(lines)


@tool
def sales_breakdown(dimension: str, start_date: str = "",
                    end_date: str = "") -> str:
    """Revenue (USD) and order count grouped by one dimension:
    'month', 'country', 'category', 'payment_method' or 'shipping_zone'."""
    if dimension not in VALID_DIMENSIONS:
        return f"Invalid dimension. Use one of: {', '.join(VALID_DIMENSIONS)}."
    df = _sales(_load(start_date, end_date))
    if df.empty:
        return "No orders in that period."
    key = df["order_date"].dt.to_period("M").astype(str) if dimension == "month" \
        else df[dimension]
    g = df.groupby(key).agg(revenue=("total", "sum"), orders=("order_id", "count"))
    g = g if dimension == "month" else g.sort_values("revenue", ascending=False)
    lines = [f"{idx}: ${r.revenue:,.0f} ({r.orders:.0f} orders)"
             for idx, r in g.iterrows()]
    return f"Sales by {dimension}:\n" + "\n".join(lines)


@tool
def returns_report(start_date: str = "", end_date: str = "") -> str:
    """Returns/devoluciones analysis: number of return requests, return rate
    over delivered orders, top return reasons, and resolution status."""
    df = _load(start_date, end_date)
    delivered = df[df["order_status"] == "delivered"]
    ret = df[df["return_request_date"].notna() & (df["return_request_date"] != "")]
    if delivered.empty:
        return "No delivered orders in that period."
    reasons = ", ".join(f"{k} ({v})" for k, v in
                        ret["return_reason"].value_counts().head(5).items())
    status = ", ".join(f"{k}: {v}" for k, v in
                       ret["return_status"].value_counts().items())
    return (f"Return requests: {len(ret)} of {len(delivered)} delivered orders "
            f"({len(ret)/len(delivered):.1%}). Top reasons: {reasons}. "
            f"Resolution status — {status}.")


@tool
def late_return_requests(allowed_days: int) -> str:
    """Count return requests filed AFTER the allowed policy window, i.e. more
    than `allowed_days` days after delivery. IMPORTANT: do not guess the
    window — first use search_policies to find the number of days the policy
    allows (retracto/withdrawal window), then call this with that number."""
    df = _load()
    ret = df[(df["return_request_date"].notna()) &
             (df["return_request_date"] != "")].copy()
    ret["return_request_date"] = pd.to_datetime(ret["return_request_date"], format="mixed")
    ret["delivery_date"] = pd.to_datetime(ret["delivery_date"], format="mixed")
    ret["days_after"] = (ret["return_request_date"] - ret["delivery_date"]).dt.days
    late = ret[ret["days_after"] > allowed_days]
    return (f"Of {len(ret)} total return requests, {len(late)} "
            f"({len(late)/len(ret):.1%}) were filed more than {allowed_days} "
            f"days after delivery (outside the policy window). "
            f"Average delay among late requests: {late['days_after'].mean():.1f} days.")


@tool
def order_lookup(order_id: str) -> str:
    """Look up a single order by its ID (format LT-1xxxxx) and return all its
    details: dates, product, amounts, payment, shipping and return info."""
    df = _load()
    row = df[df["order_id"] == order_id.strip().upper()]
    if row.empty:
        return f"Order {order_id} not found."
    r = row.iloc[0]
    ret = (f" Return requested {r.return_request_date} "
           f"(reason: {r.return_reason}, status: {r.return_status})."
           if isinstance(r.return_request_date, str) and r.return_request_date
           else " No return request.")
    return (f"Order {r.order_id}: {r.quantity}x {r['product']} ({r.category}) — "
            f"${r.total} via {r.payment_method}"
            f"{f' in {r.installments} installments' if r.installments > 1 else ''}. "
            f"Placed {r.order_date.date()} from {r.country} ({r.shipping_zone}); "
            f"status: {r.order_status}"
            f"{f', delivered {r.delivery_date} ({r.delivery_days} days)' if r.order_status == 'delivered' else ''}."
            f"{ret}")


ANALYTICS_TOOLS = [sales_overview, top_products, sales_breakdown,
                   returns_report, late_return_requests, order_lookup]


@tool
def list_orders(status: str, country: str = "", limit: int = 20) -> str:
    """List orders filtered by order_status ('in_transit', 'cancelled',
    'shipped', 'processing', 'delivered'), optionally by country. Returns up
    to `limit` rows (max 50), newest first, with days elapsed since purchase
    (aging). USE THIS whenever the user asks for the IDs, the list, or a
    table of orders in a given status."""
    df = _load()
    sel = df[df.order_status == status.strip().lower()]
    if country:
        sel = sel[sel.country.str.lower() == country.strip().lower()]
    if sel.empty:
        return f"No orders found with status '{status}'" + (f" in {country}" if country else "") + "."
    sel = sel.sort_values("order_date", ascending=False).head(min(int(limit), 50))
    today = df.order_date.max()
    lines = [f"{len(sel)} of {int((df.order_status == status.strip().lower()).sum())} '{status}' orders (newest first):",
             "order_id | date | country | product | total | days_since_order"]
    for _, r in sel.iterrows():
        lines.append(f"{r.order_id} | {r.order_date:%Y-%m-%d} | {r.country} | "
                     f"{r['product']} | ${r.total:,.2f} | {(today - r.order_date).days}d")
    return "\n".join(lines)


ANALYTICS_TOOLS.append(list_orders)
