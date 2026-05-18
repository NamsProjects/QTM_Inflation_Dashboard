# QTM Inflation Dashboard

A desktop dashboard that tests the **Quantity Theory of Money** against actual CPI inflation, using long-history FRED data. Built to answer a single question empirically: *does money growth predict inflation?*

The short answer turns out to be: **yes — but only at long horizons.** Quarterly, the relationship is noise. At 5–10 year windows, correlation jumps above +0.7.

---

## What it does

Pulls five quarterly series from FRED and computes:

```
QTM-predicted inflation  =  %ΔM2 − %ΔRealGDP        (constant-velocity assumption)
Actual inflation         =  %ΔCPI
```

Then compares the two — across both quarterly snapshots and rolling windows of 1Q / 1Y / 5Y / 10Y.

The GUI shows:
- **Raw Data tab** — the five FRED series, quarter by quarter
- **QTM Analysis tab** — predicted vs actual inflation per quarter, plus a colored gap column
- **CORR BY WINDOW strip** — correlation between predicted and actual at four time horizons, color-coded by strength

---

## Setup

**1. Clone and install dependencies**

```powershell
git clone https://github.com/NamsProjects/QTM_Inflation_Dashboard.git
cd QTM_Inflation_Dashboard
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

**2. Get a free FRED API key**

Sign up at https://fredaccount.stlouisfed.org/apikeys — takes 30 seconds.

**3. Create a `.env` file** in the project root:

```
FRED_KEY=your_32_character_fred_key_here
BEA_KEY=optional_unused_for_qtm
CACHE_DIR=data
```

A template is provided in `.env.example`.

---

## Running the dashboard

```powershell
.\.venv\Scripts\python main.py
```

Pick a start/end quarter from the dropdowns and click **FETCH DATA**. FRED responses are cached as CSVs in `data/` — subsequent fetches with the same range are instant.

To see the long-run QTM effect, fetch **1959-Q1 → present**. The 5Y and 10Y correlation cells will turn green; the quarterly one stays gray (noise).

---

## Standalone analysis script

For the headline result without the GUI:

```powershell
.\.venv\Scripts\python qtm_window_analysis.py
```

Fetches 67 years of FRED data and prints correlation + mean absolute deviation at quarterly, annual, 5-year, and 10-year windows. This is what produced the numbers cited above.

---

## The empirical finding

Sample: **268 quarters from 1959-Q2 to 2026-Q1.** Annualized growth rates of M2SL, GDPC1, CPIAUCSL.

| Window | Correlation (overlapping) | Correlation (non-overlapping) | Mean abs deviation |
|---|---|---|---|
| Quarterly | −0.07 | −0.07 | 4.67 pp |
| Annual | +0.12 | +0.15 | 3.41 pp |
| **5-year** | **+0.48** | **+0.72** | **1.85 pp** |
| 10-year | +0.57 | +0.68 | 1.42 pp |

The correlation rises monotonically with window length; mean absolute prediction error collapses. Friedman's "inflation is always and everywhere a monetary phenomenon" holds — at long horizons — but quarterly velocity noise drowns the signal in the short run.

---

## Architecture

```
main.py                 entry point — launches the tkinter GUI
gui.py                  desktop dashboard (Bloomberg-terminal aesthetic)
qtm_window_analysis.py  standalone multi-window analysis script
src/
├── config.py           loads .env (FRED_KEY, BEA_KEY, CACHE_DIR)
├── data_source.py      FRED fetching + CSV caching, monthly-to-quarterly resampling
└── qtm.py              the QTM formula: pi = %ΔM2 − %ΔRealGDP
data/                   cached FRED CSVs (gitignored)
```

**Data flow:** `main.py` → `gui.py` collects date range → `data_source.load_data()` fetches/caches FRED series → `qtm.compute()` produces the per-quarter table → GUI renders both tabs and computes windowed correlations on demand.

---

## FRED series used

| Code | Name | Native frequency |
|---|---|---|
| M2SL | M2 Money Supply (seasonally adjusted) | monthly |
| GDP | Nominal GDP | quarterly |
| GDPC1 | Real GDP (chained 2017 dollars) | quarterly |
| GDPDEF | GDP Deflator (2017 = 100) | quarterly |
| CPIAUCSL | CPI All Urban Consumers (seasonally adjusted) | monthly |

Monthly series are resampled to quarter-end (M2 uses end-of-quarter value; CPI uses quarter average).

---

## The math

Starting from the identity `MV = PY` and taking growth rates with V held constant:

```
%ΔM + %ΔV = %ΔP + %ΔY
%ΔM       = %ΔP + %ΔY        (assume %ΔV = 0)
%ΔP       = %ΔM − %ΔY
```

So **predicted inflation = money growth − real output growth.** This is implemented as a point-to-point growth calculation:

```python
growth_rate[t] = (level[t] / level[t-N]) ** (4/N) - 1   # annualized
```

The `4/N` exponent annualizes any window-length growth to a per-year rate, so 1Q / 1Y / 5Y / 10Y numbers are directly comparable.

---

## License

MIT
