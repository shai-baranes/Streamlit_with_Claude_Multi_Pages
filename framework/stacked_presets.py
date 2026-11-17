"""Shared settings for the Seconds stacked table."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


STORE_PATH = Path(__file__).resolve().parent.parent / "local_data" / "stacked_seconds_presets.sqlite3"
MAX_NAME_LENGTH = 120
VIEW_MODES = ("Full", "Stacked by Left", "Stacked by All")


class PresetError(ValueError):
    """A preset error that can be shown to the user."""


@dataclass(frozen=True)
class Preset:
    id: str
    revision: int
    name: str
    columns: tuple[str, ...]
    exclusions: tuple[str, ...]
    view_mode: str | None = None


def _settings(name, columns, exclusions, view_mode):
    name = name.strip() if isinstance(name, str) else ""
    if not name or len(name) > MAX_NAME_LENGTH or not name.isprintable():
        raise PresetError(
            f"Enter a preset name with 1–{MAX_NAME_LENGTH} printable characters to the 'Active preset' field."
        )
    for fields in (columns, exclusions):
        if (not isinstance(fields, (list, tuple))
                or any(not isinstance(field, str) or not field for field in fields)
                or len(set(fields)) != len(fields)):
            raise PresetError("Preset fields must be unique column names.")
    if not columns:
        raise PresetError("Select at least one display column before saving a preset.")
    if not set(exclusions) < set(columns):
        raise PresetError("At least one display column must remain outside the exclusion rule.")
    if view_mode is not None and view_mode not in VIEW_MODES:
        raise PresetError("Choose a supported view mode.")
    return name, tuple(columns), tuple(exclusions), view_mode


class PresetStore:
    def __init__(self, path=None):
        self.path = STORE_PATH if path is None else Path(path)

    @contextmanager
    def _connect(self, *, write=False, create=False):
        try:
            if create:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            # Read-only opens cannot recreate a file deleted by the operator.
            mode = "rwc" if create else "rw" if write else "ro"
            filename = self.path.resolve().as_uri() + f"?mode={mode}"
            with closing(sqlite3.connect(filename, uri=True, timeout=2)) as db, db:
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if create and version == 0 and self.path.stat().st_size == 0:
                    db.execute("""
                        CREATE TABLE presets (
                            id TEXT NOT NULL PRIMARY KEY,
                            revision INTEGER NOT NULL,
                            name TEXT NOT NULL,
                            name_key TEXT NOT NULL UNIQUE,
                            columns_json TEXT NOT NULL,
                            exclusions_json TEXT NOT NULL,
                            view_mode TEXT
                        )
                    """)
                    version = 2
                    db.execute("PRAGMA user_version = 2")
                elif version == 1 and write:
                    # NULL leaves the current mode unchanged for presets saved before this setting existed.
                    db.execute("ALTER TABLE presets ADD COLUMN view_mode TEXT")
                    version = 2
                    db.execute("PRAGMA user_version = 2")
                elif version not in (1, 2):
                    raise PresetError("Unsupported preset store. Ask the server operator to check or restore the file.")
                yield db, version
        except (OSError, sqlite3.Error) as exc:
            raise PresetError(
                "Unable to access the shared preset store. Retry, or ask the server operator "
                "to check the file and directory permissions."
            ) from exc

    def list(self):
        try:
            self.path.stat()
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise PresetError("Unable to read the shared preset file. Check server permissions.") from exc
        with self._connect() as (db, version):
            view_mode_field = "view_mode" if version == 2 else "NULL"
            rows = db.execute(f"""
                SELECT id, revision, name, name_key, columns_json, exclusions_json, {view_mode_field}
                FROM presets ORDER BY name_key
            """).fetchall()
        presets = []
        for preset_id, revision, name, name_key, columns, exclusions, view_mode in rows:
            try:
                settings = _settings(name, json.loads(columns), json.loads(exclusions), view_mode)
                if (not isinstance(preset_id, str) or not preset_id
                        or type(revision) is not int or revision < 1
                        or name != settings[0] or name_key != name.casefold()):
                    raise ValueError("Invalid preset metadata")
            except (ValueError, TypeError) as exc:
                raise PresetError("Invalid saved preset. Ask the server operator to check or restore the file.") from exc
            presets.append(Preset(preset_id, revision, *settings))
        return presets

    def save(self, name, columns, exclusions, *, view_mode=None, previous=None):
        name, columns, exclusions, view_mode = _settings(name, columns, exclusions, view_mode)
        values = (name, name.casefold(), json.dumps(columns), json.dumps(exclusions), view_mode)
        with self._connect(write=True, create=previous is None) as (db, _):
            # Keep the uniqueness check and write in one transaction across processes.
            duplicate = db.execute("SELECT id FROM presets WHERE name_key = ?", (values[1],)).fetchone()
            if duplicate and (previous is None or duplicate[0] != previous.id):
                raise PresetError("A preset with this name already exists.")
            if previous is None:
                preset_id, revision = uuid4().hex, 1
                db.execute("""
                    INSERT INTO presets (id, revision, name, name_key, columns_json, exclusions_json, view_mode)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (preset_id, revision, *values))
            else:
                preset_id, revision = previous.id, previous.revision + 1
                result = db.execute("""
                    UPDATE presets SET name = ?, name_key = ?, columns_json = ?,
                        exclusions_json = ?, view_mode = ?, revision = ?
                    WHERE id = ? AND revision = ?
                """, (*values, revision, preset_id, previous.revision))
                self._check_revision(result)
        return Preset(preset_id, revision, name, columns, exclusions, view_mode)

    def delete(self, previous):
        with self._connect(write=True) as (db, _):
            result = db.execute(
                "DELETE FROM presets WHERE id = ? AND revision = ?",
                (previous.id, previous.revision),
            )
            self._check_revision(result)

    @staticmethod
    def _check_revision(result):
        if result.rowcount != 1:
            raise PresetError("This preset changed or was deleted. Apply the latest version if it still exists, or choose another preset.")
