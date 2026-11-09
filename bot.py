# -*- coding: utf-8 -*-
"""
Beekeeping.Uz 🇺🇿 Telegram Bot
Muallif va Admin: Jamshid Davronov (ID: 2047501151)
Server: PythonAnywhere (Asalarichiliktv)

Xususiyatlari:
1. Guruhlada / (drob) belgisisiz ishlaydi.
2. Guruhda 'salom bot' / 'салом бот' deb yozilsa yoki botga reply qilinsa - o'sha xabarga reply qilib javob qaytaradi.
3. Guruhdagi boshqa o'zaro suhbatlarni e'tiborsiz qoldiradi (kvotani tejaydi).
4. Bot egasi (Jamshid) uchun shaxsiy va guruhlarda to'liq ochiq.
5. Gemini model zaxiralari (fallback) va xushmuomala xatolik matni bilan ta'minlangan.
"""

import os
import re
import logging
import asyncio
from typing import List, Dict

import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==========================================
# SOZLAMALAR (CONFIGURATION)
# ==========================================
BOT_TOKEN = "9209261766:AAEwCxvnB0FFfd8Km0inaEhdDNWiEI1Ycv0"
GEMINI_API_KEY = "AQ.Ab8RN6Lu3jGSvxVGoVR6ua9zV-BwFSeWNGnnqcP12NUf2Cl0mw"
ADMIN_TELEGRAM_ID = 2047501151  # Jamshid Davronov

# Tavsiya etilgan modellar ketma-ketligi (birinchisi ishlamasa, keyingisiga o'tadi)
MODELS_TO_TRY = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash"
]

SYSTEM_INSTRUCTION = (
    "Сиз Beekeeping.Uz 🇺🇿 loyihasining professional va xushmuomala sun'iy intellekt yordamchisisiz. "
    "Asalarichilik, ona ari yetishtirish, asal turlari, asalari kasalliklari (varroa, nozomatoz va boshqalar) "
    "hamda umumiy savollarga o'zbek tilida (kirill va lotin alifbolarida, foydalanuvchi qaysi tilda yozsa shu tilda) "
    "aniq, tushunarli va amaliy maslahatlar bering."
)

WELCOME_MESSAGE = (
    "🐝 Ассалому алайкум! Beekeeping.Uz 🇺🇿 асаларичилик ботига хуш келибсиз!\n\n"
    "Сизга асаларичилик, она ари парвариши, касалликларга қарши кураш ва соҳага оид барча саволлар бўйича ёрдам бера оламан.\n\n"
    "Саволингизни бемалол ёзишингиз мумкин."
)

QUOTA_ERROR_MESSAGE = (
    "🤖 Кечирасиз, ҳозирда Beekeeping.Uz🇺🇿 сўровлар чеклови (quota) вақтинча тўлди. "
    "Илтимос, бир оздан сўнг қайта ёзиб кўринг."
)

# Har bir chat uchun xotira (oxirgi 10 ta xabar)
MEMORY_LIMIT = 10
chat_memory: Dict[int, List[Dict[str, str]]] = {}

# Guruh ruxsatlari ro'yxati (Admin qo'shgan yoki ruxsat berilgan guruhlar)
approved_chats = set()

# Logging sozlash
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Gemini API ni sozlash
genai.configure(api_key=GEMINI_API_KEY)


def call_gemini_with_fallback(prompt: str, history: List[Dict[str, str]]) -> str:
    """Gemini modeliga murojaat qilish va 429/404 da avtomatik zaxira modelga o'tish."""
    full_prompt = SYSTEM_INSTRUCTION + "\n\n"
    for turn in history[-MEMORY_LIMIT:]:
        full_prompt += f"{turn['role']}: {turn['text']}\n"
    full_prompt += f"user: {prompt}\nmodel: "

    last_error = None
    for model_name in MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = e
            logger.warning(f"Model {model_name} xatosi: {e}. Keyingi model tekshirilmoqda...")

    if last_error:
        raise last_error
    return QUOTA_ERROR_MESSAGE


# ==========================================
# /start BUYRUG'I
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    # Shaxsiy chatda /start menyu tugmasini chiqarish
    if chat.type == "private":
        keyboard = ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
        await update.message.reply_text(
            WELCOME_MESSAGE,
            reply_markup=keyboard
        )
    else:
        # Guruhda bo'lsa reply qilib yuboradi
        await update.message.reply_text(
            WELCOME_MESSAGE,
            reply_to_message_id=update.message.message_id
        )


# ==========================================
# ASOSIY XABARLAR ISHLOVCHISI
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id
    user_id = user.id if user else chat_id
    raw_text = message.text.strip()
    is_group = chat.type in ["group", "supergroup"]
    text_lower = raw_text.lower()

    # 1. BOT EGASI (ADMIN) HUQUQLARI
    is_owner = (user_id == ADMIN_TELEGRAM_ID)

    # SHAXSIY CHATDAGI QAT'IY HIMOYA:
    # Bot egasidan (@JamshidjonDavronov) boshqa hech kim shaxsiyda ishlata olmaydi!
    if not is_group and not is_owner:
        access_denied = (
            "🔒 Кириш чекланган!\n\n"
            "Ушбу бот ёпиқ тизим бўлиб, фақат бот эгаси (@JamshidjonDavronov) учун очиқ.\n"
            "Бегона фойдаланувчилар учун кириш ва созламалар бутунлай ёпиқ."
        )
        await message.reply_text(access_denied)
        return

    # GURUHGA BEGONA QO'SHGAN BO'LSA - BOT CHIQIB KETADI
    if is_group and message.new_chat_members:
        if any(m.is_bot or m.id == bot_info.id for m in message.new_chat_members):
            if not is_owner:
                try:
                    await message.reply_text(
                        "🔒 Ушбу бот ёпиқ тизим бўлиб, фақат бот эгаси (@JamshidjonDavronov) учун очиқ. Бегона фойдаланувчилар ботни гуруҳ ва каналларга қўша олмайди."
                    )
                    await context.bot.leave_chat(chat_id)
                except Exception:
                    pass
                return
            else:
                approved_chats.add(chat_id)

    if is_owner and is_group and chat_id not in approved_chats:
        approved_chats.add(chat_id)
        logger.info(f"Bot egasi {user.first_name} guruhga kirdi/yozdi. Guruh tasdiqlandi: {chat.title} ({chat_id})")

    # 2. GURUHDA FILTRLASH (/ DROB KERAK EMAS!)
    # Guruhda faqat:
    # a) bot xabariga reply qilinganda
    # b) "salom bot" / "салом бот" / "bot" deb yozilganda javob beradi
    bot_info = await context.bot.get_me()
    bot_username = (bot_info.username or "").lower()

    is_reply_to_bot = (
        message.reply_to_message is not None and
        message.reply_to_message.from_user is not None and
        (message.reply_to_message.from_user.is_bot or message.reply_to_message.from_user.id == bot_info.id)
    )

    has_trigger = (
        "салом бот" in text_lower or
        "salom bot" in text_lower or
        "ассалому алайкум бот" in text_lower or
        "assalomu alaykum bot" in text_lower or
        text_lower.startswith("бот ") or text_lower.startswith("бот,") or text_lower.startswith("бот:") or
        text_lower.startswith("bot ") or text_lower.startswith("bot,") or text_lower.startswith("bot:") or
        text_lower == "бот" or text_lower == "bot" or
        (bot_username and f"@{bot_username}" in text_lower)
    )

    # Agar guruh bo'lsa va botga qaratilmagan bo'lsa - jim turadi (spam qilmaydi, quota tejaydi)
    if is_group and not (is_reply_to_bot or has_trigger or raw_text.startswith("/")):
        return

    # 3. KIRISH TRIGGERLARINI TOZALASH (Savolning o'zini ajratib olish)
    clean_text = raw_text
    if bot_username:
        clean_text = re.sub(rf"(?i)@{re.escape(bot_username)}", "", clean_text).strip()

    clean_text = re.sub(
        r"(?i)^(ассалому\s*алайкум\s*бот|assalomu\s*alaykum\s*bot|салом\s*бот|salom\s*bot|бот|bot)[,\s:]*",
        "",
        clean_text
    ).strip()

    # Agar foydalanuvchi shunchaki "salom bot" deb yozgan bo'lsa:
    if not clean_text and has_trigger:
        greeting_text = (
            "Ассалому алайкум! Beekeeping.Uz 🇺🇿 асаларичилик боти хизматингизда. "
            "Сизга қандай ёрдам беришим мумкин? Саволингизни бемалол ёзишингиз мумкин."
        )
        await message.reply_text(
            greeting_text,
            reply_to_message_id=message.message_id if is_group else None
        )
        return

    # Context (agar botning avvalgi javobiga reply qilingan bo'lsa)
    prompt_for_ai = clean_text or raw_text
    if is_reply_to_bot and message.reply_to_message and message.reply_to_message.text:
        quoted = message.reply_to_message.text[:250]
        prompt_for_ai = f"[Олдинги жавоб: \"{quoted}\"]\nСавол: {clean_text}"

    # 4. CHAT XOTIRASINI OLISH VA AI DAN JAVOB YARATISH
    thread_id = message.message_thread_id

    if chat_id not in chat_memory:
        chat_memory[chat_id] = []

    history = chat_memory[chat_id]
    chat_memory[chat_id].append({"role": "user", "text": prompt_for_ai})

    # Foydalanuvchiga 'yozmoqda...' (typing) statusini jo'natish
    try:
        if thread_id and is_group:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing", message_thread_id=thread_id)
        else:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass

    try:
        # Loop orqali sync funksiyani asinxron ishlatish
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, call_gemini_with_fallback, prompt_for_ai, history)

        chat_memory[chat_id].append({"role": "model", "text": answer})
        if len(chat_memory[chat_id]) > MEMORY_LIMIT * 2:
            chat_memory[chat_id] = chat_memory[chat_id][-MEMORY_LIMIT * 2:]

        # Guruhda bo'lsa aynan foydalanuvchi xabariga reply qilib jo'natish (Forum / Topics qo'llab-quvvatlanadi!)
        await message.reply_text(
            answer[:4096],
            reply_to_message_id=message.message_id if is_group else None,
            message_thread_id=thread_id if is_group else None,
            allow_sending_without_reply=True
        )
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await message.reply_text(
            QUOTA_ERROR_MESSAGE,
            reply_to_message_id=message.message_id if is_group else None,
            message_thread_id=thread_id if is_group else None,
            allow_sending_without_reply=True
        )


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Begona odam botni guruh yoki kanalga qo'shsa - darhol ogohlantirib chiqib ketadi"""
    if not update.my_chat_member:
        return
    user = update.my_chat_member.from_user
    chat = update.my_chat_member.chat
    if user and user.id != ADMIN_TELEGRAM_ID:
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="🔒 Ушбу бот ёпиқ тизим бўлиб, фақат бот эгаси (@JamshidjonDavronov) учун очиқ. Бегона фойдаланувчилар ботни гуруҳ ва каналларга қўша олмайди."
            )
            await context.bot.leave_chat(chat.id)
            logger.warning(f"Begona ({user.first_name}, ID: {user.id}) botni {chat.title} ga qo'shdi. Bot guruhdan chiqdi.")
        except Exception as e:
            logger.error(f"leave_chat error: {e}")
    else:
        approved_chats.add(chat.id)
        logger.info(f"Bot egasi botni {chat.title} ga qo'shdi. Guruh tasdiqlandi.")


# ==========================================
# ASOSIY DASTUR BOSHLANISHI
# ==========================================
async def post_init(application: Application):
    """Start bo'lganda / (drob) buyruqlar menyusini guruhlardan o'chirish"""
    try:
        await application.bot.delete_my_commands()
        from telegram import BotCommandScopeAllGroupChats
        await application.bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
        print("Guruhlardagi / (drob) menyusi o'chirildi.")
    except Exception as e:
        print(f"delete_my_commands xatosi: {e}")


def main():
    print("=" * 50)
    print("Beekeeping.Uz 🇺🇿 Telegram Bot ishga tushirilmoqda...")
    print(f"Admin ID: {ADMIN_TELEGRAM_ID}")
    print("=" * 50)

    from telegram.ext import ChatMemberHandler

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    app.run_polling()


if __name__ == "__main__":
    main()
