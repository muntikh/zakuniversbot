from __future__ import annotations

from aiogram import F, Router, types

router = Router(name="tariffs")


@router.message(F.text == "📣 تعرفه ها")
async def show_tariffs(message: types.Message) -> None:
    text = (
        "📣 <b>تعرفه‌ها و پلن‌های اختصاصی Zak Univers</b>\n\n"
        "💡 کلیه پلن‌ها با سرورهای قدرتمند نت ملی، آی‌پی ثابت و بدون قطعی ارائه می‌شوند:\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>پلن‌های اختصاصی اندروید (Android):</b>\n"
        "▫️ ۱ ماه | ۵۰ گیگ: <b>۲۵۹,۰۰۰ تومان</b>\n"
        "▫️ ۲ ماه | ۹۰ گیگ: <b>۳۸۵,۰۰۰ تومان</b>\n"
        "▫️ ۳ ماه | ۱۵۰ گیگ: <b>۴۲۰,۰۰۰ تومان</b>\n\n"
        "🍏 <b>پلن‌های اختصاصی آیفون (iOS):</b>\n"
        "▫️ ۱ ماه | ۵۰ گیگ: <b>۳۱۹,۰۰۰ تومان</b>\n"
        "▫️ ۲ ماه | ۹۰ گیگ: <b>۴۳۵,۰۰۰ تومان</b>\n"
        "▫️ ۳ ماه | ۱۵۰ گیگ: <b>۵۰۰,۰۰۰ تومان</b>\n"
        "▫️ نامحدود | ۶ ماه (۳ کاربر): <b>۱,۵۰۰,۰۰۰ تومان</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>ویژگی‌های ویژه:</b>\n"
        "🔹 اتصال پایدار در شبکه ملی و اینترنت بین‌الملل\n"
        "🔹 آی‌پی اختصاصی و مناسب بازی و ترید\n"
        "🔹 تحویل فوری و اتوماتیک در عرض ۲ ثانیه\n"
        "🔹 پشتیبانی ۲۴ ساعته"
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🛍️ خرید فوری سرویس", callback_data="buy:start_quick")]
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "buy:start_quick")
async def quick_buy(callback: types.CallbackQuery) -> None:
    from bot.keyboards.user_kb import single_mode_kb
    await callback.message.answer(
        "💎 لوکیشن سرویست رو انتخاب کن :",
        parse_mode="HTML",
        reply_markup=single_mode_kb(),
    )
    await callback.answer()
