"""Import the Excel valuation matrix (pasted TSV or .xlsx) into normalised rows."""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any, Iterable

# Exchange MIC -> Yahoo Finance suffix. US venues need no suffix.
YAHOO_SUFFIX = {
    "XNYS": "", "XNAS": "", "ARCX": "", "BATS": "", "XASE": "", "XNGS": "",
    "XTSE": ".TO", "XTSX": ".V", "XPHS": ".PS", "XLON": ".L", "XHKG": ".HK",
    "XASX": ".AX", "XETR": ".DE", "XPAR": ".PA", "XAMS": ".AS", "XTKS": ".T",
    "XSWX": ".SW", "XCSE": ".CO", "XSTO": ".ST", "XMIL": ".MI", "XMAD": ".MC",
}
ETF_HINTS = ("ETF", "SPDR", "ISHARES", "VANGUARD", "VANECK", "ROUNDHILL", "TIDAL",
             "GLOBAL X", "GLBL X", "INVESCO", "PROSHARES", "WISDOMTREE")
_COMPANY_RE = re.compile(r"\(([A-Z]{3,5}):([^)]+)\)\s*$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9 .\-]{0,9}$")

# normalised header -> field name
HEADER_MAP = {
    "company": "company", "ticker symbol": "ticker_cell", "ticker": "ticker_cell",
    "price": "price", "change (%)": "change_pct", "change %": "change_pct",
    "p/e": "pe", "low": "low", "mid": "mid", "high": "high",
    "updated": "valuation_updated", "buy cycle": "buy_cycle", "sell cycle": "sell_cycle",
}


def _norm_header(h: Any) -> str:
    return re.sub(r"\s+", " ", str(h or "")).strip().lower()


def _is_error(v: Any) -> bool:
    return isinstance(v, str) and v.strip().startswith("#")


def parse_number(v: Any) -> float | None:
    """'$1,662.85' -> 1662.85; '' / '#FIELD!' -> None; numbers pass through."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None
    s = str(v).strip()
    if not s or _is_error(s):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[$,\s()€£¥₱]|CAD|USD", "", s)
    if s.endswith("%"):
        s = s[:-1]
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


def parse_percent(v: Any) -> float | None:
    """Text '-0.80%' -> -0.008. Numeric cells from xlsx are already fractions."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    n = parse_number(v)
    if n is None:
        return None
    return n / 100.0 if "%" in str(v) else n


def parse_date(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse_text(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def yahoo_symbol(ticker: str, exchange: str | None) -> str:
    suffix = YAHOO_SUFFIX.get(exchange or "", "")
    sym = ticker.strip().upper()
    if suffix == "":  # US style: BRK B / BRK.B -> BRK-B
        sym = re.sub(r"[ .]+", "-", sym)
    else:
        sym = sym.replace(" ", "-")
    return sym + suffix


def resolve_ticker(company: str | None, ticker_cell: str | None) -> tuple[str | None, str | None]:
    """Prefer '(XNAS:FTNT)' in the company name; fall back to the ticker cell."""
    exchange = sym = None
    if company:
        m = _COMPANY_RE.search(company)
        if m:
            exchange, sym = m.group(1), m.group(2).strip()
    cell = (ticker_cell or "").strip().upper()
    if not sym and _TICKER_RE.match(cell):
        sym = cell
    return (sym.upper() if sym else None), exchange


def looks_like_etf(company: str | None, pe_raw: Any) -> bool:
    name = (company or "").upper()
    return _is_error(pe_raw) or any(h in name for h in ETF_HINTS)


def rows_from_grid(grid: Iterable[list[Any]]) -> list[dict]:
    """Find the header row (contains 'Ticker symbol') and parse the rows below it."""
    grid = [list(r) for r in grid]
    header_idx = next((i for i, r in enumerate(grid)
                       if any(_norm_header(c) in ("ticker symbol", "ticker") for c in r)), None)
    if header_idx is None:
        raise ValueError("Couldn't find a header row with a 'Ticker symbol' column.")
    cols: dict[str, int] = {}
    for j, h in enumerate(grid[header_idx]):
        f = HEADER_MAP.get(_norm_header(h))
        if f and f not in cols:  # first 'Price' wins over 'Market Price'
            cols[f] = j
    if "company" not in cols and "ticker_cell" not in cols:
        raise ValueError("Header row needs a 'Company' or 'Ticker symbol' column.")

    def get(r: list, f: str) -> Any:
        j = cols.get(f)
        return r[j] if j is not None and j < len(r) else None

    out, seen = [], set()
    for order, r in enumerate(grid[header_idx + 1:]):
        if not any(parse_text(c) for c in r):
            continue
        company = parse_text(get(r, "company"))
        ticker, exchange = resolve_ticker(company, parse_text(get(r, "ticker_cell")))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append({
            "ticker": ticker,
            "company": company or ticker,
            "exchange": exchange,
            "yahoo_symbol": yahoo_symbol(ticker, exchange),
            "is_etf": looks_like_etf(company, get(r, "pe")),
            "sort_order": order,
            "price": parse_number(get(r, "price")),
            "change_pct": parse_percent(get(r, "change_pct")),
            "pe": parse_number(get(r, "pe")),
            "low": parse_number(get(r, "low")),
            "mid": parse_number(get(r, "mid")),
            "high": parse_number(get(r, "high")),
            "valuation_updated": parse_date(get(r, "valuation_updated")),
            "buy_cycle": parse_text(get(r, "buy_cycle")),
            "sell_cycle": parse_text(get(r, "sell_cycle")),
        })
    return out


def rows_from_tsv(text: str) -> list[dict]:
    return rows_from_grid(csv.reader(io.StringIO(text), delimiter="\t"))


def xlsx_sheet_names(file) -> list[str]:
    from openpyxl import load_workbook
    wb = load_workbook(file, read_only=True, data_only=True)
    try:
        return wb.sheetnames
    finally:
        wb.close()


def rows_from_xlsx(file, sheet: str = "2025") -> list[dict]:
    from openpyxl import load_workbook
    wb = load_workbook(file, read_only=True, data_only=True)
    try:
        if sheet not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet}' not found. Sheets: {', '.join(wb.sheetnames)}")
        return rows_from_grid(wb[sheet].iter_rows(values_only=True))
    finally:
        wb.close()
