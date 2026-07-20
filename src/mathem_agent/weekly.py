from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .browser_auth import BrowserAuthError, get_auth_paths, refresh_session
from .mathem import MathemAuthError, MathemClient
from .planner import generate_meal_plan, load_plan, save_plan

DAY_INDEX = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}


class WeeklyAutomationError(RuntimeError):
    """Raised when a weekly automation run cannot proceed safely."""


class WeeklyRunInProgress(WeeklyAutomationError):
    """Raised when another process already owns the weekly run lock."""


@dataclass(slots=True)
class WeeklyConfig:
    enabled: bool = True
    schedule_day: str = "MON"
    schedule_time: str = "09:00"
    timezone: str = "Europe/Stockholm"
    people: int = 2
    meals: int = 4
    max_budget: float = 850.0
    preferences: str = "snabbt, billigt, mycket protein, inte för starkt"
    avoid: list[str] = field(default_factory=list)
    auto_add_to_cart: bool = True
    refresh_session_headlessly: bool = True

    def validate(self) -> None:
        day = self.schedule_day.upper()
        if day not in DAY_INDEX:
            raise WeeklyAutomationError(
                "schedule_day måste vara MON, TUE, WED, THU, FRI, SAT eller SUN."
            )
        try:
            parsed_time = time.fromisoformat(self.schedule_time)
        except ValueError as exc:
            raise WeeklyAutomationError("schedule_time måste ha formatet HH:MM.") from exc
        if parsed_time.second or parsed_time.microsecond:
            raise WeeklyAutomationError("schedule_time får endast innehålla timme och minut.")
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise WeeklyAutomationError(f"Okänd tidszon: {self.timezone}") from exc
        if self.people < 1:
            raise WeeklyAutomationError("people måste vara minst 1.")
        if not 1 <= self.meals <= 14:
            raise WeeklyAutomationError("meals måste vara mellan 1 och 14.")
        if self.max_budget <= 0:
            raise WeeklyAutomationError("max_budget måste vara större än 0.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeeklyConfig":
        allowed = cls.__dataclass_fields__.keys()
        config = cls(**{key: value for key, value in data.items() if key in allowed})
        config.schedule_day = config.schedule_day.upper()
        config.validate()
        return config

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WeeklyPaths:
    data_dir: Path
    config_file: Path
    runs_dir: Path
    latest_file: Path
    lock_file: Path
    log_file: Path


@dataclass(frozen=True, slots=True)
class WeeklyRunResult:
    status: str
    period_key: str
    plan_path: str | None
    estimated_total: float | None
    items_added: int
    items_skipped: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_weekly_paths(data_dir: str | Path | None = None) -> WeeklyPaths:
    auth_paths = get_auth_paths(data_dir)
    root = auth_paths.data_dir
    return WeeklyPaths(
        data_dir=root,
        config_file=root / "weekly-config.json",
        runs_dir=root / "weekly-runs",
        latest_file=root / "weekly-latest.json",
        lock_file=root / "weekly-run.lock",
        log_file=root / "weekly.log",
    )


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def save_weekly_config(
    config: WeeklyConfig,
    data_dir: str | Path | None = None,
) -> Path:
    config.validate()
    paths = get_weekly_paths(data_dir)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(paths.config_file, config.to_dict())
    return paths.config_file


def load_weekly_config(
    data_dir: str | Path | None = None,
    *,
    create_if_missing: bool = True,
) -> WeeklyConfig:
    paths = get_weekly_paths(data_dir)
    if not paths.config_file.exists():
        config = WeeklyConfig()
        if create_if_missing:
            save_weekly_config(config, data_dir)
        return config
    try:
        payload = json.loads(paths.config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeeklyAutomationError(
            f"Kunde inte läsa {paths.config_file}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise WeeklyAutomationError("weekly-config.json måste innehålla ett JSON-objekt.")
    return WeeklyConfig.from_dict(payload)


def scheduled_anchor(
    config: WeeklyConfig,
    now: datetime | None = None,
) -> datetime:
    """Return the latest configured weekly boundary at or before now."""
    config.validate()
    zone = ZoneInfo(config.timezone)
    local_now = now.astimezone(zone) if now else datetime.now(zone)
    target_day = DAY_INDEX[config.schedule_day]
    target_time = time.fromisoformat(config.schedule_time)
    days_since_target = (local_now.weekday() - target_day) % 7
    anchor_date = local_now.date() - timedelta(days=days_since_target)
    anchor = datetime.combine(anchor_date, target_time, tzinfo=zone)
    if local_now < anchor:
        anchor -= timedelta(days=7)
    return anchor


def period_key(config: WeeklyConfig, now: datetime | None = None) -> str:
    return scheduled_anchor(config, now).date().isoformat()


def next_scheduled_time(config: WeeklyConfig, now: datetime | None = None) -> datetime:
    zone = ZoneInfo(config.timezone)
    local_now = now.astimezone(zone) if now else datetime.now(zone)
    latest = scheduled_anchor(config, local_now)
    if latest > local_now:
        return latest
    return latest + timedelta(days=7)


def _run_paths(paths: WeeklyPaths, key: str) -> tuple[Path, Path, Path]:
    run_dir = paths.runs_dir / key
    return run_dir, run_dir / "plan.json", run_dir / "state.json"


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_log(paths: WeeklyPaths, message: str) -> None:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(ZoneInfo("Europe/Stockholm")).isoformat()
    with paths.log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _notify(title: str, message: str) -> None:
    """Best-effort local notification; failures never fail the grocery run."""
    system = platform.system().lower()
    try:
        if system == "darwin":
            script = (
                f'display notification {json.dumps(message)} '
                f'with title {json.dumps(title)}'
            )
            subprocess.run(["osascript", "-e", script], check=False, timeout=10)
        elif system == "linux":
            subprocess.run(["notify-send", title, message], check=False, timeout=10)
        elif system == "windows":
            safe = message.replace("'", "''")
            command = (
                "$wshell = New-Object -ComObject Wscript.Shell; "
                f"$wshell.Popup('{safe}', 12, 'Mathem Agent', 64) | Out-Null"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                check=False,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except Exception:
        return


class _RunLock:
    def __init__(self, path: Path, stale_after: timedelta = timedelta(hours=6)):
        self.path = path
        self.stale_after = stale_after
        self.fd: int | None = None

    def __enter__(self) -> "_RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = datetime.now().timestamp() - self.path.stat().st_mtime
            if age > self.stale_after.total_seconds():
                self.path.unlink(missing_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise WeeklyRunInProgress("En veckokörning pågår redan.") from exc
        os.write(self.fd, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.path.unlink(missing_ok=True)


def _default_plan_factory(config: WeeklyConfig, seed: int) -> Any:
    return generate_meal_plan(
        people=config.people,
        meals=config.meals,
        preferences=config.preferences,
        avoid=list(config.avoid),
        max_budget=config.max_budget,
        seed=seed,
    )


def run_weekly(
    *,
    data_dir: str | Path | None = None,
    dry_run: bool = False,
    retry_failed: bool = True,
    retry_ambiguous: bool = False,
    now: datetime | None = None,
    plan_factory: Callable[[WeeklyConfig, int], Any] | None = None,
    client_factory: Callable[[], MathemClient] | None = None,
) -> WeeklyRunResult:
    """
    Generate one plan per configured weekly period and add it to the cart exactly once.

    Each item is recorded before and after the API call. If a process dies while an item
    is being added, the item is marked ambiguous and is not retried automatically. This
    favours avoiding duplicate groceries over aggressive retries.
    """
    paths = get_weekly_paths(data_dir)
    config = load_weekly_config(data_dir)
    if not config.enabled:
        return WeeklyRunResult(
            status="disabled",
            period_key=period_key(config, now),
            plan_path=None,
            estimated_total=None,
            items_added=0,
            items_skipped=0,
            message="Veckoautomationen är avstängd.",
        )

    key = period_key(config, now)
    run_dir, plan_path, state_path = _run_paths(paths, key)
    run_dir.mkdir(parents=True, exist_ok=True)

    with _RunLock(paths.lock_file):
        state = _read_state(state_path)
        if state.get("status") == "completed":
            result = WeeklyRunResult(
                status="skipped",
                period_key=key,
                plan_path=str(plan_path) if plan_path.exists() else None,
                estimated_total=state.get("estimated_total"),
                items_added=0,
                items_skipped=len(state.get("items", {})),
                message="Den här veckoperioden har redan lagts i varukorgen.",
            )
            _atomic_write_json(paths.latest_file, result.to_dict())
            _append_log(paths, f"{key} skipped: already completed")
            return result

        state.setdefault("period_key", key)
        state.setdefault("created_at", datetime.now().astimezone().isoformat())
        state.setdefault("items", {})
        state["status"] = "planning"
        _atomic_write_json(state_path, state)

        if plan_path.exists():
            plan = load_plan(plan_path)
        else:
            factory = plan_factory or _default_plan_factory
            seed = int(key.replace("-", ""))
            plan = factory(config, seed)
            save_plan(plan, plan_path)

        state["plan_path"] = str(plan_path)
        state["estimated_total"] = round(plan.estimated_cart_total, 2)
        state["status"] = "planned"
        _atomic_write_json(state_path, state)

        if dry_run or not config.auto_add_to_cart:
            result = WeeklyRunResult(
                status="planned",
                period_key=key,
                plan_path=str(plan_path),
                estimated_total=plan.estimated_cart_total,
                items_added=0,
                items_skipped=0,
                message="Planen skapades men varukorgen ändrades inte.",
            )
            _atomic_write_json(paths.latest_file, result.to_dict())
            _append_log(paths, f"{key} planned only: {plan.estimated_cart_total:.2f} SEK")
            return result

        session_warning: str | None = None
        if config.refresh_session_headlessly:
            try:
                refreshed = refresh_session(data_dir=data_dir, headless=True)
                if not refreshed.likely_logged_in:
                    session_warning = "Sessionen kunde inte verifieras som inloggad."
            except BrowserAuthError as exc:
                # A still-valid exported cookie may continue to work. Do not open a browser.
                session_warning = str(exc)

        client = (client_factory or MathemClient)()
        added = 0
        skipped = 0
        ambiguous: list[str] = []
        failures: list[str] = []

        for line in plan.cart_lines:
            item_key = f"{line.product.id}:{line.quantity}"
            existing = state["items"].get(item_key, {})
            existing_status = existing.get("status")

            if existing_status == "added":
                skipped += 1
                continue
            if existing_status == "adding" and not retry_ambiguous:
                ambiguous.append(item_key)
                skipped += 1
                continue
            if existing_status == "failed" and not retry_failed:
                failures.append(item_key)
                skipped += 1
                continue

            state["items"][item_key] = {
                "product_id": line.product.id,
                "product": line.product.display_name,
                "quantity": line.quantity,
                "status": "adding",
                "started_at": datetime.now().astimezone().isoformat(),
            }
            state["status"] = "adding"
            _atomic_write_json(state_path, state)

            try:
                response = client.add_to_cart(line.product.id, line.quantity)
            except Exception as exc:
                state["items"][item_key]["status"] = "failed"
                state["items"][item_key]["error"] = str(exc)
                state["items"][item_key]["finished_at"] = (
                    datetime.now().astimezone().isoformat()
                )
                failures.append(item_key)
                _atomic_write_json(state_path, state)
                if isinstance(exc, MathemAuthError):
                    break
                continue

            state["items"][item_key]["status"] = "added"
            state["items"][item_key]["status_code"] = response.get("status_code")
            state["items"][item_key]["finished_at"] = (
                datetime.now().astimezone().isoformat()
            )
            added += 1
            _atomic_write_json(state_path, state)

        if ambiguous or failures:
            state["status"] = "needs_attention"
            state["ambiguous_items"] = ambiguous
            state["failed_items"] = failures
            if session_warning:
                state["session_warning"] = session_warning
            _atomic_write_json(state_path, state)
            message = (
                f"Veckokörningen behöver uppmärksamhet: {len(failures)} misslyckade och "
                f"{len(ambiguous)} osäkra varurader. Ingen synlig webbläsare öppnades."
            )
            result = WeeklyRunResult(
                status="needs_attention",
                period_key=key,
                plan_path=str(plan_path),
                estimated_total=plan.estimated_cart_total,
                items_added=added,
                items_skipped=skipped,
                message=message,
            )
            _atomic_write_json(paths.latest_file, result.to_dict())
            _append_log(paths, f"{key} needs attention: {message}")
            _notify("Mathem Agent behöver uppmärksamhet", message)
            return result

        state["status"] = "completed"
        state["completed_at"] = datetime.now().astimezone().isoformat()
        if session_warning:
            state["session_warning"] = session_warning
        _atomic_write_json(state_path, state)

        message = (
            f"{len(plan.cart_lines)} varurader lades i Mathem-varukorgen. "
            f"Estimerad summa: {plan.estimated_cart_total:.0f} kr."
        )
        result = WeeklyRunResult(
            status="completed",
            period_key=key,
            plan_path=str(plan_path),
            estimated_total=plan.estimated_cart_total,
            items_added=added,
            items_skipped=skipped,
            message=message,
        )
        _atomic_write_json(paths.latest_file, result.to_dict())
        _append_log(paths, f"{key} completed: {message}")
        _notify("Mathem-varukorgen är klar", message)
        return result


def read_latest_result(data_dir: str | Path | None = None) -> dict[str, Any]:
    paths = get_weekly_paths(data_dir)
    return _read_state(paths.latest_file)
