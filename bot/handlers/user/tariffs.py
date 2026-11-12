from __future__ import annotations

from aiogram import F, Router, types

router = Router(name="tariffs")


@router.message(F.text == "📣 تعرفه ها")
async def show_tariffs(message: types.Message) -> None:
    text = (
        "📣 <b>تعرفه‌ها و پلن‌های اشتراک Zak Univers</b>\n\n"
        "💡 تمامی پلن‌ها با سرورهای قدرتمند، آی‌پی ثابت و بدون قطعی ارائه می‌شوند:\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>اشتراک‌های ۱ ماهه (۳۰ روزه):</b>\n"
        "▫️ ۵۰ گیگابایت: <b>۲۴۰,۰۰۰ تومان</b>\n"
        "▫️ ۸۰ گیگابایت: <b>۳۸۰,۰۰۰ تومان</b>\n"
        "▫️ ۱۰۰ گیگابایت: <b>۴۸۰,۰۰۰ تومان</b>\n\n"
        "🚀 <b>اشتراک‌های ۲ ماهه (۶۰ روزه):</b>\n"
        "▫️ ۶۰ گیگابایت: <b>۲۹۰,۰۰۰ تومان</b>\n"
        "▫️ ۹۰ گیگابایت: <b>۴۳۰,۰۰۰ تومان</b>\n\n"
        "⭐️ <b>اشتراک‌های ۳ ماهه (۹۰ روزه):</b>\n"
        "▫️ ۷۰ گیگابایت: <b>۳۴۰,۰۰۰ تومان</b>\n"
        "▫️ ۱۰۰ گیگابایت: <b>۴۸۰,۰۰۰ تومان</b>\n\n"
        "🗓 <b>اشتراک‌های ۶ ماهه (۱۸۰ روزه):</b>\n"
        "▫️ ۱۵۰ گیگابایت: <b>۷۲۰,۰۰۰ تومان</b>\n"
        "▫️ ۲۰۰ گیگابایت: <b>۹۶۰,۰۰۰ تومان</b>\n\n"
        "👑 <b>اشتراک‌های ۱ ساله (۳۶۵ روزه) - ویژه:</b>\n"
        "▫️ ۱۵۰ گیگابایت: <b>۶۰۰,۰۰۰ تومان</b>\n"
        "▫️ ۲۵۰ گیگابایت: <b>۱,۰۰۰,۰۰۰ تومان</b>\n"
        "▫️ ۳۵۰ گیگابایت: <b>۱,۴۰۰,۰۰۰ تومان</b>\n"
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
