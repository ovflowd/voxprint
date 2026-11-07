"""HTTP client for the Voxprint app (app/server.py)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_VERSION, MODEL, REQUEST_TIMEOUT_S


class AppError(Exception):
    """The app couldn't give an answer. `code` is the error the sensor shows."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


class AppClient:
    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self.url = url.rstrip("/")

    async def health(self) -> dict[str, Any]:
        """The app's /health reply, checked for this integration's API version and model."""
        info = await self._request("GET", "/health", timeout=10)
        if info.get("api") != API_VERSION or info.get("model") != MODEL:
            raise AppError("app_incompatible", f"api {info.get('api')}, model {info.get('model')}")
        return info

    async def embed(self, pcm: bytes) -> dict[str, Any]:
        """One utterance (s16le, 16 kHz, mono) in, the app's reply out."""
        return await self._request(
            "POST",
            "/v1/embed",
            timeout=REQUEST_TIMEOUT_S,
            data=pcm,
            headers={"Content-Type": "application/octet-stream"},
        )

    async def _request(self, method: str, path: str, timeout: float, **kwargs: Any) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout):
                async with self._session.request(method, f"{self.url}{path}", **kwargs) as resp:
                    resp.raise_for_status()
                    body = await resp.json()
        except TimeoutError as err:
            raise AppError("app_timeout") from err
        except (aiohttp.ClientError, ValueError) as err:
            raise AppError("app_unavailable", repr(err)) from err
        if not isinstance(body, dict):
            raise AppError("bad_response", "not a JSON object")
        return body
