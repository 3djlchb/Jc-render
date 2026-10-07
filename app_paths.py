"""Shared application paths and first-run database migration."""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def _data_directory():
    """Return the per-user writable data directory for JC Render."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "JC-Render"


def _copy_database(source, destination):
    """Copy a SQLite database consistently, then atomically publish it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(
        prefix="config-", suffix=".sqlite-tmp", dir=destination.parent, delete=False
    )
    temp_path = Path(temp_handle.name)
    temp_handle.close()

    source_conn = None
    destination_conn = None
    try:
        source_conn = sqlite3.connect(str(source))
        destination_conn = sqlite3.connect(str(temp_path))
        source_conn.backup(destination_conn)
        destination_conn.close()
        destination_conn = None
        source_conn.close()
        source_conn = None
        os.replace(str(temp_path), str(destination))
    except Exception:
        if destination_conn is not None:
            destination_conn.close()
        if source_conn is not None:
            source_conn.close()
        temp_path.unlink(missing_ok=True)
        raise


def get_database_path():
    """Return the writable database path and migrate the bundled DB once."""
    if getattr(sys, "frozen", False):
        app_directory = Path(sys.executable).resolve().parent
    else:
        app_directory = Path(__file__).resolve().parent

    bundled_database = app_directory / "bbdd" / "config.db"
    destination = _data_directory() / "config.db"
    destination.parent.mkdir(parents=True, exist_ok=True)

    # A missing or zero-byte destination can be recovered from the bundled DB.
    needs_migration = not destination.exists() or destination.stat().st_size == 0
    if needs_migration and bundled_database.exists():
        if bundled_database.resolve() != destination.resolve():
            _copy_database(bundled_database, destination)

    return str(destination)
