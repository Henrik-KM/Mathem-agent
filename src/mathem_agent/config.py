from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path.cwd()


def load_env() -> None:
    """Load .env when python-dotenv is installed. Safe no-op otherwise."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    cookie: str = ""
    user_agent: str = "mathem-agent-bot/0.1 personal-prototype contact:local"
    default_people: int = 2
    default_meals: int = 4
    default_budget_sek: float = 900.0


def _read_cookie_file() -> str:
    for path in (Path("cookie.txt"), Path.home() / ".mathem-agent" / "cookie.txt"):
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    return ""


def get_settings() -> Settings:
    load_env()
    cookie = os.getenv("MATHEM_COOKIE", "").strip() or _read_cookie_file()
    return Settings(
        cookie=cookie,
        user_agent=os.getenv(
            "MATHEM_USER_AGENT",
            "mathem-agent-bot/0.1 personal-prototype contact:local",
        ).strip(),
        default_people=int(os.getenv("MATHEM_DEFAULT_PEOPLE", "2")),
        default_meals=int(os.getenv("MATHEM_DEFAULT_MEALS", "4")),
        default_budget_sek=float(os.getenv("MATHEM_DEFAULT_BUDGET_SEK", "900")),
    )
