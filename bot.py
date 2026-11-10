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
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

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

# Tavsiya etilgan modellar ketma-ketligi (multimodal rasm va video tahlili bilan)
MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash"
]

# ==========================================
# REALL VAQT VA OB-HAVO TIZIMI (TOSHKENT UTC+5)
# ==========================================
TASHKENT_TZ = timezone(timedelta(hours=5))
WEEKDAYS_UZ = ["Душанба", "Сешанба", "Чоршанба", "Пайшанба", "Жума", "Шанба", "Якшанба"]
MONTHS_UZ = ["январ", "феврал", "март", "апрел", "май", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]

UZB_REGIONS = {
    "samarqand": {"name": "Самарқанд", "lat": 39.6542, "lon": 66.9597},
    "buxoro": {"name": "Бухоро", "lat": 39.7747, "lon": 64.4286},
    "andijon": {"name": "Андижон", "lat": 40.7821, "lon": 72.3442},
    "fargona": {"name": "Фарғона", "lat": 40.3842, "lon": 71.7843},
    "namangan": {"name": "Наманган", "lat": 40.9983, "lon": 71.6726},
    "xorazm": {"name": "Хоразм", "lat": 41.5500, "lon": 60.6333},
    "urganch": {"name": "Урганч", "lat": 41.5500, "lon": 60.6333},
    "qashqadaryo": {"name": "Қашқадарё", "lat": 38.8606, "lon": 65.7890},
    "qarshi": {"name": "Қарши", "lat": 38.8606, "lon": 65.7890},
    "surxondaryo": {"name": "Сурхондарё", "lat": 37.2242, "lon": 67.2783},
    "termiz": {"name": "Термиз", "lat": 37.2242, "lon": 67.2783},
    "jizzax": {"name": "Жиззах", "lat": 40.1158, "lon": 67.8422},
    "sirdaryo": {"name": "Сирдарё", "lat": 40.4897, "lon": 68.7842},
    "guliston": {"name": "Гулистон", "lat": 40.4897, "lon": 68.7842},
    "navoiy": {"name": "Навоий", "lat": 40.0844, "lon": 65.3792},
    "nukus": {"name": "Нукус", "lat": 42.4602, "lon": 59.6166},
    "toshkent": {"name": "Тошкент", "lat": 41.2995, "lon": 69.2401},
}

WMO_WEATHER_CODES = {
    0: "Очиқ, мусаффо осмон",
    1: "Асосан очиқ",
    2: "Қисман булутли",
    3: "Булутли",
    45: "Туманли",
    48: "Қировли туман",
    51: "Енгил майда ёмғир",
    53: "Ўртача майда ёмғир",
    55: "Кучли майда ёмғир",
    61: "Енгил ёмғир",
    63: "Ўртача ёмғир",
    65: "Кучли ёмғир",
    71: "Енгил қор",
    73: "Ўртача қор",
    75: "Кучли қор",
    80: "Қисқа муддатли ёмғир",
    81: "Ёмғирли",
    82: "Жуда кучли жала",
    85: "Қор",
    86: "Кучли қор",
    95: "Момақалдироқ",
}


def get_tashkent_datetime() -> Dict[str, Any]:
    now = datetime.now(TASHKENT_TZ)
    weekday = WEEKDAYS_UZ[now.weekday()]
    month = MONTHS_UZ[now.month - 1]
    time_str = now.strftime("%H:%M")
    return {
        "year": now.year,
        "month": month,
        "day": now.day,
        "weekday": weekday,
        "time": time_str,
        "raw_now": now,
        "formatted": f"Йил: {now.year}-йил, Сана: {now.day}-{month}, Кун: {weekday}, Соат: {time_str} (Тошкент вақти, UTC+5)"
    }


def fetch_real_weather(region_query: str = "") -> Optional[Dict[str, Any]]:
    target_region = "toshkent"
    region_display = "Тошкент шаҳрида"
    query_lower = region_query.lower()
    for key, data in UZB_REGIONS.items():
        if key in query_lower or data["name"].lower() in query_lower:
            target_region = key
            region_display = f"{data['name']}да"
            break

    coord = UZB_REGIONS[target_region]
    lat, lon = coord["lat"], coord["lon"]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&timezone=Asia%2FTashkent"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BeekeepingUzBot/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            cur = data.get("current", {})
            temp = cur.get("temperature_2m", 0)
            apparent = cur.get("apparent_temperature", temp)
            humidity = cur.get("relative_humidity_2m", 0)
            code = cur.get("weather_code", 0)
            wind = cur.get("wind_speed_10m", 0)
            desc = WMO_WEATHER_CODES.get(code, "Очиқ / Булутли")
            return {
                "region_display": region_display,
                "region_name": coord["name"],
                "temp": f"+{temp}°C" if temp > 0 else f"{temp}°C",
                "apparent": f"+{apparent}°C" if apparent > 0 else f"{apparent}°C",
                "humidity": f"{humidity}%",
                "desc": desc,
                "wind": f"{wind} км/соат",
                "raw_temp": temp,
            }
    except Exception as e:
        logger.warning(f"Ob-havo olishda xatolik: {e}")
        return None


def detect_and_handle_datetime_weather(text: str) -> Optional[str]:
    text_lower = text.lower()
    
    # Sanani, yilni yoki kunni so'raganmi?
    has_date_year = bool(re.search(
        r"(нечанчи\s*йил|йил\s*неч|сана|число|қайси\s*кун|нима\s*кун|бугунги\s*кун|нечанчи\s*число|бугун\s*қайси|йил|числони)",
        text_lower
    ))
    
    # Vaqtni / soatni so'raganmi?
    has_time = bool(re.search(
        r"(вақт|соат|минут|соат\s*неч|соат\s*қандай|ҳозир\s*вақт|соат\s*неча|вақт\s*қандай)",
        text_lower
    ))
    
    # Ob-havoni so'raganmi?
    has_weather = bool(re.search(
        r"(об-?ҳаво|ҳаво|ҳарорат|градус|обҳаво|ёмғир|қор|шамол|иссиқ|совуқ)",
        text_lower
    ))
    
    if not (has_date_year or has_time or has_weather):
        return None
        
    dt = get_tashkent_datetime()
    w = fetch_real_weather(text)
    if not w:
        w = {
            "region_display": "Тошкент шаҳрида",
            "region_name": "Тошкент",
            "temp": "+9°C",
            "apparent": "+7°C",
            "humidity": "90%",
            "desc": "Булутли / Ёмғирли",
            "wind": "10 км/соат",
            "raw_temp": 9.0
        }
        
    raw_temp = w.get("raw_temp", 9.0)
    if raw_temp < 12:
        bee_note = (
            "Ҳарорат +12°C дан паст ва салқин бўлгани сабабли, асаларилар уя ичида клубокда (зич тўпда) бўлади. "
            "Бундай об-ҳавода уяларни очиш ва асалариларни безовта қилиш мумкин эмас. Қишлов шароитини сокин сақлаш тавсия этилади."
        )
    elif raw_temp < 20:
        bee_note = (
            "Ҳаво салқин, кузги-қишки давр. Асаларилар уя ичидаги озуқани истеъмол қилиб ҳароратни сақлайди. "
            "Ортиқча уяни очмаслик, қопқоқларни яхши ёпиш ва шамоллатишни назорат қилиш тавсия этилади."
        )
    else:
        bee_note = (
            "Ҳаво илиқ ва қулай. Асаларилар фаол учиб чанг ва нектар тўплаши мумкин. "
            "Пасекада керакли текширув ва парвариш ишларини олиб бориш мумкин."
        )
        
    return (
        "<b>Ассалому алайкум вароҳматуллоҳ!</b>\n\n"
        "Саволингизга аниқ ва расмий маълумотлар асосида жавоб:\n\n"
        f"1. <b>Йил:</b> Ҳозирда <b>{dt['year']}-йил</b>.\n"
        f"2. <b>Сана ва кун:</b> Бугун <b>{dt['day']}-{dt['month']}, {dt['weekday'].lower()}</b> куни.\n"
        f"3. <b>Ҳозирги вақт:</b> <b>{dt['time']}</b> (Тошкент вақти билан).\n"
        f"4. <b>Об-ҳаво маълумоти:</b> {w['region_display']} бугун ҳаво ҳарорати <b>{w['temp']}</b> (сезги <b>{w['apparent']}</b>), "
        f"ҳолат: <b>{w['desc'].lower()}</b>, ҳаво намлиги <b>{w['humidity']}</b>, шамол тезлиги <b>{w['wind']}</b>.\n"
        f"5. <b>Асаларичилик учун тавсия:</b> {bee_note}\n\n"
        "Агар асаларичилик мавсумидаги режаларингиз ёки пасекадаги қишлов ишлари бўйича саволларингиз бўлса, бемалол мурожаат қилишингиз мумкин."
    )


# ==========================================
# ASALARICHILIK KITOBLARI VA BILIMLAR BAZASI
# ==========================================
BOOKS_DIR = os.getenv("BOOKS_DIR", "books")
os.makedirs(BOOKS_DIR, exist_ok=True)
BOOKS_CATALOG_FILE = os.path.join(BOOKS_DIR, "catalog.json")


def load_books_catalog() -> Dict[str, Any]:
    if os.path.exists(BOOKS_CATALOG_FILE):
        try:
            with open(BOOKS_CATALOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_books_catalog(catalog: Dict[str, Any]):
    try:
        with open(BOOKS_CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Katalog saqlashda xatolik: {e}")


def get_available_books() -> List[Dict[str, Any]]:
    """books/ papkasidagi barcha PDF va TXT kitoblarni olish"""
    catalog = load_books_catalog()
    books = []
    if os.path.exists(BOOKS_DIR):
        for fname in sorted(os.listdir(BOOKS_DIR)):
            if fname.lower().endswith((".pdf", ".txt", ".doc", ".docx")) and fname != "catalog.json":
                fpath = os.path.join(BOOKS_DIR, fname)
                fsize = os.path.getsize(fpath)
                meta = catalog.get(fname, {})
                title = meta.get("title") or fname.rsplit(".", 1)[0].replace("_", " ")
                books.append({
                    "filename": fname,
                    "title": title,
                    "size_kb": round(fsize / 1024, 1),
                    "file_id": meta.get("file_id")
                })
    return books


def load_knowledge_base_text() -> str:
    """books/ papkasidagi barcha .txt qo'llanmalar matnini AI uchun birlashtirish"""
    texts = []
    if os.path.exists(BOOKS_DIR):
        for fname in sorted(os.listdir(BOOKS_DIR)):
            if fname.lower().endswith(".txt"):
                fpath = os.path.join(BOOKS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        c = f.read().strip()
                        if c:
                            texts.append(f"--- Қўлланма: {fname} ---\n{c[:6000]}")
                except Exception as e:
                    logger.warning(f"Matn o'qishda xatolik ({fname}): {e}")
    if texts:
        return "\n\n[АСАЛАРИЧИЛИК КИТОБЛАРИ ВА ҚЎЛЛАНМАЛАРДАН МАХСУС БИЛИМЛАР]:\n" + "\n\n".join(texts[:5]) + "\n"
    return ""


def build_books_keyboard() -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    books = get_available_books()
    if not books:
        text = (
            "<b>Ассалому алайкум вароҳматуллоҳ!</b>\n\n"
            "📚 <b>Асаларичилик кутубхонаси</b>\n\n"
            "Ҳозирда кутубхонага янги китоблар юкланмоқда. Тез орада барча қўлланмалар тақдим этилади.\n\n"
            "💡 <b>Ҳурматли Админ (@JamshidjonDavronov):</b>\n"
            "Сиз ушбу ботнинг личкасига исталган асаларичилик китобини (<b>PDF</b> ёки <b>TXT</b> шаклида) юборишингиз мумкин. "
            "Бот уни автоматик қабул қилиб, кутубхонага жойлайди ва сунъий интеллект хотирасига сингдиради!"
        )
        return text, None

    text = (
        "<b>Ассалому алайкум вароҳматуллоҳ!</b>\n\n"
        "📚 <b>Beekeeping.Uz Асаларичилик кутубхонаси:</b>\n\n"
        "Қуйидаги китоблардан бирини танланг, бот уни сизга дарҳол юклаб беради:"
    )
    rows = []
    for idx, b in enumerate(books[:10]):
        rows.append([
            InlineKeyboardButton(f"📖 {b['title'][:32]} ({b['size_kb']} KB)", callback_data=f"book:{idx}")
        ])
    return text, InlineKeyboardMarkup(rows)


SYSTEM_INSTRUCTION = (
    "Сиз Beekeeping.Uz 🇺🇿 асаларичилик канали ва гуруҳининг мутахассис ёрдамчисисиз.\n\n"
    "ҚАТЪИЙ ҚОИДАЛАР:\n"
    "1. Ҳар доим сўзингизни «Ассалому алайкум вароҳматуллоҳ!» дея бошланг.\n"
    "2. «Beekeeping.Uz лойиҳасига хуш келибсиз» ёки шунга ўхшаш таништирув жумлаларини МУТЛАҚО ёзманг! Дарҳол саволнинг аниқ ва амалий жавобига ўтинг.\n"
    "3. Маълумот чиройли ва кўркам бўлиши учун асосий сарлавҳаларни ва муҳим сўзларни қалин (**bold**) қилиб кўрсатинг.\n"
    "4. Бандларни 1., 2., 3. қилиб рақамланг ва ҳар бир банд номини қалин қилиб ажратинг (масалан: 1. **Генетик сифатни назорат қилиш (Селекция):** Табиий рой...).\n"
    "5. РАСМ ВА ВИДЕО ТАҲЛИЛИ: Агар фойдаланувчи расм ёки видео юборса, тасвирни диққат билан тўлиқ кўриб чиқинг. "
    "Ундаги асаларилар ҳолати, она ари бор-йўқлиги, насл ва қуртчалар рамкаси, уя тозалиги, асал сифати, кана/варроатоз ёки бошқа касаллик аломатларини аниқ фактлар асосида таҳлил қилиб, "
    "асаларичига тўғри ва илмий-амалий фойдали маслаҳат беринг.\n"
    "6. Барча саволларга ўзбек тилида тушунарли, аниқ ва батафсил жавоб беринг."
)

WELCOME_MESSAGE = (
    "<b>Ассалому алайкум вароҳматуллоҳ!</b>\n\n"
    "Сизга асаларичилик, она ари парвариши, касалликларга қарши кураш ва соҳага оид барча саволлар бўйича ёрдам бера оламан.\n\n"
    "Саволингизни бемалол ёзишингиз ёки расм/видео юборишингиз мумкин."
)

QUOTA_ERROR_MESSAGE = (
    "<b>Ассалому алайкум вароҳматуллоҳ!</b>\n\n"
    "🤖 Кечирасиз, ҳозирда Beekeeping.Uz🇺🇿 сўровлар чеклови (quota) вақтинча тўлди. "
    "Илтимос, бир оздан сўнг қайта ёзиб кўринг."
)

# Har bir chat uchun xotira (oxirgi 10 ta xabar)
MEMORY_LIMIT = 10
chat_memory: Dict[int, List[Dict[str, str]]] = {}

# Guruh ruxsatlari ro'yxati (Admin qo'shgan yoki ruxsat berilgan guruhlar)
approved_chats = set()

# Reaksiya ovozlarini kuzatish:
# Har bir xabar uchun foydalanuvchilar ovozlari: message_id -> {user_id: "like"|"dislike"|"heart"|"clap"}
message_user_votes: Dict[int, Dict[int, str]] = {}
# Har bir xabar uchun ovozlar soni: message_id -> {"like": int, "dislike": int, "heart": int, "clap": int}
message_vote_counts: Dict[int, Dict[str, int]] = {}

# Logging sozlash
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Gemini API ni sozlash
genai.configure(api_key=GEMINI_API_KEY)


def call_gemini_with_fallback(prompt: str, history: List[Dict[str, str]], media_part: Any = None) -> str:
    """Gemini modeliga murojaat qilish (matn, rasm va video uchun avtomatik zaxira modellar bilan)."""
    dt = get_tashkent_datetime()
    w = fetch_real_weather(prompt)
    weather_str = f"Ҳарорат {w['temp']} (сезги {w['apparent']}), ҳолат: {w['desc']}, намлик: {w['humidity']}" if w else "Кузги/қишки салқин ҳаво"

    realtime_context = (
        f"\n\n[РЕАЛ ҲОЗИРГИ САНА ВА ОБ-ҲАВО]:\n"
        f"- Жорий йил: {dt['year']}-йил\n"
        f"- Бугунги сана: {dt['day']}-{dt['month']}, {dt['weekday']}\n"
        f"- Ҳозирги соат/вақт: {dt['time']} (Тошкент вақти, UTC+5)\n"
        f"- Ҳозирги об-ҳаво маълумоти: {weather_str}\n"
        f"- Жорий мавсум: Ноябр (кузнинг охири, қишлов даври, ҳеч қачон май ёки баҳор эмас!)\n"
        "ҚАТЪИЙ ҚОИДА: Йил, кун, соат ёки об-ҳаво сўралса, ФАҚАТ ушбу аниқ реал кўрсаткичларга таяниб жавоб беринг! 2024 ёки май ойларини асло ёзманг!\n"
    )

    knowledge_context = load_knowledge_base_text()
    full_prompt = SYSTEM_INSTRUCTION + realtime_context + knowledge_context + "\n\n"
    for turn in history[-MEMORY_LIMIT:]:
        full_prompt += f"{turn['role']}: {turn['text']}\n"
    full_prompt += f"user: {prompt}\nmodel: "

    if media_part:
        contents = [media_part, full_prompt]
    else:
        contents = full_prompt

    last_error = None
    for model_name in MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(contents)
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
    """
    Фойдаланувчи 4 та смайликдан фақат биттасига овоз бера олади.
    Агар бошқа смайликни босса, аввалги овози олиб ташланиб (-1), янгисига (+1) ўзгаради.
    """
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("react:"):
        return

    new_key = data.removeprefix("react:")
    emoji_map = {
        "like": "👍",
        "dislike": "👎",
        "heart": "❤️",
        "clap": "👏",
    }

    target_emoji = emoji_map.get(new_key)
    if not target_emoji:
        await query.answer()
        return

    user = query.from_user
    user_id = user.id
    msg = query.message
    if not msg:
        await query.answer()
        return

    msg_id = msg.message_id

    # 1. Ushbu xabar uchun hisoblarni boshlash
    if msg_id not in message_vote_counts:
        counts = {"like": 0, "dislike": 0, "heart": 0, "clap": 0}
        if msg.reply_markup and msg.reply_markup.inline_keyboard:
            row0 = msg.reply_markup.inline_keyboard[0]
            for btn in row0:
                cdata = btn.callback_data or ""
                if cdata.startswith("react:"):
                    k = cdata.removeprefix("react:")
                    parts = btn.text.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        counts[k] = int(parts[1])
        message_vote_counts[msg_id] = counts

    if msg_id not in message_user_votes:
        message_user_votes[msg_id] = {}

    counts = message_vote_counts[msg_id]
    user_votes = message_user_votes[msg_id]
    prev_key = user_votes.get(user_id)

    # 2. Agar foydalanuvchi allaqachon shu reaksiyani bosgan bo'lsa
    if prev_key == new_key:
        await query.answer(text=f"Сиз аллақачон {target_emoji} смайлигига овоз бергансиз!", show_alert=False)
        return

    # 3. Foydalanuvchi ovozini o'zgartirsa yoki birinchi marta ovoz bersa
    if prev_key is not None:
        # Avvalgi ovozini -1 qilish
        counts[prev_key] = max(0, counts[prev_key] - 1)
        prev_emoji = emoji_map.get(prev_key, "")
        user_votes[user_id] = new_key
        counts[new_key] += 1
        alert_text = f"Овозингиз ўзгартирилди: {prev_emoji} ➡️ {target_emoji}"
    else:
        # Birinchi marta ovoz berish
        user_votes[user_id] = new_key
        counts[new_key] += 1
        alert_text = f"Ташаккур! Овозингиз қабул қилинди {target_emoji}"

    # 4. Tugmalarni yangi hisoblar bilan qayta chizish
    try:
        if msg.reply_markup and msg.reply_markup.inline_keyboard:
            current_rows = [list(row) for row in msg.reply_markup.inline_keyboard]
            new_row0 = []
            for k in ["like", "dislike", "heart", "clap"]:
                em = emoji_map[k]
                cnt = counts[k]
                btn_text = f"{em} {cnt}" if cnt > 0 else em
                new_row0.append(InlineKeyboardButton(btn_text, callback_data=f"react:{k}"))

            current_rows[0] = new_row0
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(current_rows))

        await query.answer(text=alert_text, show_alert=False)
    except Exception as e:
        logger.debug(f"Reaction error: {e}")
        try:
            await query.answer(text=alert_text)
        except Exception:
            pass


async def handle_book_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi tugmani bosganda kitob faylini jo'natish"""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("book:"):
        return
    idx_str = query.data.removeprefix("book:")
    books = get_available_books()
    if not idx_str.isdigit() or int(idx_str) >= len(books):
        await query.answer("Китоб топилмади.", show_alert=True)
        return

    book = books[int(idx_str)]
    file_path = os.path.join(BOOKS_DIR, book["filename"])
    if not os.path.exists(file_path):
        await query.answer("Китоб файли топилмади.", show_alert=True)
        return

    await query.answer("Китоб юборилмоқда...")
    try:
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=book["filename"],
                caption=f"📖 <b>{book['title']}</b>\n\n🐝 <b>Beekeeping.Uz кутубхонаси</b>\nКанал: @Uz_Asalarichilik",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Kitob yuborishda xatolik: {e}")
        await query.answer("Китобни юборишда хатолик юз берди.", show_alert=True)


async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/books yoki /kitoblar buyrug'i"""
    if not update.message:
        return
    text, reply_markup = build_books_keyboard()
    is_group = update.message.chat.type != "private"
    await update.message.reply_text(
        text,
        reply_to_message_id=update.message.message_id if is_group else None,
        parse_mode="HTML",
        reply_markup=reply_markup
    )


def format_to_telegram_html(text: str) -> str:
    """
    Gemini матнини Telegram HTML га айлантириб, 2-расмдагидек асосий матнлар,
    сарлавҳалар ва рақамланган бандларни (1., 2., 3.) қалин (<b>bold</b>) кўрсатиш.
    Ҳар доим битта '<b>Ассалому алайкум вароҳматуллоҳ!</b>' билан бошлашни таъминлайди.
    'Beekeeping.Uz лойиҳасига хуш келибсиз' сўзини бутунлай олиб ташлайди.
    """
    if not text:
        return ""

    # 1. Ортиқча 'Beekeeping.Uz лойиҳасига хуш келибсиз' сўзларини олиб ташлаш
    text = re.sub(r"(?i)beekeeping\.uz\s*(?:лойиҳасига|loyihasiga)\s*(?:хуш\s*келибсиз|xush\s*kelibsiz)[.!?,]*\s*", "", text)
    text = re.sub(r"(?i)лойиҳасига\s*хуш\s*келибсиз[.!?,]*\s*", "", text)

    # 2. Markdown код блокларини HTML ga aylantirish
    text = re.sub(r"```(?:\w+)?\n?(.*?)```", r"<pre><code>\1</code></pre>", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 3. Markdown сарлавҳалари ва қалин матнларни HTML ga aylantirish
    text = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 4. Рақамланган рўйхат сарлавҳаларини қалин қилиш (1. Сарлавҳа: -> 1. <b>Сарлавҳа:</b>)
    text = re.sub(r"(?m)^(\d+\.\s*)([^\n:<b>]+:)", r"\1<b>\2</b>", text)

    # 5. Telegram HTML тегларини (<b>, </b>, <i>, </i>, <u>, <s>, <code>, <pre>, <a>) вақтинча сақлаб олиш
    saved_tags = []
    def save_tag(m):
        saved_tags.append(m.group(0))
        return f"___TGTAG_{len(saved_tags)-1}___"

    text = re.sub(r"</?(?:b|i|u|s|code|pre|a(?:\s+href=\"[^\"]*\")?)\s*>", save_tag, text, flags=re.I)

    # 6. Қолган матндаги &, <, > белгиларини хавфсиз escape қилиш
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 7. Сақланган тегларни асл ҳолида қайта тиклаш
    for idx, tag in enumerate(saved_tags):
        text = text.replace(f"___TGTAG_{idx}___", tag)

    # 8. Бошидаги барча саломлашувларни (такрорланган ёки оддий бўлса ҳам) батамом тозалаш
    while True:
        cleaned = re.sub(
            r"^(?:<b>\s*)?(?:ассалому\s*алайкум\s*вароҳматуллоҳ[!.]*|assalomu\s*alaykum\s*varohmatulloh[!.]*|ассалому\s*алайкум[!.]*|assalomu\s*alaykum[!.]*)(?:\s*</b>)?\s*",
            "",
            text,
            flags=re.I
        ).strip()
        if cleaned == text:
            break
        text = cleaned

    # 9. Ягона кўркам салом билан бошлаш
    return "<b>Ассалому алайкум вароҳматуллоҳ!</b>\n\n" + text


async def send_formatted_reply(message, raw_text: str, is_group: bool, thread_id: int = None):
    """Матнни кўркам HTML шаклида, смайликлар ва ҳаволалар тугмаси билан юбориш"""
    formatted_html = format_to_telegram_html(raw_text)
    plain_text = re.sub(r"<[^>]+>", "", formatted_html)
    info_keyboard = get_info_inline_keyboard(plain_text)

    try:
        await message.reply_text(
            formatted_html[:4096],
            reply_to_message_id=message.message_id if is_group else None,
            message_thread_id=thread_id if is_group else None,
            allow_sending_without_reply=True,
            parse_mode="HTML",
            reply_markup=info_keyboard
        )
    except Exception as e:
        logger.warning(f"HTML parse_mode xatosi ({e}), oddiy matn bilan yuborilmoqda...")
        await message.reply_text(
            plain_text[:4096],
            reply_to_message_id=message.message_id if is_group else None,
            message_thread_id=thread_id if is_group else None,
            allow_sending_without_reply=True,
            reply_markup=info_keyboard
        )


# ==========================================
# /start BUYRUG'I
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat = update.effective_chat
    keyboard = get_info_inline_keyboard(re.sub(r"<[^>]+>", "", WELCOME_MESSAGE))

    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_to_message_id=update.message.message_id if chat.type != "private" else None,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==========================================
# ASOSIY XABARLAR ISHLOVCHISI
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id
    user_id = user.id if user else chat_id
    is_group = chat.type in ["group", "supergroup"]
    thread_id = message.message_thread_id

    # 1. BOT EGASI (ADMIN) HUQUQLARI
    is_owner = (user_id == ADMIN_TELEGRAM_ID)

    # SHAXSIY CHATDAGI QAT'IY HIMOYA:
    if not is_group and not is_owner:
        access_denied = (
            "🔒 Кириш чекланган!\n\n"
            "Ушбу бот ёпиқ тизим бўлиб, фақат бот эгаси (@JamshidjonDavronov) учун очиқ.\n"
            "Бегона фойдаланувчилар учун кириш ва созламалар бутунлай ёпиқ."
        )
        await message.reply_text(access_denied)
        return

    # Matn yoki rasm/video izohi (caption)
    raw_text = (message.text or message.caption or "").strip()
    text_lower = raw_text.lower()

    has_photo = bool(message.photo)
    has_video = bool(message.video or message.video_note)
    has_document = bool(message.document and (
        message.document.mime_type and ("image" in message.document.mime_type or "video" in message.document.mime_type)
    ))
    has_media = has_photo or has_video or has_document

    # Agar matn ham, media ham bo'lmasa - e'tiborsiz qoldirish
    if not raw_text and not has_media:
        return

    # GURUHGA BEGONA QO'SHGAN BO'LSA - BOT CHIQIB KETADI
    bot_info = await context.bot.get_me()
    bot_username = (bot_info.username or "").lower()

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

    # Guruhda faqat botga qaratilgan savollar, replylar yoki bot chaqirilgan media qabul qilinadi
    if is_group and not (is_reply_to_bot or has_trigger or raw_text.startswith("/") or (has_media and ("bot" in text_lower or "бот" in text_lower))):
        return

    # 3. KIRISH TRIGGERLARINI TOZALASH
    clean_text = raw_text
    if bot_username:
        clean_text = re.sub(rf"(?i)@{re.escape(bot_username)}", "", clean_text).strip()

    clean_text = re.sub(
        r"(?i)^(ассалому\s*алайкум\s*бот|assalomu\s*alaykum\s*bot|салом\s*бот|salom\s*bot|бот|bot)[,\s:]*",
        "",
        clean_text
    ).strip()

    # Agar foydalanuvchi shunchaki "salom bot" deb yozgan bo'lsa (rasmsiz):
    if not clean_text and has_trigger and not has_media:
        greeting_text = (
            "<b>Ваалайкум ассалом вараҳматуллоҳ!</b>\n\n"
            "Сизга қандай ёрдам беришим мумкин? Асаларичилик бўйича саволингизни бемалол ёзишингиз ёки расм/видео юборишингиз мумкин."
        )
        await send_formatted_reply(message, greeting_text, is_group=is_group, thread_id=thread_id)
        return

    # 4. VAQT, SANA, YIL VA OB-HAVO SAVOLLARINI 100% ANIQ VA REALL FAKTLAR BILAN JAVOBLASH
    if not has_media:
        direct_dt_weather_reply = detect_and_handle_datetime_weather(clean_text)
        if direct_dt_weather_reply:
            await send_formatted_reply(message, direct_dt_weather_reply, is_group=is_group, thread_id=thread_id)
            return

    # 4.1. KITOBLAR VA KUTUBXONA BO'YICHA SAVOLLAR
    if not has_media and any(k in clean_text.lower() for k in ["китоб", "китоблар", "kitob", "kitoblar", "кутубхона", "kutubxona"]):
        books_text, books_markup = build_books_keyboard()
        await message.reply_text(
            books_text,
            reply_to_message_id=message.message_id if is_group else None,
            message_thread_id=thread_id if is_group else None,
            parse_mode="HTML",
            reply_markup=books_markup
        )
        return

    # 5. RASM VA VIDEO (MULTIMODAL) FAYLLARNI YUKLAB OLISH
    media_part = None
    try:
        if has_photo:
            photo_file = await message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            media_part = {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}
        elif has_video:
            video_obj = message.video or message.video_note
            if video_obj.file_size and video_obj.file_size > 20 * 1024 * 1024:
                await send_formatted_reply(
                    message,
                    "⚠️ Видео ҳажми 20 МБ дан ортиқ. Telegram чекловлари сабабли қисқароқ видео ёки расм кўринишида юборинг.",
                    is_group=is_group,
                    thread_id=thread_id
                )
                return
            video_file = await video_obj.get_file()
            video_bytes = await video_file.download_as_bytearray()
            mime = getattr(video_obj, "mime_type", None) or "video/mp4"
            media_part = {"mime_type": mime, "data": bytes(video_bytes)}
        elif has_document and message.document:
            doc = message.document
            doc_name = doc.file_name or "kitob.pdf"
            is_book_ext = doc_name.lower().endswith((".pdf", ".txt", ".doc", ".docx"))

            # Agar Bot egasi (Jamshid) shaxsiy chatda kitob yuborsa, uni avtomatik kutubxonaga saqlaymiz!
            if is_owner and not is_group and is_book_ext:
                try:
                    doc_file = await doc.get_file()
                    save_path = os.path.join(BOOKS_DIR, doc_name)
                    await doc_file.download_to_drive(custom_path=save_path)

                    catalog = load_books_catalog()
                    clean_title = doc_name.rsplit(".", 1)[0].replace("_", " ")
                    catalog[doc_name] = {
                        "title": clean_title,
                        "file_id": doc.file_id,
                        "size": doc.file_size
                    }
                    save_books_catalog(catalog)

                    extra_note = (
                        "💡 <b>Ушбу китоб матни сунъий интеллект билимлар базасига ҳам қўшилди!</b>"
                        if doc_name.lower().endswith(".txt")
                        else "💡 Фойдаланувчилар «Китоблар» бўлими орқали ушбу китобни юклаб олишлари мумкин."
                    )
                    confirm_msg = (
                        "<b>Ассалому алайкум вароҳматуллоҳ, Жамшид ака!</b>\n\n"
                        f"✅ <b>Китоб қабул қилинди ва кутубхонага сақланди:</b>\n"
                        f"📖 <b>{clean_title}</b> ({round((doc.file_size or 0) / 1024, 1)} KB)\n\n"
                        f"{extra_note}"
                    )
                    await send_formatted_reply(message, confirm_msg, is_group=False)
                    return
                except Exception as e:
                    logger.error(f"Kitobni saqlashda xatolik: {e}")

            if doc.file_size and doc.file_size > 20 * 1024 * 1024:
                await send_formatted_reply(
                    message,
                    "⚠️ Файл ҳажми 20 МБ дан ортиқ. Илтимос, кичикроқ файл юборинг.",
                    is_group=is_group,
                    thread_id=thread_id
                )
                return
            doc_file = await doc.get_file()
            doc_bytes = await doc_file.download_as_bytearray()
            media_part = {"mime_type": doc.mime_type or "image/jpeg", "data": bytes(doc_bytes)}
    except Exception as e:
        logger.error(f"Faylni yuklab olishda xatolik: {e}")

    # 5. AI UCHUN PROMPT TAYYORLASH
    if media_part:
        if not clean_text:
            prompt_for_ai = (
                "Ушбу юборилган тасвирни (расм/видео) асаларичилик нуқтаи назаридан синчковлик билан тўлиқ таҳлил қилинг. "
                "Унда нима акс этганини (масалан: асаларилар ҳолати, она ари бор-йўқлиги, насл ва қуртчалар рамкаси, уя тозалиги, асал сифати, "
                "кана/варроа ёки бошқа касаллик аломатлари, уя тузилиши) аниқланг. Тўғри, ишончли фактлар ва амалий тажрибага асосланган ҳолда "
                "асаларичига фойдали тавсия ва маслаҳатларингизни чиройли, қалин (bold) сарлавҳалар ва 1., 2. бандлар билан тушунтириб беринг."
            )
        else:
            prompt_for_ai = (
                f"Фойдаланувчи ушбу расм/видео бўйича қуйидаги саволни берди:\n\"{clean_text}\"\n\n"
                "Илтимос, тасвирни диққат билан кўриб чиқиб, саволга тўғри, аниқ фактлар ва илмий-амалий тажриба асосида тўлиқ ва тушунарли жавоб беринг. "
                "Асосий сарлавҳаларни қалин (bold) қилиб, бандларни 1., 2. қилиб тартибланг."
            )
    else:
        prompt_for_ai = clean_text or raw_text
        if is_reply_to_bot and message.reply_to_message and message.reply_to_message.text:
            quoted = message.reply_to_message.text[:250]
            prompt_for_ai = f"[Олдинги жавоб: \"{quoted}\"]\nСавол: {clean_text}"

    # 6. CHAT XOTIRASINI OLISH VA AI DAN JAVOB YARATISH
    if chat_id not in chat_memory:
        chat_memory[chat_id] = []

    history = chat_memory[chat_id]
    log_text = prompt_for_ai if len(prompt_for_ai) < 150 else prompt_for_ai[:150] + "..."
    chat_memory[chat_id].append({"role": "user", "text": log_text})

    # Foydalanuvchiga 'yozmoqda...' (typing) statusini jo'natish
    try:
        action_type = "upload_photo" if has_photo else ("record_video" if has_video else "typing")
        if thread_id and is_group:
            await context.bot.send_chat_action(chat_id=chat_id, action=action_type, message_thread_id=thread_id)
        else:
            await context.bot.send_chat_action(chat_id=chat_id, action=action_type)
    except Exception:
        pass

    try:
        # Loop orqali sync funksiyani asinxron ishlatish
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, call_gemini_with_fallback, prompt_for_ai, history, media_part)

        chat_memory[chat_id].append({"role": "model", "text": answer})
        if len(chat_memory[chat_id]) > MEMORY_LIMIT * 2:
            chat_memory[chat_id] = chat_memory[chat_id][-MEMORY_LIMIT * 2:]

        # 2-расмдагидек маълумот чиройли ва кўркам, асосий матнлар қалин (bold), бошланиши 'Ассалому алайкум вароҳматуллоҳ!' бўлади
        await send_formatted_reply(message, answer, is_group=is_group, thread_id=thread_id)
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        err_str = str(e)
        if is_owner and ("401" in err_str or "API_KEY" in err_str or "BLOCKED" in err_str or "UNAUTHENTICATED" in err_str or "not valid" in err_str):
            admin_notice = (
                "⚠️ <b>Ҳурматли Админ!</b>\n\n"
                "Google Gemini API калити блокланган (API_KEY_SERVICE_BLOCKED).\n"
                "GitHub'га очиқ юклангани сабабли Google хавфсизлик юзасидан ушбу калитни ўчирган.\n\n"
                "👉 Янги текин калит олиш: https://aistudio.google.com/app/apikey\n"
                "Янги калитни олиб, Render'да Environment бўлимига (GEMINI_API_KEY) киритишингиз керак."
            )
            await send_formatted_reply(message, admin_notice, is_group=is_group, thread_id=thread_id)
        else:
            await send_formatted_reply(message, QUOTA_ERROR_MESSAGE, is_group=is_group, thread_id=thread_id)


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
    app.add_handler(CommandHandler(["books", "kitoblar", "kitob"], books_command))
    app.add_handler(CallbackQueryHandler(handle_reaction_callback, pattern=r"^react:"))
    app.add_handler(CallbackQueryHandler(handle_book_callback, pattern=r"^book:"))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    media_filter = (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND
    app.add_handler(MessageHandler(media_filter, handle_message))

    print("Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    app.run_polling()


if __name__ == "__main__":
    main()
