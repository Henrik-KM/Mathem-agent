from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .weekly import WeeklyAutomationError, WeeklyConfig, get_weekly_paths

TASK_NAME = "Mathem Agent Weekly"
CRON_BEGIN = "# BEGIN MATHEM_AGENT_WEEKLY"
CRON_END = "# END MATHEM_AGENT_WEEKLY"


class SchedulerError(WeeklyAutomationError):
    """Raised when the operating-system scheduler cannot be configured."""


@dataclass(frozen=True, slots=True)
class SchedulerStatus:
    installed: bool
    backend: str
    schedule: str
    runner: str | None = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _find_project_root(project_dir: str | Path | None = None) -> Path:
    if project_dir:
        root = Path(project_dir).expanduser().resolve()
        if not (root / "pyproject.toml").exists():
            raise SchedulerError(f"Ingen pyproject.toml hittades i {root}.")
        return root

    candidates = [Path.cwd().resolve(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        for current in (candidate, *candidate.parents):
            if (current / "pyproject.toml").exists():
                return current
    raise SchedulerError(
        "Kunde inte hitta repo-roten. Kör kommandot från Mathem-agent-katalogen."
    )


def _find_uv() -> Path:
    value = shutil.which("uv")
    if not value:
        raise SchedulerError("'uv' finns inte i PATH. Installera uv och försök igen.")
    return Path(value).resolve()


def _write_runner(
    config: WeeklyConfig,
    project_dir: str | Path | None = None,
) -> Path:
    root = _find_project_root(project_dir)
    uv = _find_uv()
    paths = get_weekly_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)

    if platform.system().lower() == "windows":
        runner = paths.data_dir / "run-mathem-weekly.cmd"
        content = (
            "@echo off\r\n"
            f'cd /d "{root}"\r\n'
            f'"{uv}" run --project "{root}" mathem-agent weekly run '
            f'>> "{paths.log_file}" 2>&1\r\n'
        )
    else:
        runner = paths.data_dir / "run-mathem-weekly.sh"
        content = (
            "#!/bin/sh\n"
            f"cd {shlex.quote(str(root))}\n"
            f"exec {shlex.quote(str(uv))} run --project {shlex.quote(str(root))} "
            f"mathem-agent weekly run >> {shlex.quote(str(paths.log_file))} 2>&1\n"
        )

    runner.write_text(content, encoding="utf-8")
    if platform.system().lower() != "windows":
        runner.chmod(0o700)
    return runner


def _run_command(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SchedulerError(f"Kunde inte köra {' '.join(command)}: {exc}") from exc


def _without_cron_block(text: str) -> str:
    output: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip() == CRON_BEGIN:
            inside = True
            continue
        if line.strip() == CRON_END:
            inside = False
            continue
        if not inside:
            output.append(line)
    return "\n".join(output).strip()


def _install_windows(config: WeeklyConfig, runner: Path) -> SchedulerStatus:
    command = [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        TASK_NAME,
        "/TR",
        f'cmd.exe /d /c "{runner}"',
        "/SC",
        "DAILY",
        "/ST",
        config.schedule_time,
        "/RL",
        "LIMITED",
    ]
    completed = _run_command(command)
    if completed.returncode != 0:
        raise SchedulerError(
            "Windows Task Scheduler kunde inte konfigureras: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return SchedulerStatus(
        installed=True,
        backend="Windows Task Scheduler",
        schedule=(
            f"daglig kontroll {config.schedule_time}; faktisk körning första gången på eller "
            f"efter {config.schedule_day} varje period"
        ),
        runner=str(runner),
        details=completed.stdout.strip(),
    )


def _install_cron(config: WeeklyConfig, runner: Path) -> SchedulerStatus:
    current = _run_command(["crontab", "-l"])
    existing = current.stdout if current.returncode == 0 else ""
    cleaned = _without_cron_block(existing)
    hour, minute = config.schedule_time.split(":", maxsplit=1)
    block = "\n".join(
        [
            CRON_BEGIN,
            f"{int(minute)} {int(hour)} * * * {shlex.quote(str(runner))}",
            CRON_END,
        ]
    )
    updated = f"{cleaned}\n{block}\n" if cleaned else f"{block}\n"
    completed = _run_command(["crontab", "-"], input_text=updated)
    if completed.returncode != 0:
        raise SchedulerError(
            f"crontab kunde inte uppdateras: {completed.stderr.strip()}"
        )
    return SchedulerStatus(
        installed=True,
        backend="cron",
        schedule=(
            f"daglig kontroll {config.schedule_time}; faktisk körning första gången på eller "
            f"efter {config.schedule_day} varje period"
        ),
        runner=str(runner),
    )


def install_scheduler(
    config: WeeklyConfig,
    *,
    project_dir: str | Path | None = None,
) -> SchedulerStatus:
    """
    Install a daily local check at the configured time.

    The job itself is weekly and idempotent. Running the lightweight check daily means a
    sleeping/offline computer catches up the next day instead of missing the whole week.
    """
    config.validate()
    runner = _write_runner(config, project_dir=project_dir)
    if platform.system().lower() == "windows":
        return _install_windows(config, runner)
    return _install_cron(config, runner)


def uninstall_scheduler() -> SchedulerStatus:
    if platform.system().lower() == "windows":
        completed = _run_command(["schtasks", "/Delete", "/F", "/TN", TASK_NAME])
        if completed.returncode != 0 and "cannot find" not in completed.stderr.lower():
            raise SchedulerError(
                "Kunde inte ta bort Windows-jobbet: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        return SchedulerStatus(
            installed=False,
            backend="Windows Task Scheduler",
            schedule="removed",
            details=completed.stdout.strip(),
        )

    current = _run_command(["crontab", "-l"])
    existing = current.stdout if current.returncode == 0 else ""
    cleaned = _without_cron_block(existing)
    completed = _run_command(["crontab", "-"], input_text=(cleaned + "\n") if cleaned else "")
    if completed.returncode != 0:
        raise SchedulerError(
            f"Kunde inte uppdatera crontab: {completed.stderr.strip()}"
        )
    return SchedulerStatus(installed=False, backend="cron", schedule="removed")


def scheduler_status(config: WeeklyConfig) -> SchedulerStatus:
    paths = get_weekly_paths()
    runner = (
        paths.data_dir / "run-mathem-weekly.cmd"
        if platform.system().lower() == "windows"
        else paths.data_dir / "run-mathem-weekly.sh"
    )

    if platform.system().lower() == "windows":
        completed = _run_command(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"])
        installed = completed.returncode == 0
        details = completed.stdout.strip() if installed else completed.stderr.strip()
        return SchedulerStatus(
            installed=installed,
            backend="Windows Task Scheduler",
            schedule=f"daily {config.schedule_time}",
            runner=str(runner) if runner.exists() else None,
            details=details,
        )

    current = _run_command(["crontab", "-l"])
    existing = current.stdout if current.returncode == 0 else ""
    installed = CRON_BEGIN in existing and CRON_END in existing
    return SchedulerStatus(
        installed=installed,
        backend="cron",
        schedule=f"daily {config.schedule_time}",
        runner=str(runner) if runner.exists() else None,
        details="Mathem Agent block found" if installed else "Mathem Agent block missing",
    )
