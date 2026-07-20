from datetime import datetime
from zoneinfo import ZoneInfo

from mathem_agent.planner import demo_plan
from mathem_agent.weekly import (
    WeeklyConfig,
    period_key,
    run_weekly,
    save_weekly_config,
)


class FakeClient:
    def __init__(self, calls, fail_once=None):
        self.calls = calls
        self.fail_once = fail_once

    def add_to_cart(self, product_id, quantity=1):
        key = str(product_id)
        self.calls.append((key, quantity))
        if self.fail_once is not None and key == self.fail_once and self.calls.count((key, quantity)) == 1:
            raise RuntimeError("temporary failure")
        return {"success": True, "status_code": 200}


def _config():
    return WeeklyConfig(
        schedule_day="MON",
        schedule_time="09:00",
        timezone="Europe/Stockholm",
        people=2,
        meals=1,
        max_budget=500,
        auto_add_to_cart=True,
        refresh_session_headlessly=False,
    )


def test_period_key_uses_latest_weekly_boundary():
    config = WeeklyConfig(schedule_day="SUN", schedule_time="18:00")
    monday = datetime(2026, 7, 20, 9, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
    assert period_key(config, monday) == "2026-07-19"


def test_weekly_run_only_adds_once(tmp_path):
    config = _config()
    save_weekly_config(config, tmp_path)
    calls = []
    now = datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Europe/Stockholm"))

    first = run_weekly(
        data_dir=tmp_path,
        now=now,
        plan_factory=lambda _config, _seed: demo_plan(),
        client_factory=lambda: FakeClient(calls),
    )
    second = run_weekly(
        data_dir=tmp_path,
        now=now,
        plan_factory=lambda _config, _seed: demo_plan(),
        client_factory=lambda: FakeClient(calls),
    )

    assert first.status == "completed"
    assert second.status == "skipped"
    assert len(calls) == 4


def test_failed_item_retries_without_readding_successful_items(tmp_path):
    config = _config()
    save_weekly_config(config, tmp_path)
    calls = []
    now = datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Europe/Stockholm"))

    first = run_weekly(
        data_dir=tmp_path,
        now=now,
        plan_factory=lambda _config, _seed: demo_plan(),
        client_factory=lambda: FakeClient(calls, fail_once="2"),
    )
    second = run_weekly(
        data_dir=tmp_path,
        now=now,
        plan_factory=lambda _config, _seed: demo_plan(),
        client_factory=lambda: FakeClient(calls, fail_once="2"),
    )

    assert first.status == "needs_attention"
    assert second.status == "completed"
    assert calls.count(("1", 1)) == 1
    assert calls.count(("2", 1)) == 2
    assert calls.count(("3", 1)) == 1
    assert calls.count(("4", 1)) == 1
