# soot_tool/auth.py
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import requests


BASE_URL  = "https://asdc.larc.nasa.gov/soot-api"
AUTH_URL  = f"{BASE_URL}/Authenticate/user"
LOGIN_URL = f"{BASE_URL}/login"
URS_BASE  = "https://urs.earthdata.nasa.gov"


# ---------------------------------------------------------------------------
# Primary auth: username + password → full OAuth flow → authenticated session
# ---------------------------------------------------------------------------

def session_from_credentials(username: str, password: str) -> requests.Session:
    username = username.strip()
    password = password.strip()

    if not username or not password:
        raise ValueError("Username and password cannot be empty.")

    session = requests.Session()
    session.headers.update({"User-Agent": "python-requests/soot-tool"})

    r1 = session.get(AUTH_URL, allow_redirects=True, timeout=30)

    # Case 1: OAuth may already be complete even if cookie inspection is unreliable.
    # Verify by calling a protected SOOT endpoint directly.
    test = session.get(
        f"{BASE_URL}/campaigns",
        allow_redirects=True,
        timeout=30,
        headers={"Accept": "application/json"},
    )

    if test.status_code == 200:
        return session

    # Case 2: We are actually on the URS login page and need to submit credentials
    if "urs.earthdata.nasa.gov" not in r1.url:
        history_urls = [resp.url for resp in r1.history]
        raise RuntimeError(
            f"Did not reach URS login page. Final URL: {r1.url}. "
            f"Redirect chain: {history_urls + [r1.url]}"
        )

    authenticity_token = _extract_authenticity_token(r1.text)
    if not authenticity_token:
        raise RuntimeError(
            "Could not extract authenticity_token from URS login page. "
            "The URS login form may have changed."
        )

    oauth_params = _extract_oauth_params(r1.url)

    login_payload = {
        "username": username,
        "password": password,
        "authenticity_token": authenticity_token,
        "client_id": oauth_params.get("client_id", ""),
        "redirect_uri": oauth_params.get("redirect_uri", ""),
        "response_type": oauth_params.get("response_type", "code"),
        "state": oauth_params.get("state", ""),
        "stay_in": "1",
        "commit": "Log in",
    }

    username = None
    password = None

    r2 = session.post(
        f"{URS_BASE}/login",
        data=login_payload,
        allow_redirects=True,
        timeout=30,
    )

    login_payload["username"] = None
    login_payload["password"] = None

    if "urs.earthdata.nasa.gov" in r2.url and "oauth" in r2.url.lower():
        raise RuntimeError(
            "Login failed — still on URS after credential submission. "
            "Please check your username and password."
        )

    if r2.status_code not in (200, 302):
        raise RuntimeError(
            f"URS login returned unexpected status {r2.status_code}. "
            "Please check your username and password."
        )

    asdc_cookies = [
        c for c in session.cookies
        if "asdc" in c.domain.lower() or "larc" in c.domain.lower()
    ]
    if not asdc_cookies:
        raise RuntimeError(
            "Authentication appeared to succeed but no ASDC session cookie "
            "was set. Please check your username and password and try again."
        )

    return session


def _extract_authenticity_token(html: str) -> str | None:
    """Extract the CSRF authenticity_token from the URS login form HTML."""
    # Try meta tag first (newer URS layout)
    match = re.search(
        r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # Fall back to hidden input field
    match = re.search(
        r'<input[^>]+name=["\']authenticity_token["\'][^>]+value=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # Try reverse attribute order
    match = re.search(
        r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']authenticity_token["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    return None


def _extract_oauth_params(url: str) -> dict:
    """Extract OAuth query parameters from the URS authorize URL."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {k: v[0] for k, v in params.items()}


# ---------------------------------------------------------------------------
# Auth verification
# ---------------------------------------------------------------------------

def assert_authorized(session: requests.Session, *, timeout: int = 60) -> None:
    """
    Verify the session can reach the SOOT metadata API.
    Uses the campaigns endpoint which is accessible with a valid session.
    """
    r = session.get(
        f"{BASE_URL}/campaigns",
        allow_redirects=True,
        timeout=timeout,
        headers={"Accept": "application/json"},
    )

    if r.status_code == 401:
        raise RuntimeError(
            "Authorization failed (HTTP 401). "
            "Please check your username and password."
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"Authorization failed (HTTP {r.status_code}). "
            "Please check your credentials and try again."
        )