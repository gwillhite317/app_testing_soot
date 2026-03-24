from __future__ import annotations

import re

import requests


BASE_URL  = "https://asdc.larc.nasa.gov/soot-api"
AUTH_URL  = f"{BASE_URL}/Authenticate/user"
URS_BASE  = "https://urs.earthdata.nasa.gov"


def session_from_credentials(username: str, password: str) -> requests.Session:
    """
    Authenticate with NASA Earthdata by completing the full OAuth2 flow
    programmatically using the user's username and password.
    """
    username = username.strip()
    password = password.strip()

    if not username or not password:
        raise ValueError("Username and password cannot be empty.")

    session = requests.Session()
    session.headers.update({"User-Agent": "python-requests/soot-tool"})

    # Step 1: Hit ASDC auth endpoint, follow to URS OAuth page
    r1 = session.get(AUTH_URL, allow_redirects=True, timeout=30)

    if "urs.earthdata.nasa.gov" not in r1.url:
        raise RuntimeError(
            f"Unexpected redirect target: {r1.url}. "
            "The ASDC auth endpoint may have changed."
        )

    # Step 2: Parse URS login form
    authenticity_token = _extract_authenticity_token(r1.text)
    if not authenticity_token:
        raise RuntimeError(
            "Could not extract authenticity_token from URS login page. "
            "The URS login form may have changed."
        )

    oauth_params = _extract_oauth_params(r1.url)

    # Step 3: Submit credentials
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

    # Step 4: Make sure we did not stay on URS
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

    # Step 5: Verify ASDC session cookie exists
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
    match = re.search(
        r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    match = re.search(
        r'<input[^>]+name=["\']authenticity_token["\'][^>]+value=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    match = re.search(
        r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']authenticity_token["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    return None


def _extract_oauth_params(url: str) -> dict:
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {k: v[0] for k, v in params.items()}


def assert_authorized(session: requests.Session, *, timeout: int = 60) -> None:
    """
    Verify the session can reach the SOOT metadata API.
    This is still only a metadata check, not a guaranteed file-download check.
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