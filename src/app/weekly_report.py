"""
LARA — Weekly Ecommerce Report v3 (Latram Shop)
Interactive single-file HTML: executive layer on top, detail in tabs.
Charts are inline SVG (hover tooltips, no external libraries, ~50 KB total).
Integration: build(week_end=<last closed Sunday>); LARA sends it Monday 07:00.
"""

import base64

# ------------------------------ CONFIG ----------------------------------
import json as _json
import os as _os
import smtplib as _smtplib
import sys as _sys
from collections import Counter as _Counter
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd

from .analytics import _load as _agent_load
from .config import AGENT_NAME, BASE_DIR, BRAND_NAME, QUESTIONS_LOG

LOGO_PNG = str(BASE_DIR / "assets" / "logo_latram.png")
OUT_HTML = str(BASE_DIR / "data" / "reports" / "weekly_report.html")
WEEK_END = None  # resolved after load() is defined (last closed Sunday)
N_TREND_WEEKS = 4

TH_CANCEL_PCT, TH_RETURN_PCT = 8.0, 10.0
TH_TRANSIT_DAYS, TH_PROC_DAYS = 10, 2
TARGETS = {}  # optional weekly targets per KPI, e.g. {"gmv": 4500}

# Return-reason buckets (explicit and editable; shown in the Methodology tab)
RETURN_BUCKETS = {
    "Product / listing quality": ["not_as_described", "defective_product"],
    "Shipping damage": ["arrived_damaged"],
    "Customer choice": ["changed_mind", "wrong_size_or_model"],
}
CUSTOMER_BUCKET = "Customer choice"  # everything else counts as company-controllable

NAVY, DEEP, SLATE, MIST, LINE = "#1a3c5e", "#12293f", "#5b6b7a", "#eef2f6", "#e2e8f0"
GREEN, RED, WARN, PREVBAR = "#2e7d32", "#c62828", "#e8873a", "#c3ced8"
PALETTE = ["#1a3c5e", "#35618f", "#5d87b2", "#8fafcc", "#e8873a", "#8a97a5", "#5b8a72"]


# ------------------------------ DATA ------------------------------------
def load():
    """Orders via the agent's loader: live Google Sheet first, local fallback."""
    df = _agent_load()  # order_date already datetime
    df["delivery_days"] = pd.to_numeric(df["delivery_days"], errors="coerce")
    for c in ("delivery_date", "return_request_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce", format="mixed")
    return df


def _last_closed_sunday() -> pd.Timestamp:
    mx = load()["order_date"].max().normalize()
    return mx - pd.Timedelta(days=(mx.weekday() + 1) % 7)


WEEK_END = _last_closed_sunday()


def week_metrics(df, end):
    start = end - pd.Timedelta(days=6)
    w = df[(df.order_date >= start) & (df.order_date <= end)]
    nc = w[w.order_status != "cancelled"]
    filed = df[(df.return_request_date >= start) & (df.return_request_date <= end)]
    dlv = w[w.order_status == "delivered"]
    gmv, orders = nc.total.sum(), len(nc)
    return dict(
        start=start,
        end=end,
        w=w,
        nc=nc,
        filed=filed,
        gmv=gmv,
        orders=orders,
        aov=gmv / orders if orders else 0,
        placed=len(w),
        cancelled=int((w.order_status == "cancelled").sum()),
        cancel_rate=(w.order_status == "cancelled").mean() * 100 if len(w) else 0,
        return_rate=len(filed) / orders * 100 if orders else 0,
        filed_n=len(filed),
        delivery=dlv.delivery_days.mean() if len(dlv) else float("nan"),
        units=int(nc.quantity.sum()),
        installments_pct=(nc.installments > 1).mean() * 100 if orders else 0,
    )


def pct(a, b):
    return (a - b) / b * 100 if b else 0.0


def money(v):
    return f"${v:,.0f}"


def delta_span(d, invert=False, label="vs prev. week", size=12, tip=""):
    t = f" title='{tip}'" if tip else ""
    if d != d or abs(d) < 0.05:
        return f"<span class='d0' style='font-size:{size}px'{t}>= {label}</span>"
    up = d > 0
    good = (up and not invert) or (not up and invert)
    cls = "dg" if good else "dr"
    return (
        f"<span class='{cls}' style='font-size:{size}px'{t}>"
        f"{'▲' if up else '▼'} {abs(d):.1f}% {label}</span>"
    )


def delta_calc(cv, bv, invert=False, label="vs prev. week", fmt=money, size=12):
    """Delta with a hover tooltip showing the exact formula and inputs."""
    tip = f"({fmt(cv)} − {fmt(bv)}) ÷ {fmt(bv)} = {pct(cv, bv):+.1f}%"
    return delta_span(pct(cv, bv), invert, label, size, tip)


# ------------------------------ SVG CHARTS ------------------------------
def spark(vals, w=120, h=30):
    vmin, vmax = min(vals), max(vals)
    rng = (vmax - vmin) or 1
    pts = [
        (i * (w - 8) / (len(vals) - 1) + 4, h - 5 - (v - vmin) / rng * (h - 12))
        for i, v in enumerate(vals)
    ]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    cx, cy = pts[-1]
    return (
        f"<svg width='{w}' height='{h}' aria-hidden='true'>"
        f"<polyline points='{poly}' fill='none' stroke='{NAVY}' stroke-width='1.6' opacity='.55'/>"
        f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='3' fill='{NAVY}'/></svg>"
    )


def vbars_grouped(labels, prev, cur, w=780, h=210, fmt=money):
    top = max(max(prev), max(cur)) or 1
    n = len(labels)
    slot = (w - 40) / n
    bw = slot * 0.32
    bars = ""
    for i, lb in enumerate(labels):
        x0 = 30 + i * slot + slot * 0.16
        for j, (v, col, tag) in enumerate(
            [(prev[i], PREVBAR, "previous week"), (cur[i], NAVY, "this week")]
        ):
            bh = v / top * (h - 55)
            bars += (
                f"<rect x='{x0 + j*bw:.1f}' y='{h-30-bh:.1f}' width='{bw:.1f}' height='{bh:.1f}' "
                f"rx='2' fill='{col}'><title>{lb} · {tag}: {fmt(v)}</title></rect>"
            )
        bars += (
            f"<text x='{30 + i*slot + slot/2:.1f}' y='{h-12}' text-anchor='middle' "
            f"class='ax'>{lb}</text>"
        )
    legend = (
        f"<rect x='30' y='6' width='10' height='10' rx='2' fill='{PREVBAR}'/>"
        f"<text x='45' y='15' class='ax'>Previous week</text>"
        f"<rect x='140' y='6' width='10' height='10' rx='2' fill='{NAVY}'/>"
        f"<text x='155' y='15' class='ax'>This week</text>"
    )
    return f"<svg viewBox='0 0 {w} {h}' class='chart'>{legend}{bars}</svg>"


def donut(items, total, fmt=money, center_label="GMV"):
    """items: [(name, value)] desc. Donut via stroked circles + native tooltips."""
    segs, legend, cum = "", "", 0.0
    for i, (name, v) in enumerate(items):
        share = v / total * 100
        col = PALETTE[i % len(PALETTE)]
        segs += (
            f"<circle class='seg' cx='85' cy='85' r='58' fill='none' stroke='{col}' "
            f"stroke-width='30' pathLength='100' stroke-dasharray='{share:.3f} {100-share:.3f}' "
            f"stroke-dashoffset='{25 - cum:.3f}'>"
            f"<title>{name}: {fmt(v)} · {share:.0f}%</title></circle>"
        )
        legend += (
            f"<div class='lg'><span class='dot' style='background:{col}'></span>"
            f"{name}<span class='lg-v'>{fmt(v)} · {share:.0f}%</span></div>"
        )
        cum += share
    svg = (
        f"<svg viewBox='0 0 170 170' width='170' height='170'>{segs}"
        f"<text x='85' y='81' text-anchor='middle' style='font-size:17px;font-weight:700;"
        f"fill:{NAVY}'>{fmt(total)}</text>"
        f"<text x='85' y='97' text-anchor='middle' class='ax'>{center_label}</text></svg>"
    )
    return f"<div class='donut'>{svg}<div class='legend'>{legend}</div></div>"


def stacked_bar(items, total, unit="orders"):
    """items: [(name, count)] desc. One 100%-stacked bar + legend, native tooltips."""
    x, segs, legend = 0.0, "", ""
    for i, (name, n) in enumerate(items):
        share = n / total * 100
        col = PALETTE[i % len(PALETTE)]
        segs += (
            f"<rect class='seg' x='{x:.2f}' y='0' width='{share:.2f}' height='30' fill='{col}'>"
            f"<title>{name}: {n} {unit} · {share:.0f}%</title></rect>"
        )
        legend += (
            f"<div class='lg'><span class='dot' style='background:{col}'></span>"
            f"{name}<span class='lg-v'>{n} · {share:.0f}%</span></div>"
        )
        x += share
    svg = (
        f"<svg viewBox='0 0 100 30' preserveAspectRatio='none' "
        f"style='width:100%;height:30px;border-radius:6px;overflow:hidden'>{segs}</svg>"
    )
    return f"{svg}<div class='legend row'>{legend}</div>"


def details_table(label, tbl):
    return f"<details class='dt'><summary>{label}</summary>{tbl}</details>"


def hbars(items, w=780, color=NAVY, fmt=money, total=None):
    rh, gap, lab_w = 26, 8, 210
    h = len(items) * (rh + gap) + 6
    top = max(v for _, v in items) or 1
    out = ""
    for i, (name, v) in enumerate(items):
        y = i * (rh + gap) + 3
        bw = max(6, (v / top) * (w - lab_w - 120))
        share = f" · {v/total*100:.0f}%" if total else ""
        out += (
            f"<text x='{lab_w-10}' y='{y+rh*0.68:.0f}' text-anchor='end' class='lbl'>{name}</text>"
            f"<rect x='{lab_w}' y='{y}' width='{bw:.1f}' height='{rh}' rx='4' fill='{color}'>"
            f"<title>{name}: {fmt(v)}{share}</title></rect>"
            f"<text x='{lab_w+bw+8:.1f}' y='{y+rh*0.68:.0f}' class='val'>{fmt(v)}{share}</text>"
        )
    return f"<svg viewBox='0 0 {w} {h}' class='chart'>{out}</svg>"


# ------------------------------ HTML PARTS ------------------------------
def img64(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def table(headers, rows, foot=None):
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    f = (
        f"<tr class='tfoot'>{''.join(f'<td>{c}</td>' for c in foot)}</tr>"
        if foot
        else ""
    )
    return f"<table class='tb'><thead><tr>{h}</tr></thead><tbody>{b}{f}</tbody></table>"


def kpi(tab, label, formula, value, wow, avg4, sparkline):
    return (
        f"<button class='kpi' data-tab='{tab}' type='button'>"
        f"<span class='k-l'>{label}</span><span class='k-f'>{formula}</span>"
        f"<span class='k-v'>{value}</span>"
        f"<span class='k-d'>{wow}<br>{avg4}</span>{sparkline}</button>"
    )


CSS = """
*{box-sizing:border-box;margin:0}
body{background:#eef2f6;font-family:'Segoe UI',-apple-system,Roboto,Helvetica,Arial,sans-serif;
     color:#28323c;padding:26px 12px}
.wrap{max-width:880px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;
      box-shadow:0 2px 14px rgba(18,41,63,.08)}
.head{display:flex;align-items:center;justify-content:space-between;gap:16px;
      padding:22px 30px 16px;border-bottom:4px solid #1a3c5e;flex-wrap:wrap}
.head img{width:250px;max-width:60vw}
.meta{text-align:right}
.meta .t{font-size:17px;font-weight:700;color:#1a3c5e}
.meta .s{font-size:12px;color:#5b6b7a;margin-top:2px}
.pad{padding:20px 30px 28px}
.eyebrow{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#8a97a5;
         font-weight:600;margin:0 0 8px}
.summary{background:#f2f6fa;border-left:4px solid #1a3c5e;border-radius:8px;
         padding:12px 16px;font-size:13.5px;line-height:1.55}
.summary b{color:#1a3c5e}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 2px}
.chip{font-size:12px;padding:5px 11px;border-radius:20px;border:1px solid;cursor:default}
.chip.warn{color:#a33d10;border-color:#f0c4a6;background:#fff6ee}
.chip.ok{color:#2e7d32;border-color:#bcd9be;background:#f2f8f2}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0 6px}
.kpi{background:#f7f9fb;border:1px solid #e2e8f0;border-radius:12px;padding:13px 14px 10px;
     text-align:left;cursor:pointer;font-family:inherit;transition:box-shadow .15s,transform .15s}
.kpi:hover{box-shadow:0 3px 10px rgba(18,41,63,.12);transform:translateY(-1px)}
.k-l{display:block;font-size:11px;color:#5b6b7a}
.k-f{display:block;font-size:9.5px;color:#8a97a5;min-height:12px}
.k-v{display:block;font-size:27px;font-weight:750;color:#1a3c5e;
     font-variant-numeric:tabular-nums;margin:2px 0}
.k-d{display:block;line-height:1.5;margin-bottom:4px}
.dg{color:#2e7d32}.dr{color:#c62828}.d0{color:#8a97a5}
.stat{font-size:12px;color:#5b6b7a;text-align:center;margin:4px 0 16px}
.tabs{display:flex;gap:4px;border-bottom:2px solid #e2e8f0;flex-wrap:wrap}
.tabs button{border:0;background:none;font-family:inherit;font-size:13px;padding:9px 14px;
             color:#5b6b7a;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px}
.tabs button[aria-selected="true"]{color:#1a3c5e;font-weight:700;border-color:#1a3c5e}
.panel{display:none;padding:18px 2px 4px;animation:fade .25s}
.panel.on{display:block}
@keyframes fade{from{opacity:0}to{opacity:1}}
h3{color:#1a3c5e;font-size:14.5px;margin:16px 0 10px}
.chart{width:100%;height:auto}
.ax{font-size:11px;fill:#5b6b7a}
.lbl{font-size:12px;fill:#28323c}
.val{font-size:11.5px;fill:#5b6b7a;font-variant-numeric:tabular-nums}
.tb{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}
.tb th{background:#1a3c5e;color:#fff;text-align:left;padding:7px 12px;font-size:12px}
.tb td{padding:7px 12px;border-bottom:1px solid #eef2f6}
.tb tbody tr:nth-child(odd){background:#f7f9fb}
.tb .tfoot td{font-weight:700;background:#fff}
.note{font-size:13px;line-height:1.55;margin:6px 0}
.callout{background:#fff6ee;border-left:4px solid #e8873a;border-radius:8px;
         padding:10px 14px;font-size:13px;margin:10px 0}
.qs li{font-size:13.5px;margin:6px 0}
code{background:#eef2f6;border-radius:4px;padding:1px 5px;font-size:11.5px;color:#1a3c5e}
.donut{display:flex;align-items:center;gap:24px;flex-wrap:wrap;margin:6px 0 2px}
.legend{display:flex;flex-direction:column;gap:5px;min-width:230px;flex:1}
.legend.row{flex-direction:row;flex-wrap:wrap;gap:6px 18px;margin-top:10px}
.lg{display:flex;align-items:center;gap:8px;font-size:12.5px;color:#28323c}
.lg-v{margin-left:auto;color:#5b6b7a;font-variant-numeric:tabular-nums;padding-left:10px}
.legend.row .lg-v{margin-left:6px}
.dot{width:10px;height:10px;border-radius:3px;flex:0 0 auto}
.seg:hover{opacity:.82;cursor:default}
.dt{margin:8px 0 4px}
.dt summary{font-size:12px;color:#35618f;cursor:pointer;user-select:none}
.dt[open] summary{margin-bottom:6px}
.foot{background:#f4f7fa;padding:12px 30px;font-size:11px;color:#8a97a5}
@media (max-width:640px){.grid{grid-template-columns:repeat(2,1fr)}.head{justify-content:center}
                         .meta{text-align:center}}
@media print{.panel{display:block!important}.tabs{display:none}}
"""

JS = """
const tabs=[...document.querySelectorAll('.tabs button')];
const panels=[...document.querySelectorAll('.panel')];
function show(id){
  tabs.forEach(b=>b.setAttribute('aria-selected',b.dataset.tab===id));
  panels.forEach(p=>p.classList.toggle('on',p.id===id));
}
tabs.forEach(b=>b.addEventListener('click',()=>show(b.dataset.tab)));
document.querySelectorAll('.kpi').forEach(k=>k.addEventListener('click',()=>{
  show(k.dataset.tab);
  document.querySelector('.tabs').scrollIntoView({behavior:'smooth',block:'start'});
}));
show('sales');
"""


# ------------------------------ BUILD -----------------------------------
def build(week_end=WEEK_END):
    df = load()
    cur = week_metrics(df, week_end)
    prev = week_metrics(df, week_end - pd.Timedelta(days=7))
    hist = [
        week_metrics(df, week_end - pd.Timedelta(days=7 * i))
        for i in range(1, N_TREND_WEEKS + 1)
    ]
    avg = {
        k: sum(h[k] for h in hist) / len(hist)
        for k in ("gmv", "orders", "aov", "cancel_rate", "return_rate", "delivery")
    }
    series = {
        k: [h[k] for h in reversed(hist)] + [cur[k]]
        for k in ("gmv", "orders", "aov", "cancel_rate", "return_rate", "delivery")
    }

    # streak of consecutive WoW GMV declines ending this week
    g = series["gmv"]
    streak = 0
    for a, b in zip(g[-2::-1], g[::-1]):
        if b < a:
            streak += 1
        else:
            break

    # cancellations / returns / backlog detail
    canc = cur["w"][cur["w"].order_status == "cancelled"]
    canc_cty = (
        canc.groupby("country")
        .agg(n=("order_id", "count"), val=("total", "sum"))
        .sort_values("n", ascending=False)
    )
    concentrated = (
        len(canc_cty) and canc_cty.n.iloc[0] / max(cur["cancelled"], 1) >= 0.5
    )
    filed = cur["filed"]
    reasons = filed.return_reason.value_counts()
    bucket_of = {r: b for b, rs in RETURN_BUCKETS.items() for r in rs}
    buckets = filed.return_reason.map(
        lambda r: bucket_of.get(r, "Other")
    ).value_counts()
    controllable = int(sum(n for b, n in buckets.items() if b != CUSTOMER_BUCKET))
    bucket_line = " · ".join(f"{b}: {n}" for b, n in buckets.items())
    risk_val = filed.total.sum()
    status_line = (
        " · ".join(
            f"{n} {s.replace('_',' ')}"
            for s, n in filed.return_status.value_counts().items()
        )
        or "—"
    )
    top5 = cur["nc"].groupby("product").total.sum().sort_values(ascending=False).head(5)
    repeat = [
        p
        for p, n in filed["product"].value_counts().items()
        if n >= 2 and p in top5.index
    ]

    open_o = df[
        df.order_status.isin(["shipped", "in_transit"]) & (df.order_date <= week_end)
    ]
    aged = open_o[(week_end - open_o.order_date).dt.days > TH_TRANSIT_DAYS]
    oldest = int((week_end - open_o.order_date.min()).days) if len(open_o) else 0
    proc = df[(df.order_status == "processing") & (df.order_date <= week_end)]
    proc_aged = proc[(week_end - proc.order_date).dt.days > TH_PROC_DAYS]

    # chips: alerts fired + all-clear markers
    chips = []
    if cur["cancel_rate"] > TH_CANCEL_PCT:
        chips.append(
            (
                "warn",
                f"⚠ Cancellations {cur['cancel_rate']:.1f}% &gt; {TH_CANCEL_PCT:.0f}%",
            )
        )
    else:
        chips.append(
            ("ok", f"Cancellations {cur['cancel_rate']:.1f}% within threshold")
        )
    if cur["return_rate"] > TH_RETURN_PCT:
        chips.append(
            (
                "warn",
                f"⚠ Returns {cur['return_rate']:.1f}% &gt; {TH_RETURN_PCT:.0f}% "
                f"({controllable} of {cur['filed_n']} company-controllable)",
            )
        )
    else:
        chips.append(("ok", f"Returns {cur['return_rate']:.1f}% within threshold"))
    if len(aged):
        chips.append(
            (
                "warn",
                f"⚠ {len(aged)} orders in transit &gt; {TH_TRANSIT_DAYS} days (oldest {oldest}d)",
            )
        )
    if len(proc_aged):
        chips.append(
            ("warn", f"⚠ {len(proc_aged)} in processing &gt; {TH_PROC_DAYS} days")
        )

    # executive summary (rule-based, max 3 lines)
    wow_g = pct(cur["gmv"], prev["gmv"])
    s1 = (
        "<b>Revenue</b> — " + f"{money(cur['gmv'])}, {'up' if wow_g>0 else 'down'} "
        f"{abs(wow_g):.1f}% vs previous week"
        + (
            f", {streak}th consecutive weekly decline"
            if streak >= 2
            else (
                f", first increase after {prev_streak_text(g)}"
                if wow_g > 0 and g[-3] > g[-2]
                else ""
            )
        )
        + f" ({delta_word(pct(cur['gmv'], avg['gmv']))} vs the 4-week average)."
    )
    s2 = (
        "<b>Cancellations</b> — " + f"{cur['cancel_rate']:.1f}% ({cur['cancelled']} of "
        f"{cur['placed']} orders placed, {money(canc.total.sum())})"
        + (
            f", {int(canc_cty.n.iloc[0])} from {canc_cty.index[0]}."
            if concentrated
            else ", no country or payment concentration."
        )
    )
    s3 = (
        "<b>Returns</b> — "
        + f"{cur['filed_n']} requests filed ({cur['return_rate']:.1f}% of orders), "
        f"{controllable} of {cur['filed_n']} company-controllable ({bucket_line})"
        + (f"; {repeat[0]} is a top-5 seller with repeat cases." if repeat else ".")
    )
    summary = "".join(f"<div>{s}</div>" for s in [s1, s2, s3])

    # KPI cards — each shows its formula; hover a delta to see the exact math
    fm_int = lambda v: f"{v:,.1f}".rstrip("0").rstrip(".")
    fm_pct = lambda v: f"{v:.1f}%"
    fm_day = lambda v: f"{v:.1f} d"
    cards = "".join(
        [
            kpi(
                "sales",
                "Revenue (GMV)",
                "Σ order total, week's non-cancelled orders",
                money(cur["gmv"]),
                delta_calc(cur["gmv"], prev["gmv"]),
                delta_calc(cur["gmv"], avg["gmv"], label="vs 4-wk avg", size=11),
                spark(series["gmv"]),
            ),
            kpi(
                "sales",
                "Orders",
                "count of non-cancelled orders placed",
                cur["orders"],
                delta_calc(cur["orders"], prev["orders"], fmt=fm_int),
                delta_calc(
                    cur["orders"],
                    avg["orders"],
                    fmt=fm_int,
                    label="vs 4-wk avg",
                    size=11,
                ),
                spark(series["orders"]),
            ),
            kpi(
                "products",
                "Avg. order value",
                "revenue ÷ orders",
                f"${cur['aov']:,.0f}",
                delta_calc(cur["aov"], prev["aov"]),
                delta_calc(cur["aov"], avg["aov"], label="vs 4-wk avg", size=11),
                spark(series["aov"]),
            ),
            kpi(
                "risk",
                "Return rate",
                "requests filed this week ÷ orders",
                f"{cur['return_rate']:.1f}%",
                delta_calc(
                    cur["return_rate"], prev["return_rate"], invert=True, fmt=fm_pct
                ),
                delta_calc(
                    cur["return_rate"],
                    avg["return_rate"],
                    invert=True,
                    fmt=fm_pct,
                    label="vs 4-wk avg",
                    size=11,
                ),
                spark(series["return_rate"]),
            ),
            kpi(
                "risk",
                "Cancellation rate",
                "cancelled ÷ all orders placed",
                f"{cur['cancel_rate']:.1f}%",
                delta_calc(
                    cur["cancel_rate"], prev["cancel_rate"], invert=True, fmt=fm_pct
                ),
                delta_calc(
                    cur["cancel_rate"],
                    avg["cancel_rate"],
                    invert=True,
                    fmt=fm_pct,
                    label="vs 4-wk avg",
                    size=11,
                ),
                spark(series["cancel_rate"]),
            ),
            kpi(
                "ops",
                "Avg. delivery time",
                "avg days to deliver, delivered orders",
                f"{cur['delivery']:.1f} d",
                delta_calc(cur["delivery"], prev["delivery"], invert=True, fmt=fm_day),
                delta_calc(
                    cur["delivery"],
                    avg["delivery"],
                    invert=True,
                    fmt=fm_day,
                    label="vs 4-wk avg",
                    size=11,
                ),
                spark(series["delivery"]),
            ),
        ]
    )

    # ---- tab: sales ----
    days = pd.date_range(cur["start"], cur["end"])
    cd = cur["nc"].groupby(cur["nc"].order_date.dt.date).total.sum()
    pdaily = prev["nc"].groupby(prev["nc"].order_date.dt.date).total.sum()
    daily_svg = vbars_grouped(
        [d.strftime("%a %d") for d in days],
        [pdaily.get((d - pd.Timedelta(days=7)).date(), 0) for d in days],
        [cd.get(d.date(), 0) for d in days],
    )
    cats = cur["nc"].groupby("category").total.sum().sort_values(ascending=False)
    cty = cur["nc"].groupby("country").total.sum().sort_values(ascending=False)
    pm = cur["nc"].payment_method.value_counts()
    tab_sales = (
        f"<h3>Daily sales (USD) — vs previous week</h3>{daily_svg}"
        f"<h3>Revenue by category</h3>{hbars(list(cats.items()), total=cur['gmv'])}"
        f"<h3>Sales by country</h3>"
        + donut(list(cty.items()), cur["gmv"])
        + details_table(
            "View table (verification)",
            table(
                ["Country", "Revenue", "Share"],
                [[c, money(v), f"{v/cur['gmv']*100:.0f}%"] for c, v in cty.items()],
                foot=["Total", money(cur["gmv"]), "100%"],
            ),
        )
        + "<h3>Payment methods</h3>"
        + stacked_bar(
            [(m.replace("_", " ").capitalize(), int(n)) for m, n in pm.items()],
            cur["orders"],
        )
        + details_table(
            "View table (verification)",
            table(
                ["Method", "Orders", "Share"],
                [
                    [
                        m.replace("_", " ").capitalize(),
                        int(n),
                        f"{n/cur['orders']*100:.0f}%",
                    ]
                    for m, n in pm.items()
                ],
                foot=["Total", cur["orders"], "100%"],
            ),
        )
    )

    # ---- tab: products ----
    tab_products = (
        f"<h3>Top 5 products of the week (USD)</h3>{hbars(list(top5.items()), color=WARN)}"
        f"<p class='note'>{cur['units']} units sold · {cur['units']/cur['orders']:.2f} units per order · "
        f"{cur['installments_pct']:.0f}% of orders paid in installments.</p>"
    )

    # ---- tab: risk ----
    canc_tbl = (
        table(
            ["Country", "Cancelled", "Value"],
            [[c, int(r.n), money(r.val)] for c, r in canc_cty.iterrows()],
            foot=["Total", cur["cancelled"], money(canc.total.sum())],
        )
        if len(canc_cty)
        else "<p class='note'>No cancellations this week.</p>"
    )
    reasons_str = (
        " · ".join(
            f"{r.replace('_',' ').capitalize()} ({n})" for r, n in reasons.items()
        )
        or "—"
    )
    repeat_html = (
        (
            f"<div class='callout'>⚠ <b>{repeat[0]}</b> is a top-5 seller and appears "
            f"{int(filed['product'].value_counts()[repeat[0]])} times among return requests. "
            f"Recommended: quality / listing-accuracy check.</div>"
        )
        if repeat
        else ""
    )
    tab_risk = (
        f"<h3>Cancellations</h3>"
        f"<p class='note'>{cur['cancelled']} of {cur['placed']} orders placed ({cur['cancel_rate']:.1f}%), "
        f"{money(canc.total.sum())} lost"
        + (
            f", concentrated in {canc_cty.index[0]}."
            if concentrated
            else ", no concentration by country or payment method."
        )
        + f"</p>{canc_tbl}"
        f"<h3>Returns</h3>"
        f"<p class='note'><b>{cur['filed_n']} return requests filed this week</b> "
        f"({cur['return_rate']:.1f}% of orders) · {money(risk_val)} at risk · Status: {status_line}.</p>"
        f"<p class='note'><b>Reasons:</b> {reasons_str}.</p>"
        f"<p class='note'><b>By bucket:</b> {bucket_line} → <b>{controllable} of "
        f"{cur['filed_n']} company-controllable</b> (everything except {CUSTOMER_BUCKET.lower()}; "
        f"mapping in the Methodology tab).</p>{repeat_html}"
    )

    # ---- tab: ops ----
    tab_ops = (
        f"<h3>Delivery</h3>"
        f"<p class='note'>Average delivery time {cur['delivery']:.1f} days "
        f"(delivered orders placed this week; recent orders still in transit are excluded).</p>"
        f"<h3>Fulfillment backlog at cutoff</h3>"
        f"<p class='note'>{len(open_o)} orders shipped or in transit not yet delivered · "
        f"{len(aged)} older than {TH_TRANSIT_DAYS} days · oldest: {oldest} days · "
        f"{len(proc)} in processing ({len(proc_aged)} beyond {TH_PROC_DAYS} days).</p>"
    )

    # ---- tab: team (fed by LARA conversation logs in production) ----
    _topics_map = {
        "search_policies": "Internal policies",
        "late_return_requests": "Returns",
        "returns_report": "Returns",
        "top_products": "Sales & products",
        "sales_breakdown": "Sales & products",
        "sales_overview": "Sales & products",
        "order_lookup": "Order lookup",
        "generate_chart": "Reports & charts",
    }
    _rows = (
        [_json.loads(l) for l in open(QUESTIONS_LOG, encoding="utf-8")]
        if QUESTIONS_LOG.exists()
        else []
    )
    # Unify surfaces: also pull last-7-days interactions from LangSmith, so
    # questions asked on the deployed Space (ephemeral disk) still feed the
    # training-needs insight. Fails silently — the report never breaks.
    try:
        import os as _o
        import re as _re

        if _o.getenv("LANGSMITH_API_KEY"):
            from datetime import datetime as _dt
            from datetime import timedelta as _td
            from datetime import timezone as _tz

            from langsmith import Client as _LSC

            _c = _LSC()
            _win = int(_o.getenv("TEAM_INSIGHTS_DAYS", "30"))
            _since = _dt.now(_tz.utc) - _td(days=_win)
            _proj = _o.getenv("LANGSMITH_PROJECT", "latram-support-agent")
            _tbt: dict = {}
            for _r in _c.list_runs(
                project_name=_proj, run_type="tool", start_time=_since
            ):
                _tbt.setdefault(str(_r.trace_id), []).append(_r.name)
            for _r in _c.list_runs(project_name=_proj, is_root=True, start_time=_since):
                _m = _re.search(
                    r"content['\"]:\s*['\"](.+?)(?:\\n\\n\[System note|['\"])",
                    str(_r.inputs),
                )
                if _m:
                    _rows.append(
                        {
                            "question": _m.group(1)[:160],
                            "tools": _tbt.get(str(_r.trace_id), []),
                        }
                    )
    except Exception:
        pass
    if _rows:
        _top5 = [q for q, _ in _Counter(r["question"] for r in _rows).most_common(5)]
        _tt = _Counter(
            _topics_map.get(t, "Other") for r in _rows for t in r.get("tools", [])
        )
        _tip = ""
        if _tt:
            _tname, _tn = _tt.most_common(1)[0]
            _tip = (
                f"<div class='callout'>{_tn/sum(_tt.values()):.0%} of questions focus on "
                f"<b>{_tname}</b> — suggested topic for the next internal training.</div>"
            )
        tab_team = (
            "<h3>Most frequent team questions</h3><ol class='qs'>"
            + "".join(f"<li>{q}</li>" for q in _top5)
            + "</ol>"
            + _tip
            + f"<p class='note'>Source: {len(_rows)} logged interactions with "
            f"{AGENT_NAME} (local log + LangSmith, rolling window).</p>"
        )
    else:
        tab_team = (
            "<h3>Most frequent team questions</h3>"
            "<p class='note'>No interactions logged in the current window. Questions asked through the CLI, the API or the deployed app feed this section automatically.</p>"
        )

    # ---- tab: methodology (every figure reproducible from the source file) ----
    ws, we = cur["start"].strftime("%d %b"), cur["end"].strftime("%d %b")
    wk4 = ", ".join(money(h["gmv"]) for h in reversed(hist))
    method_rows = [
        [
            "Revenue (GMV)",
            "SUM(<code>total</code>) where <code>order_status</code> ≠ cancelled and "
            f"<code>order_date</code> in {ws}–{we}",
            f"= {money(cur['gmv'])}",
        ],
        [
            "Orders",
            "COUNT of the same rows (non-cancelled orders placed in the week)",
            f"= {cur['orders']}",
        ],
        [
            "Avg. order value",
            "Revenue ÷ Orders",
            f"{money(cur['gmv'])} ÷ {cur['orders']} = ${cur['aov']:,.2f}",
        ],
        [
            "Cancellation rate",
            "COUNT(<code>order_status</code> = cancelled) ÷ all orders placed in the week",
            f"{cur['cancelled']} ÷ {cur['placed']} = {cur['cancel_rate']:.1f}%",
        ],
        [
            "Return rate",
            f"COUNT(<code>return_request_date</code> in {ws}–{we}, any order) ÷ Orders",
            f"{cur['filed_n']} ÷ {cur['orders']} = {cur['return_rate']:.1f}%",
        ],
        [
            "Avg. delivery time",
            "AVG(<code>delivery_days</code>) of week's orders with <code>order_status</code> = delivered",
            f"= {cur['delivery']:.1f} d",
        ],
        [
            "vs prev. week",
            "(this week − previous week) ÷ previous week",
            f"e.g. revenue: ({money(cur['gmv'])} − {money(prev['gmv'])}) ÷ {money(prev['gmv'])} "
            f"= {wow_g:+.1f}%",
        ],
        [
            "vs 4-wk avg",
            "(this week − average of the 4 prior weeks) ÷ that average",
            f"prior weekly revenue: {wk4} → avg {money(avg['gmv'])}",
        ],
        [
            "Return buckets",
            " · ".join(
                f"<b>{b}</b>: {', '.join(rs)}" for b, rs in RETURN_BUCKETS.items()
            ),
            f"{bucket_line} → {controllable} of {cur['filed_n']} company-controllable",
        ],
        [
            "Sparkline",
            "the metric's value for the last 5 closed weeks (4 prior + current)",
            "—",
        ],
    ]
    y, m0 = week_end.year, cur["start"].month
    excel_check = (
        f"Excel check for revenue: <code>=SUMIFS(total, order_date, "
        f"\"&gt;=\"&amp;DATE({y},{m0},{cur['start'].day}), order_date, "
        f"\"&lt;=\"&amp;DATE({y},{cur['end'].month},{cur['end'].day}), "
        f"order_status, \"&lt;&gt;cancelled\")</code> = ${cur['gmv']:,.2f}. "
        f"Same pattern with COUNTIFS reproduces orders and cancellations."
    )
    tab_method = (
        "<h3>How every number is calculated</h3>"
        "<p class='note'>Source: the orders file, one row per order. Any figure below can be "
        "reproduced with a filter and a formula — hover any ▲/▼ delta in the cards to see its "
        "exact math with the inputs used.</p>"
        + table(["Metric", "Formula (source columns)", "This week"], method_rows)
        + f"<p class='note'>{excel_check}</p>"
        + f"<p class='note'><b>Alert thresholds:</b> cancellations &gt; {TH_CANCEL_PCT:.0f}% · "
        f"returns &gt; {TH_RETURN_PCT:.0f}% · in transit &gt; {TH_TRANSIT_DAYS} days · "
        f"processing &gt; {TH_PROC_DAYS} days. Chips turn orange only when a threshold "
        f"is exceeded.</p>"
    )

    period = f"{cur['start'].strftime('%d %b')} – {cur['end'].strftime('%d %b %Y')}"
    chips_html = "".join(f"<span class='chip {c}'>{t}</span>" for c, t in chips)

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LARA · Weekly report · {period}</title><style>{CSS}</style></head><body>
<div class="wrap">
  <div class="head">
    <img src="{img64(LOGO_PNG)}" alt="Latram Shop">
    <div class="meta"><div class="t">LARA — Weekly report</div>
      <div class="s">Closed week {period} (Mon–Sun)<br>Data as of {cur['end'].strftime('%d %b %Y')} 23:59</div></div>
  </div>
  <div class="pad">
    <p class="eyebrow">Executive summary</p>
    <div class="summary">{summary}</div>
    <div class="chips">{chips_html}</div>
    <div class="grid">{cards}</div>
    <p class="stat">Each card shows its formula and the change vs previous week and vs the 4-week average ·
    sparkline = last 5 weeks · hover any ▲/▼ to see the exact calculation · click a card to open its detail</p>
    <div class="tabs" role="tablist">
      <button data-tab="sales" role="tab">Sales</button>
      <button data-tab="products" role="tab">Products</button>
      <button data-tab="risk" role="tab">Cancellations &amp; Returns</button>
      <button data-tab="ops" role="tab">Operations</button>
      <button data-tab="team" role="tab">Team insights</button>
      <button data-tab="method" role="tab">Methodology</button>
    </div>
    <div class="panel" id="sales">{tab_sales}</div>
    <div class="panel" id="products">{tab_products}</div>
    <div class="panel" id="risk">{tab_risk}</div>
    <div class="panel" id="ops">{tab_ops}</div>
    <div class="panel" id="team">{tab_team}</div>
    <div class="panel" id="method">{tab_method}</div>
  </div>
  <div class="foot">Automatically generated by LARA from the live orders source · Reporting window:
  {period}, closed Mon–Sun cycle · Delivered every Monday 07:00 · Data cutoff:
  {cur['end'].strftime('%d %b %Y')} 23:59.</div>
</div>
<script>{JS}</script></body></html>"""

    open(OUT_HTML, "w").write(html)
    print(f"OK -> {OUT_HTML} ({len(html.encode())/1024:.0f} KB)")
    print(
        f"GMV {money(cur['gmv'])} ({wow_g:+.1f}% vs prev wk) | orders {cur['orders']} | AOV ${cur['aov']:.2f} | "
        f"cancel {cur['cancel_rate']:.1f}% | return {cur['return_rate']:.1f}% | deliv {cur['delivery']:.1f}d"
    )
    print(
        f"4wk avg GMV {money(avg['gmv'])} | chips: {[t for _, t in chips]} | repeat: {repeat} | streak: {streak}"
    )


def delta_word(d):
    return f"{'up' if d > 0 else 'down'} {abs(d):.1f}%"


def prev_streak_text(g):
    s = 0
    for a, b in zip(g[-3::-1], g[-2::-1]):
        if b < a:
            s += 1
        else:
            break
    return f"{s} weeks of decline" if s >= 2 else "last week's dip"


def main() -> None:
    import pathlib

    pathlib.Path(OUT_HTML).parent.mkdir(parents=True, exist_ok=True)
    build()
    if "--dry-run" in _sys.argv:
        print("Dry run: abre el HTML en el navegador.")
        return
    to, user = _os.getenv("REPORT_TO", ""), _os.getenv("SMTP_USER", "")
    pwd = _os.getenv("SMTP_APP_PASSWORD", "")
    if not (to and user and pwd):
        raise OSError("Set REPORT_TO, SMTP_USER, SMTP_APP_PASSWORD in .env")
    url = _os.getenv("LARA_URL", "").strip()
    report_url = _os.getenv("REPORT_URL", "").strip()

    def _btn(href, label, primary=True):
        bg, fg, br = (NAVY, "#fff", NAVY) if primary else ("#fff", NAVY, "#c9d6e2")
        return (
            f"<a href='{href}' style='background:{bg};color:{fg};padding:11px 24px;"
            f"border:1px solid {br};border-radius:8px;text-decoration:none;"
            f"font-weight:700;display:inline-block;margin:0 10px 10px 0'>{label}</a>"
        )

    buttons = ""
    if report_url or url:
        buttons = "<p style='margin:22px 0'>"
        if report_url:
            buttons += _btn(report_url, "View interactive report")
        if url:
            buttons += _btn(url, f"Ask {AGENT_NAME}", primary=not report_url)
        buttons += "</p>"

    # When a hosted report URL exists the link replaces the attachment, whose
    # preview in webmail shows raw HTML instead of the rendered report.
    attach = _os.getenv("REPORT_ATTACH", "0" if report_url else "1") == "1"
    lead = (
        "is ready. Click below to open the interactive version: tabs, "
        "hover formulas and full methodology."
        if report_url
        else "is attached. Open the HTML file in a browser for the "
        "interactive version: tabs, hover formulas and full methodology."
    )
    period = WEEK_END.strftime("%d %b %Y")
    body = (
        f"<html><body style='font-family:Arial;color:#333'>"
        f"<img src='cid:logo' width='300'><hr style='border:2px solid {NAVY}'>"
        f"<p>Dear team,</p><p>The weekly e-commerce report (closed week ending "
        f"<b>{period}</b>) {lead}</p>{buttons}"
        f"<p>Best regards,<br><b style='color:{NAVY}'>{AGENT_NAME}</b><br>"
        f"<span style='font-size:12px;color:{SLATE}'>Internal Support Assistant · "
        f"{BRAND_NAME} · Available 24/7 for policies, data and reports</span></p>"
        f"</body></html>"
    )
    msg = MIMEMultipart("related")
    msg["Subject"] = (
        f"{AGENT_NAME} · Weekly report — {BRAND_NAME} — week ending {period}"
    )
    msg["From"] = f"{AGENT_NAME} · {BRAND_NAME} <{user}>"
    msg["To"] = to
    msg.attach(MIMEText(body, "html", "utf-8"))
    logo = MIMEImage(open(LOGO_PNG, "rb").read())
    logo.add_header("Content-ID", "<logo>")
    msg.attach(logo)
    if attach:
        att = MIMEApplication(open(OUT_HTML, "rb").read(), _subtype="html")
        att.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"LARA_weekly_report_{WEEK_END:%Y%m%d}.html",
        )
        msg.attach(att)
    with _smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.send_message(msg)
    print(f"Report sent to {to} " f"({'link' if report_url else 'attachment'} mode)")


from langchain_core.tools import tool


@tool
def report_summary(week_ending: str = "") -> str:
    """Weekly report figures WITH their formulas. Use whenever the user asks
    about the weekly report, why it shows a value, or how a report metric
    (GMV, return rate, AOV, cancellations, delivery time) is calculated.
    OMIT `week_ending` (leave it empty) unless the user explicitly names a
    specific PAST week or date — never pass today's date. Empty = the current
    report's closed week. If given, any date snaps to its closed Mon-Sun
    week.
    Same functions that generate the report — single source of truth."""
    df = load()
    end = pd.Timestamp(week_ending) if week_ending else WEEK_END
    # Snap any date UP to the Sunday closing its Mon-Sun week; dates in
    # the current/future week resolve to the latest closed week.
    end = (end + pd.Timedelta(days=(6 - end.weekday()) % 7)).normalize()
    end = min(WEEK_END, end)
    cur = week_metrics(df, end)
    prv = week_metrics(df, end - pd.Timedelta(days=7))
    p = f"{cur['start']:%d %b} – {cur['end']:%d %b %Y}"
    return (
        f"Weekly report — closed week {p} (Mon–Sun), vs previous week:\n"
        f"- Revenue (GMV): ${cur['gmv']:,.0f} [SUM(total) of non-cancelled "
        f"orders placed in the week] (prev ${prv['gmv']:,.0f})\n"
        f"- Orders: {cur['orders']} [COUNT of those rows] (prev {prv['orders']})\n"
        f"- AOV: ${cur['aov']:,.2f} [revenue ÷ orders]\n"
        f"- Cancellation rate: {cur['cancel_rate']:.1f}% "
        f"[{cur['cancelled']} cancelled ÷ {cur['placed']} placed]\n"
        f"- Return rate: {cur['return_rate']:.1f}% "
        f"[{cur['filed_n']} requests filed in the week ÷ {cur['orders']} orders]\n"
        f"- Avg delivery: {cur['delivery']:.1f} days [delivered orders placed "
        f"this week].\n"
        f"Full methodology (incl. Excel-verifiable formulas) is in the "
        f"report's Methodology tab at /report."
    )


if __name__ == "__main__":
    main()
