from __future__ import annotations

import random
from datetime import datetime

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from loguru import logger

from bot.config import is_admin_user, settings
from bot.keyboards.user_kb import cancel_kb
from bot.states.fsm import AdminSupportReplyStates, SupportStates

router = Router(name="support")


def support_subjects_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📶 مشکل در اتصال یا کانفیگ", callback_data="supp_sub:اتصال"),
                types.InlineKeyboardButton(text="💳 سوالات مالی و پرداخت", callback_data="supp_sub:مالی"),
            ],
            [
                types.InlineKeyboardButton(text="⚡️ گزارش کندی یا افت سرعت", callback_data="supp_sub:سرعت"),
                types.InlineKeyboardButton(text="❓ مشاوره قبل از خرید", callback_data="supp_sub:مشاوره"),
            ],
            [
                types.InlineKeyboardButton(text="✏️ سایر موارد (موضوع دلخواه)", callback_data="supp_sub:custom"),
            ],
            [
                types.InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="menu:main"),
            ],
        ]
    )


@router.message(F.text.in_({"👨‍💻 تماس با پشتیبانی", "📞 پشتیبانی", "تماس با پشتیبانی", "پشتیبانی"}))
@router.callback_query(F.data == "support:start")
async def start_support(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SupportStates.choosing_subject)

    text = (
        "🎫 <b>سامانه ثبت تیکت پشتیبانی Zak Univers</b>\n\n"
        "لطفاً ابتدا <b>موضوع تیکت</b> خود را از گزینه‌های زیر انتخاب نمایید یا روی «سایر موارد» بزنید:"
    )

    markup = support_subjects_kb()

    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(SupportStates.choosing_subject, F.data.startswith("supp_sub:"))
async def on_subject_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    choice = callback.data.split(":")[1]

    titles_map = {
        "اتصال": "📶 مشکل در اتصال یا کانفیگ",
        "مالی": "💳 سوالات مالی و پرداخت",
        "سرعت": "⚡️ گزارش کندی یا افت سرعت",
        "مشاوره": "❓ مشاوره قبل از خرید",
    }

    if choice == "custom":
        await state.set_state(SupportStates.waiting_custom_subject)
        await callback.message.edit_text(
            "✏️ لطفاً <b>موضوع تیکت</b> خود را تایپ و ارسال فرمایید:\n\n"
            "<i>(جهت انصراف می‌توانید /cancel را ارسال کنید)</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
        await callback.answer()
        return

    subject = titles_map.get(choice, choice)
    await state.update_data(subject=subject)
    await state.set_state(SupportStates.writing_message)

    await callback.message.edit_text(
        f"📝 <b>موضوع تیکت:</b> <b>{subject}</b>\n\n"
        "اکنون لطفاً <b>متن، توضیحات، اسکرین‌شات یا پیام صوتی</b> خود را ارسال فرمایید:\n\n"
        "<i>(جهت انصراف می‌توانید /cancel را ارسال کنید)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(SupportStates.waiting_custom_subject, F.text)
async def receive_custom_subject(message: types.Message, state: FSMContext) -> None:
    subject = message.text.strip()
    await state.update_data(subject=subject)
    await state.set_state(SupportStates.writing_message)

    await message.answer(
        f"📝 <b>موضوع تیکت:</b> <b>{subject}</b>\n\n"
        "اکنون لطفاً <b>متن، توضیحات، اسکرین‌شات یا پیام صوتی</b> خود را ارسال فرمایید:\n\n"
        "<i>(جهت انصراف می‌توانید /cancel را ارسال کنید)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(SupportStates.writing_message)
async def receive_support_message(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    subject = data.get("subject", "پشتیبانی عمومی")
    await state.clear()

    ticket_id = f"TCK-{random.randint(10000, 99999)}"
    now_str = datetime.now().strftime("%Y/%m/%d — %H:%M")

    # Log ticket internally (Admin forwarding disabled for now as requested)
    user_id = message.from_user.id
    username = message.from_user.username or "ندارد"
    logger.info(f"Registered Ticket #{ticket_id} from {user_id} (@{username}) with subject: {subject}")

    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="menu:main")]
        ]
    )

    await message.answer(
        f"✅ <b>تیکت پشتیبانی شما با موفقیت ثبت و ارسال شد!</b>\n\n"
        f"📌 کد پیگیری تیکت: <code>#{ticket_id}</code>\n"
        f"▫️ موضوع: <b>{subject}</b>\n"
        f"▫️ زمان ثبت: <b>{now_str}</b>\n\n"
        "تیکت شما با موفقیت در سیستم ثبت گردید و در اسرع وقت توسط پشتیبانی بررسی خواهد شد. 🙏",
        parse_mode="HTML",
        reply_markup=markup,
    )


# ══════════════════════════════════════════════════════════════
# Admin Reply to User Support Ticket (Preserved for future update)
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("supp_reply:"))
async def admin_start_reply(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ دسترسی غیرمجاز.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    ticket_id = parts[2]

    await state.set_state(AdminSupportReplyStates.writing_reply)
    await state.update_data(target_user_id=target_user_id, ticket_id=ticket_id)

    await callback.message.reply(
        f"✍️ <b>در حال پاسخ به تیکت #{ticket_id}</b>\n"
        f"👤 کاربر هدف: <code>{target_user_id}</code>\n\n"
        "لطفاً متن پاسخ را تایپ و ارسال کنید (یا /cancel را جهت لغو بزنید):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminSupportReplyStates.writing_reply, F.text)
async def admin_send_reply(message: types.Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id):
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    ticket_id = data.get("ticket_id")

    await state.clear()

    reply_text = (
        f"📩 <b>پاسخ پشتیبانی Zak Univers به تیکت #{ticket_id}:</b>\n\n"
        f"{message.text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "در صورت نیاز به ارسال پیام مجدد، می‌توانید از دکمه «👨‍💻 تماس با پشتیبانی» استفاده فرمایید."
    )

    try:
        await message.bot.send_message(
            chat_id=target_user_id,
            text=reply_text,
            parse_mode="HTML",
        )
        await message.answer(f"✅ پاسخ با موفقیت به کاربر <code>{target_user_id}</code> تحویل داده شد.", parse_mode="HTML")
    except Exception as exc:
        logger.error(f"Failed to send support reply to {target_user_id}: {exc}")
        await message.answer(f"❌ خطا در ارسال پاسخ به کاربر: <code>{exc}</code>", parse_mode="HTML")
