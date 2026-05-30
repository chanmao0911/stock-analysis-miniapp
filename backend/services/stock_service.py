"""
Stock data service using AKShare v1.18+ to fetch financial data.
Data sources: 东方财富 (via AKShare wrapper).
"""
import time
import logging
from datetime import datetime
from typing import Optional

import akshare as ak
import pandas as pd

from config import CACHE_TTL, RETRY_COUNT, RETRY_DELAY, COMPLETE_YEARS, CURRENT_YEAR

logger = logging.getLogger(__name__)


def _retry(func, *args, **kwargs):
    """Retry wrapper for AKShare API calls."""
    last_error = None
    for attempt in range(RETRY_COUNT):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{RETRY_COUNT} failed: {e}")
            if attempt < RETRY_COUNT - 1:
                time.sleep(RETRY_DELAY)
    raise last_error


def _safe_float(value):
    """Safely convert a value to float."""
    if value is None or value == "" or value == "-" or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value):
    """Safely convert a value to int."""
    v = _safe_float(value)
    return int(v) if v is not None else None


# ---------- cache ----------

_cache: dict = {}
_cache_time: dict = {}


def _cached(key, ttl=CACHE_TTL):
    now = time.time()
    if key in _cache and now - _cache_time.get(key, 0) < ttl:
        return _cache[key]
    return None


def _set_cache(key, value):
    _cache[key] = value
    _cache_time[key] = time.time()


# ---------- helpers ----------

def _market_prefix(stock_code: str) -> str:
    """Convert stock code to market prefix for APIs that need it."""
    code = str(stock_code).strip()
    if code.startswith("6"):
        return f"SH{code}"
    elif code.startswith(("0", "3")):
        return f"SZ{code}"
    elif code.startswith(("4", "8")):
        return f"BJ{code}"
    return code


def _market_name(stock_code: str) -> str:
    code = str(stock_code).strip()
    if code.startswith("6"):
        return "沪市"
    elif code.startswith(("0", "3")):
        return "深市"
    elif code.startswith(("4", "8")):
        return "北交所"
    return ""


# ================================================================
#  Public API
# ================================================================

def search_stocks(keyword: str) -> list[dict]:
    """Search listed companies by name keyword."""
    cache_key = f"search_{keyword}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        df = _retry(ak.stock_info_a_code_name)
    except Exception:
        logger.exception("Failed to fetch stock list")
        return []

    if df is None or df.empty:
        return []

    mask = df["name"].str.contains(keyword, na=False)
    result_df = df[mask][["code", "name"]].copy()

    results = []
    for _, row in result_df.iterrows():
        code = str(row["code"])
        results.append({
            "code": code,
            "name": str(row["name"]),
            "market": _market_name(code),
        })

    _set_cache(cache_key, results)
    return results


def get_company_info(stock_code: str) -> dict:
    """Get company basic info from 巨潮资讯 (cninfo)."""
    cache_key = f"info_{stock_code}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    info = {}

    # Primary: cninfo profile (reliable, rich profile data)
    try:
        df = ak.stock_profile_cninfo(symbol=stock_code)
        if df is not None and not df.empty:
            row = df.iloc[0]
            for col in df.columns:
                val = row[col]
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    val_str = str(val).strip()
                    if val_str and val_str.lower() != "nan" and val_str.lower() != "none":
                        info[col] = val_str
            logger.info(f"cninfo returned {len(info)} fields for {stock_code}: {list(info.keys())[:5]}...")
        else:
            logger.warning(f"cninfo returned empty dataframe for {stock_code}")
    except Exception as e:
        logger.warning(f"cninfo profile failed for {stock_code}: {e}")

    # Fallback 1: xueqiu individual info
    if not info:
        try:
            df = ak.stock_individual_basic_info_xq(
                symbol=_market_prefix(stock_code), timeout=10
            )
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    item = str(row.get("item", "")).strip()
                    value = str(row.get("value", "")).strip()
                    if item and value and value.lower() != "nan":
                        info[item] = value
        except Exception:
            pass

    # Fallback 2: eastmoney individual info
    if not info:
        try:
            df = ak.stock_individual_info_em(symbol=stock_code, timeout=10)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    item = str(row.get("item", "")).strip()
                    value = str(row.get("value", "")).strip()
                    if item and value and value.lower() != "nan":
                        info[item] = value
        except Exception:
            pass

    _set_cache(cache_key, info)
    return info


def get_all_company_data(stock_code: str) -> dict:
    """Fetch and return all financial data for a company (parallel)."""
    company_info = get_company_info(stock_code)

    # Name: try cninfo first, then old APIs, then search
    name = (company_info.get("A股简称")
            or company_info.get("股票简称")
            or company_info.get("org_short_name_cn", ""))
    if not name:
        name = _find_company_name(stock_code)

    full_name = (company_info.get("公司名称")
                or company_info.get("org_name_cn", "")
                or name)

    profile = (company_info.get("机构简介", "")
              or company_info.get("org_cn_introduction", "")
              or company_info.get("公司简介", "")
              or company_info.get("main_operation_business", ""))

    business_scope = (company_info.get("经营范围", "")
                     or company_info.get("operating_scope", "")
                     or company_info.get("主营业务", "")
                     or company_info.get("main_operation_business", ""))

    # Industry: try cninfo first, then xueqiu, then profile
    industry = company_info.get("所属行业", company_info.get("行业", ""))
    if not industry:
        ai = company_info.get("affiliate_industry", "")
        if ai and isinstance(ai, str):
            import json as _json
            try:
                industry = _json.loads(ai.replace("'", '"')).get("ind_name", "")
            except Exception:
                pass

    # Fetch data sources sequentially (with retries) to avoid SSL/rate issues
    earnings = _get_earnings_data(stock_code)
    stock_prices = _get_stock_price_data(stock_code)
    shareholders = _get_shareholder_data(stock_code)
    balance_sheet = _get_balance_sheet_data(stock_code)

    if not industry:
        industry = earnings.get("industry", "")

    # Merge net assets from both earnings (YJBB) and balance sheet
    net_assets = dict(balance_sheet.get("net_assets", {}))
    # YJBB data (more accurate for latest year) takes priority
    for y, v in earnings.get("net_assets", {}).items():
        net_assets[y] = v

    return {
        "code": stock_code,
        "name": name,
        "full_name": full_name,
        "market": _market_name(stock_code),
        "profile": profile,
        "business_scope": business_scope,
        "industry": industry,
        "revenue_structure": _get_revenue_structure(stock_code, company_info, industry),
        "revenue": earnings.get("revenue", {}),
        "eps": earnings.get("eps", {}),
        "stock_price_high": stock_prices.get("high", {}),
        "stock_price_low": stock_prices.get("low", {}),
        "today_open": stock_prices.get("today_open"),
        "today_date": stock_prices.get("today_date", ""),
        "shareholders": shareholders,
        "net_assets_per_share": net_assets,
        "asset_liability_ratio": balance_sheet.get("asset_liability", {}),
        "sources": {
            "company_info": "东方财富Choice",
            "revenue": "东方财富Choice",
            "eps": "东方财富Choice",
            "stock_price": "AKShare/新浪",
            "shareholders": "东方财富Choice",
            "net_assets": "东方财富Choice",
            "asset_liability": "东方财富Choice",
            "revenue_structure": "东方财富Choice",
        },
    }


# ================================================================
#  Earnings data (revenue, EPS, net assets)
# ================================================================

def _get_earnings_data(stock_code: str) -> dict:
    """
    Get earnings data: revenue and EPS from YJBB (year-end reports).
    Falls back to profit_sheet API if YJBB fails.
    """
    cache_key = f"earnings_{stock_code}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    result: dict = {"revenue": {}, "eps": {}, "net_assets": {}, "industry": ""}

    # --- Try YJBB for year-end dates (no retry - too slow) ---
    dates_to_try = [f"{y}1231" for y in COMPLETE_YEARS]
    # Add current year Q1 for latest data
    dates_to_try.append(f"{CURRENT_YEAR}0331")

    for date_str in dates_to_try:
        year = int(date_str[:4])
        try:
            df = ak.stock_yjbb_em(date=date_str)
            if df is None or df.empty:
                continue
            rows = df[df["股票代码"].astype(str) == str(stock_code)]
            if rows.empty:
                continue
            r = rows.iloc[0]

            revenue = _safe_float(r.get("营业总收入-营业总收入"))
            eps = _safe_float(r.get("每股收益"))
            nav = _safe_float(r.get("每股净资产"))
            ind = str(r.get("所处行业", ""))

            if revenue is not None and year not in result["revenue"]:
                result["revenue"][year] = round(revenue / 100000000, 2)
            if eps is not None and year not in result["eps"]:
                result["eps"][year] = eps
            if nav is not None and year not in result["net_assets"]:
                result["net_assets"][year] = nav
            if ind and ind != "nan" and not result["industry"]:
                result["industry"] = ind

            time.sleep(0.3)
        except Exception:
            logger.warning(f"YJBB failed for date {date_str}")
            continue

    # --- Fallback: try profit_sheet API for missing data ---
    if not result["revenue"]:
        try:
            df = ak.stock_profit_sheet_by_report_em(symbol=_market_prefix(stock_code))
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    year = _extract_year_from_date(str(row.get("REPORT_DATE", "")))
                    if year is None:
                        continue
                    report_type = str(row.get("REPORT_TYPE", ""))
                    if "年报" not in report_type and str(CURRENT_YEAR) not in str(row.get("REPORT_DATE", "")):
                        continue
                    rev = _safe_float(row.get("TOTAL_OPERATE_INCOME"))
                    # Try alternative columns for banks/other industries
                    if rev is None:
                        rev = _safe_float(row.get("OPERATE_INCOME"))
                    if rev is None:
                        rev = _safe_float(row.get("TOTAL_OPERATE_REV"))
                    eps = _safe_float(row.get("BASIC_EPS"))
                    if rev is not None and year not in result["revenue"]:
                        result["revenue"][year] = round(rev / 100000000, 2)
                    if eps is not None and year not in result["eps"]:
                        result["eps"][year] = eps
        except Exception:
            logger.warning(f"Profit sheet fallback also failed for {stock_code}")

    # Only cache if we got data
    if result["revenue"] or result["eps"]:
        _set_cache(cache_key, result)
    return result


def _find_company_name(stock_code: str) -> str:
    """Find company name from various sources."""
    # Try stock_info_a_code_name
    try:
        df = ak.stock_info_a_code_name()
        row = df[df["code"].astype(str) == str(stock_code)]
        if not row.empty:
            return str(row.iloc[0]["name"])
    except Exception:
        pass

    # Try yjbb_em with latest date
    try:
        df = ak.stock_yjbb_em(date=f"{COMPLETE_YEARS[-1]}1231")
        row = df[df["股票代码"].astype(str) == str(stock_code)]
        if not row.empty:
            return str(row.iloc[0]["股票简称"])
    except Exception:
        pass

    return ""


def _extract_year_from_date(date_str: str) -> Optional[int]:
    """Extract year from various date formats."""
    if not date_str:
        return None
    s = str(date_str).strip()
    # Handle "2026-03-31 00:00:00" format
    if " " in s:
        s = s.split(" ")[0]
    # Formats: "2024-12-31", "20241231", "2024/12/31"
    for sep in ["-", "/"]:
        if sep in s:
            parts = s.split(sep)
            if len(parts) >= 1 and parts[0].isdigit() and len(parts[0]) == 4:
                return int(parts[0])
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return None


# ================================================================
#  Stock price data (high / low by year)
# ================================================================

def _get_stock_price_data(stock_code: str) -> dict:
    """Get annual high/low prices + today's open price from sina daily data."""
    cache_key = f"price_{stock_code}"
    cached = _cached(cache_key, ttl=600)  # 10 min cache for prices
    if cached is not None:
        return cached

    result: dict = {"high": {}, "low": {}, "today_open": None, "today_date": ""}

    # Market prefix for sina API
    code = str(stock_code)
    if code.startswith("6"):
        sina_symbol = f"sh{code}"
    else:
        sina_symbol = f"sz{code}"

    try:
        df = ak.stock_zh_a_daily(
            symbol=sina_symbol,
            start_date=f"{min(COMPLETE_YEARS)}0101",
            end_date=f"{CURRENT_YEAR}1231",
            adjust="qfq",
        )
    except Exception:
        logger.warning(f"Stock price data unavailable for {stock_code}")
        _set_cache(cache_key, result)
        return result

    if df is None or df.empty:
        _set_cache(cache_key, result)
        return result

    # Columns: date, open, high, low, close, volume, amount, outstanding_share, turnover
    df["year"] = pd.to_datetime(df["date"]).dt.year

    # Annual high/low
    for y in [*COMPLETE_YEARS, CURRENT_YEAR]:
        year_data = df[df["year"] == y]
        if not year_data.empty:
            result["high"][y] = round(float(year_data["high"].max()), 2)
            result["low"][y] = round(float(year_data["low"].min()), 2)

    # Today's open price (last row in df)
    last_row = df.iloc[-1]
    result["today_open"] = round(float(last_row["open"]), 2)
    result["today_date"] = str(last_row["date"])

    # Only cache if we got data
    if result["high"] or result["low"]:
        _set_cache(cache_key, result)
    return result


# ================================================================
#  Shareholder count data
# ================================================================

def _get_shareholder_data(stock_code: str) -> dict:
    """Get shareholder count history and statistics."""
    cache_key = f"shareholders_{stock_code}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    result: dict = {
        "max_count": None,
        "max_count_year": None,
        "min_count": None,
        "min_count_year": None,
        "current_count": None,
        "by_year": {},
    }

    try:
        df = _retry(ak.stock_zh_a_gdhs_detail_em, symbol=stock_code)
    except Exception:
        logger.exception(f"Failed to fetch shareholder data for {stock_code}")
        return result

    if df is None or df.empty:
        return result

    # Columns: 股东户数统计截止日, 股东户数-本次, ...
    counts_by_year: dict[int, int] = {}

    for _, row in df.iterrows():
        date_str = str(row.get("股东户数统计截止日", ""))
        count = _safe_int(row.get("股东户数-本次"))
        if not date_str or count is None:
            continue

        year = _extract_year_from_date(date_str)
        if year is None:
            continue

        # Keep the latest count for each year (prefer Q4/12-31)
        if year not in counts_by_year or _is_year_end(date_str):
            counts_by_year[year] = count

    # Filter to relevant years
    all_counts = []
    for y in [*COMPLETE_YEARS, CURRENT_YEAR]:
        if y in counts_by_year:
            result["by_year"][y] = counts_by_year[y]
            all_counts.append(counts_by_year[y])

    if all_counts:
        result["max_count"] = max(all_counts)
        result["min_count"] = min(all_counts)
        result["current_count"] = all_counts[-1]

        # Find which year had max/min
        for y, c in result["by_year"].items():
            if c == result["max_count"]:
                result["max_count_year"] = y
            if c == result["min_count"]:
                result["min_count_year"] = y

    # Only cache if we have data
    if result["current_count"] or result["max_count"]:
        _set_cache(cache_key, result)
    return result


def _is_year_end(date_str: str) -> bool:
    """Check if date string represents a year-end period."""
    s = str(date_str)
    return "12-31" in s or "1231" in s or s.endswith("-12-31")


# ================================================================
#  Balance sheet (asset-liability ratio)
# ================================================================

def _get_balance_sheet_data(stock_code: str) -> dict:
    """Get asset-liability ratio AND net assets per share from balance sheet."""
    cache_key = f"balance_{stock_code}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    result: dict = {"asset_liability": {}, "net_assets": {}}
    prefixed = _market_prefix(stock_code)

    try:
        df = ak.stock_balance_sheet_by_report_em(symbol=prefixed)
    except Exception:
        logger.warning(f"Failed to fetch balance sheet for {stock_code}")
        return result

    if df is None or df.empty:
        return result

    for _, row in df.iterrows():
        period = str(row.get("REPORT_DATE", ""))
        report_type = str(row.get("REPORT_TYPE", ""))
        year = _extract_year_from_date(period)
        if year is None:
            continue

        is_year_end = "年报" in report_type
        is_current = str(CURRENT_YEAR) in period
        if not (is_year_end or is_current):
            continue

        # Asset-liability ratio
        total_assets = _safe_float(row.get("TOTAL_ASSETS"))
        total_liabilities = _safe_float(row.get("TOTAL_LIABILITIES"))
        if total_assets and total_liabilities and total_assets > 0:
            result["asset_liability"][year] = round((total_liabilities / total_assets) * 100, 2)

        # Net assets per share = 归母权益 / 股本 (1元面值 ≈ 股数)
        parent_equity = _safe_float(row.get("TOTAL_PARENT_EQUITY"))
        share_capital = _safe_float(row.get("SHARE_CAPITAL"))
        if parent_equity and share_capital and share_capital > 0:
            result["net_assets"][year] = round(parent_equity / share_capital, 2)

    _set_cache(cache_key, result)
    return result


# ================================================================
#  Revenue structure
# ================================================================

def _get_revenue_structure(stock_code: str, company_info: dict, industry: str = "") -> list[dict]:
    """Build revenue structure overview from available data sources."""
    cache_key = f"rev_struct_{stock_code}"
    cached = _cached(cache_key, ttl=86400)
    if cached is not None:
        return cached

    structure = []

    # 1. Industry
    ind = (company_info.get("行业")
           or company_info.get("所属行业")
           or industry)
    if not ind:
        ai = company_info.get("affiliate_industry", "")
        if ai and isinstance(ai, str):
            import json as _json
            try:
                ind = _json.loads(ai.replace("'", '"')).get("ind_name", "")
            except Exception:
                pass
    if ind:
        structure.append({"category": "所属行业", "value": ind})

    # 2. Main business description
    main_biz = (company_info.get("main_operation_business", "")
               or company_info.get("主营业务", ""))
    if main_biz:
        structure.append({"category": "主营业务", "value": main_biz})

    # 3. Detailed business scope
    scope = company_info.get("operating_scope", "")
    if scope and scope != main_biz:
        structure.append({"category": "经营范围", "value": scope})

    # 4. Get margin / ROE from YJBB (latest year-end)
    gross_margin = None
    roe_val = None
    latest_rev = None
    try:
        for try_date in [f"{COMPLETE_YEARS[-1]}1231", f"{CURRENT_YEAR}0331"]:
            try:
                df = ak.stock_yjbb_em(date=try_date)
                if df is None or df.empty:
                    continue
                row = df[df["股票代码"].astype(str) == str(stock_code)]
                if not row.empty:
                    r = row.iloc[0]
                    gross_margin = _safe_float(r.get("销售毛利率"))
                    roe_val = _safe_float(r.get("净资产收益率"))
                    latest_rev = _safe_float(r.get("营业总收入-营业总收入"))
                    if latest_rev:
                        latest_rev = round(latest_rev / 100000000, 2)
                    break
            except Exception:
                continue
    except Exception:
        pass

    if gross_margin is not None:
        structure.append({"category": "销售毛利率", "value": f"{gross_margin:.2f}%"})
    if roe_val is not None:
        structure.append({"category": "净资产收益率", "value": f"{roe_val:.2f}%"})
    if latest_rev is not None:
        structure.append({"category": f"{COMPLETE_YEARS[-1]}年营业收入", "value": f"{latest_rev}亿元"})

    # 5. Company scale info
    reg_cap = company_info.get("reg_asset", "") or company_info.get("注册资金", "")
    if reg_cap:
        try:
            cap = float(reg_cap) / 100000000
            structure.append({"category": "注册资本", "value": f"{cap:.2f}亿元"})
        except Exception:
            pass

    staff = company_info.get("staff_num", "")
    if staff:
        structure.append({"category": "员工人数", "value": f"{staff}人"})

    listed_date = company_info.get("listed_date", "")
    if listed_date and listed_date.isdigit():
        from datetime import datetime as _dt
        try:
            ts = int(listed_date) / 1000
            date_str = _dt.fromtimestamp(ts).strftime("%Y-%m-%d")
            structure.append({"category": "上市日期", "value": date_str})
        except Exception:
            pass

    _set_cache(cache_key, structure if structure else [])
    return structure if structure else []
