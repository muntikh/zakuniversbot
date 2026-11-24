from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

from aiogram import Bot, F, Router, types
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy import distinct, func, select, update

from bot.config import is_admin_user, settings
from bot.db.crud import (
    get_all_users,
    get_setting,
    get_system_stats,
    set_setting,
)
from bot.db.database import AsyncSessionLocal
from bot.db.models import Subscription, User
from bot.keyboards.user_kb import cancel_kb, main_menu_kb
from bot.services.pasarguard import panel
from bot.services.stats import (
    format_stats_dashboard,
    get_comprehensive_stats,
    scan_blocked_users,
)
from bot.states.fsm import AdminBroadcastStates, AdminCardStates

router = Router(name="admin_panel")


def is_admin(user_id: int) -> bool:
    return is_admin_user(user_id)


@router.message(Command("admin"))
@router.message(F.text.in_({"👑 پنل مدیریت", "پنل مدیریت", "مدیریت", "ادمین", "ادمین پنل", "/admin"}))
@router.callback_query(F.data.in_({"admin:menu", "admin:back_to_menu"}))
async def admin_dashboard(update: types.Message | types.CallbackQuery, state: Optional[FSMContext] = None) -> None:
    user_id = update.from_user.id
    if not is_admin(user_id):
        if isinstance(update, types.CallbackQuery):
            await update.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    if state:
        await state.clear()

    async with AsyncSessionLocal() as session:
        maint = await get_setting(session, "MAINTENANCE_MODE", "false")
        card = await get_setting(session, "BANK_CARD", "6063731268895845")
        bank = await get_setting(session, "BANK_NAME", "مهر ایران")

    maint_fa = "🔴 فعال (ربات بسته)" if maint == "true" else "🟢 غیرفعال (ربات باز)"

    text = (
        "👑 <b>پنل مدیریت اختصاصی Zak Univers</b>\n\n"
        f"💳 شماره کارت فعال: <code>{card}</code> ({bank})\n"
        f"🛠 حالت تعمیرات: <b>{maint_fa}</b>\n\n"
        "یک بخش را جهت مدیریت انتخاب کنید:"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📊 آمار کلی ربات", callback_data="admin:stats"),
                types.InlineKeyboardButton(text="🛠 تغییر وضعیت تعمیرات", callback_data="admin:toggle_maint"),
            ],
            [
                types.InlineKeyboardButton(text="💳 تغییر شماره کارت بانکی", callback_data="admin:change_card"),
                types.InlineKeyboardButton(text="📢 ارسال پیام همگانی", callback_data="admin:broadcast"),
            ],
            [
                types.InlineKeyboardButton(text="🔙 بستن منو", callback_data="admin:close"),
            ],
        ]
    )

    if isinstance(update, types.CallbackQuery):
        try:
            await update.answer()
        except Exception:
            pass
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


# ══════════════════════════════════════════════════════════════
# Admin Stats & Metrics Engine
# ══════════════════════════════════════════════════════════════

def admin_stats_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔄 بروزرسانی زنده آمار", callback_data="admin:stats:refresh"),
            ],
            [
                types.InlineKeyboardButton(text="🔍 بررسی کاربران بلاک‌کننده", callback_data="admin:stats:scan_blocked"),
            ],
            [
                types.InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="admin:back_to_menu"),
            ],
        ]
    )


@router.callback_query(F.data.in_({"admin:stats", "admin:stats:refresh"}))
async def show_admin_stats(callback: types.CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    is_refresh = callback.data == "admin:stats:refresh"
    if is_refresh:
        await callback.answer("🔄 در حال دریافت آمار زنده و محاسبه دقیق...")
    else:
        await callback.answer("📊 در حال بازخوانی اطلاعات سیستم...")

    async with AsyncSessionLocal() as session:
        stats = await get_comprehensive_stats(session, callback.bot)

    text = format_stats_dashboard(stats)
    markup = admin_stats_kb()

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        if is_refresh:
            await callback.answer("✅ آمار و وضعیت سیستم با موفقیت بروزرسانی شد.")
    except Exception as exc:
        logger.debug(f"Stats edit notice: {exc}")


@router.callback_query(F.data == "admin:stats:scan_blocked")
async def admin_scan_blocked(callback: types.CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    await callback.answer("🔍 در حال بررسی نامحسوس وضعیت بلاک کاربران... لطفاً چند لحظه صبر کنید.")

    async with AsyncSessionLocal() as session:
        scanned, newly_blocked = await scan_blocked_users(callback.bot, session, limit=150)
        stats = await get_comprehensive_stats(session, callback.bot)

    text = format_stats_dashboard(stats)
    markup = admin_stats_kb()

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass

    await callback.answer(
        f"✅ اسکن پایان یافت: {scanned} کاربر بررسی شدند و {newly_blocked} مورد بلاک جدید ثبت گردید.",
        show_alert=True,
    )


# ══════════════════════════════════════════════════════════════
# Maintenance Mode Toggle
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:toggle_maint")
async def toggle_maintenance(callback: types.CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        current = await get_setting(session, "MAINTENANCE_MODE", "false")
        new_val = "false" if current == "true" else "true"
        await set_setting(session, "MAINTENANCE_MODE", new_val)

    status_str = "🔴 فعال (دسترسی کاربران قطع شد)" if new_val == "true" else "🟢 غیرفعال (ربات برای همه در دسترس است)"
    await callback.answer(f"حالت تعمیرات: {status_str}", show_alert=True)
    await admin_dashboard(callback, None)


# ══════════════════════════════════════════════════════════════
# Change Bank Card
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:change_card")
async def ask_new_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminCardStates.waiting_card_number)
    await callback.message.edit_text(
        "💳 <b>تغییر شماره کارت بانکی:</b>\n\n"
        "لطفاً شماره کارت ۱۶ رقمی جدید را ارسال فرمایید (ارقام انگلیسی یا بدون خط فاصله):",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AdminCardStates.waiting_card_number, F.text)
async def process_card_number(message: types.Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    card = "".join(c for c in message.text if c.isdigit())
    if len(card) != 16:
        await message.answer("❌ شماره کارت باید دقیقاً ۱۶ رقم باشد. دوباره ارسال کنید:")
        return

    await state.update_data(new_card=card)
    await state.set_state(AdminCardStates.waiting_bank_name)
    await message.answer("🏦 اکنون نام بانک را وارد فرمایید (مثال: مهر ایران یا ملت):")


@router.message(AdminCardStates.waiting_bank_name, F.text)
async def process_bank_name(message: types.Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    bank = message.text.strip()
    data = await state.get_data()
    card = data.get("new_card")

    async with AsyncSessionLocal() as session:
        await set_setting(session, "BANK_CARD", card)
        await set_setting(session, "BANK_NAME", bank)

    await state.clear()
    await message.answer(
        f"✅ <b>شماره کارت با موفقیت بروزرسانی گردید!</b>\n\n"
        f"💳 شماره کارت: <code>{card}</code>\n"
        f"🏦 بانک: <b>{bank}</b>",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════
# AAA Professional Broadcast Engine
# ══════════════════════════════════════════════════════════════

def clean_btn_url(raw_url: str) -> str:
    url = raw_url.strip()
    if url.startswith("@"):
        return f"https://t.me/{url[1:]}"
    if url.startswith("t.me/"):
        return f"https://{url}"
    if not url.startswith(("http://", "https://", "tg://")):
        return f"https://{url}"
    return url


def is_valid_btn_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return bool(p.scheme in ("http", "https", "tg") and (p.netloc or url.startswith("tg://")))
    except Exception:
        return False


def parse_single_btn(part: str) -> Optional[types.InlineKeyboardButton]:
    part = part.strip()
    if not part:
        return None

    # 1. Markdown syntax: [Label](URL)
    m = re.match(r"^\[(.*?)\]\((.*?)\)$", part)
    if m:
        lbl = m.group(1).strip()
        u = clean_btn_url(m.group(2).strip())
        if lbl and is_valid_btn_url(u):
            return types.InlineKeyboardButton(text=lbl, url=u)

    # 2. Delimiter split with regex so that '+' inside URLs (e.g. t.me/+hash) is NEVER matched
    delim_patterns = [
        r"\s*[\+\-\:\=]\s*(?=(?:https?:\/\/|tg:\/\/|t\.me\/|@|[a-zA-Z0-9\-_]+\.[a-zA-Z]{2,}))",
        r"\s+[\+\-\:\=]\s+",
        r"\s*[\+\-\:\=]\s*",
    ]
    for dp in delim_patterns:
        splits = re.split(dp, part, maxsplit=1)
        if len(splits) == 2:
            lbl = splits[0].strip()
            u = clean_btn_url(splits[1].strip())
            if lbl and is_valid_btn_url(u):
                return types.InlineKeyboardButton(text=lbl, url=u)

    # 3. Fallback: find URL anywhere inside part
    url_m = re.search(r"(https?://\S+|tg://\S+|t\.me/\S+|@[\w\d_]+)", part)
    if url_m:
        lbl = part[:url_m.start()].strip(" \t\n-+:=|")
        u = clean_btn_url(url_m.group(0))
        if lbl and is_valid_btn_url(u):
            return types.InlineKeyboardButton(text=lbl, url=u)

    return None


def parse_inline_buttons(text: str) -> Optional[types.InlineKeyboardMarkup]:
    """
    Parses admin input into an InlineKeyboardMarkup.
    Supports single or multiple buttons per row using '|'.
    Handles @channels, markdown [title](url), and '+' inside private invite links cleanly.
    """
    if not text:
        return None
    rows = []
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    for line in lines:
        row = []
        btn_parts = [p.strip() for p in line.split("|") if p.strip()]
        for part in btn_parts:
            btn = parse_single_btn(part)
            if btn:
                row.append(btn)

        if row:
            rows.append(row)

    return types.InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def send_broadcast_message(
    bot: Bot,
    chat_id: int,
    content_chat_id: int,
    content_msg_id: int,
    reply_markup: Optional[types.InlineKeyboardMarkup],
    msg_type: str = "text",
    text_content: str = "",
    file_id: Optional[str] = None,
    entities: Optional[list[types.MessageEntity]] = None,
) -> Any:
    # 1. Primary engine: copy_message (preserves original format, album, forward info, etc.)
    try:
        return await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=content_chat_id,
            message_id=content_msg_id,
            reply_markup=reply_markup,
        )
    except (TelegramRetryAfter, TelegramForbiddenError):
        # Let retry/block handling take place in caller
        raise
    except Exception as copy_err:
        # Fallback to direct sending using file_id / text!
        if msg_type == "text" and text_content:
            return await bot.send_message(
                chat_id=chat_id,
                text=text_content,
                entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "photo" and file_id:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=text_content,
                caption_entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "video" and file_id:
            return await bot.send_video(
                chat_id=chat_id,
                video=file_id,
                caption=text_content,
                caption_entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "animation" and file_id:
            return await bot.send_animation(
                chat_id=chat_id,
                animation=file_id,
                caption=text_content,
                caption_entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "document" and file_id:
            return await bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=text_content,
                caption_entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "voice" and file_id:
            return await bot.send_voice(
                chat_id=chat_id,
                voice=file_id,
                caption=text_content,
                caption_entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "audio" and file_id:
            return await bot.send_audio(
                chat_id=chat_id,
                audio=file_id,
                caption=text_content,
                caption_entities=entities,
                reply_markup=reply_markup,
            )
        elif msg_type == "sticker" and file_id:
            return await bot.send_sticker(
                chat_id=chat_id,
                sticker=file_id,
                reply_markup=reply_markup,
            )
        else:
            raise copy_err


@router.callback_query(F.data == "admin:broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    await state.set_state(AdminBroadcastStates.choosing_target)

    async with AsyncSessionLocal() as session:
        count_all = await session.scalar(
            select(func.count(User.telegram_id)).where(
                User.is_banned == False,
                User.is_blocked == False,
            )
        ) or 0
        count_buyers = await session.scalar(
            select(func.count(distinct(Subscription.user_id)))
            .join(User, User.telegram_id == Subscription.user_id)
            .where(
                Subscription.status != "deleted",
                User.is_banned == False,
                User.is_blocked == False,
            )
        ) or 0
        count_free = max(0, count_all - count_buyers)

    text = (
        "📢 <b>سامانه هوشمند ارسال پیام همگانی Zak Univers (AAA)</b>\n\n"
        "لطفاً دسته <b>مخاطبان هدف</b> خود را انتخاب فرمایید:\n\n"
        f"▫️ 👥 <b>همه کاربران فعال:</b> {count_all:,} نفر\n"
        f"▫️ 💎 <b>فقط مشترکین و خریداران:</b> {count_buyers:,} نفر\n"
        f"▫️ 🎁 <b>فقط کاربران عادی (بدون سرویس):</b> {count_free:,} نفر\n\n"
        "یک گروه را جهت ارسال پیام انتخاب نمایید:"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=f"👥 همه کاربران فعال ({count_all:,} نفر)",
                    callback_data="bcast:tgt:all",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text=f"💎 فقط خریداران ({count_buyers:,} نفر)",
                    callback_data="bcast:tgt:buyers",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text=f"🎁 کاربران بدون سرویس ({count_free:,} نفر)",
                    callback_data="bcast:tgt:free",
                )
            ],
            [
                types.InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="admin:back_to_menu")
            ],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(AdminBroadcastStates.choosing_target, F.data.startswith("bcast:tgt:"))
async def on_broadcast_target_chosen(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    target = callback.data.split(":")[2]
    target_names = {
        "all": "👥 همه کاربران فعال",
        "buyers": "💎 فقط خریداران و مشترکین",
        "free": "🎁 فقط کاربران عادی و بدون سرویس",
    }
    target_title = target_names.get(target, "همه کاربران")

    await state.update_data(target=target, target_title=target_title)
    await state.set_state(AdminBroadcastStates.waiting_message)

    text = (
        f"🎯 <b>مخاطب انتخاب‌شده: {target_title}</b>\n\n"
        "اکنون پیام خود را در هر قالبی که مایلید ارسال یا فوروارد فرمایید:\n\n"
        "• 💬 <b>متن ساده یا فرمت‌دار (HTML / لینک دار / اموجی)</b>\n"
        "• 🖼 <b>عکس، ویدیو، گیف، ویس، استیکر یا آهنگ</b> (همراه با کپشن)\n"
        "• 📁 <b>فایل یا داکیومنت</b>\n"
        "• 🔄 <b>فوروارد مستقیم از کانال یا گروه دیگر</b>\n\n"
        "<i>(پیام تا قبل از تایید نهایی شما به هیچ کاربری ارسال نخواهد شد)</i>"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="bcast:cancel")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.message(AdminBroadcastStates.waiting_message)
async def on_broadcast_message_received(message: types.Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    msg_type = "text"
    text_content = message.text or message.caption or ""
    raw_entities = message.entities or message.caption_entities or []
    entities_data = [e.model_dump() for e in raw_entities]
    file_id = None

    if message.photo:
        msg_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        msg_type = "video"
        file_id = message.video.file_id
    elif message.animation:
        msg_type = "animation"
        file_id = message.animation.file_id
    elif message.document:
        msg_type = "document"
        file_id = message.document.file_id
    elif message.voice:
        msg_type = "voice"
        file_id = message.voice.file_id
    elif message.audio:
        msg_type = "audio"
        file_id = message.audio.file_id
    elif message.sticker:
        msg_type = "sticker"
        file_id = message.sticker.file_id

    await state.update_data(
        content_chat_id=message.chat.id,
        content_msg_id=message.message_id,
        msg_type=msg_type,
        text_content=text_content,
        entities_data=entities_data,
        file_id=file_id,
        buttons_raw=None,
        is_pin=False,
    )
    await state.set_state(AdminBroadcastStates.choosing_button_option)

    text = (
        "✅ <b>محتوای پیام با موفقیت در صف پیش‌نمایش قرار گرفت!</b>\n\n"
        "🔘 آیا مایلید به زیر این پیام <b>دکمه شیشه‌ای (لینکدار / Inline)</b> اضافه نمایید؟"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="➕ افزودن دکمه شیشه‌ای", callback_data="bcast:btn:add"),
                types.InlineKeyboardButton(text="⏩ بدون دکمه (مشاهده پیش‌نمایش)", callback_data="bcast:btn:skip"),
            ],
            [
                types.InlineKeyboardButton(text="❌ انصراف و لغو", callback_data="bcast:cancel")
            ],
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(AdminBroadcastStates.choosing_button_option, F.data == "bcast:btn:add")
@router.callback_query(AdminBroadcastStates.confirming_broadcast, F.data == "bcast:btn:add")
async def ask_broadcast_buttons(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminBroadcastStates.entering_buttons)

    text = (
        "⌨️ <b>تنظیم دکمه‌های شیشه‌ای زیر پیام همگانی:</b>\n\n"
        "لطفاً متن و لینک دکمه‌های خود را با فرمت <code>عنوان + لینک</code> ارسال فرمایید:\n\n"
        "▫️ <b>نمونه یک دکمه:</b>\n"
        "<code>کانال رسمی + https://t.me/zakunivers</code>\n\n"
        "▫️ <b>نمونه چند دکمه در خطوط جداگانه:</b>\n"
        "<code>کانال تلگرام + https://t.me/zakunivers</code>\n"
        "<code>خرید اشتراک + @zakuniversbot</code>\n"
        "<code>پشتیبانی آنلاین + https://t.me/zakaria_support</code>\n\n"
        "▫️ <b>نمونه دو دکمه در یک ردیف (با علامت |):</b>\n"
        "<code>کانال ما + https://t.me/... | پشتیبانی + https://t.me/...</code>"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="⏩ رد شدن بدون دکمه", callback_data="bcast:btn:skip")],
            [types.InlineKeyboardButton(text="❌ انصراف", callback_data="bcast:cancel")],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.message(AdminBroadcastStates.entering_buttons, F.text)
async def process_broadcast_buttons_input(message: types.Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    raw_text = message.text.strip()
    kb = parse_inline_buttons(raw_text)

    if not kb:
        await message.answer(
            "❌ <b>فرمت دکمه نامعتبر بود!</b>\n\n"
            "لطفاً مطمئن شوید بین عنوان و لینک علامت <code>+</code> یا <code>-</code> قرار دارد و لینک‌ها با <code>https://</code> یا <code>@</code> یا <code>t.me</code> آغاز می‌شوند.\n"
            "مجدداً تلاش نمایید:",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="⏩ رد شدن بدون دکمه", callback_data="bcast:btn:skip")],
                    [types.InlineKeyboardButton(text="❌ انصراف", callback_data="bcast:cancel")],
                ]
            ),
        )
        return

    await state.update_data(buttons_raw=raw_text)
    await render_broadcast_preview(message.bot, message.chat.id, state)


@router.callback_query(AdminBroadcastStates.choosing_button_option, F.data == "bcast:btn:skip")
@router.callback_query(AdminBroadcastStates.entering_buttons, F.data == "bcast:btn:skip")
async def skip_broadcast_buttons(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.update_data(buttons_raw=None)
    await render_broadcast_preview(callback.bot, callback.message.chat.id, state)


async def render_broadcast_preview(bot: Bot, admin_chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    content_chat_id = data.get("content_chat_id")
    content_msg_id = data.get("content_msg_id")
    msg_type = data.get("msg_type", "text")
    text_content = data.get("text_content", "")
    entities_data = data.get("entities_data", [])
    entities = [types.MessageEntity(**e) for e in entities_data] if entities_data else None
    file_id = data.get("file_id")
    buttons_raw = data.get("buttons_raw")
    target_title = data.get("target_title", "همه کاربران")
    is_pin = data.get("is_pin", False)

    reply_markup = parse_inline_buttons(buttons_raw) if buttons_raw else None

    await bot.send_message(
        chat_id=admin_chat_id,
        text="👇 <b>پیش‌نمایش زنده پیام همگانی (دقیقاً همانند دید مخاطب):</b>",
        parse_mode="HTML",
    )

    preview_ok = True
    error_msg = ""
    try:
        await send_broadcast_message(
            bot=bot,
            chat_id=admin_chat_id,
            content_chat_id=content_chat_id,
            content_msg_id=content_msg_id,
            reply_markup=reply_markup,
            msg_type=msg_type,
            text_content=text_content,
            file_id=file_id,
            entities=entities,
        )
    except Exception as exc:
        preview_ok = False
        error_msg = str(exc)
        logger.warning(f"Could not render broadcast preview: {exc}")
        await bot.send_message(
            chat_id=admin_chat_id,
            text=(
                f"⚠️ <b>خطا در نمایش پیش‌نمایش:</b>\n<code>{exc}</code>\n\n"
                "علت معمولاً نامعتبر بودن لینک دکمه‌ها یا عدم دسترسی به پیام مبدأ است."
            ),
            parse_mode="HTML",
        )

    pin_badge = "🟢 فعال (سنجاق می‌شود)" if is_pin else "🔴 غیرفعال"
    btn_badge = "🟢 متصل شد" if reply_markup else "⚪️ ندارد"

    if preview_ok:
        control_text = (
            "⚙️ <b>کنترل پنل تایید و ارسال همگانی:</b>\n\n"
            f"▫️ 🎯 <b>مخاطبان هدف:</b> <b>{target_title}</b>\n"
            f"▫️ 🔘 <b>دکمه شیشه‌ای:</b> {btn_badge}\n"
            f"▫️ 📌 <b>سنجاق (Pin) کردن پیام:</b> {pin_badge}\n\n"
            "⚠️ <i>برای جلوگیری از هرگونه ارسال اشتباهی، پیام تنها با زدن دکمه تایید زیر ارسال می‌شود:</i>"
        )
        pin_btn_text = "📌 پین کردن: 🔴 خاموش" if not is_pin else "📌 پین کردن: 🟢 روشن"
        control_kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="🚀 تایید و شروع ارسال همگانی",
                        callback_data="bcast:send:confirm",
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text=pin_btn_text,
                        callback_data="bcast:toggle:pin",
                    ),
                    types.InlineKeyboardButton(
                        text="✏️ تنظیم دکمه‌ها",
                        callback_data="bcast:btn:add",
                    ),
                ],
                [
                    types.InlineKeyboardButton(
                        text="❌ انصراف و لغو",
                        callback_data="bcast:cancel",
                    )
                ],
            ]
        )
        await state.set_state(AdminBroadcastStates.confirming_broadcast)
    else:
        # Pre-flight safety lock: prevent launching a broken broadcast!
        control_text = (
            "❌ <b>امکان ارسال این پیام وجود ندارد!</b>\n\n"
            f"▫️ علت خطا: <code>{error_msg}</code>\n\n"
            "لطفاً دکمه‌های شیشه‌ای را مجدداً تنظیم کرده یا پیام را دوباره ارسال فرمایید."
        )
        control_kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="✏️ اصلاح دکمه‌ها",
                        callback_data="bcast:btn:add",
                    ),
                    types.InlineKeyboardButton(
                        text="⏩ حذف دکمه‌ها (بدون دکمه)",
                        callback_data="bcast:btn:skip",
                    ),
                ],
                [
                    types.InlineKeyboardButton(
                        text="❌ انصراف و لغو",
                        callback_data="bcast:cancel",
                    )
                ],
            ]
        )

    await bot.send_message(
        chat_id=admin_chat_id,
        text=control_text,
        parse_mode="HTML",
        reply_markup=control_kb,
    )


@router.callback_query(AdminBroadcastStates.confirming_broadcast, F.data == "bcast:toggle:pin")
async def toggle_broadcast_pin(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    is_pin = not data.get("is_pin", False)
    await state.update_data(is_pin=is_pin)

    target_title = data.get("target_title", "همه کاربران")
    buttons_raw = data.get("buttons_raw")
    reply_markup = parse_inline_buttons(buttons_raw) if buttons_raw else None

    pin_badge = "🟢 فعال (سنجاق می‌شود)" if is_pin else "🔴 غیرفعال"
    btn_badge = "🟢 متصل شد" if reply_markup else "⚪️ ندارد"
    pin_btn_text = "📌 پین کردن: 🔴 خاموش" if not is_pin else "📌 پین کردن: 🟢 روشن"

    control_text = (
        "⚙️ <b>کنترل پنل تایید و ارسال همگانی:</b>\n\n"
        f"▫️ 🎯 <b>مخاطبان هدف:</b> <b>{target_title}</b>\n"
        f"▫️ 🔘 <b>دکمه شیشه‌ای:</b> {btn_badge}\n"
        f"▫️ 📌 <b>سنجاق (Pin) کردن پیام:</b> {pin_badge}\n\n"
        "⚠️ <i>برای جلوگیری از هرگونه ارسال اشتباهی، پیام تنها با زدن دکمه تایید زیر ارسال می‌شود:</i>"
    )

    control_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🚀 تایید و شروع ارسال همگانی",
                    callback_data="bcast:send:confirm",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text=pin_btn_text,
                    callback_data="bcast:toggle:pin",
                ),
                types.InlineKeyboardButton(
                    text="✏️ تنظیم دکمه‌ها",
                    callback_data="bcast:btn:add",
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text="❌ انصراف و لغو",
                    callback_data="bcast:cancel",
                )
            ],
        ]
    )

    try:
        await callback.message.edit_text(control_text, parse_mode="HTML", reply_markup=control_kb)
    except Exception:
        pass
    await callback.answer(f"سنجاق کردن {'فعال' if is_pin else 'غیرفعال'} شد.")


@router.callback_query(AdminBroadcastStates.confirming_broadcast, F.data == "bcast:send:confirm")
async def execute_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    await state.clear()

    target = data.get("target", "all")
    target_title = data.get("target_title", "همه کاربران فعال")
    content_chat_id = data.get("content_chat_id")
    content_msg_id = data.get("content_msg_id")
    msg_type = data.get("msg_type", "text")
    text_content = data.get("text_content", "")
    entities_data = data.get("entities_data", [])
    entities = [types.MessageEntity(**e) for e in entities_data] if entities_data else None
    file_id = data.get("file_id")
    buttons_raw = data.get("buttons_raw")
    is_pin = data.get("is_pin", False)

    reply_markup = parse_inline_buttons(buttons_raw) if buttons_raw else None

    async with AsyncSessionLocal() as session:
        if target == "buyers":
            res = await session.execute(
                select(distinct(Subscription.user_id))
                .join(User, User.telegram_id == Subscription.user_id)
                .where(
                    Subscription.status != "deleted",
                    User.is_banned == False,
                    User.is_blocked == False,
                )
            )
            target_user_ids = [r[0] for r in res.fetchall() if r[0]]
        elif target == "free":
            buyers_sub = select(distinct(Subscription.user_id)).where(Subscription.status != "deleted")
            res = await session.execute(
                select(User.telegram_id).where(
                    User.is_banned == False,
                    User.is_blocked == False,
                    User.telegram_id.not_in(buyers_sub),
                )
            )
            target_user_ids = [r[0] for r in res.fetchall() if r[0]]
        else:
            res = await session.execute(
                select(User.telegram_id).where(
                    User.is_banned == False,
                    User.is_blocked == False,
                )
            )
            target_user_ids = [r[0] for r in res.fetchall() if r[0]]

    total_target = len(target_user_ids)
    if total_target == 0:
        await callback.message.edit_text(
            "⚠️ <b>هیچ کاربری در دسته انتخابی یافت نشد!</b>",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:back_to_menu")]]
            ),
        )
        return

    status_msg = await callback.message.edit_text(
        f"🚀 <b>ارسال پیام همگانی آغاز شد...</b>\n\n"
        f"▫️ مخاطبان: <b>{target_title}</b> ({total_target:,} نفر)\n"
        f"▫️ وضعیت: در حال ارسال...",
        parse_mode="HTML",
    )

    start_ts = time.time()
    sent = 0
    failed = 0
    blocked_count = 0
    error_reasons: set[str] = set()
    last_update_ts = time.time()

    for idx, uid in enumerate(target_user_ids, 1):
        try:
            sent_msg = await send_broadcast_message(
                bot=callback.bot,
                chat_id=uid,
                content_chat_id=content_chat_id,
                content_msg_id=content_msg_id,
                reply_markup=reply_markup,
                msg_type=msg_type,
                text_content=text_content,
                file_id=file_id,
                entities=entities,
            )
            sent += 1
            if is_pin and sent_msg:
                try:
                    await callback.bot.pin_chat_message(
                        chat_id=uid,
                        message_id=sent_msg.message_id,
                        both_sides=False,
                    )
                except Exception:
                    pass
        except TelegramRetryAfter as exc:
            logger.warning(f"Broadcast rate limited: waiting {exc.retry_after}s")
            await asyncio.sleep(exc.retry_after + 1)
            try:
                sent_msg = await send_broadcast_message(
                    bot=callback.bot,
                    chat_id=uid,
                    content_chat_id=content_chat_id,
                    content_msg_id=content_msg_id,
                    reply_markup=reply_markup,
                    msg_type=msg_type,
                    text_content=text_content,
                    file_id=file_id,
                    entities=entities,
                )
                sent += 1
                if is_pin and sent_msg:
                    try:
                        await callback.bot.pin_chat_message(uid, sent_msg.message_id, both_sides=False)
                    except Exception:
                        pass
            except Exception as exc_after:
                failed += 1
                error_reasons.add(str(exc_after))
        except TelegramForbiddenError:
            failed += 1
            blocked_count += 1
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(update(User).where(User.telegram_id == uid).values(is_blocked=True))
                    await s.commit()
            except Exception:
                pass
        except Exception as exc:
            failed += 1
            error_reasons.add(str(exc))
            logger.warning(f"Broadcast failed for user {uid}: {exc}")

        await asyncio.sleep(0.04)

        now_ts = time.time()
        if (idx % 25 == 0 or idx == total_target) and (now_ts - last_update_ts >= 2.5 or idx == total_target):
            last_update_ts = now_ts
            pct = int((idx / total_target) * 100)
            bar_len = 10
            filled = int(bar_len * (idx / total_target))
            bar = "█" * filled + "░" * (bar_len - filled)
            try:
                await status_msg.edit_text(
                    f"⏳ <b>در حال ارسال پیام همگانی...</b>\n\n"
                    f"▫️ مخاطب: <b>{target_title}</b>\n"
                    f"▫️ پیشرفت: <code>[{bar}]</code> <b>{pct}%</b> ({idx:,}/{total_target:,})\n"
                    f"▫️ 🟢 موفق: <b>{sent:,}</b> | 🔴 ناموفق: <b>{failed:,}</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    elapsed = max(1.0, round(time.time() - start_ts, 1))
    speed = round(sent / elapsed, 1)

    pin_str = "🟢 انجام شد" if is_pin else "⚪️ بدون پین"
    btn_str = "🟢 متصل شد" if reply_markup else "⚪️ بدون دکمه"

    error_summary = ""
    if error_reasons:
        reasons_list = [f"• <code>{r}</code>" for r in list(error_reasons)[:3]]
        error_summary = "\n\n⚠️ <b>دلایل عمده خطاهای رخ‌داده:</b>\n" + "\n".join(reasons_list)

    warning_box = ""
    if sent == 0 and total_target > 0:
        warning_box = (
            "\n\n🚨 <b>هشدار: هیچ پیامی تحویل داده نشد!</b>\n"
            "احتمالاً دسترسی ربات به پیام مبدأ مسدود شده یا لینک دکمه‌ها معتبر نبوده است."
        )

    report_text = (
        "✅ <b>ارسال پیام همگانی با موفقیت تکمیل گردید!</b>\n\n"
        "📊 <b>گزارش تفصیلی تحویل:</b>\n"
        f"▫️ 🎯 دسته هدف: <b>{target_title}</b>\n"
        f"▫️ 👥 کل مخاطبان: <b>{total_target:,} نفر</b>\n"
        f"▫️ 🟢 تحویل موفق: <b>{sent:,} کاربر</b>\n"
        f"▫️ 🔴 ناموفق / مسدود: <b>{failed:,} کاربر</b>"
        + (f" <i>({blocked_count} نفر بلاک جدید شناسایی شد)</i>" if blocked_count > 0 else "")
        + f"\n▫️ 🔘 دکمه شیشه‌ای: <b>{btn_str}</b>\n"
        f"▫️ 📌 سنجاق (Pin): <b>{pin_str}</b>\n"
        f"▫️ ⏱ مدت زمان ارسال: <b>{elapsed} ثانیه</b>\n"
        f"▫️ ⚡️ سرعت ارسال: <b>{speed} پیام در ثانیه</b>"
        f"{error_summary}"
        f"{warning_box}"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="admin:back_to_menu")]
        ]
    )

    try:
        await status_msg.edit_text(report_text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(report_text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "bcast:cancel")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer("عملیات ارسال پیام همگانی لغو گردید.")
    await admin_dashboard(callback, state)


@router.callback_query(F.data == "admin:back_to_menu")
async def back_to_admin_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await admin_dashboard(callback, state)


@router.callback_query(F.data == "admin:close")
async def close_admin_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("منوی مدیریت بسته شد.")
    try:
        await callback.message.delete()
    except Exception:
        pass
    user_id = callback.from_user.id
    is_adm = is_admin(user_id)
    await callback.bot.send_message(
        chat_id=user_id,
        text="به منوی اصلی بازگشتید! 🚀",
        reply_markup=main_menu_kb(is_admin=is_adm, user_id=user_id),
    )
