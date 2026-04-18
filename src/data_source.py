"""
data_source.py
--------------
Fetches the four FRED series needed for QTM-based quarterly inflation analysis:

    M2SL     – M2 Money Supply          (monthly → resampled to quarterly)
    GDP      – Nominal GDP              (quarterly SAAR, billions $)
    GDPDEF   – GDP Deflator             (quarterly index, 2017=100)
    CPIAUCSL – CPI All Urban Consumers  (monthly → resampled to quarterly, for comparison)

All series are returned at quarterly frequency (quarter-end dates).
Caching writes one CSV per series to the configured CACHE_DIR.
"""

import logging
from pathlib import Path

import pandas as pd
from fredapi import Fred

# ---------------------------------------------------------------------------
# Try both relative and absolute import so the module works whether called
# as part of the package (src.data_source) or directly (python data_source.py)
# ---------------------------------------------------------------------------
try:
    from .config import Config
except ImportError:
    from config import Config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# ---------------------------------------------------------------------------
# Series definitions
# Each entry: FRED code → (display name, native frequency, resample method)
#   resample method: "last"  – use end-of-period value   (stock variables)
#                    "mean"  – use period average         (price indices)
# ---------------------------------------------------------------------------
SERIES = {
    "M2SL":     ("M2 Money Supply",           "monthly",    "last"),
    "GDP":      ("Nominal GDP",               "quarterly",  None),   # already quarterly
    "GDPDEF":   ("GDP Deflator (2017=100)",   "quarterly",  None),   # already quarterly
    "CPIAUCSL": ("CPI All Urban Consumers",   "monthly",    "mean"),
    "GDPC1": ("Real GDP (Chained 2017$)", "quarterly", None),
}

# Reasonable default start – enough history to spot trends without bloat
DEFAULT_START = "1990-01-01"


class DataSource:
    """
    Thin wrapper around the FRED API that:
      1. Fetches each required series individually (so partial failures don't kill the run)
      2. Resamples monthly series to quarterly
      3. Caches each series as a CSV in Config.CACHE_DIR
      4. Returns a single aligned quarterly DataFrame
    """

    def __init__(self):
        Config.validate_keys()
        self._fred = Fred(api_key=Config.FRED_API_KEY)
        self._cache_dir: Path = Config.CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        start: str = DEFAULT_START,
        end: str | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch all four series and return a single quarterly DataFrame.

        Parameters
        ----------
        start : str
            ISO date string, e.g. "2000-01-01"
        end : str | None
            ISO date string or None (defaults to today)
        force_refresh : bool
            If True, ignore cached CSVs and re-fetch from FRED

        Returns
        -------
        pd.DataFrame
            Index : quarterly period-end dates (QE)
            Columns: M2SL, GDP, GDPDEF, CPIAUCSL
            Rows with all-NaN are dropped.
        """
        end = end or pd.Timestamp.today().strftime("%Y-%m-%d")

        frames: dict[str, pd.Series] = {}

        for code, (name, native_freq, resample_method) in SERIES.items():
            series = self._fetch_one(
                code=code,
                name=name,
                start=start,
                end=end,
                native_freq=native_freq,
                resample_method=resample_method,
                force_refresh=force_refresh,
            )
            if series is not None:
                frames[code] = series

        if not frames:
            raise RuntimeError("No FRED series could be fetched. Check your API key and network.")

        df = pd.DataFrame(frames)
        df.index.name = "date"

        missing = [c for c in SERIES if c not in df.columns]
        if missing:
            logger.warning("Missing series (will appear as NaN): %s", missing)

        logger.info(
            "Quarterly dataset ready | %d rows × %d cols | %s → %s",
            len(df),
            len(df.columns),
            df.index.min().date(),
            df.index.max().date(),
        )
        return df

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_path(self, code: str, start: str, end: str) -> Path:
        """Return a deterministic cache file path for this series + date range."""
        safe_start = start.replace("-", "")
        safe_end = end.replace("-", "")
        return self._cache_dir / f"{code}_{safe_start}_{safe_end}.csv"

    def _fetch_one(
        self,
        code: str,
        name: str,
        start: str,
        end: str,
        native_freq: str,
        resample_method: str | None,
        force_refresh: bool,
    ) -> pd.Series | None:
        """
        Fetch a single FRED series, using the cache when available.

        Monthly series are resampled to quarterly using the configured method.
        Quarterly series are used as-is (index normalised to QE).
        """
        cache_file = self._cache_path(code, start, end)

        # ---- Try cache first ----
        if cache_file.exists() and not force_refresh:
            logger.info("Cache hit  | %s (%s)", code, name)
            raw = pd.read_csv(cache_file, index_col=0, parse_dates=True).squeeze("columns")
            return self._normalise_quarterly_index(raw)

        # ---- Fetch from FRED ----
        logger.info("Fetching   | %s – %s", code, name)
        try:
            raw: pd.Series = self._fred.get_series(code, observation_start=start, observation_end=end)
            raw.name = code
            logger.info("  ✓ %d raw observations (%s to %s)", len(raw), raw.index.min().date(), raw.index.max().date())
        except Exception as exc:
            logger.error("  ✗ Failed to fetch %s: %s", code, exc)
            return None

        # ---- Resample monthly → quarterly if needed ----
        if native_freq == "monthly" and resample_method is not None:
            quarterly = self._to_quarterly(raw, method=resample_method)
            logger.info("  ↳ Resampled to quarterly (%d obs)", len(quarterly))
        else:
            # Already quarterly; just normalise the index
            quarterly = self._normalise_quarterly_index(raw)

        # ---- Cache to disk ----
        quarterly.to_csv(cache_file, header=True)
        logger.info("  Cached    | %s", cache_file.name)

        return quarterly

    @staticmethod
    def _to_quarterly(monthly: pd.Series, method: str) -> pd.Series:
        """
        Resample a monthly series to QE (quarter-end) frequency.

        method="last"  → end-of-quarter value  (appropriate for stock variables like M2)
        method="mean"  → quarter average        (appropriate for price indices like CPI)
        """
        if method == "last":
            return monthly.resample("QE").last().dropna()
        elif method == "mean":
            return monthly.resample("QE").mean().dropna()
        else:
            raise ValueError(f"Unknown resample method: {method!r}. Use 'last' or 'mean'.")

    @staticmethod
    def _normalise_quarterly_index(series: pd.Series) -> pd.Series:
        """
        Ensure the index is a DatetimeIndex at quarter-end (QE) frequency.
        FRED quarterly series sometimes come with mid-quarter dates; this fixes that.
        """
        if not isinstance(series.index, pd.DatetimeIndex):
            series.index = pd.to_datetime(series.index)

        # Snap each date to the last day of its quarter
        series.index = series.index.to_period("Q").to_timestamp("Q")
        return series.sort_index()


# ---------------------------------------------------------------------------
# Convenience function – import this from other modules
# ---------------------------------------------------------------------------

def load_data(
    start: str = DEFAULT_START,
    end: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    One-liner wrapper around DataSource.fetch().

    Example
    -------
    >>> from src.data_source import load_data
    >>> df = load_data(start="2010-01-01", end="2024-12-31")
    >>> print(df.tail())
    """
    return DataSource().fetch(start=start, end=end, force_refresh=force_refresh)


# ---------------------------------------------------------------------------
# Quick smoke-test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = load_data(start="2015-01-01")
    print("\n=== Quarterly Data (last 8 quarters) ===")
    print(df.tail(8).to_string())
    print(f"\nShape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"Missing values:\n{df.isnull().sum()}")