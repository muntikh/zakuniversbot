from __future__ import annotations

import asyncio
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from bot.config import is_admin_user, settings
from bot.db.crud import (
    get_all_users,
    get_setting,
    get_system_stats,
    set_setting,
)
from bot.db.database import AsyncSessionLocal
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
# Broadcast Message
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminBroadcastStates.writing_message)
    await callback.message.edit_text(
        "📢 <b>ارسال پیام همگانی به کاربران:</b>\n\n"
        "متن پیام خود را ارسال فرمایید (پشتیبانی از فرمت‌های متنی و لینک):\n"
        "<i>(برای انصراف /cancel را ارسال کنید)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AdminBroadcastStates.writing_message, F.text)
async def run_broadcast(message: types.Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    text = message.text
    await state.clear()

    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)

    sent = 0
    failed = 0
    status_msg = await message.answer(f"⏳ در حال ارسال پیام به {len(users)} کاربر...")

    for u in users:
        try:
            await message.bot.send_message(u.telegram_id, text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # Telegram rate-limit prevention
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>ارسال همگانی تکمیل گردید!</b>\n\n"
        f"▫️ با موفقیت ارسال شد: <b>{sent} کاربر</b>\n"
        f"▫️ ناموفق (بلاک ربات یا غیره): <b>{failed} کاربر</b>",
        parse_mode="HTML",
    )


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
