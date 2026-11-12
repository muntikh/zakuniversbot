from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.db.crud import get_order, get_plan
from bot.db.database import AsyncSessionLocal
from bot.keyboards.user_kb import cancel_kb

router = Router(name="tracking")


class TrackStates(StatesGroup):
    waiting_order_id = State()


@router.message(F.text.in_({"🔍 پیگیری سفارش", "🔍 پیگیری اطلاعات", "پیگیری سفارش", "پیگیری اطلاعات"}))
@router.callback_query(F.data == "tracking:start")
async def start_tracking(update: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TrackStates.waiting_order_id)
    text = (
        "🔍 <b>پیگیری وضعیت سفارش</b>\n\n"
        "لطفاً <b>کد سفارش</b> خود را ارسال فرمایید (مانند: <code>ORD-01124</code>):\n\n"
        "<i>(برای انصراف /cancel را ارسال کنید)</i>"
    )
    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb())
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=cancel_kb())


@router.message(TrackStates.waiting_order_id, F.text)
async def process_tracking_id(message: types.Message, state: FSMContext) -> None:
    order_id = message.text.strip().upper()

    async with AsyncSessionLocal() as session:
        order = await get_order(session, order_id)
        if not order:
            await message.answer(
                f"❌ سفارشی با کد <code>{order_id}</code> یافت نشد.\n"
                "لطفاً کد سفارش را مجدداً بررسی و ارسال کنید:",
                parse_mode="HTML",
            )
            return

        plan = await get_plan(session, order.plan_id)

    await state.clear()

    status_translations = {
        "PENDING": "⏳ در انتظار انتخاب روش پرداخت",
        "AWAITING_RECEIPT": "💳 در انتظار ارسال فیش بانکی",
        "RECEIPT_SENT": "🔍 فیش ارسال‌شده — در حال بررسی توسط ادمین",
        "CONFIRMED": "✅ تایید شده",
        "PROVISIONING": "⚙️ در حال ساخت اکانت در سرور",
        "DELIVERED": "🚀 تحویل داده شده به کاربر",
        "REJECTED": "❌ فیش رد شده",
        "EXPIRED": "⏱ منقضی شده",
        "PAID_PENDING_PROVISION": "💰 تایید شده (محفوظ در کیف پول یا صف ساخت)",
    }
    status_str = status_translations.get(str(order.status), str(order.status))

    created_str = order.created_at.strftime("%Y/%m/%d — %H:%M") if order.created_at else "نامشخص"
    plan_desc = f"{plan.data_gb:.0f} گیگ ({plan.duration_days} روز)" if plan else "پلن اختصاصی"

    text = (
        f"📋 <b>نتیجه پیگیری سفارش {order.id}:</b>\n\n"
        f"▫️ 📊 وضعیت سفارش: <b>{status_str}</b>\n"
        f"▫️ 📦 مشخصات پلن: <b>{plan_desc}</b>\n"
        f"▫️ 🔑 شناسه کانفیگ: <code>{order.custom_config_name or 'ثبت نشده'}</code>\n"
        f"▫️ 💰 مبلغ سفارش: <b>{order.amount_toman:,} تومان</b>\n"
        f"▫️ 📅 زمان ثبت: <b>{created_str}</b>\n\n"
        "در صورت وجود هرگونه مغایرت با بخش «📞 پشتیبانی» در ارتباط باشید."
    )

    await message.answer(text, parse_mode="HTML")
