from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from typing import Any, Optional

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from loguru import logger

from bot.config import is_admin_user, settings
from bot.db.crud import (
    atomic_confirm_order,
    create_order,
    create_subscription,
    deduct_wallet_balance,
    get_order,
    get_or_create_user,
    get_pending_order_for_user,
    get_plan,
    get_setting,
    get_user,
    set_order_receipt,
    set_order_status,
    validate_and_use_discount,
)
from bot.db.database import AsyncSessionLocal
from bot.db.models import OrderStatus, PaymentMethod
from bot.keyboards.user_kb import (
    admin_order_kb,
    after_delivery_kb,
    cancel_kb,
    config_name_kb,
    delivery_choice_kb,
    discount_cancel_kb,
    duration_plans_kb,
    durations_catalog_kb,
    payment_kb,
    pending_order_kb,
    single_mode_kb,
    user_count_tier_kb,
)
from bot.services.admin_sync import (
    save_admin_receipt_messages,
    update_all_admin_receipt_messages,
)
from bot.services.pasarguard import panel
from bot.services.qr import make_qr_bytes
from bot.states.fsm import BuyStates

router = Router(name="buy")

# ─────────────────────────────────────────────────────────────
# Plan & Tier Catalog (Strictly 4,000 Tomans per GB)
# ─────────────────────────────────────────────────────────────

PLANS_CATALOG: dict[int, dict[str, Any]] = {
    30: {
        "title": "۱ ماهه (۳۰ روز)",
        "options": [
            {"gb": 50, "base_price": 240000, "template_id": 5},
            {"gb": 80, "base_price": 380000, "template_id": 14},
            {"gb": 100, "base_price": 480000, "template_id": 15},
        ],
    },
    60: {
        "title": "۲ ماهه (۶۰ روز)",
        "options": [
            {"gb": 60, "base_price": 290000, "template_id": 13},
            {"gb": 90, "base_price": 430000, "template_id": 15},
        ],
    },
    90: {
        "title": "۳ ماهه (۹۰ روز)",
        "options": [
            {"gb": 70, "base_price": 340000, "template_id": 20},
            {"gb": 100, "base_price": 480000, "template_id": 21},
        ],
    },
    180: {
        "title": "۶ ماهه (۱۸۰ روز)",
        "options": [
            {"gb": 150, "base_price": 720000, "template_id": 23},
            {"gb": 200, "base_price": 960000, "template_id": 23},
        ],
    },
    365: {
        "title": "۱ ساله (۳۶۵ روز)",
        "options": [
            {"gb": 150, "base_price": 600000, "template_id": 24},
            {"gb": 250, "base_price": 1000000, "template_id": 24},
            {"gb": 350, "base_price": 1400000, "template_id": 24},
        ],
    },
}

TIERS_INFO: dict[str, dict[str, Any]] = {
    "1": {"title": "تک‌کاربره", "extra_price": 0, "badge": "👤"},
    "2": {"title": "دوکاربره", "extra_price": 20000, "badge": "👥"},
    "3": {"title": "سه کاربره", "extra_price": 40000, "badge": "👨‍👩‍👧"},
    "99": {"title": "کاربر نامحدود (∞)", "extra_price": 60000, "badge": "👨‍👩‍👦‍👦"},
}


def parse_expire_ts(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    if isinstance(val, str):
        val = val.strip()
        if val.isdigit():
            return datetime.fromtimestamp(int(val))
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def build_delivery_caption(
    amount_toman: int,
    service_code: str,
    duration_days: int,
    data_gb: float,
    sub_url: str,
    location: str = "نت ملی",
    tier_name: str = "نامحدود",
) -> str:
    gb_text = "نامحدود" if data_gb == 0 else f"{data_gb:.0f} گیگ"
    day_text = "نامحدود" if duration_days == 0 else f"{duration_days} روزه"

    return (
        "✅ <b>فاکتور با موفقیت پرداخت گردید و سرویس شما فعال گردید</b>\n\n"
        "🔑 <b>اطلاعات سرویس شما :</b>\n\n"
        f"▫️ 📊 تعداد کاربر مجاز : <b>{tier_name}</b>\n"
        f"▫️ 💰 هزینه سرویس : <b>{amount_toman:,} تومان</b>\n"
        f"▫️ 🔑 کد سرویس : <code>{service_code}</code>\n"
        f"▫️ 🗓 دوره پرداخت : <b>{day_text}</b>\n"
        f"▫️ 🚗 ترافیک : <b>{gb_text}</b>\n"
        "▫️ ⏳ زمان ساخت : <b>در عرض ۲ ثانیه</b>\n"
        f"▫️ 💎 لوکیشن : <b>{location}</b>\n\n"
        "🔗 <b>لینک سرویس شما :</b>\n"
        f"<code>{sub_url}</code>"
    )


# ══════════════════════════════════════════════════════════════
# Step 1 — Start Buy (Single Button: Net Meli)
# ══════════════════════════════════════════════════════════════

@router.message(F.text.in_({"🚀 خرید سرویس جدید", "🛍️ خرید سرویس"}))
@router.callback_query(F.data == "buy:start")
async def buy_start(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = update.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session,
            telegram_id=user_id,
            username=update.from_user.username,
            full_name=update.from_user.full_name,
        )
        if user and user.is_blocked:
            msg = "⛔️ حساب شما مسدود شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
            if isinstance(update, types.CallbackQuery):
                await update.answer(msg, show_alert=True)
            else:
                await update.answer(msg)
            return

        existing = await get_pending_order_for_user(session, user_id)
        if existing:
            warn = (
                f"⚠️ شما یک سفارش معلق با کد <code>{existing.id}</code> دارید.\n"
                "آیا می‌خواهید آن را لغو کنید و سفارش جدید ثبت کنید؟"
            )
            markup = pending_order_kb(existing.id)
            if isinstance(update, types.CallbackQuery):
                await update.message.edit_text(warn, parse_mode="HTML", reply_markup=markup)
            else:
                await update.answer(warn, parse_mode="HTML", reply_markup=markup)
            return

    await state.set_state(BuyStates.choosing_mode)
    text = (
        "🚀 <b>خرید سرویس جدید Zak Univers</b>\n\n"
        "🌐 لطفاً وضعیت شبکه را انتخاب فرمایید:"
    )
    markup = single_mode_kb()

    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_existing_order(callback: types.CallbackQuery, state: FSMContext) -> None:
    order_id = callback.data.split(":")[1]
    async with AsyncSessionLocal() as session:
        await set_order_status(session, order_id, OrderStatus.EXPIRED)
    await callback.answer("سفارش قبلی لغو شد ✅")
    await buy_start(callback, state)


# ══════════════════════════════════════════════════════════════
# Step 2 — Duration Selection
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_mode, F.data == "mode:national")
async def choose_mode_national(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.update_data(mode_title="نت ملی")
    await state.set_state(BuyStates.choosing_duration)

    await callback.message.edit_text(
        "🗓 <b>لطفاً مدت زمان اشتراک را انتخاب نمایید:</b>",
        parse_mode="HTML",
        reply_markup=durations_catalog_kb(),
    )


@router.callback_query(F.data == "buy:back_to_dur")
async def back_to_durations(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyStates.choosing_duration)
    await callback.message.edit_text(
        "🗓 <b>لطفاً مدت زمان اشتراک را انتخاب نمایید:</b>",
        parse_mode="HTML",
        reply_markup=durations_catalog_kb(),
    )


# ══════════════════════════════════════════════════════════════
# Step 3 — Volume Plan Selection
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_duration, F.data.startswith("dur:"))
async def choose_duration(callback: types.CallbackQuery, state: FSMContext) -> None:
    duration = int(callback.data.split(":")[1])
    dur_data = PLANS_CATALOG.get(duration)

    if not dur_data:
        await callback.answer("دوره یافت نشد.", show_alert=True)
        return

    await state.update_data(duration=duration, duration_title=dur_data["title"])
    await state.set_state(BuyStates.choosing_plan)

    await callback.message.edit_text(
        f"📦 <b>پلن‌های اشتراک {dur_data['title']}:</b>\n\n"
        "💰 تعرفه مصوب: <b>هر گیگابایت ۴,۰۰۰ تومان</b>\n\n"
        "پلن مورد نظر را انتخاب نمایید:",
        parse_mode="HTML",
        reply_markup=duration_plans_kb(duration, dur_data["options"]),
    )


@router.callback_query(F.data == "buy:back_to_plans")
async def back_to_plans(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    duration = data.get("duration", 30)
    dur_data = PLANS_CATALOG.get(duration, PLANS_CATALOG[30])

    await state.set_state(BuyStates.choosing_plan)
    await callback.message.edit_text(
        f"📦 <b>پلن‌های اشتراک {dur_data['title']}:</b>\n\n"
        "💰 تعرفه مصوب: <b>هر گیگابایت ۴,۰۰۰ تومان</b>\n\n"
        "پلن مورد نظر را انتخاب نمایید:",
        parse_mode="HTML",
        reply_markup=duration_plans_kb(duration, dur_data["options"]),
    )


# ══════════════════════════════════════════════════════════════
# Step 4 — User Count Selection (تعداد کاربر)
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_plan, F.data.startswith("plan_sel:"))
async def choose_plan_volume(callback: types.CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    duration = int(parts[1])
    gb = int(parts[2])
    base_price = int(parts[3])

    # Find matching template_id from catalog
    template_id = 3
    for opt in PLANS_CATALOG.get(duration, {}).get("options", []):
        if opt["gb"] == gb:
            template_id = opt["template_id"]
            break

    await state.update_data(
        duration=duration,
        data_gb=gb,
        base_price=base_price,
        template_id=template_id,
    )
    await state.set_state(BuyStates.choosing_tier)

    await callback.message.edit_text(
        "💎 <b>خب حالا سرویس رو برای چند کاربر لازم داری؟</b>\n\n"
        "📌 <i>به ازای هر کاربر اضافه، مبلغ ۲۰,۰۰۰ تومان به مبلغ پایه افزوده خواهد شد:</i>",
        parse_mode="HTML",
        reply_markup=user_count_tier_kb(),
    )


@router.callback_query(F.data == "buy:back_to_tiers")
async def back_to_tiers(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyStates.choosing_tier)
    await callback.message.edit_text(
        "💎 <b>خب حالا سرویس رو برای چند کاربر لازم داری؟</b>\n\n"
        "📌 <i>به ازای هر کاربر اضافه، مبلغ ۲۰,۰۰۰ تومان به مبلغ پایه افزوده خواهد شد:</i>",
        parse_mode="HTML",
        reply_markup=user_count_tier_kb(),
    )


# ══════════════════════════════════════════════════════════════
# Step 5 — Config Name Selection (Zak-*****)
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_tier, F.data.startswith("tier_sel:"))
async def choose_tier(callback: types.CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    tier_key = parts[1]
    extra_price = int(parts[2])

    tier_meta = TIERS_INFO.get(tier_key, TIERS_INFO["1"])
    data = await state.get_data()
    base_price = data.get("base_price", 0)
    final_price = base_price + extra_price

    await state.update_data(
        tier_key=tier_key,
        tier_title=tier_meta["title"],
        extra_user_price=extra_price,
        final_price=final_price,
        discount_percent=0,
    )
    await state.set_state(BuyStates.entering_config_name)

    gb = data.get("data_gb", 20)
    duration = data.get("duration", 30)

    await callback.message.edit_text(
        f"📦 پلن: <b>{gb} گیگ — {duration} روزه ({tier_meta['title']})</b>\n"
        f"💰 مبلغ کل: <b>{final_price:,} تومان</b>\n\n"
        "✏️ <b>انتخاب نام دلخواه برای کانفیگ:</b>\n\n"
        "📌 پیشوند شناسه همواره با <code>Zak-</code> آغاز می‌شود (مثال: <code>Zak-pro</code>).\n\n"
        "می‌توانید یک نام دلخواه انگلیسی ارسال کنید، یا روی <b>«🎲 تولید نام تصادفی»</b> بزنید:",
        parse_mode="HTML",
        reply_markup=config_name_kb(),
    )


async def show_pre_invoice(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    final_price = data.get("final_price", 0)
    config_name = data.get("config_name", "Zak-user")
    mode_title = data.get("mode_title", "نت ملی")
    duration = data.get("duration", 30)
    gb = data.get("data_gb", 20)
    tier_title = data.get("tier_title", "تک‌کاربره")
    base_price = data.get("base_price", final_price)
    extra_user_price = data.get("extra_user_price", 0)

    user_id = update.from_user.id
    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)

    text = (
        "📋 <b>پیش‌فاکتور نهایی سفارش Zak Univers:</b>\n\n"
        f"▫️ 💎 وضعیت شبکه: <b>{mode_title}</b>\n"
        f"▫️ 📦 پلن انتخابی: <b>{gb} گیگابایت — {duration} روزه</b>\n"
        f"▫️ 👥 تعداد کاربر مجاز: <b>{tier_title}</b>\n"
        f"▫️ 🔑 شناسه کانفیگ: <code>{config_name}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"▫️ 💵 مبلغ پایه حجم: {base_price:,} تومان\n"
        f"▫️ ➕ اضافه بهای کاربران: {extra_user_price:,} تومان\n"
        f"▫️ 💰 <b>مبلغ نهایی قابل پرداخت: {final_price:,} تومان</b>\n\n"
        "روش پرداخت مورد نظر را انتخاب نمایید:"
    )

    markup = payment_kb(user.balance_toman if user else 0, final_price)
    await state.set_state(BuyStates.choosing_payment)

    if isinstance(update, types.CallbackQuery):
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(BuyStates.entering_config_name, F.data == "cfg_name:random")
async def random_config_name(callback: types.CallbackQuery, state: FSMContext) -> None:
    sfx = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    config_name = f"Zak-{sfx}"
    await state.update_data(config_name=config_name)
    await callback.answer("🎲 نام تصادفی تولید شد!")
    await show_pre_invoice(callback, state)


@router.message(BuyStates.entering_config_name, F.text)
async def custom_config_name_message(message: types.Message, state: FSMContext) -> None:
    raw = message.text.strip()
    clean = "".join(c for c in raw if c.isalnum() or c in "-_")
    if not clean:
        await message.answer("❌ لطفاً یک نام انگلیسی معتبر ارسال کنید:")
        return

    lower = clean.lower()
    if lower.startswith("zak-") or lower.startswith("zak_"):
        config_name = f"Zak-{clean[4:]}"
    else:
        config_name = f"Zak-{clean}"

    await state.update_data(config_name=config_name)
    await show_pre_invoice(message, state)


# ══════════════════════════════════════════════════════════════
# Discount Code
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_payment, F.data == "pay:discount")
async def ask_discount(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyStates.entering_discount)
    await callback.message.edit_text(
        "🎁 <b>ثبت کد تخفیف</b>\n\n"
        "لطفاً کد تخفیف خود را ارسال فرمایید:\n"
        "<i>(در صورت انصراف، روی دکمه زیر ضربه بزنید تا به پیش‌فاکتور بازگردید)</i>",
        parse_mode="HTML",
        reply_markup=discount_cancel_kb(),
    )


@router.callback_query(F.data == "discount:cancel")
async def cancel_discount_entry(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer("به پیش‌فاکتور بازگشتید.")
    await show_pre_invoice(callback, state)


@router.message(BuyStates.entering_discount, F.text)
async def process_discount(message: types.Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    async with AsyncSessionLocal() as session:
        discount = await validate_and_use_discount(session, code)

    data = await state.get_data()
    orig_price = data.get("base_price", 0) + data.get("extra_user_price", 0)

    if not discount:
        await message.answer("❌ کد تخفیف نامعتبر یا منقضی است. لطفاً کد دیگری ارسال کنید یا /cancel را بزنید:")
        return

    final_price = int(orig_price * (1 - discount.percent / 100))
    await state.update_data(discount_percent=discount.percent, final_price=final_price)
    await message.answer(f"✅ کد تخفیف <b>{discount.percent}٪</b> با موفقیت اعمال گردید!")
    await show_pre_invoice(message, state)


# ══════════════════════════════════════════════════════════════
# Payment: Card-to-Card
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_payment, F.data == "pay:card")
async def pay_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    final_price = data.get("final_price", 0)
    template_id = data.get("template_id", 3)
    discount_percent = data.get("discount_percent", 0)
    config_name = data.get("config_name", "Zak-user")
    expiry = datetime.utcnow() + timedelta(minutes=settings.order_expiry_minutes)

    async with AsyncSessionLocal() as session:
        card_number = await get_setting(session, "BANK_CARD", "6063731268895845")
        bank_name = await get_setting(session, "BANK_NAME", "مهر ایران")

        order = await create_order(
            session,
            user_id=callback.from_user.id,
            plan_id=template_id,
            amount_toman=final_price,
            discount_applied=discount_percent,
            expires_at=expiry,
            custom_config_name=config_name,
        )
        await set_order_status(session, order.id, OrderStatus.AWAITING_RECEIPT)

    await state.update_data(order_id=order.id)
    await state.set_state(BuyStates.awaiting_receipt)

    await callback.message.edit_text(
        f"💳 <b>پرداخت کارت به کارت</b>\n\n"
        f"لطفاً مبلغ را به شماره کارت زیر واریز فرمایید:\n\n"
        f"💰 مبلغ قابل پرداخت (تومان):\n<code>{final_price}</code>\n"
        f"<i>(معادل {final_price:,} تومان)</i>\n\n"
        f"💳 شماره کارت بانکی:\n<code>{card_number}</code>\n"
        f"🏦 بانک: <b>{bank_name}</b>\n\n"
        f"👆 <i>(برای کپی کردن کافیست روی مبلغ یا شماره کارت لمس کنید)</i>\n\n"
        f"⏳ مهلت پرداخت: <b>{settings.order_expiry_minutes} دقیقه</b>\n"
        f"📌 کد سفارش شما: <code>{order.id}</code>\n"
        f"🔑 نام کانفیگ درخواستی: <code>{config_name}</code>\n\n"
        f"پس از واریز، لطفاً <b>عکس فیش پرداختی</b> را همینجا ارسال نمایید:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


# ══════════════════════════════════════════════════════════════
# Payment: Wallet Balance (Direct Delivery)
# ══════════════════════════════════════════════════════════════

@router.callback_query(BuyStates.choosing_payment, F.data == "pay:wallet")
async def pay_wallet(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    final_price = data.get("final_price", 0)
    template_id = data.get("template_id", 3)
    duration = data.get("duration", 30)
    data_gb = data.get("data_gb", 20)
    config_name = data.get("config_name", "Zak-user")
    mode_title = data.get("mode_title", "نت ملی")
    tier_title = data.get("tier_title", "نامحدود")

    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)
        if not user or user.balance_toman < final_price:
            await callback.answer("⚠️ موجودی کیف پول شما برای این خرید کافی نیست.", show_alert=True)
            return

        await deduct_wallet_balance(
            session,
            user_id=callback.from_user.id,
            amount_toman=final_price,
            description=f"خرید سرویس {data_gb} گیگ — {duration} روزه ({config_name})",
        )

        order = await create_order(
            session,
            user_id=callback.from_user.id,
            plan_id=template_id,
            amount_toman=final_price,
            custom_config_name=config_name,
        )
        await set_order_status(session, order.id, OrderStatus.CONFIRMED)

    await state.clear()
    await callback.answer("✅ مبلغ کسر شد. در حال صدور کانفیگ...")

    try:
        user_data = await panel.create_user_from_template(
            template_id=template_id,
            telegram_id=order.user_id,
            note=f"order:{order.id}|user:{order.user_id}",
            custom_username=config_name,
        )
        sub_url = user_data.get("subscription_url", "")
        marzban_username = user_data.get("username", "")
        expire_ts = parse_expire_ts(user_data.get("expire"))
        data_limit = user_data.get("data_limit", 0)

        # Set exact limit and expiry if needed
        exact_bytes = int(data_gb * (1024**3))
        if exact_bytes > 0 and data_limit != exact_bytes:
            await panel.modify_user(marzban_username, {"data_limit": exact_bytes})
            data_limit = exact_bytes

        async with AsyncSessionLocal() as session:
            await create_subscription(
                session,
                user_id=order.user_id,
                order_id=order.id,
                marzban_username=marzban_username,
                subscription_url=sub_url,
                expire_timestamp=expire_ts,
                data_limit_bytes=data_limit,
            )
            await set_order_status(session, order.id, OrderStatus.DELIVERED)

        qr_bytes = make_qr_bytes(sub_url)
        caption = build_delivery_caption(
            amount_toman=final_price,
            service_code=marzban_username,
            duration_days=duration,
            data_gb=data_gb,
            sub_url=sub_url,
            location=mode_title,
            tier_name=tier_title,
        )
        delivery_kb = after_delivery_kb(sub_url)

        await callback.bot.send_photo(
            chat_id=order.user_id,
            photo=BufferedInputFile(qr_bytes, filename="qrcode.png"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=delivery_kb,
        )
        try:
            await callback.message.delete()
        except Exception:
            pass

    except Exception as exc:
        logger.error(f"Wallet provision failed: {exc}")
        async with AsyncSessionLocal() as session:
            await set_order_status(session, order.id, OrderStatus.PAID_PENDING_PROVISION)
        await callback.message.edit_text(
            f"🎉 <b>پرداخت شما با موفقیت انجام شد!</b>\n\n"
            f"💵 مبلغ <b>{final_price:,} تومان</b> از موجودی کیف پول شما کسر گردید.\n"
            f"📌 کد سفارش: <code>{order.id}</code>\n\n"
            f"⏳ کانفیگ شما به زودی صادر و ارسال خواهد شد.",
            parse_mode="HTML",
            reply_markup=after_delivery_kb(),
        )


# ══════════════════════════════════════════════════════════════
# Receipt Photo Handler (CRITICAL BUG FIX: state.clear() immediately!)
# ══════════════════════════════════════════════════════════════

@router.message(BuyStates.awaiting_receipt, F.photo)
async def receive_receipt(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data.get("order_id")
    file_id = message.photo[-1].file_id

    # CRITICAL: Clear state so user is NEVER stuck in awaiting_receipt!
    await state.clear()

    async with AsyncSessionLocal() as session:
        order = await get_order(session, order_id)
        if not order or order.status not in (OrderStatus.AWAITING_RECEIPT,):
            await message.answer("⚠️ سفارش یافت نشد یا منقضی شده است.")
            return

        await set_order_receipt(session, order_id, file_id, PaymentMethod.CARD)

    admin_text = (
        f"🔔 <b>سفارش جدید {order_id}</b>\n\n"
        f"👤 کاربر: @{message.from_user.username or 'بدون username'} "
        f"(ID: <code>{message.from_user.id}</code>)\n"
        f"🔑 نام درخواستی: <code>{order.custom_config_name or 'Zak-auto'}</code>\n"
        f"💰 مبلغ: {order.amount_toman:,} تومان\n"
        f"📅 زمان: {datetime.now().strftime('%Y/%m/%d — %H:%M')}"
    )

    bot = message.bot
    sent_admin_msgs = []
    for admin_id in settings.owner_ids:
        try:
            m = await bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=admin_order_kb(order_id),
            )
            sent_admin_msgs.append(m)
        except Exception as exc:
            logger.warning(f"Could not notify admin {admin_id}: {exc}")

    if sent_admin_msgs:
        async with AsyncSessionLocal() as session:
            await save_admin_receipt_messages(session, f"order:{order_id}", sent_admin_msgs)

    await message.answer(
        f"⏳ <b>فیش واریزی شما دریافت شد</b>\n\n"
        f"پرداخت شما در حال بررسی توسط مدیریت است.\n"
        f"معمولاً در کمتر از ۱۵ دقیقه تایید می‌شود.\n\n"
        f"📌 کد سفارش: <code>{order_id}</code>",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════
# Admin: Confirm Order -> Credit Wallet -> Ask User Delivery Choice
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ شما اجازه این کار را ندارید.", show_alert=True)
        return

    order_id = callback.data.split(":")[1]
    admin_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        won, user_balance = await atomic_confirm_order(session, order_id, admin_id)
        if not won:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.answer("⚠️ این سفارش قبلاً توسط ادمین دیگری پردازش شده است.", show_alert=True)
            return

        order = await get_order(session, order_id)
        target_user_id = order.user_id
        amount_toman = order.amount_toman

        base_caption = callback.message.caption or f"سفارش {order_id}"
        confirm_caption = (
            f"{base_caption}\n\n"
            f"✅ <b>سفارش تایید شد!</b>\n"
            f"💰 مبلغ {amount_toman:,} تومان به کیف پول کاربر منظور شد."
        )
        await update_all_admin_receipt_messages(
            callback.bot,
            session,
            f"order:{order_id}",
            confirm_caption,
            callback.from_user,
        )

    await callback.answer("✅ سفارش تایید شد و برای تمام ادمین‌ها بروزرسانی گردید.")

    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 <b>فیش پرداخت شما با موفقیت تایید گردید!</b>\n\n"
                f"💰 مبلغ <b>{amount_toman:,} تومان</b> به کیف پول شما منظور گردید.\n"
                f"💵 موجودی فعلی: <b>{user_balance:,} تومان</b>\n"
                f"📌 کد سفارش: <code>{order_id}</code>\n\n"
                f"آیا مایلید هم‌اکنون کانفیگ اختصاصی شما ساخته و تحویل داده شود یا مبلغ در کیف پول شما باقی بماند؟"
            ),
            parse_mode="HTML",
            reply_markup=delivery_choice_kb(order_id),
        )
    except Exception as exc:
        logger.error(f"Failed to notify user {target_user_id}: {exc}")


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ شما اجازه این کار را ندارید.", show_alert=True)
        return

    order_id = callback.data.split(":")[1]
    async with AsyncSessionLocal() as session:
        order = await get_order(session, order_id)
        if not order or order.status != OrderStatus.RECEIPT_SENT:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.answer("⚠️ این سفارش قبلاً پردازش شده یا قابل رد نیست.", show_alert=True)
            return
        await set_order_status(session, order_id, OrderStatus.REJECTED)

        base_caption = callback.message.caption or f"سفارش {order_id}"
        reject_caption = (
            f"{base_caption}\n\n"
            f"❌ <b>سفارش رد شد!</b>"
        )
        await update_all_admin_receipt_messages(
            callback.bot,
            session,
            f"order:{order_id}",
            reject_caption,
            callback.from_user,
        )

    await callback.answer("❌ سفارش رد شد و برای تمام ادمین‌ها بروزرسانی گردید.")

    try:
        await callback.bot.send_message(
            chat_id=order.user_id,
            text=(
                f"❌ <b>فیش پرداخت تایید نشد</b>\n\n"
                f"📌 کد سفارش: <code>{order_id}</code>\n\n"
                f"لطفاً فیش معتبر ارسال کنید یا با پشتیبانی تماس بگیرید."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# User Choice: Direct Config Delivery or Save in Wallet
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_delivery:wallet:"))
async def user_choose_wallet(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("💰 موجودی در کیف پول شما ذخیره شد.")
    await callback.message.edit_text(
        "💰 <b>مبلغ در کیف پول شما محفوظ ماند</b>\n\n"
        "موجودی شما با موفقیت در حسابتان ثبت شد.\n"
        "هر زمان که مایل باشید می‌توانید از منوی اصلی ربات جهت خرید سرویس یا حجم اضافه از آن استفاده کنید. ✅",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("user_delivery:direct:"))
async def user_choose_direct(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    order_id = callback.data.split(":")[2]
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        order = await get_order(session, order_id)
        if not order:
            await callback.answer("سفارش یافت نشد.", show_alert=True)
            return

        if order.status == OrderStatus.DELIVERED:
            await callback.answer("این سرویس قبلاً تحویل داده شده است.", show_alert=True)
            return

        user = await get_user(session, user_id)
        if not user or user.balance_toman < order.amount_toman:
            await callback.answer("⚠️ موجودی کیف پول برای تحویل این سفارش کافی نیست.", show_alert=True)
            return

        amount_toman = order.amount_toman
        template_id = order.plan_id or 3
        custom_config_name = order.custom_config_name or f"Zak-{user_id}"

    await callback.answer("🚀 در حال صدور کانفیگ اختصاصی شما...")

    try:
        user_data = await panel.create_user_from_template(
            template_id=template_id,
            telegram_id=user_id,
            note=f"order:{order_id}|user:{user_id}",
            custom_username=custom_config_name,
        )
    except Exception as exc:
        logger.error(f"User direct provision failed: {exc}")
        await callback.message.edit_text(
            f"🚨 <b>خطا در ساخت اکانت در پنل!</b>\n\n"
            f"مبلغ <b>{amount_toman:,} تومان</b> در کیف پول شما کاملاً محفوظ است.\n"
            f"پشتیبانی فنی در حال بررسی می‌باشد.",
            parse_mode="HTML",
        )
        return

    sub_url = user_data.get("subscription_url", "")
    marzban_username = user_data.get("username", "")
    expire_ts = parse_expire_ts(user_data.get("expire"))
    data_limit = user_data.get("data_limit", 0)

    async with AsyncSessionLocal() as session:
        await create_subscription(
            session,
            user_id=user_id,
            order_id=order_id,
            marzban_username=marzban_username,
            subscription_url=sub_url,
            expire_timestamp=expire_ts,
            data_limit_bytes=data_limit,
        )
        await deduct_wallet_balance(
            session,
            user_id=user_id,
            amount_toman=amount_toman,
            description=f"تحویل سفارش {order_id} ({marzban_username})",
        )
        await set_order_status(session, order_id, OrderStatus.DELIVERED)

    qr_bytes = make_qr_bytes(sub_url)
    caption = build_delivery_caption(
        amount_toman=amount_toman,
        service_code=marzban_username,
        duration_days=30,
        data_gb=data_limit / (1024**3) if data_limit else 0,
        sub_url=sub_url,
    )
    delivery_kb = after_delivery_kb(sub_url)

    await callback.bot.send_photo(
        chat_id=user_id,
        photo=BufferedInputFile(qr_bytes, filename="qrcode.png"),
        caption=caption,
        parse_mode="HTML",
        reply_markup=delivery_kb,
    )

    try:
        await callback.message.delete()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# Cancel Handler
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "buy:cancel")
@router.message(Command("cancel"))
async def cancel_buy(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = update.from_user.id
    from bot.config import is_admin_user
    from bot.keyboards.user_kb import main_menu_inline_kb, main_menu_kb
    is_admin = is_admin_user(user_id)
    text = "❌ عملیات لغو شد. به منوی اصلی بازگشتید."
    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, reply_markup=main_menu_inline_kb(is_admin=is_admin, user_id=user_id))
    else:
        await update.answer(text, reply_markup=main_menu_kb(is_admin=is_admin, user_id=user_id))
