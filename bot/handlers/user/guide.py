from __future__ import annotations

from aiogram import F, Router, types

router = Router(name="guide")


@router.message(F.text.in_({"💡 آموزش استفاده", "آموزش استفاده", "🔗 راهنمای اتصال", "راهنمای اتصال", "آموزش", "راهنما"}))
@router.callback_query(F.data == "guide:main")
async def show_guide(update: types.Message | types.CallbackQuery) -> None:
    text = (
        "💡 <b>آموزش اتصال سریع به سرویس‌های Zak Univers</b>\n\n"
        "⭐️ <b>نرم‌افزار پیشنهادی رسمی ما: Hiddify (هیدیفای)</b>\n"
        "برنامه هیدیفای سریع‌ترین، مدرن‌ترین و پایدارترین اپلیکیشن فیلترشکن است که از تمامی پروتکل‌ها و اینترنت ملی به خوبی پشتیبانی می‌کند.\n\n"
        "لطفاً سیستم‌عامل دستگاه خود را جهت دریافت لینک دانلود رسمی و آموزش اتصال انتخاب نمایید:"
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🤖 اندروید (Android)", callback_data="guide:android"),
                types.InlineKeyboardButton(text="🍎 آیفون (iOS)", callback_data="guide:ios"),
            ],
            [
                types.InlineKeyboardButton(text="💻 ویندوز (Windows)", callback_data="guide:windows"),
                types.InlineKeyboardButton(text="🍏 مک (macOS)", callback_data="guide:mac"),
            ],
            [
                types.InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="menu:main"),
            ],
        ]
    )
    if isinstance(update, types.CallbackQuery):
        await update.answer()
        await update.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "guide:android")
async def guide_android(callback: types.CallbackQuery) -> None:
    text = (
        "🤖 <b>آموزش اتصال در اندروید با برنامه Hiddify (هیدیفای):</b>\n\n"
        "۱. برنامه <b>Hiddify</b> را از لینک‌های رسمی زیر دانلود و نصب کنید.\n"
        "۲. لینک سابسکریپشن دریافتی از ربات را کپی کنید.\n"
        "۳. وارد برنامه هیدیفای شوید؛ برنامه به طور خودکار لینک کپی‌شده را تشخیص داده و با زدن یک کلیک آن را اضافه می‌کند (یا روی علامت <b>+</b> بالا بزنید و <b>افزودن از کلیپ‌بورد</b> را انتخاب کنید).\n"
        "۴. دکمه بزرگ دایره‌ای وسط را بزنید تا در کمتر از ۲ ثانیه متصل شوید! 🚀"
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📥 دانلود Hiddify از گوگل‌پلی", url="https://play.google.com/store/apps/details?id=app.hiddify.com"),
            ],
            [
                types.InlineKeyboardButton(text="📥 دانلود فایل APK مستقیم از گیت‌هاب", url="https://github.com/hiddify/hiddify-app/releases/latest"),
            ],
            [types.InlineKeyboardButton(text="🔙 بازگشت به راهنما", callback_data="guide:main")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "guide:ios")
async def guide_ios(callback: types.CallbackQuery) -> None:
    text = (
        "🍎 <b>آموزش اتصال در آیفون و آیپد (iOS) با Hiddify:</b>\n\n"
        "۱. برنامه <b>Hiddify</b> را به صورت رایگان از App Store دانلود کنید.\n"
        "۲. لینک سابسکریپشن خود را از بخش «📱 سرویس های من» کپی کنید.\n"
        "۳. برنامه هیدیفای را باز کنید و روی دکمه <b>+</b> یا <b>New Profile</b> بزنید و <b>Add from Clipboard</b> را لمس نمایید.\n"
        "۴. دکمه اتصال را بزنید و دسترسی شبکه VPN را تایید (Allow) کنید."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📥 دانلود Hiddify از اپ استور (iOS)", url="https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532"),
            ],
            [
                types.InlineKeyboardButton(text="📥 دانلود Streisand (جایگزین دوم)", url="https://apps.apple.com/us/app/streisand/id6450534064"),
            ],
            [types.InlineKeyboardButton(text="🔙 بازگشت به راهنما", callback_data="guide:main")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "guide:windows")
async def guide_windows(callback: types.CallbackQuery) -> None:
    text = (
        "💻 <b>آموزش اتصال در ویندوز (Windows) با Hiddify:</b>\n\n"
        "۱. نسخه ویندوز <b>Hiddify</b> را از لینک رسمی گیت‌هاب زیر دانلود و نصب کنید.\n"
        "۲. لینک سابسکریپشن خود را کپی کنید.\n"
        "۳. نرم‌افزار را اجرا کرده و روی علامت <b>+</b> بزنید تا کانفیگ‌ها وارد شوند.\n"
        "۴. دکمه Connect را بزنید."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📥 دانلود Hiddify ویندوز از گیت‌هاب", url="https://github.com/hiddify/hiddify-app/releases/latest"),
            ],
            [types.InlineKeyboardButton(text="🔙 بازگشت به راهنما", callback_data="guide:main")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "guide:mac")
async def guide_mac(callback: types.CallbackQuery) -> None:
    text = (
        "🍏 <b>آموزش اتصال در مک (macOS) با Hiddify:</b>\n\n"
        "۱. نسخه مک <b>Hiddify</b> را دانلود و در پوشه Applications قرار دهید.\n"
        "۲. لینک سابسکریپشن را کپی و در برنامه اضافه کنید.\n"
        "۳. به راحتی و با یک کلیک متصل شوید."
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📥 دانلود Hiddify مک از اپ استور / گیت‌هاب", url="https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532"),
            ],
            [types.InlineKeyboardButton(text="🔙 بازگشت به راهنما", callback_data="guide:main")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
