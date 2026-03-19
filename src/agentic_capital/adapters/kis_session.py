"""Shared KIS API session — single token and rate limiter for all KIS adapters."""

from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
import structlog

from agentic_capital.config import settings

logger = structlog.get_logger()

_REAL_BASE = "https://openapi.koreainvestment.com:9443"
_PAPER_BASE = "https://openapivts.koreainvestment.com:29443"

# KIS 모의투자 rate limit is strict (~1 req/sec for some endpoints)
_MIN_REQUEST_INTERVAL = 0.35  # 350ms between requests

# Token cache path — persists across process restarts to avoid 1/min rate limit
_TOKEN_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".cache", "agentic_capital", "kis_token.json")
_TOKEN_BUFFER_SECS = 300  # Treat token as expired 5 min before actual expiry


def _load_cached_token(app_key: str, is_paper: bool) -> str | None:
    """Load token from file cache if still valid."""
    try:
        with open(_TOKEN_CACHE_PATH) as f:
            data = json.load(f)
        # Cache is keyed by (app_key prefix + mode) to handle multiple accounts
        cache_key = f"{app_key[:8]}:{'paper' if is_paper else 'real'}"
        entry = data.get(cache_key)
        if not entry:
            return None
        expires_at = entry.get("expires_at", 0)
        if time.time() < expires_at - _TOKEN_BUFFER_SECS:
            return entry.get("token")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def _save_cached_token(app_key: str, is_paper: bool, token: str, expires_in: int = 86400) -> None:
    """Save token to file cache with expiry timestamp."""
    try:
        os.makedirs(os.path.dirname(_TOKEN_CACHE_PATH), exist_ok=True)
        try:
            with open(_TOKEN_CACHE_PATH) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        cache_key = f"{app_key[:8]}:{'paper' if is_paper else 'real'}"
        data[cache_key] = {"token": token, "expires_at": time.time() + expires_in}
        with open(_TOKEN_CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # Cache write failure is non-fatal


class KISSession:
    """Shared session for KIS Open API.

    Manages a single access token, httpx client, and request throttling,
    shared across trading and market data adapters.
    """

    def __init__(
        self,
        *,
        app_key: str = "",
        app_secret: str = "",
        account_no: str = "",
        is_paper: bool | None = None,
    ) -> None:
        self.is_paper = is_paper if is_paper is not None else settings.kis_is_paper
        self.app_key = app_key or settings.effective_kis_app_key
        self.app_secret = app_secret or settings.effective_kis_app_secret
        self.account_no = account_no or settings.effective_kis_account_no
        if not all([self.app_key, self.app_secret, self.account_no]):
            raise ValueError("KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO are required")

        self.base_url = _PAPER_BASE if self.is_paper else _REAL_BASE
        self.client = httpx.AsyncClient(timeout=15.0)
        self._access_token: str | None = _load_cached_token(self.app_key, self.is_paper)
        self._last_request_time: float = 0.0
        self._throttle_lock = asyncio.Lock()

        mode = "paper" if self.is_paper else "LIVE"
        logger.info("kis_session_created", mode=mode, account=self.account_no)

    async def _throttle(self) -> None:
        """Enforce minimum interval between API requests."""
        async with self._throttle_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < _MIN_REQUEST_INTERVAL:
                await asyncio.sleep(_MIN_REQUEST_INTERVAL - elapsed)
            self._last_request_time = time.monotonic()

    async def _request_with_retry(
        self, method: str, url: str, max_retries: int = 2, **kwargs
    ) -> httpx.Response:
        """Rate-limited request with retry on rate limit errors."""
        for attempt in range(max_retries + 1):
            await self._throttle()
            if method == "GET":
                r = await self.client.get(url, **kwargs)
            else:
                r = await self.client.post(url, **kwargs)

            data = r.json()
            msg = data.get("msg1", "")
            if "초당 거래건수를 초과" in str(msg) and attempt < max_retries:
                wait = 1.0 * (attempt + 1)
                logger.warning("kis_rate_limited", attempt=attempt + 1, wait=wait)
                await asyncio.sleep(wait)
                continue
            return r
        return r  # pragma: no cover

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Rate-limited GET request with retry."""
        return await self._request_with_retry("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Rate-limited POST request with retry."""
        return await self._request_with_retry("POST", url, **kwargs)

    async def ensure_token(self) -> str:
        """Get or reuse cached access token. Retries on rate limit (1/min)."""
        if self._access_token:
            return self._access_token
        # Check file cache (populated on previous runs)
        cached = _load_cached_token(self.app_key, self.is_paper)
        if cached:
            self._access_token = cached
            logger.info("kis_token_reused_from_cache")
            return self._access_token

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                await self._throttle()
                r = await self.client.post(
                    f"{self.base_url}/oauth2/tokenP",
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self.app_key,
                        "appsecret": self.app_secret,
                    },
                )
                data = r.json()
                if "access_token" in data:
                    self._access_token = data["access_token"]
                    expires_in = int(data.get("expires_in", 86400))
                    _save_cached_token(self.app_key, self.is_paper, self._access_token, expires_in)
                    logger.info("kis_token_acquired")
                    return self._access_token

                error_code = data.get("error_code", "")
                if error_code == "EGW00133" and attempt < max_retries:
                    wait = 62  # KIS enforces 1 token per minute
                    logger.warning("kis_token_rate_limited", attempt=attempt + 1, wait=wait)
                    await asyncio.sleep(wait)
                    continue

                raise RuntimeError(f"KIS token failed: {data}")
            except RuntimeError:
                raise
            except Exception:
                logger.exception("kis_token_failed")
                raise
        raise RuntimeError("KIS token failed after retries")  # pragma: no cover

    def headers(self, tr_id: str) -> dict[str, str]:
        """Build request headers with current token."""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    @property
    def cano(self) -> str:
        return self.account_no[:8]

    @property
    def prdt_cd(self) -> str:
        return self.account_no[8:]
