"""MCP server: exposes LARA's tools over the Model Context Protocol.

Any MCP client (Claude Desktop, IDEs, other agents) can call these tools
directly. The compute stays here — only results enter the caller's context,
so data access, policies and auditability remain on our side.

Run:  python -m src.app.mcp_server        (stdio transport)

Claude Desktop config (claude_desktop_config.json):
    {"mcpServers": {"lara": {
        "command": "/ABSOLUTE/PATH/.venv/bin/python",
        "args": ["-m", "src.app.mcp_server"],
        "cwd": "/ABSOLUTE/PATH/Lara-agent"}}}
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .analytics import (late_return_requests, list_orders, order_lookup,
                        returns_report, sales_breakdown, sales_overview,
                        top_products)
from .charts import generate_chart
from .retrieval import search_policies
from .weekly_report import report_summary

mcp = FastMCP("lara-latram-support")


@mcp.tool()
def policy_search(query: str) -> str:
    """Search Latram Shop's internal policy documents (returns, shipping,
    warranty, payments, affiliates) and return relevant passages with their
    source document and section."""
    return search_policies.invoke({"query": query})


@mcp.tool()
def sales_summary(start_date: str = "", end_date: str = "") -> str:
    """Sales overview: revenue, orders, AOV, cancellations and returns for
    an optional ISO date range (YYYY-MM-DD)."""
    return sales_overview.invoke({"start_date": start_date,
                                  "end_date": end_date})


@mcp.tool()
def best_sellers(n: int = 5, by: str = "revenue") -> str:
    """Top N products ranked by 'revenue' or 'units'."""
    return top_products.invoke({"n": n, "by": by})


@mcp.tool()
def sales_by(dimension: str, start_date: str = "", end_date: str = "") -> str:
    """Sales broken down by a dimension: country, category, product,
    payment_method, shipping_zone or month."""
    return sales_breakdown.invoke({"dimension": dimension,
                                   "start_date": start_date,
                                   "end_date": end_date})


@mcp.tool()
def returns_summary(start_date: str = "", end_date: str = "") -> str:
    """Return requests by reason and status, with rates, for a date range."""
    return returns_report.invoke({"start_date": start_date,
                                  "end_date": end_date})


@mcp.tool()
def returns_outside_window(allowed_days: int) -> str:
    """Count return requests filed after the policy withdrawal window
    (allowed_days after delivery), with the average delay."""
    return late_return_requests.invoke({"allowed_days": allowed_days})


@mcp.tool()
def order_details(order_id: str) -> str:
    """Full record of a single order by its ID (e.g. LT-102500)."""
    return order_lookup.invoke({"order_id": order_id})


@mcp.tool()
def orders_by_status(status: str, country: str = "", limit: int = 20) -> str:
    """List orders by status (in_transit, cancelled, shipped, processing,
    delivered), optionally by country, with aging in days."""
    return list_orders.invoke({"status": status, "country": country,
                               "limit": limit})


@mcp.tool()
def weekly_report_figures(week_ending: str = "") -> str:
    """Weekly BI report figures with their formulas. Empty week_ending
    returns the latest closed week; an ISO date returns that week's report."""
    return report_summary.invoke({"week_ending": week_ending})


@mcp.tool()
def chart(kind: str, lang: str = "en", n: int = 10) -> str:
    """Generate a chart and return its file path. Certified kinds:
    monthly_sales, sales_by_country, top_products, payment_share,
    returns_by_reason, delivery_days_hist. lang: 'en' or 'es'."""
    return generate_chart.invoke({"kind": kind, "lang": lang, "n": n})


if __name__ == "__main__":
    mcp.run()
