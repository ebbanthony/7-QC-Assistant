"""Smoke-test the Streamlit app end to end with Streamlit's AppTest harness."""
import importlib

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_core import SAMPLE


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUATION_DB", str(tmp_path / "t.db"))
    import valuation.db as dbmod
    importlib.reload(dbmod)
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.run()
    yield at
    at.session_state  # keep fixture alive


def test_empty_then_paste_import_then_save_and_settings(app):
    assert not app.exception
    assert any("No tickers yet" in i.value for i in app.info)

    next(r for r in app.radio if r.label == "Source").set_value("Paste from Excel").run()
    app.text_area[0].input(SAMPLE).run()
    assert any("5 tickers found" in m.value for m in app.markdown)
    next(b for b in app.button if "Import" in b.label).click().run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["1", "1", "1", "0", "1", "1"]  # band counts

    next(b for b in app.button if "Save changes" in b.label).click().run()  # no-op save
    assert not app.exception

    app.number_input[0].set_value(60.0)
    next(b for b in app.button if b.label == "Save").click().run()
    assert not app.exception
