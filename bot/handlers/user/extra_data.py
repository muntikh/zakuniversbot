from __future__ import annotations

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
    update_subscription_traffic,
)
from bot.db.database import AsyncSessionLocal
from bot.keyboards.user_kb import cancel_kb
from bot.services.admin_sync import (
    save_admin_receipt_messages,
    update_all_admin_receipt_messages,
)
from bot.services.pasarguard import panel
from bot.states.fsm import ExtraDataStates

router = Router(name="extra_data")


@router.message(F.text.in_({"♾️ حجم اضافه", "حجم اضافه"}))
@router.callback_query(F.data == "extra:start")
async def start_extra_data(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = update.from_user.id

    async with AsyncSessionLocal() as session:
        subs = await get_user_subscriptions(session, user_id)

    if not subs:
        msg = (
            "⚠️ <b>شما در حال حاضر هیچ سرویس فعالی برای افزودن حجم ندارید.</b>\n\n"
            "ابتدا از بخش «🚀 خرید سرویس جدید» یک اشتراک تهیه فرمایید."
        )
        if isinstance(update, types.CallbackQuery):
            await update.answer()
            await update.message.edit_text(msg, parse_mode="HTML")
        else:
            await update.answer(msg, parse_mode="HTML")
        return

    if len(subs) == 1:
        # Auto-select the only service
        sub = subs[0]
        await state.update_data(sub_id=sub.id, username=sub.marzban_username)
        await show_extra_gb_options(update, sub.marzban_username, state)
        return

    # Multiple services — let user choose
    buttons = []
    for s in subs:
        buttons.append([
            types.InlineKeyboardButton(
                text=f"🔑 {s.marzban_username}",
                callback_data=f"extra_svc:{s.id}",
            )
        ])
    buttons.append([types.InlineKeyboardButton(text="❌ انصراف", callback_data="buy:cancel")])

    await state.set_state(ExtraDataStates.choosing_service)
    text = (
        "♾️ <b>افزایش حجم سرویس Zak Univers</b>\n\n"
        "لطفاً سرویسی که می‌خواهید به آن حجم اضافه کنید را انتخاب فرمایید:"
    )
    markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("svc_extradata:"))
async def extra_from_service_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    sub_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)

    if not sub:
        await callback.answer("سرویس یافت نشد.", show_alert=True)
        return

    await state.update_data(sub_id=sub.id, username=sub.marzban_username)
    await show_extra_gb_options(callback, sub.marzban_username, state)


@router.callback_query(ExtraDataStates.choosing_service, F.data.startswith("extra_svc:"))
async def choose_service_for_extra(callback: types.CallbackQuery, state: FSMContext) -> None:
    sub_id = int(callback.data.split(":")[1])

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, sub_id)

    if not sub:
        await callback.answer("سرویس یافت نشد.", show_alert=True)
        return

    await state.update_data(sub_id=sub.id, username=sub.marzban_username)
    await show_extra_gb_options(callback, sub.marzban_username, state)


async def show_extra_gb_options(
    update: types.Message | types.CallbackQuery, username: str, state: FSMContext
) -> None:
    await state.set_state(ExtraDataStates.choosing_amount)

    text = (
        "♾️ <b>خرید حجم اضافه</b>\n\n"
        f"🔑 سرویس هدف: <code>{username}</code>\n"
        "💰 تعرفه هر گیگابایت: <b>۴,۰۰۰ تومان</b>\n\n"
        "میزان حجم مورد نظر را انتخاب نمایید:"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="➕ ۵ گیگ (۲۰,۰۰۰ ت)", callback_data="extra_amt:5"),
                types.InlineKeyboardButton(text="➕ ۱۰ گیگ (۴۰,۰۰۰ ت)", callback_data="extra_amt:10"),
            ],
            [
                types.InlineKeyboardButton(text="➕ ۲۰ گیگ (۸۰,۰۰۰ ت)", callback_data="extra_amt:20"),
                types.InlineKeyboardButton(text="➕ ۵۰ گیگ (۲۰۰,۰۰۰ ت)", callback_data="extra_amt:50"),
            ],
            [
                types.InlineKeyboardButton(text="✏️ ورود حجم دلخواه", callback_data="extra_amt:custom"),
            ],
            [
                types.InlineKeyboardButton(text="❌ انصراف", callback_data="extra_cancel"),
            ],
        ]
    )

    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(ExtraDataStates.choosing_amount, F.data == "extra_amt:custom")
async def ask_custom_gb(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExtraDataStates.entering_custom_gb)
    await callback.message.edit_text(
        "✏️ لطفاً مقدار حجم مورد نظرتان را به <b>گیگابایت</b> (عدد انگلیسی) وارد فرمایید:\n\n"
        "<i>(مثلاً: 15 برای ۱۵ گیگابایت)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(ExtraDataStates.entering_custom_gb, F.text)
async def process_custom_gb(message: types.Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ لطفاً یک عدد صحیح بزرگتر از صفر وارد کنید:")
        return

    gb = int(text)
    await process_selected_gb(message, gb, state)


@router.callback_query(ExtraDataStates.choosing_amount, F.data.startswith("extra_amt:"))
async def process_fixed_gb(callback: types.CallbackQuery, state: FSMContext) -> None:
    gb = int(callback.data.split(":")[1])
    await process_selected_gb(callback, gb, state)


async def process_selected_gb(
    update: types.Message | types.CallbackQuery, gb: int, state: FSMContext
) -> None:
    price = gb * 4000
    await state.update_data(extra_gb=gb, price=price)
    await state.set_state(ExtraDataStates.choosing_payment)

    user_id = update.from_user.id
    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)
        user_balance = user.balance_toman if user else 0

    data = await state.get_data()
    username = data.get("username", "")

    text = (
        "📋 <b>پیش‌فاکتور خرید حجم اضافه:</b>\n\n"
        f"🔑 سرویس: <code>{username}</code>\n"
        f"➕ ترافیک مازاد: <b>{gb} گیگابایت</b>\n"
        f"💰 مبلغ کل: <b>{price:,} تومان</b>\n\n"
        "روش پرداخت را انتخاب نمایید:"
    )

    rows = [
        [types.InlineKeyboardButton(text="💳 کارت به کارت", callback_data="extra_pay:card")],
    ]
    if user_balance >= price:
        rows.append([
            types.InlineKeyboardButton(
                text=f"💰 پرداخت از کیف پول (موجودی: {user_balance:,} ت)",
                callback_data="extra_pay:wallet",
            )
        ])
    rows.append([types.InlineKeyboardButton(text="❌ انصراف", callback_data="extra_cancel")])

    markup = types.InlineKeyboardMarkup(inline_keyboard=rows)

    if isinstance(update, types.CallbackQuery):
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


# ══════════════════════════════════════════════════════════════
# Payment for Extra Traffic: Wallet
# ══════════════════════════════════════════════════════════════

@router.callback_query(ExtraDataStates.choosing_payment, F.data == "extra_pay:wallet")
async def pay_extra_wallet(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    gb = data.get("extra_gb", 0)
    price = data.get("price", 0)
    sub_id = data.get("sub_id")
    username = data.get("username", "")
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
            description=f"افزایش {gb} گیگ حجم سرویس {username}",
        )

    await state.clear()
    await callback.answer("در حال اعمال افزایش حجم در سرور...")

    extra_bytes = gb * (1024**3)
    try:
        await panel.add_user_traffic(username, extra_bytes)
        async with AsyncSessionLocal() as session:
            await update_subscription_traffic(session, sub_id, extra_bytes)
    except Exception as exc:
        logger.error(f"Failed to add traffic in panel for {username}: {exc}")

    await callback.message.edit_text(
        f"✅ <b>افزایش حجم با موفقیت انجام شد!</b>\n\n"
        f"🔑 سرویس: <code>{username}</code>\n"
        f"➕ حجم افزوده شده: <b>{gb} گیگابایت</b>\n"
        f"💰 مبلغ کسر شده: <b>{price:,} تومان</b>\n\n"
        "ترافیک سرویس شما بلافاصله در سرور بروزرسانی گردید.",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🐍 مشاهده مشخصات سرویس", callback_data=f"svc_view:{sub_id}")]
            ]
        ),
    )


# ══════════════════════════════════════════════════════════════
# Payment for Extra Traffic: Card
# ══════════════════════════════════════════════════════════════

@router.callback_query(ExtraDataStates.choosing_payment, F.data == "extra_pay:card")
async def pay_extra_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    price = data.get("price", 0)
    gb = data.get("extra_gb", 0)
    username = data.get("username", "")

    async with AsyncSessionLocal() as session:
        card_number = await get_setting(session, "BANK_CARD", "6063731268895845")
        bank_name = await get_setting(session, "BANK_NAME", "مهر ایران")

    await state.set_state(ExtraDataStates.awaiting_receipt)

    await callback.message.edit_text(
        f"💳 <b>پرداخت کارت به کارت جهت افزایش حجم</b>\n\n"
        f"🔑 سرویس هدف: <code>{username}</code>\n"
        f"➕ حجم درخواستی: <b>{gb} گیگابایت</b>\n\n"
        f"💰 مبلغ قابل پرداخت (تومان):\n<code>{price}</code>\n"
        f"<i>(معادل {price:,} تومان)</i>\n\n"
        f"🏦 بانک: <b>{bank_name}</b>\n"
        f"💳 شماره کارت بانکی:\n<code>{card_number}</code>\n\n"
        f"👆 <i>(برای کپی کردن کافیست روی مبلغ یا شماره کارت لمس کنید)</i>\n\n"
        f"لطفاً پس از واریز، <b>تصویر فیش پرداخت</b> را همینجا ارسال فرمایید:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(ExtraDataStates.awaiting_receipt, F.photo)
async def receive_extra_receipt(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    gb = data.get("extra_gb", 0)
    price = data.get("price", 0)
    username = data.get("username", "")
    sub_id = data.get("sub_id")
    file_id = message.photo[-1].file_id

    # CRITICAL: Clear state immediately so user is not trapped!
    await state.clear()

    caption = (
        f"🔔 <b>درخواست افزایش حجم برای {username}</b>\n\n"
        f"👤 کاربر: @{message.from_user.username or 'بدون username'} "
        f"(ID: <code>{message.from_user.id}</code>)\n"
        f"➕ حجم: <b>{gb} گیگابایت</b>\n"
        f"💰 مبلغ: <b>{price:,} تومان</b>"
    )

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ تایید و اعمال حجم",
                    callback_data=f"admin_extra_ok:{message.from_user.id}:{sub_id}:{gb}",
                ),
                types.InlineKeyboardButton(
                    text="❌ رد درخواست",
                    callback_data=f"admin_extra_no:{message.from_user.id}",
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
            await save_admin_receipt_messages(session, f"extra:{sub_id}:{gb}", sent_admin_msgs)

    await state.clear()
    await message.answer(
        "⏳ <b>فیش پرداخت دریافت شد.</b>\n\n"
        "پس از بررسی و تایید مدیریت، حجم به سرویس شما اضافه خواهد شد.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_extra_ok:"))
async def admin_confirm_extra(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    sub_id = int(parts[2])
    gb = int(parts[3])

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

    extra_bytes = gb * (1024**3)
    try:
        await panel.add_user_traffic(username, extra_bytes)
        async with AsyncSessionLocal() as session:
            await update_subscription_traffic(session, sub_id, extra_bytes)
            base_caption = callback.message.caption or "درخواست حجم اضافه"
            confirm_text = f"{base_caption}\n\n✅ <b>تایید و {gb} گیگابایت حجم اعمال شد.</b>"
            await update_all_admin_receipt_messages(
                callback.bot,
                session,
                f"extra:{sub_id}:{gb}",
                confirm_text,
                callback.from_user,
            )
    except Exception as exc:
        logger.error(f"Error applying extra traffic in panel: {exc}")

    await callback.answer("✅ حجم اضافه اعمال شد و پیام برای تمام ادمین‌ها بروزرسانی گردید.")

    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 <b>فیش پرداخت حجم اضافه شما تایید شد!</b>\n\n"
                f"🔑 سرویس: <code>{username}</code>\n"
                f"➕ مقدار <b>{gb} گیگابایت</b> ترافیک مازاد به سرویس شما اضافه گردید. ✅"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_extra_no:"))
async def admin_reject_extra(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    sub_id = int(parts[2]) if len(parts) > 2 else 0
    gb = int(parts[3]) if len(parts) > 3 else 0

    base_caption = callback.message.caption or "درخواست حجم اضافه"
    reject_text = f"{base_caption}\n\n❌ <b>درخواست رد شد.</b>"

    async with AsyncSessionLocal() as session:
        await update_all_admin_receipt_messages(
            callback.bot,
            session,
            f"extra:{sub_id}:{gb}",
            reject_text,
            callback.from_user,
        )

    await callback.answer("❌ درخواست رد شد.")

    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text="❌ فیش پرداخت حجم اضافه شما تایید نشد. در صورت مغایرت با پشتیبانی تماس بگیرید.",
        )
    except Exception:
        pass


@router.callback_query(F.data == "extra_cancel")
async def cancel_extra(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("❌ عملیات خرید حجم اضافه لغو شد.")
