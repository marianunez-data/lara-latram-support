"""Chart-generation tool for LARA (bilingual labels, fixed chart catalog).

Same safety posture as analytics.py: the LLM chooses among FIXED, parameterized
chart kinds — it never writes plotting code. Charts render headlessly to PNG;
titles and axis labels are localized (en/es) via a translation table so the
artifact matches the language of the user's question.
"""

from __future__ import annotations

from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # headless-safe: render to files, never to a window
import matplotlib.pyplot as plt
from langchain_core.tools import tool

from .analytics import _load, _sales
from .config import BASE_DIR

CHARTS_DIR = BASE_DIR / "data" / "charts"
BRAND_COLOR = "#1a3c5e"
ACCENT_COLOR = "#e8873a"
PIE_PALETTE = ["#1a3c5e", "#2e6da4", "#e8873a", "#7fa8c9", "#c9d6e3"]

CHART_KINDS = (
    "monthly_sales",
    "sales_by_country",
    "sales_by_category",
    "top_products",
    "returns_by_reason",
    "payment_share",
    "delivery_days_hist",
)

L = {
    "en": {
        "monthly_sales": "Latram Shop — Monthly Revenue (USD)",
        "top_products": "Latram Shop — Top {n} Products by Revenue (USD)",
        "sales_by_country": "Latram Shop — Revenue by Country (USD)",
        "sales_by_category": "Latram Shop — Revenue by Category (USD)",
        "returns_by_reason": "Latram Shop — Return Requests by Reason",
        "payment_share": "Latram Shop — Orders by Payment Method",
        "delivery_days_hist": "Latram Shop — Delivery Time Distribution",
        "revenue": "Revenue (USD)",
        "requests": "Requests",
        "days": "Delivery days",
        "orders": "Orders",
    },
    "es": {
        "monthly_sales": "Latram Shop — Ventas mensuales (USD)",
        "top_products": "Latram Shop — Top {n} productos por ingresos (USD)",
        "sales_by_country": "Latram Shop — Ventas por país (USD)",
        "sales_by_category": "Latram Shop — Ventas por categoría (USD)",
        "returns_by_reason": "Latram Shop — Devoluciones por motivo",
        "payment_share": "Latram Shop — Pedidos por método de pago",
        "delivery_days_hist": "Latram Shop — Distribución de tiempos de entrega",
        "revenue": "Ingresos (USD)",
        "requests": "Solicitudes",
        "days": "Días de entrega",
        "orders": "Pedidos",
    },
}


VALUE_LABELS_ES = {
    # payment methods
    "credit_card": "Tarjeta de crédito",
    "debit_card": "Tarjeta de débito",
    "digital_wallet": "Billetera digital",
    "bank_transfer": "Transferencia",
    "cash_on_delivery": "Contra entrega",
    # return reasons
    "defective_product": "Producto defectuoso",
    "not_as_described": "No corresponde a la descripción",
    "changed_mind": "Arrepentimiento",
    "wrong_size_or_model": "Talla o modelo incorrecto",
    "arrived_damaged": "Llegó dañado",
    # categories
    "Electronics": "Electrónica",
    "Home": "Hogar",
    "Fashion": "Moda",
    "Sports": "Deportes",
    "Beauty": "Belleza",
    "Accessories": "Accesorios",
}


def _loc_values(labels, lang: str) -> list[str]:
    """Localize categorical DISPLAY labels; underlying data stays canonical."""
    if lang != "es":
        return list(labels)
    return [VALUE_LABELS_ES.get(x, x) for x in labels]


def _fig_path(kind: str) -> str:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(CHARTS_DIR / f"{kind}_{stamp}.png")


@tool
def generate_chart(
    kind: str, lang: str = "en", n: int = 10, start_date: str = "", end_date: str = ""
) -> str:
    """Render a chart from the orders dataset and save it as a PNG image.
    Use whenever the user asks for a chart/graph/plot/'gráfica'. `kind` must
    be one of: 'monthly_sales' (line), 'sales_by_country' (bar),
    'sales_by_category' (bar), 'top_products' (top-n horizontal bar, uses
    `n`), 'returns_by_reason' (bar), 'payment_share' (pie),
    'delivery_days_hist' (histogram). Set `lang` to 'es' if the user asked in
    Spanish, 'en' otherwise — chart titles and axis labels follow it.
    Optional ISO date filters (dataset spans 2025-07-01 to 2026-07-24).
    Returns the saved file path plus a short data summary — always tell the
    user the path so they can open the image.
    """
    if kind not in CHART_KINDS:
        return f"Invalid kind. Use one of: {', '.join(CHART_KINDS)}."
    t = L["es" if lang == "es" else "en"]
    df = _sales(_load(start_date, end_date))
    if df.empty:
        return "No orders in that period — nothing to chart."

    fig, ax = plt.subplots(figsize=(9, 5))

    if kind == "monthly_sales":
        series = df.groupby(df["order_date"].dt.to_period("M"))["total"].sum()
        series.index = series.index.astype(str)
        ax.plot(
            series.index, series.values, marker="o", color=BRAND_COLOR, linewidth=2.2
        )
        ax.fill_between(series.index, series.values, alpha=0.12, color=BRAND_COLOR)
        ax.set_title(t[kind])
        ax.set_ylabel(t["revenue"])
        plt.xticks(rotation=45, ha="right")
        summary = (
            f"peak {series.idxmax()} (${series.max():,.0f}), "
            f"low {series.idxmin()} (${series.min():,.0f})"
        )
    elif kind == "top_products":
        series = (
            df.groupby("product")["total"].sum().sort_values().tail(max(3, min(n, 15)))
        )
        ax.barh(series.index, series.values, color=BRAND_COLOR)
        ax.set_title(t[kind].format(n=len(series)))
        ax.set_xlabel(t["revenue"])
        summary = f"#1 is {series.index[-1]} (${series.iloc[-1]:,.0f})"
    elif kind == "returns_by_reason":
        ret = df[df["return_reason"].notna() & (df["return_reason"] != "")]
        if ret.empty:
            plt.close(fig)
            return "No return requests in that period — nothing to chart."
        series = ret["return_reason"].value_counts()
        series.index = _loc_values(series.index, lang)
        ax.bar(series.index, series.values, color=ACCENT_COLOR)
        ax.set_title(t[kind])
        ax.set_ylabel(t["requests"])
        plt.xticks(rotation=30, ha="right")
        summary = f"top reason: {series.index[0]} ({series.iloc[0]})"
    elif kind == "payment_share":
        series = df["payment_method"].value_counts()
        series.index = _loc_values(series.index, lang)
        ax.pie(
            series.values,
            labels=series.index,
            autopct="%1.0f%%",
            startangle=90,
            colors=PIE_PALETTE[: len(series)],
            wedgeprops={"edgecolor": "white", "linewidth": 1.5},
        )
        ax.set_title(t[kind])
        summary = (
            f"top method: {series.index[0]} "
            f"({series.iloc[0]/series.sum():.0%} of orders)"
        )
    elif kind == "delivery_days_hist":
        delivered = df[df["delivery_days"].notna() & (df["delivery_days"] != "")]
        values = delivered["delivery_days"].astype(int)
        ax.hist(
            values,
            bins=range(int(values.min()), int(values.max()) + 2),
            color=BRAND_COLOR,
            edgecolor="white",
        )
        ax.set_title(t[kind])
        ax.set_xlabel(t["days"])
        ax.set_ylabel(t["orders"])
        summary = (
            f"mean {values.mean():.1f} days, " f"median {values.median():.0f} days"
        )
    else:  # sales_by_country / sales_by_category
        dim = "country" if kind == "sales_by_country" else "category"
        series = df.groupby(dim)["total"].sum().sort_values(ascending=False)
        series.index = _loc_values(series.index, lang)
        ax.bar(series.index, series.values, color=BRAND_COLOR)
        ax.set_title(t[kind])
        ax.set_ylabel(t["revenue"])
        plt.xticks(rotation=30, ha="right")
        summary = f"#1 is {series.index[0]} (${series.iloc[0]:,.0f})"

    if kind != "payment_share":
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = _fig_path(kind)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return f"Chart saved to {path}. Summary: {summary}."
