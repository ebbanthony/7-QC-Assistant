import pandas as pd
import pytest

from valuation import db
from valuation.bands import BandThresholds, classify, mid_vs_price, NO_VALUATION
from valuation.importer import rows_from_tsv, yahoo_symbol, parse_number, parse_percent

# Illustrative numbers only (not real valuations).
SAMPLE = "\n".join([
    "Stock Valuation Matrix\t\t\t\t\t\tAverage of Intrinsic Valuations",
    "Company\tTicker symbol\tPrice\tChange (%)\tP/E\t Mid vs Price \tMarket Price\t Low \t Mid \t High \t Updated \tBuy Cycle\tSell Cycle",
    "ACME CORP (XNYS:ACM)\t ACM \t $100.00 \t-0.80%\t20.00\t10%\t $100.00 \t $80.00 \t $110.00 \t $1,300.00 \t10/19/2026\tLate Cycle\tEarly Cycle",
    "FORTINET, INC. (XNAS:FTNT)\t US Stocks \t $50.00 \t5.90%\t30\t-50%\t $50 \t $20.00 \t $25.00 \t $30.00 \t\tEarly Cycle\tLate Cycle",
    "Sel Sector:Tech SPDR (ARCX:XLK)\t XLK \t $191.00 \t0.80%\t#FIELD!\t-100%\t $191.0 \t\t\t\t\tEarly Cycle\tLate Cycle",
    "BERKSHIRE HATHAWAY INC. (XNYS:BRK B)\t BRK B \t $500 \t0%\t13\t0%\t$500\t$400\t$$520\t$600\t\t\t",
    "Constellation Software Inc. (XTSE:CSU)\t CSU \t $3,000.00 \t1.27%\t50\t67%\t$3000\t$4000\t$5,000\t$6000\t\tEarly\tLate",
])


def test_parsers():
    assert parse_number(" $1,662.85 ") == 1662.85
    assert parse_number("#FIELD!") is None and parse_number("") is None
    assert parse_percent("-0.80%") == pytest.approx(-0.008)
    assert parse_percent(0.0123) == 0.0123
    assert yahoo_symbol("BRK B", "XNYS") == "BRK-B"
    assert yahoo_symbol("CSU", "XTSE") == "CSU.TO"


def test_rows_from_tsv():
    rows = {r["ticker"]: r for r in rows_from_tsv(SAMPLE)}
    assert list(rows) == ["ACM", "FTNT", "XLK", "BRK B", "CSU"]
    acm = rows["ACM"]
    assert acm["price"] == 100 and acm["mid"] == 110 and acm["high"] == 1300
    assert acm["change_pct"] == pytest.approx(-0.008)
    assert acm["valuation_updated"] == "2026-10-19"
    assert rows["FTNT"]["exchange"] == "XNAS"            # recovered from company name
    assert rows["XLK"]["is_etf"] and rows["XLK"]["mid"] is None
    assert not rows["ACM"]["is_etf"]
    assert rows["CSU"]["yahoo_symbol"] == "CSU.TO"


def test_bands():
    t = BandThresholds()
    assert classify(mid_vs_price(130, 100), t) == "Strong Buy"
    assert classify(0.10, t) == "Add"
    assert classify(0.0, t) == "Hold"
    assert classify(-0.10, t) == "Trim"
    assert classify(-0.25, t) == "Sell"
    assert classify(None, t) == NO_VALUATION
    with pytest.raises(ValueError):
        BandThresholds(strong_buy=0.1, add=0.2).validate()


def test_import_edit_history_roundtrip():
    con = db.connect(":memory:")
    rows = rows_from_tsv(SAMPLE)
    assert db.import_rows(con, rows) == {"added": 5, "updated": 0, "removed": 0}
    df = db.load_table(con)
    assert df.set_index("ticker").loc["ACM", "band"] == "Add"
    assert df.set_index("ticker").loc["XLK", "band"] == NO_VALUATION

    # Re-import merges and archives
    assert db.import_rows(con, rows[:2], mode="replace") == {"added": 0, "updated": 2, "removed": 3}
    assert len(db.load_table(con)) == 2

    # Edit: change ACM mid, remove FTNT, add NEW
    orig = db.load_table(con)
    edited = orig.copy()
    edited.loc[edited.ticker == "ACM", "mid"] = 150.0
    edited = edited[edited.ticker != "FTNT"]
    edited = pd.concat([edited, pd.DataFrame([{"id": None, "ticker": "new", "company": "New Co"}])])
    assert db.apply_edits(con, orig, edited) == {"added": 1, "updated": 1, "removed": 1}
    now = db.load_table(con).set_index("ticker")
    assert now.loc["ACM", "band"] == "Strong Buy"
    assert now.loc["ACM", "valuation_source"] == "manual edit"
    assert "NEW" in now.index and now.loc["NEW", "yahoo_symbol"] == "NEW"
    hist = db.load_history(con, "ACM")
    assert hist.iloc[0]["mid"] == 110  # previous value kept

    # Rename ticker keeps id, regenerates yahoo symbol
    orig = db.load_table(con)
    edited = orig.copy()
    edited.loc[edited.ticker == "NEW", "ticker"] = "brk b"
    db.apply_edits(con, orig, edited)
    assert db.load_table(con).set_index("ticker").loc["BRK B", "yahoo_symbol"] == "BRK-B"


def test_thresholds_setting():
    con = db.connect(":memory:")
    db.set_setting(con, "band_thresholds", {"strong_buy": 0.5, "add": 0.2, "trim": -0.2, "sell": -0.4})
    assert db.get_thresholds(con).strong_buy == 0.5


def test_rows_from_xlsx(tmp_path):
    from datetime import datetime
    from openpyxl import Workbook
    from valuation.importer import rows_from_xlsx
    wb = Workbook()
    wb.active.title = "2024"
    ws = wb.create_sheet("2025")
    ws.append(["Stock Valuation Matrix", None, None, None, None, None, None, "Average of Intrinsic Valuations"])
    ws.append(["Company", "Ticker symbol", "Price", "Change (%)", "P/E", "Mid vs Price", "Market Price",
               "Low", "Mid", "High", "Updated", "Buy Cycle", "Sell Cycle"])
    ws.append(["ACME CORP (XNYS:ACM)", None, 100.0, -0.008, 20.0, 0.1, 100.0, 80, 110, 130,
               datetime(2026, 10, 19), "Late Cycle", "Early Cycle"])
    ws.append(["Some ETF (ARCX:ETFX)", "ETFX", 50.0, 0.01, "#FIELD!", -1, 50.0])
    path = tmp_path / "book.xlsx"
    wb.save(path)
    rows = {r["ticker"]: r for r in rows_from_xlsx(path, "2025")}
    assert rows["ACM"]["change_pct"] == -0.008 and rows["ACM"]["valuation_updated"] == "2026-10-19"
    assert rows["ETFX"]["is_etf"] and rows["ETFX"]["mid"] is None
    with pytest.raises(ValueError, match="not found"):
        rows_from_xlsx(path, "2023")
