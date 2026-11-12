from __future__ import annotations

from aiogram import F, Router, types

router = Router(name="faq")


@router.message(F.text.in_({"💡 سوالات متداول", "سوالات متداول", "پرسش های متداول", "سوالات"}))
@router.callback_query(F.data == "faq:main")
async def show_faq(update: types.Message | types.CallbackQuery) -> None:
    text = (
        "💡 <b>پرسش‌های متداول کاربران Zak Univers</b>\n\n"
        "روی هر کدام از پرسش‌های زیر ضربه بزنید تا پاسخ آن را مشاهده کنید:"
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="❓ آیا در زمان نت ملی کار می‌کند؟", callback_data="faq:national")],
            [types.InlineKeyboardButton(text="❓ تفاوت تک‌کاربره و دوکاربره چیست؟", callback_data="faq:users")],
            [types.InlineKeyboardButton(text="❓ چرا پینگ من بالاست یا وصل نمی‌شود؟", callback_data="faq:ping")],
            [types.InlineKeyboardButton(text="❓ چگونه از حجم و زمانم مطلع شوم؟", callback_data="faq:check")],
            [types.InlineKeyboardButton(text="❓ آیا امکان تمدید سرویس وجود دارد؟", callback_data="faq:renew")],
        ]
    )
    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "faq:national")
async def faq_national(callback: types.CallbackQuery) -> None:
    text = (
        "🇮🇷 <b>آیا سرویس در زمان قطعی اینترنت بین‌الملل (نت ملی) کار می‌کند؟</b>\n\n"
        "بله! سرورهای Zak Univers دارای تونل‌های اختصاصی و سرورهای واسط داخلی هستند که حتی در شدیدترین اختلالات و وضعیت سفید/نت ملی نیز امکان اتصال پایدار و دسترسی به اینترنت آزاد را فراهم می‌آورند."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 بازگشت به سوالات", callback_data="faq:main")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "faq:users")
async def faq_users(callback: types.CallbackQuery) -> None:
    text = (
        "👥 <b>تفاوت پلن‌های تک‌کاربره، دوکاربره و نامحدود چیست؟</b>\n\n"
        "▫️ <b>تک‌کاربره:</b> مناسب برای اتصال همزمان ۱ دستگاه گوشی یا لپ‌تاپ.\n"
        "▫️ <b>دوکاربره:</b> امکان اتصال همزمان ۲ دستگاه مجزا با ترافیک مشترک.\n"
        "▫️ <b>کاربر نامحدود:</b> بدون محدودیت در تعداد دستگاه‌های متصل، ایده‌آل برای خانواده و اشتراک با دوستان."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 بازگشت به سوالات", callback_data="faq:main")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "faq:ping")
async def faq_ping(callback: types.CallbackQuery) -> None:
    text = (
        "📶 <b>چرا پینگ بالاست یا متصل نمی‌شود؟</b>\n\n"
        "۱. ابتدا لینک سابسکریپشن را در نرم‌افزار خود Update Sub کنید تا آخرین کانفیگ‌های روز دریافت شوند.\n"
        "۲. در صورت استفاده از همراه اول یا ایرانسل، یک بار حالت پرواز را روشن و خاموش نمایید.\n"
        "۳. تست پینگ واقعی را با باز کردن یک سایت (مثل یوتیوب) بسنجید؛ تست پینگ داخل نرم‌افزارها ممکن است با تاخیر باشد."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 بازگشت به سوالات", callback_data="faq:main")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "faq:check")
async def faq_check(callback: types.CallbackQuery) -> None:
    text = (
        "📊 <b>چگونه از میزان حجم و مهلت اشتراک خود مطلع شوم؟</b>\n\n"
        "کافیست در منوی اصلی ربات روی دکمه <b>«🐍 سرویس ها»</b> بزنید. تمام سرویس‌های شما با نمایش ترافیک مصرفی، حجم باقی‌مانده و روزهای باقی‌مانده به صورت لحظه‌ای قابل مشاهده خواهند بود."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 بازگشت به سوالات", callback_data="faq:main")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "faq:renew")
async def faq_renew(callback: types.CallbackQuery) -> None:
    text = (
        "⚡️ <b>آیا امکان تمدید سرویس بدون تعویض کانفیگ وجود دارد؟</b>\n\n"
        "بله! با زدن دکمه <b>«⚡️ تمدید سرویس»</b>، همان کانفیگ قبلی شما تمدید می‌شود و نیازی به تغییر لینک سابسکریپشن در نرم‌افزار نخواهید داشت."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 بازگشت به سوالات", callback_data="faq:main")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
