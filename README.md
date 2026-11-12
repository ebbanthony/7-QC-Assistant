# Stock Valuation Dashboard

A local dashboard that replaces the Excel valuation matrix. It shows each ticker's price against your
intrinsic-value range (Low / Mid / High) and colours it by how far the price is from **Mid**:

| Signal | Mid vs Price | Meaning |
|---|---|---|
| Strong Buy | ≥ +30% | Obvious buy / add |
| Add | +10% to +30% | Accumulate |
| Hold | −10% to +10% | Fairly valued |
| Trim | −25% to −10% | Trim / take some profit |
| Sell | ≤ −25% | Sell / take profit |

The thresholds are editable in **⚙️ Settings**. See [PLAN.md](PLAN.md) for the full roadmap.

## Privacy
Your tickers, valuations and history live only in `data/valuations.db` on your PC.
That folder is git-ignored and is never committed (this repository is public).
The app listens on `localhost` only.

## Setup (Windows, one time)
1. Unzip the app anywhere you like (e.g. `Documents\Valuation Dashboard`).
2. Double-click **`setup.bat`**. If Python isn't installed, it installs it with winget; then run `setup.bat` again.

**Updating:** unzip a new version over the old folder. Your data is in the `data` folder, which updates never touch.

## Use
1. Double-click **`Launch Dashboard.bat`**. Your browser opens at http://localhost:8501.
2. **📥 Import**: upload your workbook (the `2025` sheet is pre-selected) or paste the table copied from Excel,
   check the preview, and click **Import**.
3. **📊 Dashboard**: filter by signal, search, and sort by upside or downside.
4. **✏️ Edit tickers**: add, edit or delete rows, then **Save changes**. Previous values go to **🕘 History**.
   Use **Pinned** to protect your own numbers from future automatic refreshes.

Close the black console window to stop the app.

## Status
- [x] Step 1: import, local database, dashboard, signal bands, ticker editor, history
- [ ] Step 2: live prices (Yahoo Finance, with Claude as a fallback)
- [ ] Step 3: Claude valuation research (stocks)
- [ ] Step 4: ETF look-through valuations
- [ ] Step 5: monthly/quarterly schedule (Windows Task Scheduler) and settings
- [ ] Step 6: Excel export and history charts

## Developers
```
pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```
Set `VALUATION_DB=path\to\file.db` to use a different database file.
