from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from framework import stacked_presets
from framework.stacked_presets import PresetError, PresetStore


ROOT = Path(__file__).resolve().parents[1]
PAGE = "2_📈_Stacked_Values_Enhanced Seconds.py"


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "presets.sqlite3"
    monkeypatch.setattr(stacked_presets, "STORE_PATH", path)
    return PresetStore(path)


def test_shared_store_round_trip_and_revisions(store):
    assert store.list() == []
    original = store.save("  Straße ✈️  ", ["C", "B", "A"], ["B", "C"])
    reopened = PresetStore(store.path)
    assert reopened.list() == [original]
    assert (original.name, original.columns, original.exclusions) == (
        "Straße ✈️", ("C", "B", "A"), ("B", "C")
    )
    with pytest.raises(PresetError, match="already exists"):
        reopened.save("STRASSE ✈️", ["A"], [])
    updated = reopened.save("A new name", ["A"], [], previous=original)
    assert updated.id == original.id
    with pytest.raises(PresetError, match="Apply the latest version"):
        store.save("Third name", ["A"], [], previous=original)
    with pytest.raises(PresetError, match="Apply the latest version"):
        store.delete(original)
    store.delete(updated)
    assert reopened.list() == []


def test_concurrent_saves(store):
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda n: PresetStore(store.path).save(f"Preset {n}", ["A"], []), range(12)))
    assert [item.name for item in store.list()] == sorted(f"Preset {n}" for n in range(12))


def test_storage_failures(store, tmp_path):
    invalid = b"corrupt file contents"
    store.path.write_bytes(invalid)
    with pytest.raises(PresetError, match="server operator"):
        store.list()
    with pytest.raises(PresetError, match="server operator"):
        store.save("Example", ["A"], [])
    assert store.path.read_bytes() == invalid

    unsupported = tmp_path / "unsupported.sqlite"
    with sqlite3.connect(unsupported) as db:
        db.execute("PRAGMA user_version = 3")
    db.close()
    with pytest.raises(PresetError, match="Unsupported preset store"):
        PresetStore(unsupported).list()
    with pytest.raises(PresetError, match="permissions"):
        PresetStore(store.path / "preset.sqlite").save("Example", ["A"], [])


def widget(app, kind, label):
    return next(w for w in getattr(app, kind) if w.label == label)


def page(columns):
    app = AppTest.from_file(str(ROOT / "pages" / PAGE))
    app.session_state["df_full"] = pd.DataFrame({c: [0, 1] for c in ["Seconds", *columns]})
    return app.run()


def test_legacy_presets_keep_current_view_mode_until_updated(store):
    with sqlite3.connect(store.path) as db:
        db.executescript("""
            CREATE TABLE presets (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE, columns_json TEXT NOT NULL,
                exclusions_json TEXT NOT NULL
            );
            INSERT INTO presets VALUES ('old', 1, 'Older preset', 'older preset', '["A"]', '[]');
            PRAGMA user_version = 1;
        """)
    db.close()
    assert store.list()[0].view_mode is None
    app = page(["A"])
    widget(app, "selectbox", "View mode").set_value("Full").run()
    widget(app, "selectbox", "Saved presets").select("old").run()
    widget(app, "button", "Apply preset").click().run()
    assert widget(app, "selectbox", "View mode").value == "Full"
    widget(app, "selectbox", "View mode").set_value("Stacked by All").run()
    assert widget(app, "text_input", "Active preset").value == ""
    widget(app, "button", "Update selected").click().run()
    assert store.list()[0].view_mode == "Stacked by All"
    widget(app, "selectbox", "View mode").set_value("Full").run()
    widget(app, "button", "Apply preset").click().run()
    assert widget(app, "selectbox", "View mode").value == "Stacked by All"
    assert not app.exception


def test_presets_save_hidden_exclusions_and_apply_in_another_session(store):
    author = page(["A", "B", "C"])
    reader = page(["A", "B"])
    widget(author, "multiselect", "Select columns to display").set_value(["C", "B", "A"]).run()
    widget(author, "selectbox", "View mode").set_value("Stacked by All").run()
    widget(author, "multiselect", "Exclusion rule").set_value(["B", "C"]).run()
    widget(author, "selectbox", "View mode").set_value("Full").run()
    widget(author, "text_input", "Active preset").set_value("Flight ✈️")
    widget(author, "button", "Save new").click().run()
    assert store.list()[0].exclusions == ("B", "C")

    reader.run()
    choice = widget(reader, "selectbox", "Saved presets")
    assert choice.options == ["Flight ✈️"]
    assert widget(reader, "multiselect", "Select columns to display").value == []
    choice.select(store.list()[0].id).run()
    widget(reader, "button", "Apply preset").click().run()
    assert widget(reader, "multiselect", "Select columns to display").value == ["B", "A"]
    assert "Unavailable display columns: C" in [item.value for item in reader.text]
    assert any("Exclusions omitted" in item.value and "C" in item.value for item in reader.text)
    assert widget(reader, "selectbox", "View mode").value == "Full"
    widget(reader, "selectbox", "View mode").set_value("Stacked by All").run().run()
    assert widget(reader, "multiselect", "Exclusion rule").value == ["B"]
    assert widget(author, "multiselect", "Select columns to display").value == ["C", "B", "A"]
    assert not author.exception and not reader.exception


def test_adjust_exclusions_and_keep_settings_without_matching_columns(store):
    partial = store.save("Partial", ["C", "B"], ["B"])
    unrelated = store.save("Unrelated", ["Z"], [])
    app = page(["A", "B"])
    widget(app, "selectbox", "View mode").set_value("Stacked by All").run()
    widget(app, "selectbox", "Saved presets").select(partial.id).run()
    widget(app, "button", "Apply preset").click().run()
    assert widget(app, "multiselect", "Select columns to display").value == ["B"]
    assert widget(app, "multiselect", "Exclusion rule").value == []
    assert any(item.value.endswith(": B") and "Exclusions omitted" in item.value for item in app.text)

    widget(app, "selectbox", "Saved presets").select(unrelated.id).run()
    widget(app, "button", "Apply preset").click().run()
    assert widget(app, "multiselect", "Select columns to display").value == ["B"]
    assert any("None of this preset" in item.value for item in app.warning)
    assert not app.exception


def test_update_and_confirm_delete_from_page(store):
    preset = store.save("Original", ["A"], [])
    app = page(["A", "B"])
    widget(app, "selectbox", "Saved presets").select(preset.id).run()
    assert widget(app, "button", "Update selected").disabled
    widget(app, "button", "Apply preset").click().run()
    assert not widget(app, "button", "Update selected").disabled
    widget(app, "multiselect", "Select columns to display").set_value(["B"]).run()
    store.save("Elsewhere", ["A"], [], previous=preset)
    widget(app, "button", "Update selected").click().run()
    assert any("Apply the latest version" in item.value for item in app.error)
    widget(app, "button", "Apply preset").click().run()
    assert widget(app, "text_input", "Active preset").value == "Elsewhere"
    assert widget(app, "multiselect", "Select columns to display").value == ["A"]
    widget(app, "multiselect", "Select columns to display").set_value(["B"]).run()
    other = store.save("Other preset", ["A"], [])
    app.run()
    widget(app, "selectbox", "Saved presets").select(other.id).run()
    widget(app, "button", "Update selected").click().run()
    assert [(p.name, p.columns) for p in store.list()] == [
        ("Elsewhere", ("B",)), ("Other preset", ("A",))
    ]
    assert widget(app, "text_input", "Active preset").value == "Elsewhere"
    assert widget(app, "selectbox", "Saved presets").value == preset.id
    widget(app, "text_input", "Active preset").set_value("Renamed")
    widget(app, "button", "Update selected").click().run()
    choice = widget(app, "selectbox", "Saved presets")
    assert choice.value == preset.id
    assert choice.options == ["Other preset", "Renamed"]
    assert widget(app, "text_input", "Active preset").value == "Renamed"
    widget(app, "button", "Delete selected").click().run()
    assert store.list()
    widget(app, "button", "Confirm delete").click().run()
    assert store.list() == [other]
    assert not app.exception


def test_presets_survive_navigation_and_clear(store):
    preset = store.save("Flight", ["B", "A"], ["B"])
    app = AppTest.from_file(str(ROOT / "Load CSV.py")).run()
    app.session_state["df_full"] = pd.DataFrame({"Seconds": [0], "A": [1], "B": [2]})
    app.switch_page(f"pages/{PAGE}").run()
    widget(app, "selectbox", "Saved presets").select(preset.id).run()
    widget(app, "button", "Apply preset").click().run()
    app.switch_page("Load CSV.py").run()
    app.switch_page(f"pages/{PAGE}").run()
    assert widget(app, "multiselect", "Select columns to display").value == ["B", "A"]

    app.switch_page("Load CSV.py").run()
    widget(app, "button", "Clear dataset").click().run()
    assert "df_full" not in app.session_state
    assert store.list() == [preset]
    app.session_state["df_full"] = pd.DataFrame({"Seconds": [0], "A": [1], "B": [2]})
    app.switch_page(f"pages/{PAGE}").run()
    assert widget(app, "selectbox", "Saved presets").options == ["Flight"]
    assert widget(app, "multiselect", "Select columns to display").value == []
    assert not app.exception


def test_name_tracks_applied_preset_and_clears_on_settings_changes(store):
    first = store.save("First", ["B", "A"], ["B"], view_mode="Stacked by All")
    second = store.save("Second", ["A", "B"], [])
    app = page(["A", "B"])

    def name():
        return widget(app, "text_input", "Active preset").value

    widget(app, "selectbox", "Saved presets").select(first.id).run()
    assert name() == ""
    widget(app, "button", "Apply preset").click().run()
    assert name() == "First"
    assert widget(app, "button", "Apply preset").disabled
    widget(app, "text_input", "Active preset").set_value("Draft").run()
    assert not widget(app, "button", "Apply preset").disabled
    widget(app, "button", "Apply preset").click().run()
    assert widget(app, "button", "Apply preset").disabled
    widget(app, "selectbox", "Saved presets").select(second.id).run()
    assert not widget(app, "button", "Apply preset").disabled
    assert name() == "First"
    assert widget(app, "selectbox", "View mode").value == "Stacked by All"
    assert name() == "First"
    widget(app, "multiselect", "Exclusion rule").set_value([]).run()
    assert name() == ""
    widget(app, "button", "Apply preset").click().run()
    assert name() == "Second"
    widget(app, "multiselect", "Select columns to display").set_value(["B"]).run()
    assert name() == ""
    assert not widget(app, "button", "Apply preset").disabled
    assert not app.exception
