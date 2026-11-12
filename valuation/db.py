"""SQLite storage: tickers, current values, history and settings."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .bands import BandThresholds, classify, mid_vs_price

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path(os.environ.get("VALUATION_DB", ROOT / "data" / "valuations.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    company TEXT,
    exchange TEXT,
    yahoo_symbol TEXT,
    is_etf INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valuations (
    ticker_id INTEGER PRIMARY KEY REFERENCES tickers(id) ON DELETE CASCADE,
    price REAL, change_pct REAL, pe REAL,
    price_source TEXT, price_updated_at TEXT,
    low REAL, mid REAL, high REAL,
    valuation_updated TEXT,
    buy_cycle TEXT, sell_cycle TEXT,
    valuation_source TEXT, confidence TEXT, sources_json TEXT,
    pinned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    archived_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_ticker ON history(ticker, archived_at);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

TICKER_FIELDS = ["ticker", "company", "exchange", "yahoo_symbol", "is_etf", "active", "sort_order"]
VALUE_FIELDS = ["price", "change_pct", "pe", "price_source", "price_updated_at", "low", "mid", "high",
                "valuation_updated", "buy_cycle", "sell_cycle", "valuation_source", "confidence",
                "sources_json", "pinned"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


# ---------- settings ----------
def get_setting(con, key: str, default=None):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(con, key: str, value) -> None:
    with con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def get_thresholds(con) -> BandThresholds:
    return BandThresholds.from_dict(get_setting(con, "band_thresholds"))


# ---------- reads ----------
def snapshot(con, ticker_id: int) -> dict | None:
    row = con.execute("SELECT t.*, v.* FROM tickers t LEFT JOIN valuations v ON v.ticker_id=t.id "
                      "WHERE t.id=?", (ticker_id,)).fetchone()
    return dict(row) if row else None


def load_table(con, include_inactive: bool = False) -> pd.DataFrame:
    q = ("SELECT t.id, t.ticker, t.company, t.exchange, t.yahoo_symbol, t.is_etf, t.active, t.sort_order, "
         + ", ".join(f"v.{f}" for f in VALUE_FIELDS) +
         " FROM tickers t LEFT JOIN valuations v ON v.ticker_id=t.id"
         + ("" if include_inactive else " WHERE t.active=1") + " ORDER BY t.sort_order, t.id")
    df = pd.read_sql_query(q, con)
    t = get_thresholds(con)
    df["is_etf"] = df["is_etf"].astype(bool)
    df["active"] = df["active"].astype(bool)
    df["pinned"] = df["pinned"].fillna(0).astype(bool)
    df["mid_vs_price"] = [mid_vs_price(m, p) for m, p in zip(df["mid"], df["price"])]
    df["band"] = [classify(g, t) for g in df["mid_vs_price"]]
    return df


def load_history(con, ticker: str | None = None) -> pd.DataFrame:
    q, args = "SELECT * FROM history", ()
    if ticker:
        q, args = q + " WHERE ticker=?", (ticker,)
    df = pd.read_sql_query(q + " ORDER BY archived_at DESC, id DESC", con, params=args)
    if df.empty:
        return df
    snaps = pd.json_normalize([json.loads(s) for s in df["snapshot_json"]])
    keep = [c for c in ["price", "low", "mid", "high", "valuation_updated", "buy_cycle", "sell_cycle",
                        "company", "is_etf"] if c in snaps]
    return pd.concat([df[["archived_at", "ticker", "reason"]], snaps[keep]], axis=1)


# ---------- writes ----------
def _archive(con, ticker_id: int, reason: str) -> None:
    snap = snapshot(con, ticker_id)
    if snap:
        con.execute("INSERT INTO history(ticker,snapshot_json,reason,archived_at) VALUES(?,?,?,?)",
                    (snap["ticker"], json.dumps(snap, default=str), reason, now()))


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def upsert(con, row: dict, reason: str, ticker_id: int | None = None) -> int:
    """Insert or update one ticker + its values. Archives the previous state first."""
    row = {k: _clean(v) for k, v in row.items()}
    if not row.get("ticker"):
        raise ValueError("Ticker is required")
    row["ticker"] = str(row["ticker"]).upper()
    if ticker_id is None:
        hit = con.execute("SELECT id FROM tickers WHERE ticker=?", (row["ticker"],)).fetchone()
        ticker_id = hit["id"] if hit else None
    if ticker_id is not None:
        _archive(con, ticker_id, reason)
        tf = {k: row[k] for k in TICKER_FIELDS if k in row}
        if tf:
            con.execute(f"UPDATE tickers SET {', '.join(f'{k}=?' for k in tf)} WHERE id=?",
                        (*tf.values(), ticker_id))
    else:
        if row.get("sort_order") is None:
            row["sort_order"] = (con.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tickers")
                                 .fetchone()[0])
        tf = {k: row.get(k) for k in TICKER_FIELDS}
        tf["is_etf"] = int(bool(tf["is_etf"]))
        tf["active"] = 1 if tf["active"] is None else int(bool(tf["active"]))
        tf["company"] = tf["company"] or row["ticker"]
        if not tf["yahoo_symbol"]:
            from .importer import yahoo_symbol
            tf["yahoo_symbol"] = yahoo_symbol(row["ticker"], tf["exchange"])
        cur = con.execute(f"INSERT INTO tickers({', '.join(tf)}, added_at) VALUES({', '.join('?' * len(tf))}, ?)",
                          (*tf.values(), now()))
        ticker_id = cur.lastrowid
        con.execute("INSERT INTO valuations(ticker_id) VALUES(?)", (ticker_id,))
    vf = {k: row[k] for k in VALUE_FIELDS if k in row}
    if "pinned" in vf:
        vf["pinned"] = int(bool(vf["pinned"]))
    if vf:
        con.execute("INSERT OR IGNORE INTO valuations(ticker_id) VALUES(?)", (ticker_id,))
        con.execute(f"UPDATE valuations SET {', '.join(f'{k}=?' for k in vf)} WHERE ticker_id=?",
                    (*vf.values(), ticker_id))
    return ticker_id


def delete(con, ticker_id: int, reason: str = "removed") -> None:
    _archive(con, ticker_id, reason)
    con.execute("DELETE FROM tickers WHERE id=?", (ticker_id,))


def import_rows(con, rows: list[dict], mode: str = "merge", source: str = "excel import") -> dict:
    """mode='merge': update matching tickers, add new ones. mode='replace': also remove tickers not in rows."""
    if mode not in ("merge", "replace"):
        raise ValueError(mode)
    stats = {"added": 0, "updated": 0, "removed": 0}
    with con:
        existing = {r["ticker"]: r["id"] for r in con.execute("SELECT id, ticker FROM tickers")}
        for r in rows:
            r = {**r, "price_source": "excel import", "valuation_source": source,
                 "price_updated_at": now()}
            if r["ticker"] in existing:
                upsert(con, r, reason=source, ticker_id=existing[r["ticker"]])
                stats["updated"] += 1
            else:
                upsert(con, r, reason=source)
                stats["added"] += 1
        if mode == "replace":
            incoming = {r["ticker"] for r in rows}
            for t, tid in existing.items():
                if t not in incoming:
                    delete(con, tid, reason=f"{source} (replace)")
                    stats["removed"] += 1
    return stats


EDITABLE = ["ticker", "company", "yahoo_symbol", "is_etf", "active", "price", "low", "mid", "high",
            "valuation_updated", "buy_cycle", "sell_cycle", "pinned"]


def _differs(a, b) -> bool:
    a, b = _clean(a), _clean(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) > 1e-9
    return a != b


def apply_edits(con, original: pd.DataFrame, edited: pd.DataFrame) -> dict:
    """Diff the editor grid against the original and persist adds / changes / removals."""
    stats = {"added": 0, "updated": 0, "removed": 0}
    orig = original.set_index("id")
    with con:
        kept_ids = set()
        for _, r in edited.iterrows():
            rid = _clean(r.get("id"))
            data = {k: r.get(k) for k in EDITABLE if k in r}
            if isinstance(data.get("valuation_updated"), (pd.Timestamp, datetime)):
                data["valuation_updated"] = data["valuation_updated"].date().isoformat()
            elif hasattr(data.get("valuation_updated"), "isoformat"):
                data["valuation_updated"] = data["valuation_updated"].isoformat()
            if rid is None:
                if _clean(data.get("ticker")):
                    upsert(con, data, reason="manual add")
                    stats["added"] += 1
                continue
            rid = int(rid)
            kept_ids.add(rid)
            before = orig.loc[rid]
            changed = {k: v for k, v in data.items() if _differs(v, before.get(k))}
            if changed:
                if "ticker" in changed:
                    changed["ticker"] = str(changed["ticker"]).strip().upper()
                    if not changed["ticker"]:
                        raise ValueError("Ticker can't be blank")
                    if _clean(data.get("yahoo_symbol")) == _clean(before.get("yahoo_symbol")):
                        from .importer import yahoo_symbol
                        changed["yahoo_symbol"] = yahoo_symbol(changed["ticker"], _clean(before.get("exchange")))
                if any(k in changed for k in ("low", "mid", "high", "buy_cycle", "sell_cycle")):
                    changed.setdefault("valuation_source", "manual edit")
                upsert(con, {"ticker": data.get("ticker") or before["ticker"], **changed},
                       reason="manual edit", ticker_id=rid)
                stats["updated"] += 1
        for rid in set(orig.index) - kept_ids:
            delete(con, int(rid), reason="manual remove")
            stats["removed"] += 1
    return stats
