from __future__ import annotations

from datetime import datetime

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from loguru import logger

from bot.config import is_admin_user, settings
from bot.db.crud import (
    atomic_confirm_deposit,
    create_deposit_transaction,
    get_or_create_user,
    get_setting,
    get_transaction,
    get_user,
    get_user_stats,
    get_user_transactions,
    reject_deposit,
)
from bot.db.database import AsyncSessionLocal
from bot.db.models import TransactionStatus, TransactionType
from bot.keyboards.user_kb import (
    account_kb,
    admin_deposit_kb,
    back_to_account_kb,
    cancel_kb,
    deposit_amounts_kb,
)
from bot.services.admin_sync import (
    save_admin_receipt_messages,
    update_all_admin_receipt_messages,
)
from bot.states.fsm import WalletStates

router = Router(name="account")


# ══════════════════════════════════════════════════════════════
# User Account Profile Card
# ══════════════════════════════════════════════════════════════

async def build_account_text(user, stats: dict) -> str:
    created_str = user.created_at.strftime("%Y/%m/%d") if user.created_at else "نامشخص"
    balance_formatted = f"{user.balance_toman:,}"

    return (
        "👤 <b>حساب کاربری شما</b>\n\n"
        f"🆔 شناسه عددی: <code>{user.telegram_id}</code>\n"
        f"👤 نام: <b>{user.full_name}</b>\n"
        f"💰 موجودی کیف پول: <b>{balance_formatted} تومان</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 سرویس‌های ثبت‌شده: <b>{stats['active_subs']} عدد</b>\n"
        f"🛒 سفارش‌های تحویل‌شده: <b>{stats['successful_orders']} عدد</b>\n"
        f"👥 زیرمجموعه‌های شما: <b>{stats['referrals']} نفر</b>\n"
        f"📅 تاریخ پیوستن: <b>{created_str}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "برای افزایش موجودی یا مشاهده گردش حساب از دکمه‌های زیر استفاده کنید:"
    )


@router.message(F.text.in_({"💰 اعتبار من", "🖥️ حساب کاربری", "اعتبار من", "حساب کاربری", "اعتبار", "کیف پول"}))
async def show_account(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        stats = await get_user_stats(session, user.telegram_id)

    text = await build_account_text(user, stats)
    await message.answer(text, parse_mode="HTML", reply_markup=account_kb())


@router.callback_query(F.data == "wallet:back_to_account")
async def back_to_account(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        user = await get_user(session, callback.from_user.id)
        stats = await get_user_stats(session, callback.from_user.id)

    text = await build_account_text(user, stats)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=account_kb())


@router.callback_query(F.data == "wallet:close")
async def close_account(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.delete()


# ══════════════════════════════════════════════════════════════
# Wallet Deposit Flow
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "wallet:deposit")
async def start_deposit(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WalletStates.choosing_amount)
    await callback.message.edit_text(
        "💰 <b>افزایش موجودی کیف پول</b>\n\n"
        "لطفاً مبلغ مورد نظر برای شارژ حساب را انتخاب کنید:\n"
        "<i>(موجودی کیف پول برای خریدهای بعدی بلافاصله قابل استفاده است)</i>",
        parse_mode="HTML",
        reply_markup=deposit_amounts_kb(),
    )


@router.callback_query(WalletStates.choosing_amount, F.data.startswith("deposit_amt:"))
async def process_deposit_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    choice = callback.data.split(":")[1]

    if choice == "custom":
        await state.set_state(WalletStates.entering_custom_amount)
        await callback.message.edit_text(
            "✏️ <b>ورود مبلغ دلخواه</b>\n\n"
            "لطفاً مبلغ مورد نظر را به <b>تومان</b> ارسال کنید:\n"
            "<i>(حداقل مبلغ: ۱۰,۰۰۰ تومان)</i>",
            parse_mode="HTML",
            reply_markup=back_to_account_kb(),
        )
        return

    amount = int(choice)
    await show_deposit_invoice(callback.message, state, amount)


@router.message(WalletStates.entering_custom_amount)
async def process_custom_amount(message: types.Message, state: FSMContext) -> None:
    text = message.text.strip().replace(",", "").replace("،", "")
    if not text.isdigit():
        await message.answer("❌ لطفاً مبلغ را فقط به صورت عدد انگلیسی وارد کنید (مثال: 150000).")
        return

    amount = int(text)
    if amount < 10000:
        await message.answer("❌ حداقل مبلغ شارژ ۱۰,۰۰۰ تومان است. لطفاً مبلغ بیشتری وارد کنید:")
        return
    if amount > 50000000:
        await message.answer("❌ سقف هر تراکنش ۵۰,۰۰۰,۰۰۰ تومان است.")
        return

    await show_deposit_invoice(message, state, amount)


async def show_deposit_invoice(target_message: types.Message, state: FSMContext, amount: int) -> None:
    async with AsyncSessionLocal() as session:
        card_number = await get_setting(session, "BANK_CARD", "6063731268895845")
        bank_name = await get_setting(session, "BANK_NAME", "مهر ایران")

    await state.update_data(deposit_amount=amount)
    await state.set_state(WalletStates.awaiting_deposit_receipt)

    invoice_text = (
        f"💳 <b>اطلاعات پرداخت جهت شارژ کیف پول</b>\n\n"
        f"💰 مبلغ قابل پرداخت (تومان):\n<code>{amount}</code>\n"
        f"<i>(معادل {amount:,} تومان)</i>\n\n"
        f"💳 شماره کارت بانکی:\n<code>{card_number}</code>\n"
        f"🏦 بانک: <b>{bank_name}</b>\n\n"
        f"👆 <i>(برای کپی کردن روی مبلغ یا شماره کارت لمس کنید)</i>\n\n"
        f"📸 پس از واریز، <b>تصویر فیش بانکی</b> را همینجا ارسال نمایید:"
    )

    if hasattr(target_message, "edit_text"):
        await target_message.edit_text(invoice_text, parse_mode="HTML", reply_markup=cancel_kb())
    else:
        await target_message.answer(invoice_text, parse_mode="HTML", reply_markup=cancel_kb())


# ══════════════════════════════════════════════════════════════
# Receive Deposit Receipt
# ══════════════════════════════════════════════════════════════

@router.message(WalletStates.awaiting_deposit_receipt, F.photo)
async def receive_deposit_receipt(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = data.get("deposit_amount", 0)
    file_id = message.photo[-1].file_id

    async with AsyncSessionLocal() as session:
        txn = await create_deposit_transaction(
            session,
            user_id=message.from_user.id,
            amount_toman=amount,
            receipt_file_id=file_id,
        )

    await state.clear()

    # Admin notification text
    admin_caption = (
        f"💰 <b>درخواست شارژ کیف پول {txn.id}</b>\n\n"
        f"👤 کاربر: @{message.from_user.username or 'بدون username'} "
        f"(ID: <code>{message.from_user.id}</code>)\n"
        f"💵 مبلغ: <b>{amount:,} تومان</b>\n"
        f"📅 زمان: {datetime.now().strftime('%Y/%m/%d — %H:%M')}"
    )

    bot = message.bot
    sent_admin_msgs = []
    for admin_id in settings.owner_ids:
        try:
            m = await bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=admin_caption,
                parse_mode="HTML",
                reply_markup=admin_deposit_kb(txn.id),
            )
            sent_admin_msgs.append(m)
        except Exception as exc:
            logger.warning(f"Could not notify admin {admin_id} for deposit: {exc}")

    if sent_admin_msgs:
        async with AsyncSessionLocal() as session:
            await save_admin_receipt_messages(session, f"deposit:{txn.id}", sent_admin_msgs)

    await message.answer(
        f"⏳ <b>فیش واریز شما با شناسه <code>{txn.id}</code> دریافت شد!</b>\n\n"
        "درخواست شارژ شما برای مدیریت ارسال گردید.\n"
        "به محض تایید، موجودی کیف پول شما افزایش یافته و به شما اطلاع داده می‌شود.",
        parse_mode="HTML",
    )


@router.message(WalletStates.awaiting_deposit_receipt, ~F.photo)
async def wrong_deposit_file(message: types.Message) -> None:
    await message.answer("❌ لطفاً فقط <b>عکس فیش واریزی</b> را ارسال کنید.")


# ══════════════════════════════════════════════════════════════
# Admin Deposit Approval / Rejection
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("admin_dep_confirm:"))
async def admin_confirm_deposit(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ شما دسترسی به این بخش ندارید.", show_alert=True)
        return

    txn_id = callback.data.split(":")[1]
    admin_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        new_balance = await atomic_confirm_deposit(session, txn_id, admin_id)
        txn = await get_transaction(session, txn_id)

        if new_balance is None:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.answer("⚠️ این درخواست قبلاً توسط ادمین دیگری تعیین وضعیت شده است.", show_alert=True)
            return

        base_caption = callback.message.caption or f"درخواست شارژ {txn_id}"
        confirm_text = (
            f"{base_caption}\n\n"
            f"✅ <b>شارژ تایید شد!</b>\n"
            f"💰 مبلغ {txn.amount_toman:,} تومان اضافه شد (موجودی جدید: {new_balance:,} ت)."
        )
        await update_all_admin_receipt_messages(
            callback.bot,
            session,
            f"deposit:{txn_id}",
            confirm_text,
            callback.from_user,
        )

    await callback.answer("✅ موجودی کاربر شارژ شد و پیام برای تمام ادمین‌ها بروزرسانی گردید.")

    try:
        await callback.bot.send_message(
            chat_id=txn.user_id,
            text=(
                "🎉 <b>کیف پول شما با موفقیت شارژ شد!</b>\n\n"
                f"💵 مبلغ واریزی: <b>{txn.amount_toman:,} تومان</b>\n"
                f"💰 موجودی فعلی کیف پول: <b>{new_balance:,} تومان</b>\n"
                f"📌 شناسه تراکنش: <code>{txn.id}</code>\n\n"
                "اکنون می‌توانید از موجودی خود برای خرید سرویس‌ها استفاده کنید."
            ),
            parse_mode="HTML",
            reply_markup=account_kb(),
        )
    except Exception as exc:
        logger.warning(f"Could not notify user {txn.user_id} of deposit confirmation: {exc}")


@router.callback_query(F.data.startswith("admin_dep_reject:"))
async def admin_reject_deposit(callback: types.CallbackQuery) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ شما دسترسی به این بخش ندارید.", show_alert=True)
        return

    txn_id = callback.data.split(":")[1]
    admin_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        ok = await reject_deposit(session, txn_id, admin_id)
        txn = await get_transaction(session, txn_id)

        if not ok:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.answer("⚠️ این درخواست قبلاً تعیین وضعیت شده است.", show_alert=True)
            return

        base_caption = callback.message.caption or f"درخواست شارژ {txn_id}"
        reject_text = (
            f"{base_caption}\n\n"
            f"❌ <b>درخواست شارژ رد شد!</b>"
        )
        await update_all_admin_receipt_messages(
            callback.bot,
            session,
            f"deposit:{txn_id}",
            reject_text,
            callback.from_user,
        )

    await callback.answer("❌ درخواست رد شد و برای تمام ادمین‌ها بروزرسانی گردید.")

    await callback.answer("❌ درخواست شارژ رد شد.")
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>رد شد</b>",
        parse_mode="HTML",
    )

    try:
        await callback.bot.send_message(
            chat_id=txn.user_id,
            text=(
                "❌ <b>فیش شارژ حساب تایید نشد</b>\n\n"
                f"📌 شناسه تراکنش: <code>{txn.id}</code>\n"
                f"مبلغ: {txn.amount_toman:,} تومان\n\n"
                "لطفاً فیش معتبر ارسال کنید یا با پشتیبانی تماس بگیرید."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# Transaction & Activity History
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "wallet:history")
async def show_transaction_history(callback: types.CallbackQuery) -> None:
    async with AsyncSessionLocal() as session:
        txns = await get_user_transactions(session, callback.from_user.id, limit=10)

    if not txns:
        await callback.message.edit_text(
            "📜 <b>تاریخچه تراکنش‌های شما</b>\n\n"
            "هنوز هیچ تراکنشی برای حساب شما ثبت نشده است.",
            parse_mode="HTML",
            reply_markup=back_to_account_kb(),
        )
        return

    history_lines = ["📜 <b>آخرین فعالیت‌ها و گردش حساب:</b>\n"]
    for t in txns:
        created_str = t.created_at.strftime("%Y/%m/%d %H:%M") if t.created_at else ""
        if t.status == TransactionStatus.SUCCESS:
            sign = "🟢 +" if t.amount_toman > 0 else "🔴 "
            status_text = "موفق"
        elif t.status == TransactionStatus.PENDING:
            sign = "⏳ "
            status_text = "در انتظار تایید"
        else:
            sign = "❌ "
            status_text = "رد شده"

        history_lines.append(
            f"{sign}<b>{abs(t.amount_toman):,} تومان</b> | {t.description}\n"
            f"   وضعیت: {status_text} | زمان: {created_str}\n"
            f"   کد رهگیری: <code>{t.id}</code>"
        )
        history_lines.append("─────────────────────")

    text = "\n".join(history_lines)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_account_kb())


# ══════════════════════════════════════════════════════════════
# Referral System View
# ══════════════════════════════════════════════════════════════

@router.message(F.text.in_({"👥 معرفی به دوستان", "معرفی به دوستان", "دعوت دوستان"}))
@router.callback_query(F.data == "wallet:referral")
async def show_referral(update: types.Message | types.CallbackQuery) -> None:
    user_id = update.from_user.id
    async with AsyncSessionLocal() as session:
        user = await get_user(session, user_id)
        stats = await get_user_stats(session, user_id)

    bot_user = await update.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref_{user.referral_code}"

    ref_text = (
        "👥 <b>سیستم کسب درآمد و زیرمجموعه‌گیری</b>\n\n"
        "با معرفی ربات به دوستان خود، از هر خرید آن‌ها هدیه دریافت کنید! 🎁\n\n"
        f"🔗 <b>لینک اختصاصی دعوت شما:</b>\n"
        f"<code>{ref_link}</code>\n"
        "<i>(برای کپی کردن روی لینک لمس کنید)</i>\n\n"
        f"👥 تعداد دعوت‌های موفق: <b>{stats['referrals']} نفر</b>\n\n"
        "با به اشتراک‌گذاری این لینک با دوستانتان، به ازای خرید هر اشتراک، موجودی کیف پول شما شارژ خواهد شد."
    )
    if isinstance(update, types.CallbackQuery):
        await update.message.edit_text(ref_text, parse_mode="HTML", reply_markup=back_to_account_kb())
    else:
        await update.answer(ref_text, parse_mode="HTML", reply_markup=back_to_account_kb())
