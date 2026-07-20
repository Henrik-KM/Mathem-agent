from pathlib import Path

from mathem_agent.browser_auth import (
    cookie_header_from_cookies,
    get_auth_paths,
    get_auth_status,
    write_cookie_header,
)


def test_cookie_header_filters_non_mathem_domains():
    cookies = [
        {"name": "sessionid", "value": "abc", "domain": ".mathem.se"},
        {"name": "csrftoken", "value": "def", "domain": "www.mathem.se"},
        {"name": "other", "value": "ignored", "domain": ".example.com"},
    ]
    header = cookie_header_from_cookies(cookies)
    assert header == "csrftoken=def; sessionid=abc"


def test_auth_status_for_saved_cookie(tmp_path: Path):
    paths = get_auth_paths(tmp_path)
    paths.profile_dir.mkdir(parents=True)
    write_cookie_header("a=1; b=2", paths.cookie_file)
    status = get_auth_status(tmp_path)
    assert status.configured
    assert status.cookie_count == 2
