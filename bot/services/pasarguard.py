from __future__ import annotations

import asyncio
import random
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp
from loguru import logger

from bot.config import settings


class PasarGuardClient:
    """
    High-performance async REST client for PasarGuard / Marzban API.
    Features:
    - Connection pooling (up to 100 connections)
    - DNS caching
    - In-memory 30s TTL cache for get_user (protects Marzban under 10k users)
    - Automatic token refresh & exponential retry
    """

    def __init__(self) -> None:
        self._base_url = settings.panel_url.rstrip("/")
        self._token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._user_cache: dict[str, tuple[float, dict]] = {}  # username -> (timestamp, data)
        self._cache_ttl = 30.0  # seconds

    @property
    def is_configured(self) -> bool:
        has_api_key = bool(self._base_url and settings.panel_api_key)
        has_user_pass = bool(self._base_url and settings.panel_username and settings.panel_password)
        return has_api_key or has_user_pass

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

        if not self.is_configured:
            logger.info("PasarGuard: مشخصات پنل خالی است — ربات در حالت مستقل/کیف‌پول اجرا می‌شود.")
            return

        if settings.panel_api_key:
            try:
                info = await self.get_admin_info()
                logger.info(f"PasarGuard: با موفقیت به پنل متصل شد (ادمین: {info.get('username')})")
            except Exception as exc:
                logger.warning(f"PasarGuard: خطا در اتصال با کلید API ({exc})")
            return

        try:
            await self._login()
        except Exception as exc:
            logger.warning(
                f"PasarGuard: اتصال اولیه به پنل برقرار نشد ({exc}). ربات در حالت آماده‌باش/کیف‌پول اجرا می‌شود."
            )

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    # ─── Auth ───────────────────────────────────────────────

    async def _login(self) -> None:
        """Obtain a fresh JWT token from the panel."""
        assert self._session is not None
        payload = {
            "username": settings.panel_username,
            "password": settings.panel_password,
        }
        async with self._session.post(
            f"{self._base_url}/api/admin/token",
            data=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._token = data.get("access_token")
            logger.info("PasarGuard: توکن ادمین دریافت گردید.")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if settings.panel_api_key:
            headers["X-Api-Key"] = settings.panel_api_key
        elif self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        retry: int = 3,
        **kwargs: Any,
    ) -> Any:
        assert self._session is not None
        url = f"{self._base_url}{path}"

        for attempt in range(retry):
            try:
                async with self._session.request(
                    method,
                    url,
                    headers=self._headers(),
                    **kwargs,
                ) as resp:
                    if resp.status == 401 and not settings.panel_api_key:
                        logger.warning("PasarGuard 401 — renewing token")
                        await self._login()
                        continue
                    if resp.status == 403:
                        body = await resp.json()
                        raise PermissionError(body.get("detail", "Permission denied"))
                    resp.raise_for_status()
                    return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < retry - 1:
                    wait = 2 ** attempt
                    logger.warning(f"PasarGuard request failed (attempt {attempt+1}): {exc}. Retrying in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    raise

    # ─── User Templates ─────────────────────────────────────

    async def get_templates(self) -> list[dict]:
        return await self._request("GET", "/api/user_templates")

    async def get_all_users(self) -> list[dict]:
        res = await self._request("GET", "/api/users")
        if isinstance(res, dict):
            return res.get("users", [])
        return res if isinstance(res, list) else []

    # ─── User Provisioning ──────────────────────────────────

    def _generate_username(self, telegram_id: int, prefix: str = "zak") -> str:
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{prefix}_{telegram_id}_{rand}"

    async def create_user_from_template(
        self,
        template_id: int,
        telegram_id: int,
        note: str = "",
        custom_username: str = "",
    ) -> dict:
        base_name = ""
        if custom_username:
            clean = "".join(c for c in custom_username if c.isalnum() or c in "_-").replace("-", "_")
            if clean:
                base_name = clean.lower()

        for attempt in range(5):
            if base_name and attempt == 0:
                username = base_name
            elif base_name:
                rand_sfx = "".join(random.choices(string.ascii_lowercase + string.digits, k=3))
                username = f"{base_name}_{rand_sfx}"
            else:
                username = self._generate_username(telegram_id, "zak")

            try:
                res = await self._request(
                    "POST",
                    "/api/user/from_template",
                    json={
                        "user_template_id": template_id,
                        "username": username,
                        "note": note,
                    },
                )
                actual_username = res.get("username", username) if isinstance(res, dict) else username
                self._user_cache.pop(actual_username, None)
                user_data = await self.get_user(actual_username)
                return user_data
            except aiohttp.ClientResponseError as exc:
                if exc.status == 409:
                    logger.warning(f"Username '{username}' taken, retrying ({attempt+1}/5)")
                    continue
                raise
        raise RuntimeError("Could not generate a unique username after 5 attempts")

    async def get_user(self, username: str, force_fresh: bool = False) -> dict:
        now = time.time()
        if not force_fresh and username in self._user_cache:
            ts, data = self._user_cache[username]
            if now - ts < self._cache_ttl:
                return data

        data = await self._request("GET", f"/api/user/{username}")
        if isinstance(data, dict):
            self._user_cache[username] = (now, data)
        return data

    async def reset_user_traffic(self, username: str) -> None:
        self._user_cache.pop(username, None)
        await self._request("POST", f"/api/user/{username}/reset")

    async def modify_user(self, username: str, data: dict) -> dict:
        self._user_cache.pop(username, None)
        return await self._request("PUT", f"/api/user/{username}", json=data)

    async def add_user_traffic(self, username: str, extra_bytes: int) -> dict:
        user = await self.get_user(username, force_fresh=True)
        current_limit = user.get("data_limit", 0) or 0
        new_limit = current_limit + extra_bytes
        return await self.modify_user(username, {"data_limit": new_limit})

    async def renew_user(self, username: str, duration_days: int) -> dict:
        await self.reset_user_traffic(username)
        user = await self.get_user(username, force_fresh=True)
        raw_expire = user.get("expire")
        now = datetime.now(timezone.utc)
        if raw_expire:
            try:
                current_exp = datetime.fromisoformat(raw_expire.replace("Z", "+00:00"))
                base = current_exp if current_exp > now else now
            except Exception:
                base = now
        else:
            base = now

        new_expire = base + timedelta(days=duration_days)
        new_expire_str = new_expire.strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self.modify_user(username, {"expire": new_expire_str, "status": "active"})

    async def delete_user(self, username: str) -> None:
        self._user_cache.pop(username, None)
        await self._request("DELETE", f"/api/user/{username}")

    # ─── Admin Info ─────────────────────────────────────────

    async def get_admin_info(self) -> dict:
        return await self._request("GET", "/api/admin")

    async def get_admin_usage(self) -> dict:
        return await self.get_admin_info()

    async def is_admin_limited(self) -> bool:
        if not self.is_configured:
            return True
        try:
            info = await self.get_admin_info()
            return info.get("status") == "limited"
        except Exception:
            return True


# Singleton instance — initialised in main.py
panel = PasarGuardClient()
