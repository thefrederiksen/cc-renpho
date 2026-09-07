"""Credential loading and a thin wrapper over the `renpho-api` client.

Renpho publishes no official API. The Renpho Health app talks to a private REST
backend at cloud.renpho.com where every request and response body is AES-128-ECB
encrypted with a key compiled into the app. The `renpho-api` package implements
that protocol; this module adds credential handling and errors that say what to
do next.

There is deliberately no fallback path. If the credentials are missing, or the
login is rejected, or the API changes shape, this raises with the specific cause
rather than degrading to a partial result - a health export that silently
returns less than the account holds is worse than one that fails.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .errors import AuthError, ConfigError, ApiError


def load_credentials(credentials_file: str | os.PathLike | None = None) -> tuple[str, str]:
    """Resolve the Renpho email and password.

    Order: explicit file, then RENPHO_EMAIL / RENPHO_PASSWORD in the
    environment. Never prompts - this runs unattended under an agent.
    """
    if credentials_file:
        path = Path(credentials_file)
        if not path.exists():
            raise ConfigError(f"Credentials file not found: {path}")
        values = parse_env_file(path)
        email = values.get("RENPHO_EMAIL")
        password = values.get("RENPHO_PASSWORD")
        missing = [k for k, v in (("RENPHO_EMAIL", email), ("RENPHO_PASSWORD", password)) if not v]
        if missing:
            raise ConfigError(
                f"{path} is missing {' and '.join(missing)}. "
                "Add them as KEY=VALUE lines and run again."
            )
        return email, password

    email = os.environ.get("RENPHO_EMAIL")
    password = os.environ.get("RENPHO_PASSWORD")
    if not email or not password:
        raise ConfigError(
            "Set RENPHO_EMAIL and RENPHO_PASSWORD in the environment, or pass "
            "--credentials-file pointing at a file containing them. The password is the "
            "plaintext account password - the client performs the encryption the app does."
        )
    return email, password


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env style file. Ignores blanks, comments and malformed lines."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


class Renpho:
    """A logged-in Renpho Health account."""

    def __init__(self, email: str, password: str, debug: bool = False):
        try:
            from renpho.client import RenphoClient
        except ImportError as exc:  # pragma: no cover - install-time problem
            raise ConfigError(
                "The `renpho-api` package is required and is not installed. "
                "Install it with: pip install renpho-api"
            ) from exc

        self.email = email
        self._client = RenphoClient(email, password, debug=debug)
        self._logged_in = False

    def login(self) -> str:
        from renpho.client import RenphoAPIError

        try:
            self._client.login()
        except RenphoAPIError as exc:
            raise AuthError(
                f"Renpho rejected the login for {self.email}: {exc}. "
                "Check the password, and check the account is a Renpho Health account - "
                "the older Renpho app uses a different backend and different credentials."
            ) from exc
        self._logged_in = True
        return str(self._client.user_id)

    @property
    def user_id(self) -> str:
        self._require_login()
        return str(self._client.user_id)

    def _require_login(self) -> None:
        if not self._logged_in:
            raise ApiError("login() must be called before using the account")

    def server_record_count(self) -> int | None:
        """How many scale records the server says it holds.

        This is the only independent check on the download. Without it, a short
        download looks exactly like a complete one.
        """
        self._require_login()
        info = self._client.get_device_info() or {}
        scales = info.get("scale") or []
        if not scales:
            return None
        return sum(table.get("count", 0) for table in scales)

    def device_info(self) -> dict[str, Any]:
        self._require_login()
        return self._client.get_device_info() or {}

    def measurements(self) -> list[dict]:
        """Every scale measurement on the account, oldest first."""
        self._require_login()
        from renpho.client import RenphoAPIError

        try:
            records = self._client.get_all_measurements()
        except RenphoAPIError as exc:
            raise ApiError(f"Renpho refused the measurement request: {exc}") from exc
        records.sort(key=lambda m: m["localCreatedAt"])
        return records
