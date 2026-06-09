from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from core.logging_config import get_logger
from services.iol_api.config import IOLBotSettings

logger = get_logger(__name__)


class IOLApiError(RuntimeError):
    """Error de comunicacion con API IOL."""


@dataclass
class _TokenState:
    access_token: str = ""
    refresh_token: str = ""
    expires_at_epoch: float = 0.0

    def valid_for(self, min_seconds: float = 20.0) -> bool:
        return bool(self.access_token) and (self.expires_at_epoch - time.time() > min_seconds)


class IOLApiClient:
    def __init__(
        self,
        settings: IOLBotSettings,
        session: requests.Session | None = None,
        max_retries: int = 3,
        retry_backoff_sec: float = 1.0,
    ) -> None:
        self.settings = settings
        self._session = session or requests.Session()
        self._tokens = _TokenState()
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_sec = max(0.1, float(retry_backoff_sec))

    def _url(self, path: str) -> str:
        return f"{self.settings.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        if auth:
            self.ensure_authenticated()
            headers = kwargs.setdefault("headers", {})
            headers["Authorization"] = f"Bearer {self._tokens.access_token}"

        last_error: Exception | None = None
        url = self._url(path)
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._session.request(method=method, url=url, timeout=self.settings.timeout_sec, **kwargs)
                if response.status_code == 401 and auth:
                    self.refresh_access_token()
                    kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {self._tokens.access_token}"
                    response = self._session.request(
                        method=method, url=url, timeout=self.settings.timeout_sec, **kwargs
                    )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
                wait = self._retry_backoff_sec * (2 ** (attempt - 1))
                logger.warning(
                    "IOL request retry method=%s path=%s attempt=%s/%s error=%s",
                    method,
                    path,
                    attempt,
                    self._max_retries,
                    exc,
                )
                time.sleep(wait)
        raise IOLApiError(f"Fallo request {method} {path}: {last_error}") from last_error

    def login(self) -> dict[str, Any]:
        if not self.settings.username or not self.settings.password:
            raise IOLApiError("Faltan IOL_USERNAME/IOL_PASSWORD en entorno.")
        payload = {
            "username": self.settings.username,
            "password": self.settings.password,
            "grant_type": "password",
        }
        response = self._request_with_retry(
            "POST",
            self.settings.auth_path,
            auth=False,
            data=payload,
        )
        data = response.json()
        self._tokens.access_token = str(data.get("access_token", ""))
        self._tokens.refresh_token = str(data.get("refresh_token", ""))
        expires_in = float(data.get("expires_in", 900) or 900)
        self._tokens.expires_at_epoch = time.time() + expires_in
        if not self._tokens.access_token:
            raise IOLApiError("Login IOL sin access_token.")
        return data

    def refresh_access_token(self) -> dict[str, Any]:
        if not self._tokens.refresh_token:
            return self.login()
        payload = {
            "refresh_token": self._tokens.refresh_token,
            "grant_type": "refresh_token",
        }
        response = self._request_with_retry(
            "POST",
            self.settings.auth_path,
            auth=False,
            data=payload,
        )
        data = response.json()
        self._tokens.access_token = str(data.get("access_token", ""))
        self._tokens.refresh_token = str(data.get("refresh_token", self._tokens.refresh_token))
        expires_in = float(data.get("expires_in", 900) or 900)
        self._tokens.expires_at_epoch = time.time() + expires_in
        if not self._tokens.access_token:
            raise IOLApiError("Refresh IOL sin access_token.")
        return data

    def ensure_authenticated(self) -> None:
        if self._tokens.valid_for():
            return
        if self._tokens.refresh_token:
            self.refresh_access_token()
        else:
            self.login()

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request_with_retry("GET", path, params=params or {})
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"items": data}

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request_with_retry("POST", path, json=payload)
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"items": data}

    def get_quote(self, market: str, symbol: str) -> dict[str, Any]:
        path = self.settings.quote_endpoint_template.format(market=market, symbol=symbol)
        return self.get_json(path)
