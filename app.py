"""Stock Valuation Dashboard — run with:  streamlit run app.py"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from valuation import db
from valuation.bands import BAND_ORDER, BANDS, NO_VALUATION, BandThresholds
from valuation.importer import rows_from_tsv, rows_from_xlsx, xlsx_sheet_names

st.set_page_config(page_title="Stock Valuation Matrix", page_icon="📈", layout="wide")


@st.cache_resource
def get_con():
    return db.connect()


con = get_con()


def band_css(band: str) -> str:
    bg, fg, _ = BANDS.get(band, BANDS[NO_VALUATION])
    return f"background-color:{bg};color:{fg};font-weight:600"


def flash(msg: str) -> None:
    st.session_state["flash"] = msg


if msg := st.session_state.pop("flash", None):
    st.toast(msg, icon="✅")

# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Refresh")
    st.button("🔄 Refresh prices", disabled=True, width="stretch",
              help="Coming in step 2: Yahoo Finance, with Claude as a fallback")
    st.button("🧠 Refresh valuations", disabled=True, width="stretch",
              help="Coming in step 3: Claude research per ticker")
    st.caption("Scheduled monthly/quarterly refresh arrives in step 5.")
    st.divider()
    st.header("Signal bands")
    t = db.get_thresholds(con)
    legend = {
        "Strong Buy": f"≥ {t.strong_buy:+.0%}",
        "Add": f"{t.add:+.0%} to {t.strong_buy:+.0%}",
        "Hold": f"{t.trim:+.0%} to {t.add:+.0%}",
        "Trim": f"{t.sell:+.0%} to {t.trim:+.0%}",
        "Sell": f"≤ {t.sell:+.0%}",
        NO_VALUATION: "missing Mid or price",
    }
    for band in BAND_ORDER:
        bg, fg, meaning = BANDS[band]
        st.markdown(
            f"<div style='background:{bg};color:{fg};padding:4px 8px;border-radius:6px;margin:3px 0;"
            f"font-size:0.85rem'><b>{band}</b> · {legend[band]}<br><span style='opacity:.85'>{meaning}</span></div>",
            unsafe_allow_html=True)
    st.caption("Mid vs Price = (Mid − Price) ÷ Price")

df = db.load_table(con)

tab_dash, tab_edit, tab_import, tab_hist, tab_settings = st.tabs(
    ["📊 Dashboard", "✏️ Edit tickers", "📥 Import", "🕘 History", "⚙️ Settings"])

# ---------------- dashboard ----------------
with tab_dash:
    st.title("Stock Valuation Matrix")
    if df.empty:
        st.info("No tickers yet. Use **📥 Import** to load your Excel sheet (2025 tab), "
                "or add tickers in **✏️ Edit tickers**.")
    else:
        counts = df["band"].value_counts()
        cols = st.columns(len(BAND_ORDER))
        for c, band in zip(cols, BAND_ORDER):
            c.metric(band, int(counts.get(band, 0)))

        f1, f2, f3, f4 = st.columns([3, 2, 2, 1.3])
        bands_sel = f1.pills("Signal", BAND_ORDER, selection_mode="multi", default=BAND_ORDER) or BAND_ORDER
        search = f2.text_input("Search", placeholder="ticker or company")
        sort = f3.selectbox("Sort", ["Sheet order", "Biggest upside first", "Biggest downside first",
                                     "Oldest valuation first", "Ticker A→Z"])
        etfs = f4.radio("Show", ["All", "Stocks", "ETFs"], horizontal=False)

        view = df[df["band"].isin(bands_sel)]
        if search:
            s = search.lower()
            view = view[view["ticker"].str.lower().str.contains(s, regex=False)
                        | view["company"].str.lower().str.contains(s, regex=False)]
        if etfs != "All":
            view = view[view["is_etf"] == (etfs == "ETFs")]
        if sort == "Biggest upside first":
            view = view.sort_values("mid_vs_price", ascending=False, na_position="last")
        elif sort == "Biggest downside first":
            view = view.sort_values("mid_vs_price", ascending=True, na_position="last")
        elif sort == "Oldest valuation first":
            view = view.sort_values("valuation_updated", ascending=True, na_position="first")
        elif sort == "Ticker A→Z":
            view = view.sort_values("ticker")

        def money(v):
            return "" if pd.isna(v) else f"${v:,.2f}"

        def gap_fmt(v):
            if pd.isna(v):
                return "—"
            return "0%" if abs(v) < 0.005 else f"{v:+.0%}"

        def fmt(series, f):
            return [("" if pd.isna(v) else f(v)) for v in series]

        updated = pd.to_datetime(view["valuation_updated"], errors="coerce")
        # Display copy is pre-formatted text so blanks stay blank; use the Sort control to sort by value.
        show = pd.DataFrame({
            "Signal": view["band"].tolist(),
            "Company": view["company"].tolist(),
            "Ticker": (view["ticker"] + view["is_etf"].map({True: " · ETF", False: ""})).tolist(),
            "Price": fmt(view["price"], lambda v: f"${v:,.2f}"),
            "Change": fmt(view["change_pct"], lambda v: f"{v:+.2%}"),
            "P/E": fmt(view["pe"], lambda v: f"{v:.2f}"),
            "Mid vs Price": [gap_fmt(v) for v in view["mid_vs_price"]],
            "Low": fmt(view["low"], money),
            "Mid": fmt(view["mid"], money),
            "High": fmt(view["high"], money),
            "Updated": fmt(updated, lambda v: f"{v.month}/{v.day}/{v.year}"),
            "Buy Cycle": view["buy_cycle"].fillna("").tolist(),
            "Sell Cycle": view["sell_cycle"].fillna("").tolist(),
        })
        bands_col = show["Signal"]
        changes = view["change_pct"].tolist()

        def row_style(row):
            css = band_css(bands_col[row.name])
            ch = changes[row.name]
            ch_css = "" if pd.isna(ch) or ch == 0 else ("color:#1e8e3e" if ch > 0 else "color:#d93025")
            return [css if c in ("Signal", "Mid vs Price") else ch_css if c == "Change" else ""
                    for c in row.index]

        right = ["Price", "Change", "P/E", "Mid vs Price", "Low", "Mid", "High", "Updated"]
        styler = (show.style.apply(row_style, axis=1)
                  .set_properties(subset=right, **{"text-align": "right"}))
        num = lambda label: st.column_config.Column(label, width=95)
        st.dataframe(styler, hide_index=True, width="stretch",
                     height=min(35 * (len(show) + 1) + 4, 1400),
                     column_config={"Signal": st.column_config.Column(width=100),
                                    "Company": st.column_config.Column(width=300),
                                    "Ticker": st.column_config.Column(width=85),
                                    "Price": num("Price"), "Low": num("Low"), "Mid": num("Mid"),
                                    "High": num("High"),
                                    "Mid vs Price": st.column_config.Column(width=95),
                                    "Change": st.column_config.Column(width=75),
                                    "P/E": st.column_config.Column(width=65),
                                    "Updated": st.column_config.Column(width=95)})

        stale = df["valuation_updated"].isna() & df["mid"].notna()
        st.caption(f"{len(view)} of {len(df)} tickers shown · "
                   f"{int((df['band'] == NO_VALUATION).sum())} without valuation · "
                   f"{int(stale.sum())} valued but missing an Updated date. "
                   "Prices shown are from the last import until live refresh is added (step 2).")
        st.download_button("⬇️ Download CSV", view.drop(columns=["sources_json"]).to_csv(index=False),
                           file_name=f"valuations_{date.today():%Y-%m-%d}.csv", mime="text/csv")

# ---------------- edit ----------------
with tab_edit:
    st.subheader("Add, edit or remove tickers")
    st.caption("Add a row at the bottom, edit any cell, or select rows and press the 🗑 icon to delete. "
               "Then click **Save changes**. Every change keeps the previous values in 🕘 History. "
               "Tick **Pinned** to stop future automatic refreshes from overwriting your own numbers.")
    full = db.load_table(con, include_inactive=True)
    grid = full[["id"] + db.EDITABLE].copy()
    grid["valuation_updated"] = pd.to_datetime(grid["valuation_updated"], errors="coerce").dt.date
    edited = st.data_editor(
        grid, key="editor", num_rows="dynamic", hide_index=True, width="stretch", height=620,
        column_order=db.EDITABLE,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", required=True, max_chars=12),
            "company": st.column_config.TextColumn("Company"),
            "yahoo_symbol": st.column_config.TextColumn(
                "Yahoo symbol", help="Auto-filled. Override for non-US listings, e.g. CSU.TO, PSE.PS"),
            "is_etf": st.column_config.CheckboxColumn("ETF", default=False),
            "active": st.column_config.CheckboxColumn("Active", default=True,
                                                      help="Untick to hide without deleting"),
            "price": st.column_config.NumberColumn("Price", format="$%.2f", min_value=0),
            "low": st.column_config.NumberColumn("Low", format="$%.2f", min_value=0),
            "mid": st.column_config.NumberColumn("Mid", format="$%.2f", min_value=0),
            "high": st.column_config.NumberColumn("High", format="$%.2f", min_value=0),
            "valuation_updated": st.column_config.DateColumn("Updated", format="M/D/YYYY"),
            "buy_cycle": st.column_config.TextColumn("Buy Cycle"),
            "sell_cycle": st.column_config.TextColumn("Sell Cycle"),
            "pinned": st.column_config.CheckboxColumn("Pinned", default=False),
        })
    c1, c2 = st.columns([1, 5])
    if c1.button("💾 Save changes", type="primary"):
        tickers = edited["ticker"].dropna().astype(str).str.strip().str.upper()
        dupes = tickers[tickers.duplicated()].unique()
        bad = edited[(edited["low"] > edited["mid"]) | (edited["mid"] > edited["high"])]["ticker"].tolist()
        if len(dupes):
            st.error(f"Duplicate tickers: {', '.join(dupes)}")
        elif bad:
            st.error(f"Low ≤ Mid ≤ High is violated for: {', '.join(map(str, bad))}")
        else:
            try:
                stats = db.apply_edits(con, full, edited)
            except Exception as e:  # surface constraint errors to the user
                st.error(f"Couldn't save: {e}")
            else:
                st.session_state.pop("editor", None)
                flash(f"Saved: {stats['added']} added, {stats['updated']} updated, {stats['removed']} removed")
                st.rerun()
    c2.caption("Unsaved edits are lost if you switch tabs and reload.")

# ---------------- import ----------------
with tab_import:
    st.subheader("Import from your Excel sheet")
    st.caption("Reads the Company, Ticker symbol, Price, Change (%), P/E, Low, Mid, High, Updated, "
               "Buy Cycle and Sell Cycle columns. Formatting and colours are ignored; signals are recalculated.")
    src = st.radio("Source", ["Upload .xlsx", "Paste from Excel"], horizontal=True)
    rows, err = None, None
    if src == "Upload .xlsx":
        up = st.file_uploader("Workbook", type=["xlsx", "xlsm"])
        if up:
            try:
                sheets = xlsx_sheet_names(up)
                sheet = st.selectbox("Sheet", sheets, index=sheets.index("2025") if "2025" in sheets else 0)
                up.seek(0)
                rows = rows_from_xlsx(up, sheet)
            except Exception as e:
                err = str(e)
    else:
        txt = st.text_area("Select the table in Excel (including the header row), copy, and paste here",
                           height=200)
        if txt.strip():
            try:
                rows = rows_from_tsv(txt)
            except Exception as e:
                err = str(e)
    if err:
        st.error(err)
    if rows:
        prev = pd.DataFrame(rows)
        existing = set(df["ticker"])
        prev.insert(0, "status", ["update" if t in existing else "new" for t in prev["ticker"]])
        st.write(f"**{len(prev)} tickers found** · {(prev.status == 'new').sum()} new · "
                 f"{(prev.status == 'update').sum()} already in dashboard")
        st.dataframe(prev[["status", "ticker", "company", "yahoo_symbol", "is_etf", "price", "low", "mid",
                           "high", "valuation_updated", "buy_cycle", "sell_cycle"]],
                     hide_index=True, width="stretch", height=320)
        mode = st.radio("Mode", ["merge", "replace"], horizontal=True, format_func={
            "merge": "Merge: update matching tickers and add new ones",
            "replace": "Replace: also remove tickers that aren't in this sheet"}.get)
        if st.button("📥 Import", type="primary"):
            stats = db.import_rows(con, rows, mode=mode)
            flash(f"Imported: {stats['added']} added, {stats['updated']} updated, {stats['removed']} removed")
            st.rerun()

# ---------------- history ----------------
with tab_hist:
    st.subheader("History")
    st.caption("A row is saved here every time a ticker's values are overwritten or the ticker is removed.")
    tick = st.selectbox("Ticker", ["All"] + sorted(set(df["ticker"]) | set(
        r["ticker"] for r in con.execute("SELECT DISTINCT ticker FROM history"))))
    hist = db.load_history(con, None if tick == "All" else tick)
    if hist.empty:
        st.info("No history yet.")
    else:
        st.dataframe(hist, hide_index=True, width="stretch", height=500)

# ---------------- settings ----------------
with tab_settings:
    st.subheader("Signal band thresholds")
    t = db.get_thresholds(con)
    with st.form("bands"):
        c = st.columns(4)
        sb = c[0].number_input("Strong Buy at ≥ (%)", value=t.strong_buy * 100, step=1.0)
        ad = c[1].number_input("Add at ≥ (%)", value=t.add * 100, step=1.0)
        tr = c[2].number_input("Trim at ≤ (%)", value=t.trim * 100, step=1.0)
        se = c[3].number_input("Sell at ≤ (%)", value=t.sell * 100, step=1.0)
        a, b = st.columns([1, 6])
        save = a.form_submit_button("Save", type="primary")
        reset = b.form_submit_button("Reset to defaults")
    if save or reset:
        nt = BandThresholds() if reset else BandThresholds(sb / 100, ad / 100, tr / 100, se / 100)
        try:
            nt.validate()
        except ValueError as e:
            st.error(str(e))
        else:
            db.set_setting(con, "band_thresholds", nt.to_dict())
            flash("Band thresholds saved")
            st.rerun()
    st.divider()
    st.caption(f"Database: `{db.DEFAULT_DB}`. Back this file up to keep your data and history.")
