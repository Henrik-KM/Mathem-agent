from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MATHEM_BASE_URL = "https://www.mathem.se"
SIGNUP_URL = f"{MATHEM_BASE_URL}/se/user/signup/"
LOGIN_URL = f"{MATHEM_BASE_URL}/se/user/login/"
CART_URL = f"{MATHEM_BASE_URL}/se/cart/"


class BrowserAuthError(RuntimeError):
    """Raised when the local browser onboarding cannot be completed."""


@dataclass(frozen=True, slots=True)
class AuthPaths:
    data_dir: Path
    profile_dir: Path
    cookie_file: Path
    storage_state_file: Path
    metadata_file: Path


@dataclass(frozen=True, slots=True)
class AuthStatus:
    profile_exists: bool
    cookie_file_exists: bool
    cookie_count: int
    updated_at: str | None
    data_dir: str

    @property
    def configured(self) -> bool:
        return self.profile_exists and self.cookie_file_exists and self.cookie_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "profile_exists": self.profile_exists,
            "cookie_file_exists": self.cookie_file_exists,
            "cookie_count": self.cookie_count,
            "updated_at": self.updated_at,
            "data_dir": self.data_dir,
        }


@dataclass(frozen=True, slots=True)
class SetupResult:
    current_url: str
    cookie_count: int
    cookie_file: str
    storage_state_file: str
    likely_logged_in: bool


def get_auth_paths(data_dir: str | Path | None = None) -> AuthPaths:
    configured = data_dir or os.getenv("MATHEM_AGENT_HOME", "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".mathem-agent"
    return AuthPaths(
        data_dir=root,
        profile_dir=root / "browser-profile",
        cookie_file=root / "cookie.txt",
        storage_state_file=root / "storage-state.json",
        metadata_file=root / "session-metadata.json",
    )


def _make_private(path: Path, directory: bool = False) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if directory else 0))
    except OSError:
        # chmod is best-effort on Windows.
        pass


def ensure_auth_directories(paths: AuthPaths | None = None) -> AuthPaths:
    paths = paths or get_auth_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.profile_dir.mkdir(parents=True, exist_ok=True)
    _make_private(paths.data_dir, directory=True)
    _make_private(paths.profile_dir, directory=True)
    return paths


def cookie_header_from_cookies(cookies: list[dict[str, Any]]) -> str:
    """Convert Playwright cookies into a Cookie request header."""
    relevant: list[tuple[str, str]] = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lower()
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", ""))
        if not name or "mathem.se" not in domain:
            continue
        relevant.append((name, value))
    relevant.sort(key=lambda pair: pair[0].lower())
    return "; ".join(f"{name}={value}" for name, value in relevant)


def write_cookie_header(header: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header.strip(), encoding="utf-8")
    _make_private(path)


def _write_metadata(paths: AuthPaths, current_url: str, cookie_count: int) -> None:
    metadata = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_url": current_url,
        "cookie_count": cookie_count,
    }
    paths.metadata_file.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _make_private(paths.metadata_file)


def playwright_is_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return True


def install_chromium() -> None:
    if not playwright_is_available():
        raise BrowserAuthError("Playwright saknas. Kör 'uv sync' och försök igen.")
    completed = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if completed.returncode != 0:
        raise BrowserAuthError(
            "Chromium kunde inte installeras automatiskt. "
            "Kör 'uv run playwright install chromium' och försök igen."
        )


def _import_sync_playwright() -> Any:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise BrowserAuthError("Playwright saknas. Kör 'uv sync' och försök igen.") from exc
    return sync_playwright, PlaywrightError


def _launch_context(playwright: Any, paths: AuthPaths, headless: bool = False) -> Any:
    try:
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(paths.profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="sv-SE",
        )
    except Exception as exc:
        message = str(exc).lower()
        browser_missing = "executable doesn't exist" in message or (
            "browser" in message and "install" in message
        )
        if browser_missing:
            raise BrowserAuthError(
                "Chromium är inte installerad. Kör "
                "'uv run playwright install chromium' och försök igen."
            ) from exc
        raise BrowserAuthError(
            f"Kunde inte starta den lokala Mathem-webbläsaren: {exc}"
        ) from exc


def _export_context(context: Any, paths: AuthPaths, current_url: str) -> SetupResult:
    cookies = context.cookies([MATHEM_BASE_URL])
    header = cookie_header_from_cookies(cookies)
    if not header:
        raise BrowserAuthError(
            "Ingen Mathem-session hittades. Slutför registrering/inloggning i webbläsaren "
            "innan du bekräftar i terminalen."
        )
    write_cookie_header(header, paths.cookie_file)
    context.storage_state(path=str(paths.storage_state_file))
    _make_private(paths.storage_state_file)
    _write_metadata(paths, current_url=current_url, cookie_count=len(cookies))
    likely_logged_in = "/user/login" not in current_url and "/user/signup" not in current_url
    return SetupResult(
        current_url=current_url,
        cookie_count=len(cookies),
        cookie_file=str(paths.cookie_file),
        storage_state_file=str(paths.storage_state_file),
        likely_logged_in=likely_logged_in,
    )


def setup_account(
    *,
    existing_account: bool = False,
    install_browser: bool = True,
    data_dir: str | Path | None = None,
) -> SetupResult:
    """
    Open Mathem's own signup/login page and save the resulting local browser session.

    The user enters personal data and accepts Mathem's terms directly on Mathem's website.
    This function never receives or stores the user's password.
    """
    paths = ensure_auth_directories(get_auth_paths(data_dir))
    if install_browser:
        install_chromium()

    sync_playwright, _ = _import_sync_playwright()
    target_url = LOGIN_URL if existing_account else SIGNUP_URL
    with sync_playwright() as playwright:
        context = _launch_context(playwright, paths, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=120_000)
            print()
            print("Mathem har öppnats i en separat lokal webbläsarprofil.")
            if existing_account:
                print("Logga in på ditt Mathem-konto.")
            else:
                print("Skapa ditt konto direkt hos Mathem och logga in.")
            print("Fyll själv i personuppgifter och godkänn Mathems villkor på deras webbplats.")
            print("Lägg gärna in leveransadress nu, så används lokala priser och leveranstider.")
            input("När du är inloggad och ser Mathems startsida: tryck Enter här ... ")
            current_page = context.pages[-1] if context.pages else page
            result = _export_context(context, paths, current_url=current_page.url)
        finally:
            context.close()
    return result


def refresh_session(
    *,
    data_dir: str | Path | None = None,
    headless: bool = True,
) -> SetupResult:
    """Export fresh cookies from the saved persistent browser profile."""
    paths = get_auth_paths(data_dir)
    if not paths.profile_dir.exists():
        raise BrowserAuthError("Ingen lokal Mathem-profil finns. Kör 'mathem-agent setup' först.")

    sync_playwright, _ = _import_sync_playwright()
    with sync_playwright() as playwright:
        context = _launch_context(playwright, paths, headless=headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(MATHEM_BASE_URL, wait_until="domcontentloaded", timeout=120_000)
            result = _export_context(context, paths, current_url=page.url)
        finally:
            context.close()
    return result


def open_authenticated_browser(
    url: str = CART_URL,
    *,
    data_dir: str | Path | None = None,
) -> SetupResult:
    """Open a page in the persistent Mathem browser profile and refresh exported cookies."""
    paths = get_auth_paths(data_dir)
    if not paths.profile_dir.exists():
        raise BrowserAuthError("Ingen lokal Mathem-profil finns. Kör 'mathem-agent setup' först.")

    sync_playwright, _ = _import_sync_playwright()
    with sync_playwright() as playwright:
        context = _launch_context(playwright, paths, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            print("Den inloggade Mathem-webbläsaren är öppen.")
            input("Slutför det du vill göra där och tryck sedan Enter här för att stänga ... ")
            current_page = context.pages[-1] if context.pages else page
            result = _export_context(context, paths, current_url=current_page.url)
        finally:
            context.close()
    return result


def get_auth_status(data_dir: str | Path | None = None) -> AuthStatus:
    paths = get_auth_paths(data_dir)
    cookie_count = 0
    if paths.cookie_file.exists():
        header = paths.cookie_file.read_text(encoding="utf-8").strip()
        cookie_count = sum(1 for part in header.split(";") if "=" in part)

    updated_at: str | None = None
    if paths.metadata_file.exists():
        try:
            metadata = json.loads(paths.metadata_file.read_text(encoding="utf-8"))
            value = metadata.get("updated_at")
            updated_at = str(value) if value else None
        except (OSError, json.JSONDecodeError):
            updated_at = None

    return AuthStatus(
        profile_exists=paths.profile_dir.exists(),
        cookie_file_exists=paths.cookie_file.exists(),
        cookie_count=cookie_count,
        updated_at=updated_at,
        data_dir=str(paths.data_dir),
    )
