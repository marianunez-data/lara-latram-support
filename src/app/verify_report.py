"""Report self-audit: recompute headline figures via an INDEPENDENT code path
and assert they match week_metrics(). If both implementations agree, a silent
formula bug would need to exist twice, identically — the standard 'golden
check' pattern for certifying deterministic reports.

Usage: python -m src.app.verify_report
"""

from __future__ import annotations

import pandas as pd

from .weekly_report import WEEK_END, load, week_metrics


def main() -> None:
    df = load()
    m = week_metrics(df, WEEK_END)
    start = WEEK_END - pd.Timedelta(days=6)

    # Independent recomputation (different expressions on purpose)
    w = df.query("@start <= order_date <= @WEEK_END")
    ind = {
        "gmv": w.loc[w.order_status.ne("cancelled"), "total"].sum(),
        "orders": int(w.order_status.ne("cancelled").sum()),
        "cancelled": int(w.order_status.eq("cancelled").sum()),
        "filed_n": int(df.return_request_date.between(start, WEEK_END).sum()),
    }
    ok = True
    for k, v in ind.items():
        match = abs(float(m[k]) - float(v)) < 0.01
        ok &= match
        print(f"{'PASS' if match else 'FAIL'}  {k:<10} report={m[k]}  audit={v}")
    print(
        "AUDIT OK — report figures independently verified."
        if ok
        else "AUDIT FAILED — investigate before sending."
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
