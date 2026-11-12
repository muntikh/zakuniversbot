from __future__ import annotations

from aiogram import F, Router, types

router = Router(name="tariffs")


@router.message(F.text == "📣 تعرفه ها")
async def show_tariffs(message: types.Message) -> None:
    text = (
        "📣 <b>تعرفه‌ها و قیمت‌های اشتراک Zak Univers</b>\n\n"
        "💡 تمامی قیمت‌ها به صورت شفاف، عادلانه و بر مبنای <b>هر گیگابایت ۴,۰۰۰ تومان</b> محاسبه گردیده‌اند:\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>اشتراک‌های ۱ ماهه (۳۰ روزه):</b>\n"
        "▫️ ۱۰ گیگابایت: <b>۴۰,۰۰۰ تومان</b>\n"
        "▫️ ۲۰ گیگابایت: <b>۸۰,۰۰۰ تومان</b>\n"
        "▫️ ۳۰ گیگابایت: <b>۱۲۰,۰۰۰ تومان</b>\n"
        "▫️ ۵۰ گیگابایت: <b>۲۰۰,۰۰۰ تومان</b>\n"
        "▫️ ۱۰۰ گیگابایت: <b>۴۰۰,۰۰۰ تومان</b>\n"
        "▫️ نامحدود ۱ ماهه: <b>۳۵۰,۰۰۰ تومان</b>\n\n"
        "🚀 <b>اشتراک‌های ۳ ماهه (۹۰ روزه):</b>\n"
        "▫️ ۳۰ گیگابایت: <b>۱۲۰,۰۰۰ تومان</b>\n"
        "▫️ ۵۰ گیگابایت: <b>۲۰۰,۰۰۰ تومان</b>\n"
        "▫️ ۱۰۰ گیگابایت: <b>۴۰۰,۰۰۰ تومان</b>\n"
        "▫️ ۲۰۰ گیگابایت: <b>۸۰۰,۰۰۰ تومان</b>\n\n"
        "⭐️ <b>اشتراک‌های ۶ ماهه و ۱ ساله:</b>\n"
        "▫️ طبق تعرفه پایه ۴,۰۰۰ ت/گیگ با ترافیک‌های متنوع در دسترس است.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>امکانات ویژه:</b>\n"
        "🔹 اتصال پایدار در اینترنت ملی و بین‌الملل\n"
        "🔹 آی‌پی اختصاصی و ثابت مناسب ترید و گیم\n"
        "🔹 بدون قطعی و پشتیبانی ۲۴ ساعته"
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🛍️ خرید فوری سرویس", callback_data="buy:start_quick")]
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "buy:start_quick")
async def quick_buy(callback: types.CallbackQuery) -> None:
    from bot.keyboards.user_kb import mode_kb
    await callback.message.answer(
        "🛍️ <b>خرید سرویس Zak Univers</b>\n\n"
        "🌐 لطفاً وضعیت شبکه مورد نظر خود را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=mode_kb(),
    )
    await callback.answer()
