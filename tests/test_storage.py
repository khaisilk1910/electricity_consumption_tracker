"""Standalone storage tests; no Home Assistant installation required."""
import asyncio
from datetime import date
import importlib
from pathlib import Path
import sqlite3
import sys
import types

import pytest

PKG_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "electricity_consumption_tracker"
pkg = types.ModuleType("ect_under_test")
pkg.__path__ = [str(PKG_PATH)]
sys.modules.setdefault("ect_under_test", pkg)
const = importlib.import_module("ect_under_test.const")
storage = importlib.import_module("ect_under_test.storage")


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        return await asyncio.to_thread(func, *args)


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("kwh, expected", [
    (0, 0), (100, 190100), (200, 419000),
    (400, 997800), (700, 2034600), (701, 2038444),
])
def test_2026_five_tier_prices(kwh, expected):
    cost, effective_date = storage.calculate_cost(kwh, date(2026, 11, 1))
    assert cost == expected
    assert effective_date == "2026-11-01"


def test_price_history_timeline():
    assert storage.calculate_cost(50, date(2023, 5, 4))[0] == 50 * 1728
    assert storage.calculate_cost(50, date(2023, 11, 9))[0] == 50 * 1806
    assert storage.calculate_cost(50, date(2025, 5, 10))[0] == 50 * 1984
    assert storage.calculate_cost(50, date(2026, 10, 31))[0] == 50 * 1984
    assert storage.calculate_cost(50, date(2026, 11, 1))[0] == 50 * 1901


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_refuse_invalid_consumption(value):
    with pytest.raises(ValueError):
        storage.calculate_cost(value, date(2026, 11, 1))


def test_billing_period_rollover_and_effective_date():
    apply = date(2024, 1, 1)
    assert storage.billing_period(date(2026, 12, 14), 15, apply) == (2026, 12)
    assert storage.billing_period(date(2026, 12, 15), 15, apply) == (2027, 1)
    assert storage.billing_range(2027, 1, 15, apply) == (date(2026, 12, 15), date(2027, 1, 14))
    assert storage.billing_period(date(2023, 12, 16), 15, apply) == (2023, 12)
    assert storage.billing_range(2024, 1, 15, apply) == (date(2024, 1, 1), date(2024, 1, 14))


def test_create_save_revise_and_restart(tmp_path):
    async def scenario():
        db = tmp_path / "data" / "meter.db"
        store = storage.ElectricityStore(FakeHass(), db)
        await store.async_initialize()
        billing_day, apply = 1, date(2024, 1, 1)
        day = date(2026, 11, 7)
        assert await store.async_write(day, 110.5, billing_day, apply)
        assert not await store.async_write(day, 110.5, billing_day, apply)
        snapshot = await store.async_snapshot()
        assert len(snapshot["daily"]) == 1
        assert snapshot["monthly"][0]["tong_san_luong"] == 110.5
        assert snapshot["total"][0]["tong_san_luong"] == 110.5
        assert snapshot["monthly"][0]["thanh_tien"] == storage.calculate_cost(110.5, date(2026, 11, 30))[0]
        assert snapshot["monthly"][0]["thanh_tien_sau_thue"] > snapshot["monthly"][0]["thanh_tien"]
        assert await store.async_write(day, 40.0, billing_day, apply)
        assert (await store.async_snapshot())["total"][0]["tong_san_luong"] == 40
        assert await store.async_rebuild_if_needed(billing_day, apply)
        assert not await store.async_rebuild_if_needed(billing_day, apply)
        snapshot = await store.async_snapshot()
        assert snapshot["monthly"][0]["tong_san_luong"] == 40
        assert snapshot["yearly"][0]["tong_san_luong"] == 40
        # Reopen without losing existing historical data.
        reopened = storage.ElectricityStore(FakeHass(), db)
        await reopened.async_initialize()
        assert (await reopened.async_snapshot())["daily"][0]["san_luong"] == 40
    run(scenario())


def test_cross_month_bill_and_force_rebuild(tmp_path):
    async def scenario():
        store = storage.ElectricityStore(FakeHass(), tmp_path / "meter.db")
        await store.async_initialize()
        apply = date(2024, 1, 1)
        await store.async_write(date(2026, 10, 20), 20, 15, apply)
        await store.async_write(date(2026, 11, 5), 30, 15, apply)
        rows = await store.async_snapshot()
        assert rows["monthly"][0]["nam"] == 2026
        assert rows["monthly"][0]["thang"] == 11
        assert rows["monthly"][0]["tong_san_luong"] == 50
        assert rows["monthly"][0]["ngay_bat_dau"] == "2026-10-15"
        assert rows["monthly"][0]["ngay_ket_thuc"] == "2026-11-14"
        # Changing cycle day must rebuild and move affected daily rows.
        assert await store.async_rebuild_if_needed(1, apply)
        rows = await store.async_snapshot()
        assert {(r["nam"], r["thang"]) for r in rows["monthly"]} == {(2026, 10), (2026, 11)}
        assert rows["total"][0]["tong_san_luong"] == 50
        assert sum(r["tong_san_luong"] for r in rows["yearly"]) == 50
    run(scenario())


def test_concurrent_writes_serialized(tmp_path):
    async def scenario():
        store = storage.ElectricityStore(FakeHass(), tmp_path / "meter.db")
        await store.async_initialize()
        apply = date(2024, 1, 1)
        await asyncio.gather(*(store.async_write(date(2026, 11, 1 + day), float(day + 1), 1, apply) for day in range(20)))
        rows = await store.async_snapshot()
        assert len(rows["daily"]) == 20
        assert rows["total"][0]["tong_san_luong"] == sum(range(1, 21))
    run(scenario())


def test_migrate_legacy_schema(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE monthly_bill (nam INTEGER, thang INTEGER, tong_san_luong REAL, don_vi_san_luong TEXT, thanh_tien REAL, don_vi_tien TEXT, PRIMARY KEY (nam, thang))")
        conn.execute("CREATE TABLE yearly_bill (nam INTEGER PRIMARY KEY, tong_san_luong REAL, tong_tien REAL)")
        conn.execute("CREATE TABLE total_usage (tong_san_luong REAL, don_vi TEXT, tong_so_thang INTEGER)")
    async def scenario():
        store = storage.ElectricityStore(FakeHass(), path)
        await store.async_initialize()
        assert await store.async_write(date(2026, 11, 7), 60, 1, date(2024, 1, 1))
        rows = await store.async_snapshot()
        assert rows["monthly"][0]["thanh_tien_sau_thue"] > 0
        assert rows["total"][0]["thoi_diem_bat_dau"] == '07/11/2026'
    run(scenario())
