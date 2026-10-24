# -*- coding: utf-8 -*-
import os
import re
import time
import random
import threading
from datetime import datetime, timezone, timedelta

from pyrubi import Client

# ============================== CONFIG ==============================

SESSION_NAME = "Z_SELF_RUBIKA"
POLL_SECONDS = 2
AUTO_REPLY_DELAY = 120
AUTO_REPLY_COOLDOWN = 7200
TIMER_DELAY = 300
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

RESET = "\033[0m"
CYAN = "\033[96m"
GREEN = "\033[92m"
WHITE = "\033[97m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"

DIGITS_ARABIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
DIGITS_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
DIGITS_DOUBLESTRUCK = str.maketrans("0123456789", "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡")
DIGITS_BOLD = str.maketrans("0123456789", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗")

# ============================== STATE ==============================

app = None
my_guid = None
base_first_name = ""
base_last_name = ""

features_enabled = True
timer_enabled = False
auto_reply_enabled = False
show_info_enabled = False
bold_enabled = False
ai_reply_enabled = False

timer_style = 3
awaiting_timer_style = False

seen_messages = {}
pending_replies = {}
last_auto_reply = {}

last_activity_at = None
activity_version = 0
profile_lock = threading.Lock()

# ============================== TERMINAL ==============================

def clear_screen():
    os.system("clear")


def print_header():
    clear_screen()
    print(f"{CYAN}╔══════════════════════════════════════╗{RESET}")
    print(f"{CYAN}║          Z - SELF RUBIKA             ║{RESET}")
    print(f"{CYAN}╚══════════════════════════════════════╝{RESET}")
    print(f"{WHITE}Telegram : {CYAN}@ID_Zertal{RESET}")
    print(f"{WHITE}Rubika   : {CYAN}@ZertalCode_ir{RESET}")
    print(f"{WHITE}GitHub   : {CYAN}@Ahora-ir{RESET}")
    print()


def typewrite(text, color=WHITE, delay=0.012):
    print(color, end="")
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print(RESET)


def startup_animation():
    clear_screen()
    print(f"{CYAN}╭──────────────────────────────────────╮{RESET}")
    print(f"{CYAN}│          Z - SELF RUBIKA             │{RESET}")
    print(f"{CYAN}╰──────────────────────────────────────╯{RESET}")

    for label in (
        "Preparing session",
        "Loading command system",
        "Starting message monitor",
    ):
        for i in range(1, 13):
            bar = "█" * i + "░" * (12 - i)
            print(
                f"\r{GREEN}[{bar}] {label}{RESET}",
                end="",
                flush=True,
            )
            time.sleep(0.025)

        print(f"\r{GREEN}[{'█' * 12}] {label} ✓{RESET}")
        time.sleep(0.12)

    time.sleep(0.25)
    print_header()


# ============================== HELPERS ==============================

def safe_dict(value):
    return value if isinstance(value, dict) else {}


def get_message_text(message):
    if not isinstance(message, dict):
        return ""
    return str(
        message.get("text") or message.get("message") or ""
    ).strip()


def get_message_id(message):
    if not isinstance(message, dict):
        return None
    return message.get("message_id") or message.get("id")


def get_author_guid(message):
    if not isinstance(message, dict):
        return None

    return (
        message.get("author_object_guid")
        or message.get("author_guid")
        or message.get("sender_object_guid")
        or message.get("user_guid")
    )


def get_reply_id(message):
    if not isinstance(message, dict):
        return None

    return (
        message.get("reply_to_message_id")
        or safe_dict(message.get("reply_to")).get("message_id")
        or safe_dict(message.get("reply_to_message")).get("message_id")
    )


def chats_list(response):
    if isinstance(response, dict):
        chats = response.get("chats", [])
        return chats if isinstance(chats, list) else []
    return []


def messages_list(response):
    if isinstance(response, dict):
        messages = response.get("messages", [])
        return messages if isinstance(messages, list) else []
    return []


def send_text(chat_guid, text, reply_id=None):
    try:
        if reply_id:
            return app.send_text(chat_guid, text, reply_id)
        return app.send_text(chat_guid, text)

    except Exception as exc:
        print(f"{RED}[SEND ERROR] {exc}{RESET}")
        return None


def is_private_guid(guid):
    return isinstance(guid, str) and guid.startswith("u")


def current_time():
    return datetime.now(IRAN_TZ)


def format_clock(style=None, moment=None):
    style = timer_style if style is None else style
    moment = moment or current_time()
    value = moment.strftime("%H:%M")

    if style == 1:
        return value.translate(DIGITS_DOUBLESTRUCK)
    if style == 2:
        return value.translate(DIGITS_BOLD)
    if style == 4:
        return value.translate(DIGITS_ARABIC)
    if style == 5:
        return value.translate(DIGITS_PERSIAN)

    return value


def normalize_text(text):
    text = str(text or "").strip().lower()
    text = text.replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text)


def escape_markdown(text):
    for char in ("\\", "*", "_", "`", "["):
        text = text.replace(char, "\\" + char)
    return text


# ============================== PRESET REPLIES ==============================

RESPONSES = {
    "سلام": [
        "سلام رفیق 🌹 خوبی؟",
        "درود داش ✨ چه خبر؟",
        "سلام سلام 😄 حالت چطوره؟",
        "به‌به سلام! خوبی؟",
    ],
    "خوبی": [
        "مرسی رفیق خوبم تو چطوری؟",
        "خوبم ممنون ازت 🌱 تو خوبی؟",
        "بد نیستم داش تو چه خبر؟",
    ],
    "چه خبر": [
        "سلامتیه داش 😄 از تو چه خبر؟",
        "خبر خاصی نیست رفیق تو تعریف کن",
        "همه‌چی آرومه فعلاً ✨ تو چطوری؟",
    ],
    "چیکار میکنی": [
        "فعلاً درگیر کارای خودمم 😅 تو چی؟",
        "چیز خاصی نیست رفیق تو مشغول چی هستی؟",
        "دارم به پیام تو جواب می‌دم دیگه 😂 تو چی کار می‌کنی؟",
    ],
    "کجایی": [
        "فعلاً در دسترسم رفیق 😄 تو کجایی؟",
        "همین حوالی مجازی‌ام 😂 چه شده؟",
    ],
    "ممنون": [
        "قربونت رفیق 🌹",
        "خواهش می‌کنم داش 🤝",
        "کاری نکردم که ✨",
    ],
    "مرسی": [
        "خواهش می‌کنم ❤️",
        "قربونت داش",
        "دمت گرم که گفتی 😄",
    ],
    "ببخشید": [
        "اشکالی نداره رفیق",
        "راحت باش داش پیش میاد 🌱",
    ],
    "خداحافظ": [
        "فعلاً رفیق مراقب خودت باش 🌹",
        "بدرود داش به امید دیدار ✨",
        "فعلاً خوش بگذره 😄",
    ],
    "شب بخیر": [
        "شب تو هم آروم و قشنگ 🌙",
        "شب بخیر رفیق خوابای خوب ببینی ✨",
    ],
    "صبح بخیر": [
        "صبح تو هم بخیر 🌞 روز خوبی داشته باشی",
        "صبحت قشنگ داش ☀️",
    ],
    "خسته نباشی": [
        "سلامت باشی رفیق 🌹",
        "ممنون داش تو هم خسته نباشی",
    ],
    "دلتنگ": [
        "امیدوارم زودتر ببینیش یا باهاش حرف بزنی رفیق 🌱",
        "دلتنگی سخته داش امیدوارم حالت زودتر بهتر شه",
    ],
    "ناراحتم": [
        "متأسفم که حالت خوب نیست رفیق اگه خواستی تعریف کن چی شده 🌱",
        "گاهی حرف زدن یه کم سبک می‌کنه آدمو من گوش می‌دم",
    ],
    "خوشحالم": [
        "چه عالی رفیق 😄 امیدوارم همیشه همین‌قدر خوشحال باشی",
        "به‌به همین حس خوبو نگه دار ✨",
    ],
    "دوستت دارم": [
        "محبت داری رفیق ❤️",
        "قربون محبتت برم 🌹",
    ],
    "کی هستی": [
        "من دستیار خودکار حساب صاحب اکانتم پیام رو دریافت می‌کنم و بر اساس متن جواب می‌دم 🤖",
    ],
    "ساعت": [
        lambda: f"الان ساعت {current_time().strftime('%H:%M')} به وقت ایرانه 🕒",
    ],
    "روز بخیر": [
        "روزت پر از اتفاقای خوب رفیق 🌱",
    ],
}

KEYWORD_GROUPS = [
    (("سلام", "درود", "سلااام", "سلاممم", "صبح بخیر", "عصر بخیر"), "سلام"),
    (("خوبی", "خوب هستی", "چطوری", "چه طور", "حالت چطوره"), "خوبی"),
    (("چه خبر", "چخبر", "خبرها"), "چه خبر"),
    (("چیکار میکنی", "چه کار میکنی", "چیکار می‌کنی", "مشغولی"), "چیکار میکنی"),
    (("کجایی", "کجا هستی"), "کجایی"),
    (("ممنون", "متشکرم", "سپاس"), "ممنون"),
    (("مرسی", "دمت گرم"), "مرسی"),
    (("ببخشید", "معذرت", "شرمنده"), "ببخشید"),
    (("خداحافظ", "فعلا", "بای", "بدرود"), "خداحافظ"),
    (("شب بخیر", "شب‌خیر"), "شب بخیر"),
    (("صبح بخیر",), "صبح بخیر"),
    (("خسته نباشی",), "خسته نباشی"),
    (("دلتنگ", "دلم برات تنگ شده"), "دلتنگ"),
    (("ناراحتم", "حالم بده", "غمگینم"), "ناراحتم"),
    (("خوشحالم", "خیلی خوشحالم"), "خوشحالم"),
    (("دوستت دارم", "عاشقتم"), "دوستت دارم"),
    (("کی هستی", "تو کی هستی", "رباتی"), "کی هستی"),
    (("ساعت چنده", "ساعت", "الان چه ساعتی"), "ساعت"),
    (("روز بخیر",), "روز بخیر"),
]


def preset_reply(text):
    normalized = normalize_text(text)

    for phrases, key in KEYWORD_GROUPS:
        if any(normalize_text(p) in normalized for p in phrases):
            options = RESPONSES.get(key, [])
            if options:
                answer = random.choice(options)
                return answer() if callable(answer) else answer

    return None


# ============================== HELP ==============================

HELP_TEXT = """🧩 ربات فعال می‌باشد.

لیست دستورات:

خاموش / روشن
خاموش یا روشن کردن قابلیت‌های ربات

تایمر روشن / تایمر خاموش
بعد از تایمر روشن یکی از گزینه‌های ۱ تا ۵ را بفرست. پس از ۵ دقیقه بی‌فعالیتی ساعت در فامیلی ثبت می‌شود و ثابت می‌ماند.

فونت تایم یک
فونت تایم دو
فونت تایم سه
فونت تایم عربی
فونت تایم فارسی
انتخاب شکل اعداد ساعت

پاسخگویی خودکار / پاسخگویی خاموش
پاسخ خودکار به پیام خصوصی جدید پس از ۲ دقیقه

نمایش اطلاعات روشن / نمایش اطلاعات خاموش
در گروه روی پیام عضو ریپلای کن و بنویس اطلاعات

برجسته روشن / برجسته خاموش
برجسته‌سازی پیام‌های ارسالی خودت

پاسخ Ai روشن / پاسخ Ai خاموش
پاسخ‌گویی با کلیدواژه‌ها و جواب‌های از پیش تعیین‌شده

برای دیدن این فهرست دوباره بنویس کمک
"""


def send_help():
    send_text(my_guid, HELP_TEXT)


# ============================== COMMANDS ==============================

def initialize_seen_messages():
    try:
        for chat in chats_list(app.get_chats()):
            guid = chat.get("object_guid")
            last = chat.get("last_message")
            mid = get_message_id(last)

            if guid and mid:
                seen_messages[guid] = mid

    except Exception as exc:
        print(f"{YELLOW}[WARN] {exc}{RESET}")


def apply_timer_style(style):
    global timer_style
    timer_style = style


def handle_saved_command(text):
    global features_enabled, timer_enabled, auto_reply_enabled
    global show_info_enabled, bold_enabled, ai_reply_enabled
    global awaiting_timer_style, last_activity_at, activity_version

    cmd = normalize_text(text)

    if cmd in ("کمک", "help", "/help", "دستورات"):
        send_help()
        return True

    if cmd == "خاموش":
        features_enabled = False
        timer_enabled = False
        auto_reply_enabled = False
        show_info_enabled = False
        bold_enabled = False
        ai_reply_enabled = False
        awaiting_timer_style = False
        activity_version += 1
        send_text(my_guid, "تمام قابلیت‌ها خاموش شدند. برای فعال‌سازی دوباره بنویس روشن")
        return True

    if cmd == "روشن":
        features_enabled = True
        send_text(my_guid, "قابلیت‌های ربات فعال شدند. برای دیدن دستورات بنویس کمک")
        return True

    if not features_enabled:
        return False

    if awaiting_timer_style and cmd in (
        "1", "2", "3", "4", "5", "۱", "۲", "۳", "۴", "۵"
    ):
        style_digits = {
            "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
            "۱": 1, "۲": 2, "۳": 3, "۴": 4, "۵": 5,
        }

        apply_timer_style(style_digits[cmd])
        awaiting_timer_style = False
        timer_enabled = True
        last_activity_at = time.time()
        activity_version += 1

        send_text(
            my_guid,
            f"تایمر روشن شد. فونت انتخابی: {format_clock()}. بعد از ۵ دقیقه سکوت ثبت می‌شود."
        )
        return True

    if cmd == "تایمر روشن":
        awaiting_timer_style = True
        send_text(
            my_guid,
            "فونت ساعت را با فرستادن شماره انتخاب کن:\n\n"
            "𝟘𝟜:𝟙𝟘 — 1\n"
            "𝟎𝟒:𝟏𝟎 — 2\n"
            "04:10 — 3\n"
            "٠٤:١٠ — 4 (اعداد عربی)\n"
            "۰۴:۱۰ — 5 (اعداد فارسی)\n\n"
            "فقط شماره 1 تا 5 را بفرست."
        )
        return True

    if cmd == "تایمر خاموش":
        timer_enabled = False
        awaiting_timer_style = False
        activity_version += 1
        send_text(my_guid, "تایمر خاموش شد.")
        return True

    style_map = {
        "فونت تایم یک": 1,
        "فونت تایم دو": 2,
        "فونت تایم سه": 3,
        "فونت تایم فارسی": 5,
        "فونت تایم عربی": 4,
    }

    if cmd in style_map:
        apply_timer_style(style_map[cmd])
        send_text(my_guid, f"فونت ساعت تغییر کرد: {format_clock()}")
        return True

    if cmd == "پاسخگویی خودکار":
        auto_reply_enabled = True
        send_text(my_guid, "پاسخ‌گویی خودکار روشن شد.")
        return True

    if cmd == "پاسخگویی خاموش":
        auto_reply_enabled = False
        pending_replies.clear()
        send_text(my_guid, "پاسخ‌گویی خودکار خاموش شد.")
        return True

    if cmd == "نمایش اطلاعات روشن":
        show_info_enabled = True
        send_text(my_guid, "نمایش اطلاعات گروه روشن شد. روی پیام عضو ریپلای کن و بنویس اطلاعات")
        return True

    if cmd == "نمایش اطلاعات خاموش":
        show_info_enabled = False
        send_text(my_guid, "نمایش اطلاعات گروه خاموش شد.")
        return True

    if cmd == "برجسته روشن":
        bold_enabled = True
        send_text(my_guid, "برجسته‌سازی پیام‌های ارسالی روشن شد.")
        return True

    if cmd == "برجسته خاموش":
        bold_enabled = False
        send_text(my_guid, "برجسته‌سازی پیام‌های ارسالی خاموش شد.")
        return True

    if cmd in ("پاسخ ai روشن", "پاسخ ai فعال", "پاسخ هوشمند روشن"):
        ai_reply_enabled = True
        send_text(my_guid, "پاسخ‌گویی کلیدواژه‌ای روشن شد.")
        return True

    if cmd in ("پاسخ ai خاموش", "پاسخ هوشمند خاموش"):
        ai_reply_enabled = False
        send_text(my_guid, "پاسخ‌گویی کلیدواژه‌ای خاموش شد.")
        return True

    return False


# ============================== GROUP INFO ==============================

def handle_group_info(chat_guid, message, all_messages):
    if not show_info_enabled or not str(chat_guid).startswith("g0"):
        return

    if normalize_text(get_message_text(message)) != "اطلاعات":
        return

    reply_id = get_reply_id(message)
    if not reply_id:
        return

    target = next(
        (item for item in all_messages if get_message_id(item) == reply_id),
        None,
    )
    if not target:
        return

    user_guid = get_author_guid(target)
    if not user_guid:
        return

    try:
        info = safe_dict(app.get_chat_info(user_guid))
        user = safe_dict(info.get("user") or info.get("chat") or info)

        first = user.get("first_name") or "نامشخص"
        last = user.get("last_name") or ""
        username = user.get("username") or "ندارد"
        bio = user.get("bio") or "ندارد"

        response = (
            "اطلاعات حساب\n"
            f"نام: {(first + ' ' + last).strip()}\n"
            f"نام کاربری: @{username}\n"
            f"بیو: {bio}\n"
            f"شناسه: {user_guid}"
        )

        send_text(chat_guid, response)

    except Exception as exc:
        print(f"{YELLOW}[INFO ERROR] {exc}{RESET}")


# ============================== BOLD ==============================

def handle_bold(chat_guid, message):
    if not features_enabled or not bold_enabled:
        return

    if not message.get("is_mine"):
        return

    text = get_message_text(message)
    mid = get_message_id(message)

    if not text or not mid:
        return

    if text.startswith("**") and text.endswith("**"):
        return

    if text in ("کمک", "روشن", "خاموش"):
        return

    try:
        app.edit_message(chat_guid, f"**{escape_markdown(text)}**", mid)
    except Exception as exc:
        print(f"{DIM}[BOLD] {exc}{RESET}")


# ============================== STABLE TIMER ==============================

def handle_timer_activity(message):
    global last_activity_at, activity_version

    if message.get("is_mine"):
        last_activity_at = time.time()
        activity_version += 1


def timer_worker():
    recorded_activity_version = -1

    while True:
        time.sleep(2)

        if not features_enabled or not timer_enabled:
            continue

        if last_activity_at is None:
            continue

        version = activity_version
        last_activity = last_activity_at

        if version == recorded_activity_version:
            continue

        if time.time() - last_activity < TIMER_DELAY:
            continue

        with profile_lock:
            if version != activity_version:
                continue

            if not timer_enabled or not features_enabled:
                continue

            if version == recorded_activity_version:
                continue

            # Freeze the timestamp for this inactive period.
            estimated_time = last_activity + TIMER_DELAY / 2
            stamp = datetime.fromtimestamp(
                estimated_time, IRAN_TZ
            ).strftime("%H:%M")

            if timer_style == 1:
                stamp = stamp.translate(DIGITS_DOUBLESTRUCK)
            elif timer_style == 2:
                stamp = stamp.translate(DIGITS_BOLD)
            elif timer_style == 4:
                stamp = stamp.translate(DIGITS_ARABIC)
            elif timer_style == 5:
                stamp = stamp.translate(DIGITS_PERSIAN)

            family = f"{base_last_name} - {stamp}".strip(" -")

            # The saved timestamp is written once, not every second.
            try:
                app.update_profile(last_name=family)
                print(f"{GREEN}[TIMER] Fixed time saved: {stamp}{RESET}")
            except Exception as exc:
                print(f"{RED}[TIMER ERROR] {exc}{RESET}")
                continue

            recorded_activity_version = version


# ============================== AUTO REPLY ==============================

def handle_auto_reply(chat_guid, message):
    if not features_enabled or not auto_reply_enabled:
        return

    if not is_private_guid(chat_guid) or message.get("is_mine"):
        return

    mid = get_message_id(message)
    text = get_message_text(message)

    if not mid or not text:
        return

    author = get_author_guid(message) or chat_guid
    now = time.time()

    if author in last_auto_reply:
        if now - last_auto_reply[author] < AUTO_REPLY_COOLDOWN:
            pending_replies.pop(author, None)
            return

    if author not in pending_replies or pending_replies[author][1] != mid:
        pending_replies[author] = (now, mid)
        return

    started, pending_mid = pending_replies[author]

    if now - started < AUTO_REPLY_DELAY:
        return

    answer = (
        "کاربر گرامی، صاحب این حساب در حال حاضر در دسترس نیست. "
        "پیام شما دریافت شد و به ایشان ارجاع داده می‌شود. "
        "پس از بازگشت و در اولین فرصت پاسخ‌گوی شما خواهد بود. ✨"
    )

    send_text(chat_guid, answer)
    last_auto_reply[author] = now
    pending_replies.pop(author, None)


# ============================== KEYWORD AI ==============================

def handle_keyword_ai(chat_guid, message):
    if not features_enabled or not ai_reply_enabled:
        return

    if message.get("is_mine") or not is_private_guid(chat_guid):
        return

    text = get_message_text(message)
    if not text:
        return

    answer = preset_reply(text)
    if answer:
        send_text(chat_guid, answer)


# ============================== MESSAGE MONITOR ==============================

def process_chat(chat):
    chat_guid = chat.get("object_guid")
    message = chat.get("last_message")

    if not chat_guid or not isinstance(message, dict):
        return

    mid = get_message_id(message)
    if not mid:
        return

    if seen_messages.get(chat_guid) == mid:
        return

    seen_messages[chat_guid] = mid

    handle_timer_activity(message)

    if message.get("is_mine"):
        text = get_message_text(message)

        if chat_guid == my_guid and text:
            if handle_saved_command(text):
                return

        handle_bold(chat_guid, message)
        return

    if show_info_enabled and str(chat_guid).startswith("g0"):
        if (
            normalize_text(get_message_text(message)) == "اطلاعات"
            and get_reply_id(message)
        ):
            try:
                group_messages = messages_list(
                    app.get_messages(chat_guid, limit=50)
                )
                handle_group_info(chat_guid, message, group_messages)
            except Exception as exc:
                print(f"{YELLOW}[INFO ERROR] {exc}{RESET}")

    handle_auto_reply(chat_guid, message)
    handle_keyword_ai(chat_guid, message)


def monitor_loop():
    while True:
        try:
            for chat in chats_list(app.get_chats()):
                process_chat(chat)

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            break

        except Exception as exc:
            print(f"{YELLOW}[MONITOR] {exc}{RESET}")
            time.sleep(4)


# ============================== MAIN ==============================

def main():
    global app, my_guid, base_first_name, base_last_name

    startup_animation()
    typewrite("Enter your account details to sign in", WHITE, 0.008)

    app = Client(SESSION_NAME)

    me = safe_dict(app.get_me())
    user = safe_dict(me.get("user") or me)

    my_guid = (
        user.get("user_guid")
        or user.get("object_guid")
        or user.get("guid")
        or me.get("user_guid")
        or me.get("object_guid")
    )

    base_first_name = str(
        user.get("first_name") or me.get("first_name") or ""
    )
    base_last_name = str(
        user.get("last_name") or me.get("last_name") or ""
    )

    if not my_guid:
        print(f"{YELLOW}Could not determine your own GUID from get_me().{RESET}")
        print(f"{YELLOW}Returned keys: {list(me.keys())}{RESET}")
        print("Send this output back so the GUID field can be mapped accurately.")
        return

    print_header()

    typewrite(
        "Account login successful. Send HELP in Saved Messages to view bot instructions.",
        GREEN,
        0.006,
    )
    typewrite(
        "The bot runs while your internet is connected and Termux stays open. "
        "Run this script again to restart it.",
        CYAN,
        0.018,
    )

    print()
    initialize_seen_messages()

    threading.Thread(target=timer_worker, daemon=True).start()
    monitor_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Z - SELF RUBIKA stopped.{RESET}")
