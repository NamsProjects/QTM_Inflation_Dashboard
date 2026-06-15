"""
QTM correlation across aggregation windows.

Tests whether the constant-velocity assumption holds better over longer
horizons by comparing predicted vs actual inflation at quarterly, annual,
5-year, and 10-year windows.

Predicted: pi = %dM2 - %dRealGDP   (constant V)
Actual:    %dCPI (CPIAUCSL)

Uses the project's existing FRED API config (api.stlouisfed.org).
"""

from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).parent
sys.path.insert(0, str(PROJ))

from src.config import Config  # noqa: E402
from fredapi import Fred       # noqa: E402


def fetch_quarterly(fred: Fred, code: str, method: str) -> pd.Series:
    """Fetch a FRED series and resample to quarter-end."""
    raw = fred.get_series(code, observation_start="1959-01-01")
    raw.name = code
    if method == "mean":
        q = raw.resample("QE").mean()
    elif method == "last":
        q = raw.resample("QE").last()
    elif method == "asis":
        # Already quarterly — snap to QE
        q = raw.copy()
        q.index = q.index.to_period("Q").to_timestamp("Q")
    else:
        raise ValueError(method)
    return q.dropna()


def pct_change(s: pd.Series, periods: int) -> pd.Series:
    """Annualized growth rate over `periods` quarters. Returns a fraction (e.g. 0.032), not a %."""
    years = periods / 4.0
    return (s / s.shift(periods)) ** (1.0 / years) - 1.0


def analyze(m2: pd.Series, rgdp: pd.Series, cpi: pd.Series,
            window_years: float, label: str) -> dict:
    periods = max(1, int(round(window_years * 4)))
    pi_pred = pct_change(m2, periods) - pct_change(rgdp, periods)
    pi_actual = pct_change(cpi, periods)

    df = pd.concat({"pred": pi_pred, "actual": pi_actual}, axis=1).dropna()
    if window_years >= 1:
        # Step backward from the most recent observation so the selected rows
        # are anchored to the latest data point rather than the (potentially
        # non-calendar-aligned) first post-shift row.
        indices = list(range(len(df) - 1, -1, -periods))[::-1]
        non_overlap = df.iloc[indices]
    else:
        non_overlap = df

    return {
        "label": label,
        "n_all": len(df),
        "n_indep": len(non_overlap),
        "corr_all": df["pred"].corr(df["actual"]),
        "corr_indep": non_overlap["pred"].corr(non_overlap["actual"]),
        "mean_pred": df["pred"].mean() * 100,
        "mean_actual": df["actual"].mean() * 100,
        "mean_abs_dev_pp": (df["pred"] - df["actual"]).abs().mean() * 100,
        "start": df.index.min().strftime("%Y-%m"),
        "end": df.index.max().strftime("%Y-%m"),
    }


def main():
    fred = Fred(api_key=Config.FRED_API_KEY)
    print("Fetching FRED series via API...")
    m2 = fetch_quarterly(fred, "M2SL", "mean")   # quarterly mean matches GDP's period-average
    rgdp = fetch_quarterly(fred, "GDPC1", "asis")
    cpi = fetch_quarterly(fred, "CPIAUCSL", "last")  # end-of-quarter matches BLS point-to-point
    print(f"  M2SL:     {m2.index.min().date()} -> {m2.index.max().date()}  ({len(m2)} obs)")
    print(f"  GDPC1:    {rgdp.index.min().date()} -> {rgdp.index.max().date()}  ({len(rgdp)} obs)")
    print(f"  CPIAUCSL: {cpi.index.min().date()} -> {cpi.index.max().date()}  ({len(cpi)} obs)")

    windows = [
        (0.25, "Quarterly (1Q)"),
        (1.0,  "Annual (1Y)"),
        (5.0,  "5-year"),
        (10.0, "10-year"),
    ]
    results = [analyze(m2, rgdp, cpi, yrs, lbl) for yrs, lbl in windows]

    print("\n=== QTM predicted vs actual inflation, by aggregation window ===")
    print("Predicted = %dM2 - %dRealGDP  (annualized, constant V)")
    print(f"Sample spans roughly: {results[0]['start']} to {results[0]['end']}\n")
    hdr = (f"{'Window':<16}{'N(all)':>8}{'N(indep)':>10}"
           f"{'corr(all)':>12}{'corr(indep)':>14}"
           f"{'meanPred':>11}{'meanAct':>10}{'mAbsDev(pp)':>14}")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(f"{r['label']:<16}{r['n_all']:>8d}{r['n_indep']:>10d}"
              f"{r['corr_all']:>12.3f}{r['corr_indep']:>14.3f}"
              f"{r['mean_pred']:>10.2f}%{r['mean_actual']:>9.2f}%"
              f"{r['mean_abs_dev_pp']:>14.2f}")

    # Also report decade-averaged scatter explicitly
    print("\n=== 10-year non-overlapping data points (the honest test) ===")
    periods = 40
    pred = pct_change(m2, periods) - pct_change(rgdp, periods)
    actual = pct_change(cpi, periods)
    df = pd.concat({"pred": pred * 100, "actual": actual * 100}, axis=1).dropna().iloc[::periods]
    print(df.round(2).to_string())

    print("\n=== 5-year non-overlapping data points ===")
    periods = 20
    pred = pct_change(m2, periods) - pct_change(rgdp, periods)
    actual = pct_change(cpi, periods)
    df = pd.concat({"pred": pred * 100, "actual": actual * 100}, axis=1).dropna().iloc[::periods]
    print(df.round(2).to_string())


if __name__ == "__main__":
    main()
