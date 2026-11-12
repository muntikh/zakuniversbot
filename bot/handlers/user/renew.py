from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from loguru import logger

from bot.config import is_admin_user, settings
from bot.db.crud import (
    deduct_wallet_balance,
    get_setting,
    get_subscription,
    get_user,
    get_user_subscriptions,
    update_subscription_renew,
)
from bot.db.database import AsyncSessionLocal
from bot.keyboards.user_kb import cancel_kb
from bot.services.admin_sync import (
    save_admin_receipt_messages,
    update_all_admin_receipt_messages,
)
from bot.services.pasarguard import panel
from bot.states.fsm import RenewStates

router = Router(name="renew")

RENEW_PLANS = {
    30: [
        {"gb": 50, "price": 240000},
        {"gb": 80, "price": 380000},
        {"gb": 100, "price": 480000},
    ],
    60: [
        {"gb": 60, "price": 290000},
        {"gb": 90, "price": 430000},
    ],
    90: [
        {"gb": 70, "price": 340000},
        {"gb": 100, "price": 480000},
    ],
    180: [
        {"gb": 150, "price": 720000},
        {"gb": 200, "price": 960000},
    ],
    365: [
        {"gb": 150, "price": 600000},
        {"gb": 250, "price": 1000000},
        {"gb": 350, "price": 1400000},
    ],
}


@router.message(F.text.in_({"♻️ تمدید سرویس", "⚡️ تمدید سرویس", "تمدید سرویس", "تمدید"}))
@router.callback_query(F.data == "renew:start")
async def start_renew(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = update.from_user.id

    async with AsyncSessionLocal() as session:
        subs = await get_user_subscriptions(session, user_id)

    if not subs:
        msg = (
            "⚠️ <b>شما هیچ سرویس فعالی برای تمدید ندارید.</b>\n\n"
            "جهت خرید سرویس جدید می‌توانید از دکمه «🚀 خرید سرویس جدید» استفاده فرمایید."
        )
        if isinstance(update, types.CallbackQuery):
            await update.answer()
            await update.message.edit_text(msg, parse_mode="HTML")
        else:
            await update.answer(msg, parse_mode="HTML")
        return

    if len(subs) == 1:
        sub = subs[0]
        await state.update_data(sub_id=sub.id, username=sub.marzban_username)
        await show_renew_durations(update, sub.marzban_username, state)
        return

    buttons = []
    for s in subs:
        buttons.append([
            types.InlineKeyboardButton(
                text=f"🔑 {s.marzban_username}",
                callback_data=f"renew_svc:{s.id}",
            )
        ])
    buttons.append([types.InlineKeyboardButton(text="❌ انصراف", callback_data="buy:cancel")])

    await state.set_state(RenewStates.choosing_service)
    text = (
        "♻️ <b>تمدید اشتراک Zak Univers</b>\n\n"
        "لطفاً سرویسی که مایل به تمدید آن هستید را انتخاب نمایید:"
    )
    markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("svc_renew:"))
async def renew_from_service_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    sub_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)

    if not sub:
        await callback.answer("سرویس یافت نشد.", show_alert=True)
        return

    await state.update_data(sub_id=sub.id, username=sub.marzban_username)
    await show_renew_durations(callback, sub.marzban_username, state)


@router.callback_query(RenewStates.choosing_service, F.data.startswith("renew_svc:"))
async def choose_service_for_renew(callback: types.CallbackQuery, state: FSMContext) -> None:
    sub_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)

    if not sub:
        await callback.answer("سرویس یافت نشد.", show_alert=True)
        return

    await state.update_data(sub_id=sub.id, username=sub.marzban_username)
    await show_renew_durations(callback, sub.marzban_username, state)


async def show_renew_durations(
    update: types.Message | types.CallbackQuery, username: str, state: FSMContext
) -> None:
    await state.set_state(RenewStates.choosing_duration)

    text = (
        "♻️ <b>انتخاب مدت زمان تمدید:</b>\n\n"
        f"🔑 سرویس هدف: <code>{username}</code>\n\n"
        "مدت زمان تمدید اشتراک خود را مشخص فرمایید:"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📅 ۱ ماهه (۳۰ روز)", callback_data="renew_dur:30"),
                types.InlineKeyboardButton(text="🚀 ۲ ماهه (۶۰ روز)", callback_data="renew_dur:60"),
            ],
            [
                types.InlineKeyboardButton(text="⭐️ ۳ ماهه (۹۰ روز)", callback_data="renew_dur:90"),
                types.InlineKeyboardButton(text="🗓 ۶ ماهه (۱۸۰ روز)", callback_data="renew_dur:180"),
            ],
            [
                types.InlineKeyboardButton(text="👑 ۱ ساله (۳۶۵ روز)", callback_data="renew_dur:365"),
            ],
            [
                types.InlineKeyboardButton(text="❌ انصراف", callback_data="buy:cancel"),
            ],
        ]
    )

    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(RenewStates.choosing_duration, F.data.startswith("renew_dur:"))
async def choose_renew_duration(callback: types.CallbackQuery, state: FSMContext) -> None:
    duration = int(callback.data.split(":")[1])
    await state.update_data(duration=duration)

    options = RENEW_PLANS.get(duration, RENEW_PLANS[30])

    rows = []
    for opt in options:
        gb = opt["gb"]
        price = opt["price"]
        rows.append([
            types.InlineKeyboardButton(
                text=f"📦 {gb} گیگ — {price:,} تومان",
                callback_data=f"renew_opt:{gb}:{price}",
            )
        ])
    rows.append([types.InlineKeyboardButton(text="🔙 مرحله قبل", callback_data="renew:start")])

    await state.set_state(RenewStates.choosing_plan)
    await callback.message.edit_text(
        f"📦 <b>انتخاب حجم تمدید ({duration} روزه):</b>\n\n"
        "💰 تعرفه هر گیگابایت: ۴,۰۰۰ تومان\n\n"
        "پلن مورد نظر را انتخاب نمایید:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(RenewStates.choosing_plan, F.data.startswith("renew_opt:"))
async def choose_renew_opt(callback: types.CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    gb = int(parts[1])
    price = int(parts[2])

    await state.update_data(gb=gb, price=price)
    await state.set_state(RenewStates.choosing_payment)

    data = await state.get_data()
    username = data.get("username", "")
    duration = data.get("duration", 30)

    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)
        user_balance = user.balance_toman if user else 0

    text = (
        "📋 <b>پیش‌فاکتور تمدید سرویس:</b>\n\n"
        f"🔑 سرویس: <code>{username}</code>\n"
        f"🗓 دوره تمدید: <b>{duration} روز</b>\n"
        f"🚗 ترافیک شارژ: <b>{gb} گیگابایت</b>\n"
        f"💰 مبلغ تمدید: <b>{price:,} تومان</b>\n\n"
        "روش پرداخت را انتخاب نمایید:"
    )

    rows = [
        [types.InlineKeyboardButton(text="💳 کارت به کارت", callback_data="renew_pay:card")],
    ]
    if user_balance >= price:
        rows.append([
            types.InlineKeyboardButton(
                text=f"💰 پرداخت از کیف پول (موجودی: {user_balance:,} ت)",
                callback_data="renew_pay:wallet",
            )
        ])
    rows.append([types.InlineKeyboardButton(text="❌ انصراف", callback_data="buy:cancel")])

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ══════════════════════════════════════════════════════════════
# Payment: Wallet
# ══════════════════════════════════════════════════════════════

@router.callback_query(RenewStates.choosing_payment, F.data == "renew_pay:wallet")
async def pay_renew_wallet(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    price = data.get("price", 0)
    sub_id = data.get("sub_id")
    username = data.get("username", "")
    duration = data.get("duration", 30)
    gb = data.get("gb", 20)
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)
        if not user or user.balance_toman < price:
            await callback.answer("⚠️ موجودی کیف پول کافی نیست.", show_alert=True)
            return

        await deduct_wallet_balance(
            session,
            user_id=user_id,
            amount_toman=price,
            description=f"تمدید سرویس {username} ({duration} روز - {gb} گیگ)",
        )

    await state.clear()
    await callback.answer("در حال تمدید سرویس در سرور...")

    try:
        user_data = await panel.renew_user(username, duration)
        extra_bytes = int(gb * (1024**3))
        await panel.modify_user(username, {"data_limit": extra_bytes})

        raw_exp = user_data.get("expire")
        if raw_exp:
            new_expire = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))
        else:
            new_expire = datetime.now(timezone.utc) + timedelta(days=duration)

        async with AsyncSessionLocal() as session:
            await update_subscription_renew(session, sub_id, new_expire)
    except Exception as exc:
        logger.error(f"Renewal error in panel for {username}: {exc}")

    await callback.message.edit_text(
        f"✅ <b>سرویس با موفقیت تمدید شد!</b>\n\n"
        f"🔑 سرویس: <code>{username}</code>\n"
        f"🗓 تمدید به مدت: <b>{duration} روز</b>\n"
        f"🚗 ترافیک جدید: <b>{gb} گیگابایت</b>\n"
        f"💰 مبلغ کسر شده: <b>{price:,} تومان</b>",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="📱 مشاهده مشخصات سرویس", callback_data=f"svc_view:{sub_id}")]
            ]
        ),
    )


# ══════════════════════════════════════════════════════════════
# Payment: Card
# ══════════════════════════════════════════════════════════════

@router.callback_query(RenewStates.choosing_payment, F.data == "renew_pay:card")
async def pay_renew_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    price = data.get("price", 0)
    duration = data.get("duration", 30)
    gb = data.get("gb", 20)
    username = data.get("username", "")

    async with AsyncSessionLocal() as session:
        card_number = await get_setting(session, "BANK_CARD", "6063731268895845")
        bank_name = await get_setting(session, "BANK_NAME", "مهر ایران")

    await state.set_state(RenewStates.awaiting_receipt)

    await callback.message.edit_text(
        f"💳 <b>پرداخت کارت به کارت جهت تمدید سرویس</b>\n\n"
        f"🔑 سرویس هدف: <code>{username}</code>\n"
        f"🗓 مدت تمدید: <b>{duration} روز</b> ({gb} گیگ)\n\n"
        f"💰 مبلغ قابل پرداخت (تومان):\n<code>{price}</code>\n"
        f"<i>(معادل {price:,} تومان)</i>\n\n"
        f"🏦 بانک: <b>{bank_name}</b>\n"
        f"💳 شماره کارت بانکی:\n<code>{card_number}</code>\n\n"
        f"👆 <i>(برای کپی کردن کافیست روی مبلغ یا شماره کارت لمس کنید)</i>\n\n"
        f"لطفاً پس از واریز، <b>تصویر فیش پرداخت</b> را همینجا ارسال فرمایید:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(RenewStates.awaiting_receipt, F.photo)
async def receive_renew_receipt(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    duration = data.get("duration", 30)
    gb = data.get("gb", 20)
    price = data.get("price", 0)
    username = data.get("username", "")
    sub_id = data.get("sub_id")
    file_id = message.photo[-1].file_id

    # CRITICAL: Clear state immediately so user is not stuck!
    await state.clear()

    caption = (
        f"🔔 <b>درخواست تمدید برای سرویس {username}</b>\n\n"
        f"👤 کاربر: @{message.from_user.username or 'بدون username'} "
        f"(ID: <code>{message.from_user.id}</code>)\n"
        f"🗓 دوره: <b>{duration} روز ({gb} گیگ)</b>\n"
        f"💰 مبلغ: <b>{price:,} تومان</b>"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ تایید و تمدید سرویس",
                    callback_data=f"admin_renew_ok:{message.from_user.id}:{sub_id}:{duration}:{gb}",
                ),
                types.InlineKeyboardButton(
                    text="❌ رد درخواست",
                    callback_data=f"admin_renew_no:{message.from_user.id}",
                ),
            ]
        ]
    )

    bot = message.bot
    sent_admin_msgs = []
    for admin_id in settings.owner_ids:
        try:
            m = await bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
            sent_admin_msgs.append(m)
        except Exception:
            pass

    if sent_admin_msgs:
        async with AsyncSessionLocal() as session:
            await save_admin_receipt_messages(session, f"renew:{sub_id}:{duration}", sent_admin_msgs)

    await message.answer(
        "⏳ <b>فیش پرداخت تمدید دریافت شد.</b>\n\n"
        "پس از بررسی و تایید مدیریت، سرویس شما تمدید خواهد شد.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_renew_ok:"))
async def admin_confirm_renew(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    sub_id = int(parts[2])
    duration = int(parts[3])
    gb = int(parts[4]) if len(parts) > 4 else 20

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)
        if not sub:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.answer("سرویس یافت نشد یا قبلاً پردازش شده است.", show_alert=True)
            return
        username = sub.marzban_username

    try:
        user_data = await panel.renew_user(username, duration)
        extra_bytes = int(gb * (1024**3))
        await panel.modify_user(username, {"data_limit": extra_bytes})

        raw_exp = user_data.get("expire")
        if raw_exp:
            new_expire = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))
        else:
            new_expire = datetime.now(timezone.utc) + timedelta(days=duration)

        async with AsyncSessionLocal() as session:
            await update_subscription_renew(session, sub_id, new_expire)
            base_caption = callback.message.caption or "درخواست تمدید"
            confirm_text = f"{base_caption}\n\n✅ <b>سرویس تایید و به مدت {duration} روز ({gb} گیگ) تمدید شد.</b>"
            await update_all_admin_receipt_messages(
                callback.bot,
                session,
                f"renew:{sub_id}:{duration}",
                confirm_text,
                callback.from_user,
            )
    except Exception as exc:
        logger.error(f"Error renewing user in panel: {exc}")

    await callback.answer("✅ سرویس تمدید شد و پیام برای تمام ادمین‌ها بروزرسانی گردید.")

    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 <b>فیش پرداخت تمدید سرویس شما تایید شد!</b>\n\n"
                f"🔑 سرویس: <code>{username}</code>\n"
                f"🗓 اشتراک شما به مدت <b>{duration} روز ({gb} گیگ)</b> با موفقیت تمدید گردید. ✅"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_renew_no:"))
async def admin_reject_renew(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    sub_id = int(parts[2]) if len(parts) > 2 else 0
    duration = int(parts[3]) if len(parts) > 3 else 0

    base_caption = callback.message.caption or "درخواست تمدید"
    reject_text = f"{base_caption}\n\n❌ <b>درخواست تمدید رد شد.</b>"

    async with AsyncSessionLocal() as session:
        await update_all_admin_receipt_messages(
            callback.bot,
            session,
            f"renew:{sub_id}:{duration}",
            reject_text,
            callback.from_user,
        )

    await callback.answer("❌ درخواست تمدید رد شد.")

    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text="❌ فیش پرداخت تمدید سرویس شما تایید نشد. در صورت وجود سوال با پشتیبانی تماس بگیرید.",
        )
    except Exception:
        pass
