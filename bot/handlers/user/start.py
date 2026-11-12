from __future__ import annotations

from aiogram import F, Router, types
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy import select, update

from bot.config import is_admin_user, settings
from bot.db.crud import get_or_create_user
from bot.db.database import AsyncSessionLocal
from bot.db.models import Transaction, TransactionStatus, TransactionType, User
from bot.keyboards.user_kb import main_menu_inline_kb, main_menu_kb
from bot.services.pasarguard import panel

router = Router(name="start")

WELCOME_TEXT = (
    "👋 سلام <b>{name}</b> عزیز!\n\n"
    "به ربات <b>Zak Univers</b> خوش آمدید 🌐\n\n"
    "از منوی زیر می‌توانید سرویس تهیه کنید، اشتراک‌های خود را مدیریت کنید یا با پشتیبانی ارتباط برقرار نمایید."
)


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    is_admin = is_admin_user(user_id)

    # Handle referral
    referral_code = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        referral_code = args[1].replace("ref_", "").strip()

    async with AsyncSessionLocal() as session:
        # Check if user already exists
        existing_user = await session.get(User, user_id)
        is_new_user = existing_user is None

        ref_txn_id = f"REF_{user_id}"
        already_rewarded = await session.get(Transaction, ref_txn_id) is not None

        # Cross check with panel: if user already exists on PasarGuard, they are not a new user
        if is_new_user and not already_rewarded:
            try:
                panel_users = await panel.get_all_users()
                uid_str = str(user_id)
                for pu in panel_users:
                    if str(pu.get("telegram_id", "")) == uid_str or f"user:{uid_str}" in pu.get("note", ""):
                        is_new_user = False
                        break
            except Exception:
                pass

        user = await get_or_create_user(
            session,
            telegram_id=user_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

        # Apply 2,000 Tomans referral bonus ONLY if strictly new user, never rewarded, and has no prior referrer
        if is_new_user and referral_code and not already_rewarded and not user.referred_by:
            res = await session.execute(
                select(User).where(User.referral_code == referral_code)
            )
            referrer = res.scalar_one_or_none()
            if referrer and referrer.telegram_id != user_id:
                user.referred_by = referrer.telegram_id
                referrer.balance_toman += 2000

                txn = Transaction(
                    id=ref_txn_id,
                    user_id=referrer.telegram_id,
                    amount_toman=2000,
                    balance_after=referrer.balance_toman,
                    transaction_type=TransactionType.DEPOSIT,
                    status=TransactionStatus.SUCCESS,
                    description=f"پاداش دعوت از کاربر @{message.from_user.username or user_id}",
                )
                session.add(txn)
                await session.commit()

                try:
                    await message.bot.send_message(
                        chat_id=referrer.telegram_id,
                        text=(
                            "🎉 <b>پاداش دعوت کاربر جدید!</b>\n\n"
                            f"کاربر @{message.from_user.username or 'جدید'} با لینک اختصاصی شما به ربات پیوست.\n"
                            "مبلغ <b>۲,۰۰۰ تومان</b> پاداش به کیف پول شما واریز گردید! 🎁\n\n"
                            f"💰 <b>موجودی فعلی شما: {referrer.balance_toman:,} تومان</b>"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning(f"Could not notify referrer {referrer.telegram_id}: {exc}")

    try:
        # 1. Set persistent keyboard under chat input
        await message.answer(
            WELCOME_TEXT.format(name=message.from_user.first_name or "کاربر"),
            parse_mode="HTML",
            reply_markup=main_menu_kb(is_admin=is_admin, user_id=user_id),
        )

        # 2. Show rich colorful inline menu inside chat
        await message.answer(
            "⚡️ <b>پنل دسترسی سریع Zak Univers:</b>\n"
            "یکی از گزینه‌های زیر را انتخاب نمایید:",
            parse_mode="HTML",
            reply_markup=main_menu_inline_kb(is_admin=is_admin, user_id=user_id),
        )
    except TelegramForbiddenError:
        logger.info(f"User {user_id} blocked the bot on /start")
        try:
            async with AsyncSessionLocal() as s:
                await s.execute(update(User).where(User.telegram_id == user_id).values(is_blocked=True))
                await s.commit()
        except Exception:
            pass
    except Exception as exc:
        logger.warning(f"Failed to send start welcome to {user_id}: {exc}")


@router.message(Command("menu"))
@router.message(F.text.in_({"منو", "منوی اصلی", "🔙 منوی اصلی", "بازگشت به منوی اصلی"}))
async def cmd_menu(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    is_admin = is_admin_user(user_id)
    await message.answer(
        WELCOME_TEXT.format(name=message.from_user.first_name or "کاربر"),
        parse_mode="HTML",
        reply_markup=main_menu_kb(is_admin=is_admin, user_id=user_id),
    )
    await message.answer(
        "⚡️ <b>پنل دسترسی سریع Zak Univers:</b>\n"
        "یکی از گزینه‌های زیر را انتخاب نمایید:",
        parse_mode="HTML",
        reply_markup=main_menu_inline_kb(is_admin=is_admin, user_id=user_id),
    )


@router.callback_query(F.data == "menu:main")
async def show_main_inline_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    is_admin = is_admin_user(user_id)
    await callback.message.edit_text(
        "به منوی اصلی بازگشتید! 🚀\n\n"
        "جهت استفاده از خدمات، یکی از گزینه‌های زیر را انتخاب فرمایید:",
        parse_mode="HTML",
        reply_markup=main_menu_inline_kb(is_admin=is_admin, user_id=user_id),
    )
    if is_admin:
        # Guarantee that the admin's bottom keyboard is refreshed with the admin button
        await callback.bot.send_message(
            chat_id=user_id,
            text="👑 <b>دسترسی مدیریت Zak Univers فعال است.</b>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(is_admin=True, user_id=user_id),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:menu")
async def open_admin_via_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    from bot.handlers.admin.panel import admin_dashboard
    await admin_dashboard(callback, state)
