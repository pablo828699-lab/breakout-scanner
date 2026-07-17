"""
Fundamental filter — evaluates financial health of US equity tickers
and correlation-based filtering for crypto assets.

US Equities:
    Fetches quarterly financials via yfinance and computes solvency ratios
    (Interest Coverage, Current Ratio, Quick Ratio).

Crypto:
    Compares the asset's recent daily returns against BTC to flag
    idiosyncratic drops that are not market-wide.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field-name variations that yfinance may return across quarterly reports
# ---------------------------------------------------------------------------
_EBIT_FIELDS = ("EBIT", "Ebit", "Operating Income", "OperatingIncome")
_INTEREST_FIELDS = (
    "Interest Expense",
    "Interest expense",
    "InterestExpense",
    "Interest Expense Non Operating",
)
_CURRENT_ASSETS_FIELDS = (
    "Current Assets",
    "Total Current Assets",
    "CurrentAssets",
    "TotalCurrentAssets",
)
_CURRENT_LIABILITIES_FIELDS = (
    "Current Liabilities",
    "Total Current Liabilities",
    "CurrentLiabilities",
    "TotalCurrentLiabilities",
)
_INVENTORY_FIELDS = ("Inventory", "Inventories", "NetInventory")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _first_valid(data: dict[str, Any] | pd.Series, keys: tuple[str, ...]) -> float | None:
    """Return the first non-NaN value found for any of *keys*, or ``None``."""
    for key in keys:
        try:
            val = data[key]
        except (KeyError, TypeError):
            continue
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return float(val)
    return None


def _extract_latest_column(df: pd.DataFrame) -> pd.Series | None:
    """Return the most-recent column of a quarterly statement DataFrame.

    yfinance returns columns as dates; the first column is the latest quarter.
    """
    if df is None or df.empty:
        return None
    return df.iloc[:, 0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_fundamentals(ticker: str) -> dict[str, float | None] | None:
    """Fetch key solvency-related fundamentals for *ticker* via yfinance.

    Parameters
    ----------
    ticker : str
        US equity ticker symbol (e.g. ``"AAPL"``).

    Returns
    -------
    dict | None
        Dictionary with keys ``ebit``, ``interest_expense``,
        ``current_assets``, ``current_liabilities``, ``inventory``.
        Returns ``None`` when data is completely unavailable.
    """
    try:
        info = yf.Ticker(ticker)

        income_stmt = _extract_latest_column(info.quarterly_financials)
        balance_sheet = _extract_latest_column(info.quarterly_balance_sheet)

        if income_stmt is None and balance_sheet is None:
            logger.warning(
                "No quarterly financial data returned for %s.", ticker
            )
            return None

        ebit = _first_valid(income_stmt, _EBIT_FIELDS) if income_stmt is not None else None
        interest_exp = _first_valid(income_stmt, _INTEREST_FIELDS) if income_stmt is not None else None

        current_assets = _first_valid(balance_sheet, _CURRENT_ASSETS_FIELDS) if balance_sheet is not None else None
        current_liabilities = _first_valid(balance_sheet, _CURRENT_LIABILITIES_FIELDS) if balance_sheet is not None else None
        inventory = _first_valid(balance_sheet, _INVENTORY_FIELDS) if balance_sheet is not None else None

        fundamentals: dict[str, float | None] = {
            "ebit": ebit,
            "interest_expense": interest_exp,
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "inventory": inventory,
        }

        logger.info("Fundamentals for %s: %s", ticker, fundamentals)
        return fundamentals

    except Exception:
        logger.exception("Failed to fetch fundamentals for %s.", ticker)
        return None


def evaluate_solvency(fundamentals: dict[str, float | None]) -> dict[str, Any]:
    """Compute solvency ratios from raw fundamental values.

    Parameters
    ----------
    fundamentals : dict
        Output of :func:`fetch_fundamentals`.

    Returns
    -------
    dict
        ``icr`` – Interest Coverage Ratio
        ``current_ratio`` – Current Assets / Current Liabilities
        ``quick_ratio`` – (Current Assets − Inventory) / Current Liabilities
        ``is_solvent`` – ``True`` when ICR ≥ 3 **and** Current Ratio ≥ 1.0
        ``risk_flags`` – human-readable warnings list
    """
    risk_flags: list[str] = []

    # -- Interest Coverage Ratio (ICR) --
    ebit = fundamentals.get("ebit")
    interest_exp = fundamentals.get("interest_expense")

    if interest_exp is None or interest_exp == 0.0:
        icr = 999.0  # no debt burden
    else:
        icr = round(ebit / abs(interest_exp), 2) if ebit is not None else 0.0

    if icr < 3.0:
        risk_flags.append(f"Low interest coverage (ICR={icr})")

    # -- Current Ratio --
    current_assets = fundamentals.get("current_assets")
    current_liabilities = fundamentals.get("current_liabilities")

    if (
        current_assets is not None
        and current_liabilities is not None
        and current_liabilities != 0.0
    ):
        current_ratio = round(current_assets / current_liabilities, 2)
    else:
        current_ratio = 0.0
        risk_flags.append("Unable to compute current ratio (missing data)")

    if current_ratio < 1.0:
        risk_flags.append(f"Liquidity stress (Current Ratio={current_ratio})")

    # -- Quick Ratio --
    inventory = fundamentals.get("inventory")
    if (
        inventory is not None
        and current_assets is not None
        and current_liabilities is not None
        and current_liabilities != 0.0
    ):
        quick_ratio = round(
            (current_assets - inventory) / current_liabilities, 2
        )
    else:
        quick_ratio = current_ratio  # fall back to current ratio

    is_solvent = icr >= 3.0 and current_ratio >= 1.0

    result = {
        "icr": icr,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "is_solvent": is_solvent,
        "risk_flags": risk_flags,
    }

    logger.info(
        "Solvency evaluation: solvent=%s, ICR=%.2f, CR=%.2f, QR=%.2f, flags=%s",
        is_solvent,
        icr,
        current_ratio,
        quick_ratio,
        risk_flags,
    )
    return result


def evaluate_correlation_filter(
    ticker_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
) -> dict[str, Any]:
    """Compare the asset's recent daily return against a benchmark (BTC).

    An *idiosyncratic* drop is one where the asset fell ≥ 2 % while the
    benchmark fell < 1 % — i.e. the weakness is asset-specific, not
    market-wide.

    Parameters
    ----------
    ticker_df : pd.DataFrame
        Daily OHLCV for the target asset (must contain a ``Close`` column).
    benchmark_df : pd.DataFrame
        Daily OHLCV for the benchmark asset (e.g. BTC-USD).

    Returns
    -------
    dict
        ``correlation`` – 20-day rolling Pearson correlation of returns
        ``asset_return`` – latest 1-day pct change of the asset
        ``benchmark_return`` – latest 1-day pct change of the benchmark
        ``is_idiosyncratic`` – ``True`` when asset dropped ≥ 2 % while
        benchmark dropped < 1 %
    """
    lookback = 20

    # --- Defensive length checks ---
    min_rows = lookback + 1
    if ticker_df is None or len(ticker_df) < min_rows:
        logger.warning(
            "Insufficient ticker data for correlation filter (%d rows, need %d).",
            0 if ticker_df is None else len(ticker_df),
            min_rows,
        )
        return {
            "correlation": 0.0,
            "asset_return": 0.0,
            "benchmark_return": 0.0,
            "is_idiosyncratic": False,
        }

    if benchmark_df is None or len(benchmark_df) < min_rows:
        logger.warning(
            "Insufficient benchmark data for correlation filter (%d rows, need %d).",
            0 if benchmark_df is None else len(benchmark_df),
            min_rows,
        )
        return {
            "correlation": 0.0,
            "asset_return": 0.0,
            "benchmark_return": 0.0,
            "is_idiosyncratic": False,
        }

    # --- Returns ---
    asset_returns = ticker_df["Close"].pct_change().dropna().tail(lookback)
    bench_returns = benchmark_df["Close"].pct_change().dropna().tail(lookback)

    # Align on index intersection to handle date mismatches
    common_idx = asset_returns.index.intersection(bench_returns.index)
    if len(common_idx) < 5:
        logger.warning(
            "Fewer than 5 overlapping return observations; correlation unreliable."
        )
        correlation = 0.0
    else:
        correlation = float(
            asset_returns.loc[common_idx].corr(bench_returns.loc[common_idx])
        )
        if np.isnan(correlation):
            correlation = 0.0

    asset_return = float(asset_returns.iloc[-1]) if len(asset_returns) > 0 else 0.0
    benchmark_return = float(bench_returns.iloc[-1]) if len(bench_returns) > 0 else 0.0

    is_idiosyncratic = asset_return <= -0.02 and benchmark_return > -0.01

    logger.info(
        "Correlation filter: corr=%.3f, asset_ret=%.4f, bench_ret=%.4f, idiosyncratic=%s",
        correlation,
        asset_return,
        benchmark_return,
        is_idiosyncratic,
    )
    return {
        "correlation": round(correlation, 4),
        "asset_return": round(asset_return, 4),
        "benchmark_return": round(benchmark_return, 4),
        "is_idiosyncratic": is_idiosyncratic,
    }


def run_fundamental_filter(
    ticker: str,
    market: str,
    daily_df: pd.DataFrame | None = None,
    benchmark_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Orchestrate the correct filter pipeline based on asset market.

    Parameters
    ----------
    ticker : str
        Symbol to evaluate.
    market : str
        ``"US_EQUITIES"`` or ``"CRYPTO"``.
    daily_df : pd.DataFrame | None
        Daily OHLCV of the ticker (required for ``CRYPTO``).
    benchmark_df : pd.DataFrame | None
        Daily OHLCV of the benchmark, e.g. BTC-USD (required for ``CRYPTO``).

    Returns
    -------
    dict
        ``passed`` – whether the asset cleared the filter
        ``market`` – echo of the market parameter
        ``details`` – sub-dict with ratio / correlation results
    """
    market_upper = market.upper().replace(" ", "_")

    if market_upper == "US_EQUITIES":
        fundamentals = fetch_fundamentals(ticker)
        if fundamentals is None:
            logger.warning(
                "Fundamental filter FAIL for %s — no data available.", ticker
            )
            return {
                "passed": False,
                "market": market_upper,
                "details": {"error": "No fundamental data available"},
            }

        solvency = evaluate_solvency(fundamentals)
        passed = solvency["is_solvent"]
        return {
            "passed": passed,
            "market": market_upper,
            "details": {**fundamentals, **solvency},
        }

    if market_upper == "CRYPTO":
        if daily_df is None or benchmark_df is None:
            logger.warning(
                "Correlation filter FAIL for %s — missing price DataFrames.",
                ticker,
            )
            return {
                "passed": False,
                "market": market_upper,
                "details": {"error": "Daily or benchmark DataFrame not provided"},
            }

        corr_result = evaluate_correlation_filter(daily_df, benchmark_df)
        # Pass when the drop is NOT idiosyncratic (market-wide sell-off is ok)
        passed = not corr_result["is_idiosyncratic"]
        return {
            "passed": passed,
            "market": market_upper,
            "details": corr_result,
        }

    logger.error("Unknown market type '%s' for ticker %s.", market, ticker)
    return {
        "passed": False,
        "market": market_upper,
        "details": {"error": f"Unsupported market type: {market}"},
    }
