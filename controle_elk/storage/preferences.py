import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from .paths import data_directory

DEFAULT_BRIGHTNESS = 70


@dataclass(frozen=True)
class SavedDevice:
    address: str
    model: str
    variant: str | None
    name: str | None = None

    @property
    def label(self):
        return f"{self.model}  {self.address}"


class DeviceStore:
    def __init__(self, path=None):
        self.path = (
            Path(path)
            if path is not None
            else data_directory() / "preferencias.sqlite3"
        )

    @contextmanager
    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=1)) as database, database:
            database.execute("PRAGMA foreign_keys = ON")
            database.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    address TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    variant TEXT
                )
            """)
            database.execute("""
                CREATE TABLE IF NOT EXISTS device_names (
                    address TEXT PRIMARY KEY REFERENCES devices(address) ON DELETE CASCADE,
                    name TEXT NOT NULL
                )
            """)
            database.execute("""
                CREATE TABLE IF NOT EXISTS solid_colors (
                    id INTEGER PRIMARY KEY,
                    color TEXT NOT NULL UNIQUE
                )
            """)
            database.execute("""
                CREATE TABLE IF NOT EXISTS custom_gradients (
                    name TEXT PRIMARY KEY COLLATE NOCASE NOT NULL,
                    values_json TEXT NOT NULL
                )
            """)
            database.execute("""
                CREATE TABLE IF NOT EXISTS custom_sequences (
                    name TEXT PRIMARY KEY COLLATE NOCASE NOT NULL,
                    values_json TEXT NOT NULL
                )
            """)
            database.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
            """)
            yield database

    def load_brightness(self):
        with self.open() as database:
            row = database.execute(
                "SELECT value FROM settings WHERE name = 'brightness'"
            ).fetchone()
        if row and isinstance(row[0], int) and 1 <= row[0] <= 100:
            return row[0]
        return DEFAULT_BRIGHTNESS

    def save_brightness(self, value):
        with self.open() as database:
            database.execute(
                """
                INSERT INTO settings (name, value) VALUES ('brightness', ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                (value,),
            )

    def load(self):
        with self.open() as database:
            return [
                SavedDevice(*row)
                for row in database.execute(
                    """
                SELECT devices.address, devices.model, devices.variant, device_names.name
                FROM devices LEFT JOIN device_names USING (address)
                ORDER BY devices.model, devices.address
                """
                )
            ]

    def load_last_device(self):
        with self.open() as database:
            row = database.execute("""
                SELECT devices.address
                FROM devices JOIN settings ON devices.address = settings.value
                WHERE settings.name = 'last_device'
            """).fetchone()
        return row[0] if row else None

    def remember(self, device):
        with self.open() as database:
            database.execute(
                """
                INSERT INTO devices (address, model, variant) VALUES (?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET model = excluded.model, variant = excluded.variant
            """,
                (device.address, device.model, device.variant),
            )
            database.execute(
                """
                INSERT INTO settings (name, value) VALUES ('last_device', ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
            """,
                (device.address,),
            )

    def forget(self, address):
        with self.open() as database:
            database.execute("DELETE FROM devices WHERE address = ?", (address,))

    def rename(self, address, name):
        with self.open() as database:
            if name:
                database.execute(
                    """
                    INSERT INTO device_names (address, name) VALUES (?, ?)
                    ON CONFLICT(address) DO UPDATE SET name = excluded.name
                """,
                    (address, name),
                )
            else:
                database.execute(
                    "DELETE FROM device_names WHERE address = ?", (address,)
                )

    def load_colors(self):
        with self.open() as database:
            return [
                color
                for (color,) in database.execute(
                    "SELECT color FROM solid_colors ORDER BY id"
                )
            ]

    def save_color(self, color):
        with self.open() as database:
            result = database.execute(
                "INSERT INTO solid_colors (color) VALUES (?) ON CONFLICT(color) DO NOTHING",
                (color,),
            )
            return result.rowcount == 1

    def remove_color(self, color):
        with self.open() as database:
            database.execute("DELETE FROM solid_colors WHERE color = ?", (color,))

    def load_gradients(self, *, sequence=False):
        table = "custom_sequences" if sequence else "custom_gradients"
        with self.open() as database:
            return {
                name: json.loads(values)
                for name, values in database.execute(
                    f"SELECT name, values_json FROM {table} ORDER BY name"
                )
            }

    def save_gradient(self, name, values, *, sequence=False):
        table = "custom_sequences" if sequence else "custom_gradients"
        with self.open() as database:
            result = database.execute(
                f"""
                INSERT INTO {table} (name, values_json) VALUES (?, ?)
                ON CONFLICT(name) DO NOTHING
            """,
                (name, json.dumps(values)),
            )
            return result.rowcount == 1
