from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from aiogram import F, Router, types
from aiogram.types import BufferedInputFile
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_subscription, get_user_subscriptions
from bot.db.database import AsyncSessionLocal
from bot.db.models import Subscription
from bot.keyboards.user_kb import after_delivery_kb
from bot.services.pasarguard import panel
from bot.services.qr import make_qr_bytes

router = Router(name="services")


def parse_expire_ts(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        val = val.strip()
        if val.isdigit():
            return datetime.fromtimestamp(int(val), tz=timezone.utc)
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


async def reconcile_user_services(session: AsyncSession, user_id: int) -> list[Subscription]:
    """
    Heavy Two-Way Synchronization & Anti-Loss Engine:
    1. Forward Check: If admin deleted user in panel -> marks status='deleted' in DB.
    2. Reverse Check: If user exists in panel but missing from local DB -> auto-restores into DB.
    3. Live Update: Keeps usage, limit, and expire in sync.
    """
    # 1. Fetch local subscriptions
    local_subs = await get_user_subscriptions(session, user_id)
    active_subs: list[Subscription] = []
    known_usernames: set[str] = set()

    for sub in local_subs:
        if sub.status == "deleted":
            continue

        try:
            user_data = await panel.get_user(sub.marzban_username, force_fresh=True)
            if not user_data or user_data.get("status") == "deleted":
                sub.status = "deleted"
                await session.commit()
                continue

            # Update live stats in DB
            sub.used_traffic_bytes = user_data.get("used_traffic", sub.used_traffic_bytes)
            sub.data_limit_bytes = user_data.get("data_limit", sub.data_limit_bytes)
            sub.status = user_data.get("status", sub.status)
            if user_data.get("subscription_url"):
                sub.subscription_url = user_data["subscription_url"]
            await session.commit()

            active_subs.append(sub)
            known_usernames.add(sub.marzban_username.lower())
        except Exception as exc:
            # If 404 from panel -> user was deleted manually from panel by admin
            err_str = str(exc)
            if "404" in err_str:
                logger.info(f"User {sub.marzban_username} deleted from panel. Removing from bot account.")
                sub.status = "deleted"
                await session.commit()
            else:
                # Temporary network error — keep service safe in DB
                active_subs.append(sub)
                known_usernames.add(sub.marzban_username.lower())

    # 2. Reverse Recovery: Check panel for any orphaned users belonging to this user_id
    try:
        panel_users = await panel.get_all_users()
        uid_str = str(user_id)
        for pu in panel_users:
            uname = pu.get("username", "")
            note = pu.get("note", "")
            # Check if this panel account belongs to user_id
            belongs = (
                str(pu.get("telegram_id", "")) == uid_str
                or f"user:{uid_str}" in note
                or f"_{uid_str}_" in uname
                or f"_{uid_str}" in uname
                or f"zak_{uid_str}" in uname
            )
            if belongs and uname.lower() not in known_usernames:
                # Restore missing subscription into local DB
                logger.info(f"Reverse recovery: Restoring panel user {uname} for Telegram ID {user_id}")
                expire_ts = parse_expire_ts(pu.get("expire"))
                sub_url = pu.get("subscription_url", "")
                if not sub_url:
                    try:
                        full_u = await panel.get_user(uname)
                        sub_url = full_u.get("subscription_url", "")
                    except Exception:
                        pass
                new_sub = Subscription(
                    user_id=user_id,
                    order_id="RESTORED",
                    marzban_username=uname,
                    subscription_url=sub_url,
                    expire_timestamp=expire_ts,
                    data_limit_bytes=pu.get("data_limit", 0),
                    used_traffic_bytes=pu.get("used_traffic", 0),
                    status=pu.get("status", "active"),
                )
                session.add(new_sub)
                await session.commit()
                await session.refresh(new_sub)
                active_subs.append(new_sub)
                known_usernames.add(uname.lower())
    except Exception as exc:
        logger.warning(f"Error during reverse recovery: {exc}")

    return active_subs


@router.message(F.text.in_({"📱 سرویس های من", "📱 سرویس‌های من", "سرویس های من", "سرویس‌های من", "سرویس ها", "سرویس‌ها", "🐍 سرویس ها", "سرویس من"}))
@router.callback_query(F.data == "services:list")
async def list_services(update: types.Message | types.CallbackQuery) -> None:
    user_id = update.from_user.id
    if isinstance(update, types.CallbackQuery):
        await update.answer("در حال همگام‌سازی لحظه‌ای با سرور...")

    async with AsyncSessionLocal() as session:
        subs = await reconcile_user_services(session, user_id)

    if not subs:
        text = (
            "📱 <b>سرویس‌های من</b>\n\n"
            "شما در حال حاضر هیچ اشتراک فعالی ندارید.\n\n"
            "جهت خرید سرویس جدید می‌توانید از دکمه <b>«🚀 خرید سرویس جدید»</b> استفاده فرمایید."
        )
        markup = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🚀 خرید سرویس جدید", callback_data="buy:start")],
                [types.InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="menu:main")],
            ]
        )
        if isinstance(update, types.CallbackQuery):
            await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await update.answer(text, parse_mode="HTML", reply_markup=markup)
        return

    buttons = []
    for sub in subs:
        status_dot = "🟢" if sub.status == "active" else "🔴"
        btn_text = f"🔑 {sub.marzban_username} | {status_dot}"
        buttons.append([
            types.InlineKeyboardButton(
                text=btn_text,
                callback_data=f"svc_view:{sub.id}",
            )
        ])
    buttons.append([types.InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="menu:main")])

    text = (
        "📱 <b>سرویس‌های فعال شما:</b>\n\n"
        "جهت مشاهده اطلاعات زنده، حجم باقی‌مانده و دریافت مجدد کانفیگ یا QR Code، روی سرویس مورد نظر ضربه بزنید:"
    )
    markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(update, types.CallbackQuery):
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("svc_view:"))
async def view_service(callback: types.CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)

    if not sub:
        await callback.answer("سرویس یافت نشد.", show_alert=True)
        return

    await callback.answer("در حال دریافت اطلاعات زنده از سرور...")

    try:
        user_data = await panel.get_user(sub.marzban_username, force_fresh=True)
    except Exception as exc:
        logger.warning(f"Could not fetch live data for {sub.marzban_username}: {exc}")
        user_data = {}

    used_bytes = user_data.get("used_traffic", sub.used_traffic_bytes or 0)
    limit_bytes = user_data.get("data_limit", sub.data_limit_bytes or 0)
    raw_status = user_data.get("status", sub.status or "active")
    sub_url = user_data.get("subscription_url") or sub.subscription_url

    if user_data.get("subscription_url") and user_data["subscription_url"] != sub.subscription_url:
        sub.subscription_url = user_data["subscription_url"]
        async with AsyncSessionLocal() as session:
            sub_db = await get_subscription(session, sub_id)
            if sub_db:
                sub_db.subscription_url = sub.subscription_url
                await session.commit()

    status_map = {
        "active": "🟢 فعال و متصل",
        "limited": "🔴 حجم به پایان رسیده",
        "expired": "⏱ منقضی شده",
        "disabled": "⛔️ غیرفعال",
    }
    status_fa = status_map.get(raw_status, "🟢 فعال")

    used_gb = used_bytes / (1024**3)
    total_gb = limit_bytes / (1024**3) if limit_bytes else 0
    remain_gb = max(0.0, total_gb - used_gb) if total_gb > 0 else 0.0

    raw_expire = user_data.get("expire")
    expire_dt = parse_expire_ts(raw_expire) or sub.expire_timestamp

    now_utc = datetime.now(timezone.utc)
    if expire_dt:
        if expire_dt.tzinfo is None:
            expire_dt = expire_dt.replace(tzinfo=timezone.utc)
        diff = (expire_dt - now_utc).days
        days_left = max(0, diff)
        expire_str = expire_dt.strftime("%Y/%m/%d")
        time_text = f"{days_left} روز باقی‌مانده (تا {expire_str})"
    else:
        time_text = "نامحدود"

    limit_text = f"{total_gb:.1f} گیگابایت" if total_gb > 0 else "نامحدود"
    used_text = f"{used_gb:.1f} گیگابایت"
    remain_text = f"{remain_gb:.1f} گیگابایت" if total_gb > 0 else "نامحدود"

    text = (
        f"🔑 <b>مشخصات سرویس:</b> <code>{sub.marzban_username}</code>\n\n"
        f"▫️ 📊 وضعیت اتصال: <b>{status_fa}</b>\n"
        f"▫️ 🚗 ترافیک مصرفی: <b>{used_text}</b> از <b>{limit_text}</b>\n"
        f"▫️ 🔋 ترافیک باقی‌مانده: <b>{remain_text}</b>\n"
        f"▫️ ⏳ مهلت اشتراک: <b>{time_text}</b>\n\n"
        "🔗 <b>لینک اتصال سابسکریپشن:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "جهت دریافت بارکد، تمدید یا افزایش حجم از دکمه‌های زیر استفاده کنید:"
    )

    rows = [
        [types.InlineKeyboardButton(text="📸 دریافت کیوآرکد (QR Code)", callback_data=f"svc_qr:{sub.id}")],
        [
            types.InlineKeyboardButton(text="♻️ تمدید این سرویس", callback_data=f"svc_renew:{sub.id}"),
            types.InlineKeyboardButton(text="♾️ افزایش حجم این سرویس", callback_data=f"svc_extradata:{sub.id}"),
        ],
    ]
    if sub_url and sub_url.startswith("http"):
        rows.append([types.InlineKeyboardButton(text="⚙️ ورود به پنل مدیریت سرویس", url=sub_url)])
    rows.append([types.InlineKeyboardButton(text="🔙 بازگشت به لیست سرویس‌ها", callback_data="services:list")])

    markup = types.InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("svc_qr:"))
async def send_service_qr(callback: types.CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)

    if not sub:
        await callback.answer("سرویس یافت نشد.", show_alert=True)
        return

    await callback.answer("در حال تولید بارکد QR...")

    sub_url = sub.subscription_url
    if not sub_url or not sub_url.startswith("http"):
        # Fetch fresh user from panel
        try:
            ud = await panel.get_user(sub.marzban_username, force_fresh=True)
            if ud.get("subscription_url"):
                sub_url = ud["subscription_url"]
                async with AsyncSessionLocal() as session:
                    sub_db = await get_subscription(session, sub_id)
                    if sub_db:
                        sub_db.subscription_url = sub_url
                        await session.commit()
        except Exception as exc:
            logger.warning(f"Could not fetch subscription url for {sub.marzban_username}: {exc}")

    if not sub_url:
        await callback.answer("❌ لینک اتصال برای این سرویس یافت نشد.", show_alert=True)
        return

    qr_bytes = make_qr_bytes(sub_url)
    caption = (
        f"📸 <b>کیوآرکد اتصال سرویس:</b> <code>{sub.marzban_username}</code>\n\n"
        "🔗 <b>لینک سابسکریپشن:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "<i>با نرم‌افزار Hiddify اسکن کنید یا لینک را کپی نمایید.</i>"
    )
    buttons = []
    if sub_url and sub_url.startswith("http"):
        buttons.append([types.InlineKeyboardButton(text="⚙️ پنل مدیریت سرویس", url=sub_url)])
    buttons.append([types.InlineKeyboardButton(text="🔙 بازگشت به جزییات", callback_data=f"svc_view:{sub.id}")])
    markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        await callback.bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=BufferedInputFile(qr_bytes, filename="qrcode.png"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception as exc:
        logger.error(f"Failed to send QR photo: {exc}")
        await callback.message.answer(
            f"{caption}\n\n⚠️ ارسال عکس بارکد ناموفق بود، اما می‌توانید از لینک فوق استفاده فرمایید.",
            parse_mode="HTML",
            reply_markup=markup,
        )
