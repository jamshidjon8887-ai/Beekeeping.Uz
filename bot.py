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
import urllib.parse
from typing import List, Dict

import google.generativeai as genai
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==========================================
# SOZLAMALAR (CONFIGURATION)
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "9209261766:AAEwCxvnB0FFfd8Km0inaEhdDNWiEI1Ycv0")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6Lu3jGSvxVGoVR6ua9zV-BwFSeWNGnnqcP12NUf2Cl0mw")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_ID", "2047501151"))  # Jamshid Davronov

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
# MA'LUMOTLAR OSTIDAGI TUGMALAR VA REAKSIYALAR
# ==========================================
def get_info_inline_keyboard(text_to_share: str = "") -> InlineKeyboardMarkup:
    """
    Бот юборган ҳар қандай маълумот остида:
    1-қатор: 👍 | 👎 | ❤️ | 👏 (босилганда сони ошади)
    2-қатор: 📢 Asalarichilik.Uz 🇺🇿 (@Uz_Asalarichilik) | 👥 Расмий Гуруҳ (@Asalarichilik_Uzbekistan)
    3-қатор: 📺 YouTube Каналимиз (https://youtube.com/@asalarichilikuztv?feature=shared)
    4-қатор: ↗️ Улашиш (тўлиқ кўчириб улашиш) | 💬 Мутахассис (@Asalarichilikuztv_bot)
    """
    clean_text = text_to_share.strip()
    if len(clean_text) > 1200:
        clean_text = clean_text[:1200] + "..."

    share_caption = (
        f"{clean_text}\n\n"
        "🐝 Канал: @Uz_Asalarichilik\n"
        "👥 Расмий Гуруҳ: @Asalarichilik_Uzbekistan\n"
        "📺 YouTube: https://youtube.com/@asalarichilikuztv?feature=shared\n"
        "💬 Мутахассис: @Asalarichilikuztv_bot"
    )
    share_link = f"https://t.me/share/url?url=https://t.me/Uz_Asalarichilik&text={urllib.parse.quote(share_caption)}"

    keyboard = [
        # 1-қатор: Смайликлар (реакциялар)
        [
            InlineKeyboardButton("👍", callback_data="react:like"),
            InlineKeyboardButton("👎", callback_data="react:dislike"),
            InlineKeyboardButton("❤️", callback_data="react:heart"),
            InlineKeyboardButton("👏", callback_data="react:clap"),
        ],
        # 2-қатор: Канал ва Расмий Гуруҳ
        [
            InlineKeyboardButton("📢 Asalarichilik.Uz 🇺🇿", url="https://t.me/Uz_Asalarichilik"),
            InlineKeyboardButton("👥 Расмий Гуруҳ", url="https://t.me/Asalarichilik_Uzbekistan"),
        ],
        # 3-қатор: YouTube каналимиз
        [
            InlineKeyboardButton("📺 YouTube Каналимиз", url="https://youtube.com/@asalarichilikuztv?feature=shared"),
        ],
        # 4-қатор: Улашиш ва Мутахассис
        [
            InlineKeyboardButton("↗️ Улашиш", url=share_link),
            InlineKeyboardButton("💬 Мутахассис", url="https://t.me/Asalarichilikuztv_bot"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фойдаланувчи смайликларни босганда сонини ошириш ва ташаккур билдириш"""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("react:"):
        return

    emoji_map = {
        "react:like": "👍",
        "react:dislike": "👎",
        "react:heart": "❤️",
        "react:clap": "👏",
    }

    target_emoji = emoji_map.get(data)
    if not target_emoji:
        await query.answer()
        return

    try:
        msg = query.message
        if msg and msg.reply_markup and msg.reply_markup.inline_keyboard:
            current_rows = [list(row) for row in msg.reply_markup.inline_keyboard]
            row0 = current_rows[0]
            new_row0 = []
            for btn in row0:
                if btn.callback_data == data:
                    current_text = btn.text
                    parts = current_text.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        new_count = int(parts[1]) + 1
                        new_text = f"{parts[0]} {new_count}"
                    else:
                        new_text = f"{target_emoji} 1"
                    new_row0.append(InlineKeyboardButton(new_text, callback_data=btn.callback_data))
                else:
                    new_row0.append(btn)

            current_rows[0] = new_row0
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(current_rows))

        await query.answer(text=f"Ташаккур! Фикрингиз қабул қилинди {target_emoji}", show_alert=False)
    except Exception as e:
        logger.debug(f"Reaction error: {e}")
        try:
            await query.answer(text=f"Фикрингиз қабул қилинди {target_emoji}")
        except Exception:
            pass


# ==========================================
# /start BUYRUG'I
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat = update.effective_chat
    keyboard = get_info_inline_keyboard(WELCOME_MESSAGE)

    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_to_message_id=update.message.message_id if chat.type != "private" else None,
        reply_markup=keyboard
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
            reply_to_message_id=message.message_id if is_group else None,
            reply_markup=get_info_inline_keyboard(greeting_text)
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
        # Ҳар бир маълумот остида смайликлар ва ҳаволалар тўплами қўшилади
        info_keyboard = get_info_inline_keyboard(answer)
        await message.reply_text(
            answer[:4096],
            reply_to_message_id=message.message_id if is_group else None,
            message_thread_id=thread_id if is_group else None,
            allow_sending_without_reply=True,
            reply_markup=info_keyboard
        )
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        err_str = str(e)
        if is_owner and ("401" in err_str or "API_KEY" in err_str or "BLOCKED" in err_str or "UNAUTHENTICATED" in err_str or "not valid" in err_str):
            admin_notice = (
                "⚠️ Ҳурматли Админ!\n\n"
                "Google Gemini API калити блокланган (API_KEY_SERVICE_BLOCKED).\n"
                "GitHub'га очиқ юклангани сабабли Google хавфсизлик юзасидан ушбу калитни ўчирган.\n\n"
                "👉 Янги текин калит олиш: https://aistudio.google.com/app/apikey\n"
                "Янги калитни олиб, Render'да Environment бўлимига (GEMINI_API_KEY) киритишингиз керак."
            )
            await message.reply_text(
                admin_notice,
                reply_to_message_id=message.message_id if is_group else None,
                message_thread_id=thread_id if is_group else None,
                allow_sending_without_reply=True
            )
        else:
            await message.reply_text(
                QUOTA_ERROR_MESSAGE,
                reply_to_message_id=message.message_id if is_group else None,
                message_thread_id=thread_id if is_group else None,
                allow_sending_without_reply=True,
                reply_markup=get_info_inline_keyboard(QUOTA_ERROR_MESSAGE)
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


import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Beekeeping.Uz Telegram Bot is running 24/7 on Render!".encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_render_web_server():
    """Render.com Web Service port scan xatosini to'liq yechuvchi server"""
    port = int(os.getenv("PORT", "10000"))
    try:
        server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
        print(f"Render.com учун {port}-port муваффақиятли очилди ва тингланмоқда...")
        server.serve_forever()
    except Exception as e:
        print(f"Port binding xabari: {e}")


def main():
    print("=" * 50)
    print("Beekeeping.Uz 🇺🇿 Telegram Bot ishga tushirilmoqda...")
    print(f"Admin ID: {ADMIN_TELEGRAM_ID}")
    print("=" * 50)

    # 1. Render.com Web Service port scan xatosini oldini olish uchun port ochish
    threading.Thread(target=run_render_web_server, daemon=True).start()

    from telegram.ext import ChatMemberHandler

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_reaction_callback, pattern=r"^react:"))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    app.run_polling()


if __name__ == "__main__":
    main()
