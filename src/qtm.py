"""
qtm.py
------
Quantity Theory of Money inflation estimate, compared against actual CPI.

Core formula (V assumed constant, so it cancels):
    QTM_inflation = M2_growth (QoQ) - RealGDP_growth (QoQ)

This comes from differencing MV = PY with V held constant:
    P_t/P_t-1 = (M_t/M_t-1) * (Y_t-1/Y_t)
    → % change in P ≈ % change in M - % change in Y

CPI comparison:
    CPI_inflation = QoQ % change in CPIAUCSL

Output columns
--------------
    M2_growth       : QoQ % change in M2 money supply
    RGDP_growth     : QoQ % change in Real GDP
    QTM_inflation   : M2_growth - RGDP_growth  (QTM predicted inflation)
    CPI_inflation   : QoQ % change in CPI
    gap             : QTM_inflation - CPI_inflation  (how well QTM tracks CPI)

All values are expressed as percentages (e.g. 2.1 means 2.1%).
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Required columns from data_source
REQUIRED = {"M2SL", "GDPC1", "CPIAUCSL"}


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute QTM inflation and CPI inflation from the raw quarterly DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Output of load_data() — quarterly, columns include at minimum
        M2SL, GDPC1, CPIAUCSL.

    Returns
    -------
    pd.DataFrame
        Quarterly DataFrame with columns:
        M2_growth, RGDP_growth, QTM_inflation, CPI_inflation, gap.
        First row is always NaN (no prior quarter to diff against).
        Rows where any required input is NaN are dropped.
    """
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(
            f"Input DataFrame is missing required columns: {missing}. "
            f"Make sure data_source.py fetches GDPC1."
        )

    # Work on a clean copy with only the columns we need
    raw = df[["M2SL", "GDPC1", "CPIAUCSL"]].copy()

    # Drop rows where any of the three inputs is NaN
    raw = raw.dropna()

    if len(raw) < 2:
        raise ValueError("Need at least 2 quarters of complete data to compute growth rates.")

    result = pd.DataFrame(index=raw.index)

    # QoQ % changes
    result["M2_growth"]    = raw["M2SL"].pct_change()   * 100
    result["RGDP_growth"]  = raw["GDPC1"].pct_change()  * 100
    result["CPI_inflation"] = raw["CPIAUCSL"].pct_change() * 100

    # QTM predicted inflation: money growth minus real output growth
    result["QTM_inflation"] = result["M2_growth"] - result["RGDP_growth"]

    # Gap: how much QTM over/under-shoots actual CPI
    result["gap"] = result["QTM_inflation"] - result["CPI_inflation"]

    # Drop the first row (all NaN from pct_change)
    result = result.iloc[1:]

    logger.info(
        "QTM analysis complete | %d quarters | %s → %s",
        len(result),
        result.index.min().date(),
        result.index.max().date(),
    )

    _log_summary(result)

    return result


def _log_summary(result: pd.DataFrame) -> None:
    """Log a brief summary of recent QTM vs CPI numbers."""
    recent = result.tail(4)
    logger.info("--- Recent QTM vs CPI (last 4 quarters) ---")
    for date, row in recent.iterrows():
        try:
            q = (date.month - 1) // 3 + 1
            label = f"{date.year}-Q{q}"
        except Exception:
            label = str(date)[:7]

        logger.info(
            "  %s | M2: %+.2f%%  RealGDP: %+.2f%%  "
            "QTM: %+.2f%%  CPI: %+.2f%%  Gap: %+.2f pp",
            label,
            row["M2_growth"],
            row["RGDP_growth"],
            row["QTM_inflation"],
            row["CPI_inflation"],
            row["gap"],
        )


# ---------------------------------------------------------------------------
# Convenience wrapper — mirrors load_data() pattern from data_source.py
# ---------------------------------------------------------------------------

def compute_from_source(
    start: str = "1990-01-01",
    end: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch raw data and compute QTM analysis in one call.

    Example
    -------
    >>> from src.qtm import compute_from_source
    >>> qtm_df = compute_from_source(start="2015-01-01")
    >>> print(qtm_df.tail(8))
    """
    try:
        from .data_source import load_data
    except ImportError:
        from data_source import load_data

    raw = load_data(start=start, end=end, force_refresh=force_refresh)
    return compute(raw)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = compute_from_source(start="2015-01-01")
    print("\n=== QTM vs CPI Inflation (last 12 quarters) ===")
    print(df.tail(12).round(2).to_string())
    print(f"\nAverage gap (QTM - CPI): {df['gap'].mean():.2f} pp")
    print(f"Correlation QTM vs CPI:  {df['QTM_inflation'].corr(df['CPI_inflation']):.3f}")