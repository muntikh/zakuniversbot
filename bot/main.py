from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.config import settings
from bot.db.crud import get_setting
from bot.db.database import AsyncSessionLocal, init_db
from bot.handlers.admin import panel as admin_panel
from bot.handlers.user import (
    account,
    buy,
    extra_data,
    faq,
    guide,
    renew,
    services,
    start,
    support,
    tariffs,
    tracking,
)
from bot.services.pasarguard import panel
from bot.services.scheduler import setup_scheduler
from bot.services.stats import record_user_activity, touch_user_last_seen_bg

MENU_COMMANDS_AND_BUTTONS = {
    "🚀 خرید سرویس جدید", "🛍️ خرید سرویس", "خرید سرویس جدید", "خرید سرویس",
    "📱 سرویس های من", "📱 سرویس‌های من", "سرویس های من", "سرویس‌های من", "سرویس ها", "سرویس‌ها", "🐍 سرویس ها", "سرویس من",
    "♻️ تمدید سرویس", "⚡️ تمدید سرویس", "تمدید سرویس", "تمدید",
    "💡 آموزش استفاده", "🔗 راهنمای اتصال", "آموزش استفاده", "راهنمای اتصال", "آموزش", "راهنما",
    "💡 سوالات متداول", "سوالات متداول", "پرسش های متداول", "سوالات",
    "💰 اعتبار من", "🖥️ حساب کاربری", "اعتبار من", "حساب کاربری", "اعتبار", "کیف پول",
    "👨‍💻 تماس با پشتیبانی", "📞 پشتیبانی", "تماس با پشتیبانی", "پشتیبانی",
    "👥 معرفی به دوستان", "معرفی به دوستان", "دعوت دوستان",
    "♾️ حجم اضافه", "حجم اضافه",
    "🔍 پیگیری سفارش", "🔍 پیگیری اطلاعات", "پیگیری سفارش", "پیگیری اطلاعات", "پیگیری",
    "👑 پنل مدیریت", "پنل مدیریت", "مدیریت", "ادمین", "ادمین پنل",
    "بازگشت به منوی اصلی", "انصراف و بازگشت", "انصراف", "لغو", "بازگشت",
    "/start", "/cancel", "/help", "/admin", "/menu",
}


class NavigationFSMResetMiddleware(BaseMiddleware):
    """
    CRITICAL: Automatically clears any active FSM state when user presses
    any main navigation button or cancel callback. Eliminates users getting stuck in awaiting_receipt forever!
    """
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state: Optional[FSMContext] = data.get("state")
        if state:
            if isinstance(event, types.Message) and event.text:
                text = event.text.strip()
                if (
                    text.startswith("/")
                    or text in MENU_COMMANDS_AND_BUTTONS
                    or any(k in text for k in ("منوی اصلی", "انصراف", "بازگشت به منو", "پشتیبانی"))
                ):
                    current_state = await state.get_state()
                    if current_state:
                        logger.debug(f"Navigation text triggered; clearing state: {current_state}")
                        await state.clear()
            elif isinstance(event, types.CallbackQuery) and event.data:
                cdata = event.data
                if (
                    cdata in {"menu:main", "buy:cancel", "extra_cancel", "renew_cancel"}
                    or cdata.endswith(":cancel")
                    or "cancel" in cdata
                    or cdata == "back_to_menu"
                ):
                    current_state = await state.get_state()
                    if current_state:
                        logger.debug(f"Navigation callback triggered; clearing state: {current_state}")
                        await state.clear()

        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Prevents spamming under 10k users. Limits each user to max 5 updates per second.
    """
    def __init__(self, rate_limit: float = 0.2):
        self._rate_limit = rate_limit
        self._user_last_action: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            record_user_activity(user.id)
            asyncio.create_task(touch_user_last_seen_bg(user.id))
        if user and user.id not in settings.owner_ids:
            now = time.time()
            last = self._user_last_action.get(user.id, 0.0)
            if now - last < self._rate_limit:
                if isinstance(event, types.CallbackQuery):
                    await event.answer("⏳ لطفاً کمی آرام‌تر کلیک کنید.", show_alert=False)
                return None
            self._user_last_action[user.id] = now

        return await handler(event, data)


class MaintenanceMiddleware(BaseMiddleware):
    """Checks if bot is in maintenance mode; allows admins through."""
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user and user.id in settings.owner_ids:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            maint = await get_setting(session, "MAINTENANCE_MODE", "false")

        if maint == "true":
            if isinstance(event, types.Message):
                await event.answer(
                    "🛠 <b>ربات Zak Univers در حال حاضر در دست ارتقا و تعمیرات می‌باشد.</b>\n\n"
                    "لطفاً دقایقی دیگر مراجعه فرمایید. از شکیبایی شما سپاسگزاریم. 🙏",
                    parse_mode="HTML",
                )
            elif isinstance(event, types.CallbackQuery):
                await event.answer(
                    "🛠 ربات در حال حاضر در دست تعمیر و بروزرسانی است.",
                    show_alert=True,
                )
            return None

        return await handler(event, data)


async def github_actions_shift_watchdog(dp: Dispatcher, max_seconds: int) -> None:
    """
    Relay Runner Watchdog:
    In GitHub Actions environment, monitors execution time and cleanly shuts down
    polling when shift ends (e.g. 4h 10m) so workflow step exits with code 0,
    commits database state, and hands off to the next relay runner.
    """
    logger.info(
        f"[*] Relay Runner Watchdog armed: shift length = {max_seconds} seconds "
        f"({max_seconds // 3600}h {(max_seconds % 3600) // 60}m)"
    )
    await asyncio.sleep(max_seconds)
    logger.warning("[*] Relay Watchdog: Shift completed! Gracefully stopping polling for runner handoff...")
    try:
        await dp.stop_polling()
    except Exception as exc:
        logger.warning(f"Error in graceful stop_polling: {exc}")
    await asyncio.sleep(2)


async def main() -> None:
    # ── Logging ──────────────────────────────────────────────
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    logger.add("logs/bot.log", rotation="10 MB", retention="30 days", level="DEBUG")

    logger.info("Starting Zak Univers Bot...")

    # ── Database ─────────────────────────────────────────────
    await init_db()
    logger.info("Database initialised")

    # ── PasarGuard Client ────────────────────────────────────
    await panel.start()

    # ── Scheduler ────────────────────────────────────────────
    setup_scheduler()

    # ── Bot & Dispatcher ─────────────────────────────────────
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares (Execution order: Throttling -> Maintenance -> NavigationReset)
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(MaintenanceMiddleware())
    dp.callback_query.middleware(MaintenanceMiddleware())
    dp.message.middleware(NavigationFSMResetMiddleware())
    dp.callback_query.middleware(NavigationFSMResetMiddleware())

    # Register all routers
    dp.include_router(admin_panel.router)
    dp.include_router(start.router)
    dp.include_router(account.router)
    dp.include_router(buy.router)
    dp.include_router(services.router)
    dp.include_router(extra_data.router)
    dp.include_router(renew.router)
    dp.include_router(tariffs.router)
    dp.include_router(support.router)
    dp.include_router(guide.router)
    dp.include_router(faq.router)
    dp.include_router(tracking.router)

    # ── Relay Runner Watchdog (GitHub Actions 24/7) ───────────
    if os.environ.get("GITHUB_ACTIONS"):
        max_run_seconds = int(os.environ.get("MAX_RUN_SECONDS", 15000))
        asyncio.create_task(github_actions_shift_watchdog(dp, max_run_seconds))

    # ── Run ──────────────────────────────────────────────────
    try:
        logger.info("Bot polling started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await panel.stop()
        logger.info("Bot stopped")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
