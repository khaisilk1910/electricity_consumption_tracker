"""SQLite access and bill calculations; all disk activity runs in an executor."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
from pathlib import Path
import sqlite3

from .const import applicable_tariff, get_vat_rate

_LOGGER = logging.getLogger(__name__)
# Bump when tariff calculation rules change to rebuild stored bills once.
CALCULATION_REVISION = 4


def billing_period(day: date, billing_day: int, apply_date: date) -> tuple[int, int]:
    """Return bill's (year, month); billing_day starts the next month's bill."""
    if day < apply_date or billing_day == 1 or day.day < billing_day:
        return day.year, day.month
    return (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)


def billing_range(year: int, month: int, billing_day: int, apply_date: date) -> tuple[date, date]:
    """Find the contiguous period belonging to a bill (inclusive dates)."""
    anchor = date(year, month, 1)
    start = end = anchor
    for distance in range(1, 46):
        candidate = anchor - timedelta(days=distance)
        if billing_period(candidate, billing_day, apply_date) != (year, month):
            break
        start = candidate
    for distance in range(1, 46):
        candidate = anchor + timedelta(days=distance)
        if billing_period(candidate, billing_day, apply_date) != (year, month):
            break
        end = candidate
    return start, end


def calculate_cost(kwh: float, day: date) -> tuple[int, str]:
    """Estimate progressive residential cost before VAT, in whole VND."""
    if not 0 <= kwh < float("inf"):
        raise ValueError("kWh must be a non-negative finite number")
    tariff_date, tiers = applicable_tariff(day)
    remaining = Decimal(str(kwh))
    charge = Decimal(0)
    for width, price in tiers:
        used = min(remaining, Decimal(str(width))) if width != float("inf") else remaining
        charge += used * price
        remaining -= used
        if remaining <= 0:
            break
    return int(charge.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), tariff_date


def _ensure_columns(cursor: sqlite3.Cursor, table: str, definitions: dict[str, str]) -> None:
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    for column, ddl in definitions.items():
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            _LOGGER.info("Migrated %s: added %s", table, column)


def _create_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""CREATE TABLE IF NOT EXISTS daily_usage (
        nam INTEGER, thang INTEGER, ngay INTEGER, san_luong REAL, don_vi TEXT,
        PRIMARY KEY (nam, thang, ngay))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS monthly_bill (
        nam INTEGER, thang INTEGER, tong_san_luong REAL, don_vi_san_luong TEXT,
        thanh_tien REAL, don_vi_tien TEXT, thanh_tien_sau_thue REAL,
        vat INTEGER, ngay_bat_dau TEXT, ngay_ket_thuc TEXT,
        PRIMARY KEY (nam, thang))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS yearly_bill (
        nam INTEGER PRIMARY KEY, tong_san_luong REAL, tong_tien REAL,
        tong_tien_sau_thue REAL, vat INTEGER)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS total_usage (
        tong_san_luong REAL, don_vi TEXT, tong_so_thang INTEGER,
        thoi_diem_bat_dau TEXT, thoi_diem_ket_thuc TEXT,
        tong_tien_tich_luy REAL, tong_tien_tich_luy_sau_thue REAL, vat INTEGER)""")
    _ensure_columns(cursor, "monthly_bill", {
        "thanh_tien_sau_thue": "REAL DEFAULT 0", "vat": "INTEGER DEFAULT 8",
        "ngay_bat_dau": "TEXT", "ngay_ket_thuc": "TEXT",
    })
    _ensure_columns(cursor, "yearly_bill", {
        "tong_tien_sau_thue": "REAL DEFAULT 0", "vat": "INTEGER DEFAULT 8",
    })
    _ensure_columns(cursor, "total_usage", {
        "thoi_diem_bat_dau": "TEXT", "thoi_diem_ket_thuc": "TEXT",
        "tong_tien_tich_luy": "REAL DEFAULT 0",
        "tong_tien_tich_luy_sau_thue": "REAL DEFAULT 0", "vat": "INTEGER DEFAULT 8",
    })


def _recalculate_month(cursor: sqlite3.Cursor, year: int, month: int, billing_day: int, apply_date: date) -> None:
    start, end = billing_range(year, month, billing_day, apply_date)
    used = cursor.execute("""SELECT COALESCE(SUM(san_luong), 0) FROM daily_usage
        WHERE printf('%04d-%02d-%02d', nam, thang, ngay) BETWEEN ? AND ?""",
        (start.isoformat(), end.isoformat())).fetchone()[0]
    # Rate at bill end approximates the bill. Changes during the cycle are estimates.
    cost, tariff = calculate_cost(used, end)
    vat = get_vat_rate(end.year, end.month, end.day)
    taxed = int((Decimal(cost) * (1 + Decimal(str(vat)))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    cursor.execute("""INSERT OR REPLACE INTO monthly_bill
        (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien,
         thanh_tien_sau_thue, vat, ngay_bat_dau, ngay_ket_thuc)
        VALUES (?, ?, ?, 'kWh', ?, 'đ', ?, ?, ?, ?)""",
        (year, month, used, cost, taxed, round(vat * 100), start.isoformat(), end.isoformat()))
    _LOGGER.debug("Bill %04d-%02d: %.3f kWh; price=%s; tariff=%s; VAT=%s%%", year, month, used, cost, tariff, round(vat * 100))


def _recalculate_year(cursor: sqlite3.Cursor, year: int) -> None:
    values = cursor.execute("""SELECT COALESCE(SUM(tong_san_luong), 0),
        COALESCE(SUM(thanh_tien), 0), COALESCE(SUM(thanh_tien_sau_thue), 0)
        FROM monthly_bill WHERE nam=?""", (year,)).fetchone()
    last = cursor.execute("SELECT vat FROM monthly_bill WHERE nam=? ORDER BY thang DESC LIMIT 1", (year,)).fetchone()
    cursor.execute("""INSERT OR REPLACE INTO yearly_bill
        (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
        VALUES (?, ?, ?, ?, ?)""", (year, *values, last[0] if last else 8))


def _recalculate_total(cursor: sqlite3.Cursor) -> None:
    kwh, cost, taxed, months = cursor.execute("""SELECT
        COALESCE(SUM(tong_san_luong), 0), COALESCE(SUM(thanh_tien), 0),
        COALESCE(SUM(thanh_tien_sau_thue), 0), COUNT(*) FROM monthly_bill""").fetchone()
    first = cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam, thang, ngay LIMIT 1").fetchone()
    last = cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam DESC, thang DESC, ngay DESC LIMIT 1").fetchone()
    display = lambda r: f"{r[2]:02d}/{r[1]:02d}/{r[0]}" if r else "N/A"
    vat = round(100 * get_vat_rate(*last)) if last else 8
    cursor.execute("DELETE FROM total_usage")
    cursor.execute("""INSERT INTO total_usage
        (tong_san_luong, don_vi, tong_so_thang, thoi_diem_bat_dau, thoi_diem_ket_thuc,
         tong_tien_tich_luy, tong_tien_tich_luy_sau_thue, vat)
         VALUES (?, 'kWh', ?, ?, ?, ?, ?, ?)""",
         (kwh, months, display(first), display(last), cost, taxed, vat))


def _rebuild(cursor: sqlite3.Cursor, billing_day: int, apply_date: date) -> int:
    rows = cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam, thang, ngay").fetchall()
    periods = {billing_period(date(*row), billing_day, apply_date) for row in rows}
    cursor.execute("DELETE FROM monthly_bill")
    cursor.execute("DELETE FROM yearly_bill")
    for year, month in sorted(periods):
        _recalculate_month(cursor, year, month, billing_day, apply_date)
    for year in sorted({year for year, _ in periods}):
        _recalculate_year(cursor, year)
    _recalculate_total(cursor)
    return len(periods)


class ElectricityStore:
    """Serialize writes and database snapshots for one config entry."""

    def __init__(self, hass, db_path: Path) -> None:
        self.hass = hass
        self.db_path = db_path
        self.lock = asyncio.Lock()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.execute("PRAGMA busy_timeout=20000")
        return conn

    def _initialize_sync(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connection()) as conn:
            with conn:
                _create_schema(conn.cursor())
        _LOGGER.debug("Database ready: %s", self.db_path.name)

    async def async_initialize(self) -> None:
        async with self.lock:
            await self.hass.async_add_executor_job(self._initialize_sync)

    def _write_sync(self, on_date: date, kwh: float, billing_day: int, apply_date: date) -> bool:
        with closing(self._connection()) as conn:
            with conn:
                cursor = conn.cursor()
                existing = cursor.execute("SELECT san_luong FROM daily_usage WHERE nam=? AND thang=? AND ngay=?",
                                          (on_date.year, on_date.month, on_date.day)).fetchone()
                if existing and abs(existing[0] - kwh) < 1e-9:
                    return False
                cursor.execute("""INSERT OR REPLACE INTO daily_usage
                    (nam, thang, ngay, san_luong, don_vi) VALUES (?, ?, ?, ?, 'kWh')""",
                    (on_date.year, on_date.month, on_date.day, kwh))
                y, m = billing_period(on_date, billing_day, apply_date)
                _recalculate_month(cursor, y, m, billing_day, apply_date)
                _recalculate_year(cursor, y)
                _recalculate_total(cursor)
        return True

    async def async_write(self, on_date: date, kwh: float, billing_day: int, apply_date: date) -> bool:
        async with self.lock:
            return await self.hass.async_add_executor_job(self._write_sync, on_date, kwh, billing_day, apply_date)

    def _rebuild_if_needed_sync(self, billing_day: int, apply_date: date, force: bool) -> bool:
        with closing(self._connection()) as conn:
            with conn:
                cursor = conn.cursor()
                # Store rules outside the user's tables, for backward-compatible migrations.
                cursor.execute("CREATE TABLE IF NOT EXISTS tracker_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                signature = f"{CALCULATION_REVISION}:{billing_day}:{apply_date.isoformat()}"
                last = cursor.execute("SELECT value FROM tracker_meta WHERE key='calculation_signature'").fetchone()
                if last and last[0] == signature and not force:
                    return False
                months = _rebuild(cursor, billing_day, apply_date)
                cursor.execute("INSERT OR REPLACE INTO tracker_meta(key, value) VALUES('calculation_signature', ?)", (signature,))
        _LOGGER.info("Recalculated %d billing periods in %s (rules %s)", months, self.db_path.name, signature)
        return True

    async def async_rebuild_if_needed(self, billing_day: int, apply_date: date, *, force: bool = False) -> bool:
        async with self.lock:
            return await self.hass.async_add_executor_job(self._rebuild_if_needed_sync, billing_day, apply_date, force)

    def _snapshot_sync(self) -> dict:
        with closing(self._connection()) as conn:
            conn.row_factory = sqlite3.Row
            return {
                "total": [dict(row) for row in conn.execute("SELECT * FROM total_usage")],
                "monthly": [dict(row) for row in conn.execute("SELECT * FROM monthly_bill ORDER BY nam, thang")],
                "yearly": [dict(row) for row in conn.execute("SELECT * FROM yearly_bill ORDER BY nam")],
                "daily": [dict(row) for row in conn.execute("SELECT * FROM daily_usage ORDER BY nam, thang, ngay")],
            }

    async def async_snapshot(self) -> dict:
        async with self.lock:
            return await self.hass.async_add_executor_job(self._snapshot_sync)
