import logging
import re
from datetime import datetime
import pytz

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters
)

import database as db
from nutrition import calculate_calorie_target, calculate_protein_target
from config import TIMEZONE

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)

# حالات محادثة التسجيل (onboarding)
GENDER, WEIGHT, HEIGHT, AGE, ACTIVITY = range(5)

# يتتبع آخر رسالة تأكيد وجبة أرسلها البوت لكل مستخدم، علمود لو المستخدم
# رد (Reply) عليها بالضبط نعرف يقصد يصحح هذي الوجبة بالذات، مو يسجل وجبة جديدة.
LAST_MEAL_MESSAGE: dict[int, dict] = {}

# يقبل رقمين (سعرات وبروتين) مفصولين بمسافة أو فاصلة، بأي ترتيب كتابة
# مثلا: "600 35" أو "600,35" أو "٦٠٠ ٣٥"
NUMBER_PAIR_RE = re.compile(r"(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)")
SINGLE_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def parse_calories_protein(text: str):
    """
    يحاول يستخرج رقمين (سعرات، بروتين) من النص. يرجع (calories, protein)
    أو None لو ما لكى ولا رقم بالنص.
    """
    text = text.strip()
    pair = NUMBER_PAIR_RE.search(text)
    if pair:
        return float(pair.group(1)), float(pair.group(2))

    single = SINGLE_NUMBER_RE.search(text)
    if single:
        return float(single.group(1)), 0.0

    return None


# ================== الأوامر الأساسية ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_chat.id)
    if user and user["onboarded"]:
        await update.message.reply_text(
            f"هلا بيك رجعت 👋\n"
            f"هدفك اليومي: {int(user['calorie_target'])} سعرة، "
            f"{int(user['protein_target'])} غرام بروتين.\n"
            f"لما تاكل وجبة بس ادزلي رقمين: السعرات والبروتين (مثلا: 600 35).\n"
            f"اوامر مفيدة: /today لملخص اليوم، /reset لتعديل بياناتك."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "هلا وغلا! 👋 هذا بوت حساب الوجبات ومساعدتك تحقق هدف زيادة الوزن (تسمين) بطريقة صحية.\n\n"
        "خلي نسولف شوية عنك أول:\n"
        "شنو جنسك؟ اكتب: ذكر أو انثى"
    )
    return GENDER


async def gender_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("ذكر", "رجال", "male"):
        context.user_data["gender"] = "male"
    elif text in ("انثى", "أنثى", "بنت", "female"):
        context.user_data["gender"] = "female"
    else:
        await update.message.reply_text("اكتبلي بس: ذكر أو انثى 🙏")
        return GENDER

    await update.message.reply_text("تمام 👍 هسه وزنك الحالي كم؟ (بالكيلوغرام، مثلا: 65)")
    return WEIGHT


async def weight_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text.strip().replace(",", "."))
        if not (20 <= weight <= 300):
            raise ValueError
    except ValueError:
        await update.message.reply_text("رجاءا ادخل رقم صحيح للوزن بالكيلوغرام (مثلا: 65)")
        return WEIGHT

    context.user_data["weight_kg"] = weight
    await update.message.reply_text("زين. هسه طولك كم؟ (بالسنتيمتر، مثلا: 175)")
    return HEIGHT


async def height_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        height = float(update.message.text.strip().replace(",", "."))
        if not (100 <= height <= 250):
            raise ValueError
    except ValueError:
        await update.message.reply_text("رجاءا ادخل رقم صحيح للطول بالسنتيمتر (مثلا: 175)")
        return HEIGHT

    context.user_data["height_cm"] = height
    await update.message.reply_text("تمام. عمرك كم؟")
    return AGE


async def age_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text.strip())
        if not (10 <= age <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("رجاءا ادخل عمر صحيح (رقم فقط)")
        return AGE

    context.user_data["age"] = age
    await update.message.reply_text(
        "آخر سؤال 🙌 شلون توصف مستوى نشاطك اليومي؟\n"
        "1 = قليل (شغل مكتبي، ماكو رياضة)\n"
        "2 = متوسط (رياضة 3-4 مرات بالاسبوع)\n"
        "3 = عالي (رياضة يومية أو شغل بدني تعبان)\n"
        "اكتب: 1 أو 2 أو 3"
    )
    return ACTIVITY


async def activity_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mapping = {"1": "low", "2": "medium", "3": "high"}
    choice = update.message.text.strip()
    if choice not in mapping:
        await update.message.reply_text("اكتب بس 1 أو 2 أو 3 🙏")
        return ACTIVITY

    activity_level = mapping[choice]
    data = context.user_data

    calorie_target = calculate_calorie_target(
        gender=data["gender"],
        weight_kg=data["weight_kg"],
        height_cm=data["height_cm"],
        age=data["age"],
        activity_level=activity_level,
    )
    protein_target = calculate_protein_target(data["weight_kg"])

    db.upsert_user_profile(
        chat_id=update.effective_chat.id,
        gender=data["gender"],
        weight_kg=data["weight_kg"],
        height_cm=data["height_cm"],
        age=data["age"],
        activity_level=activity_level,
        calorie_target=calorie_target,
        protein_target=protein_target,
    )

    await update.message.reply_text(
        f"تم ✅ هذا ملخص هدفك اليومي:\n\n"
        f"🎯 السعرات: {calorie_target} سعرة حرارية\n"
        f"💪 البروتين: {protein_target} غرام\n"
        f"(فائض 500 سعرة عن حاجتك الطبيعية لزيادة وزن تدريجية وصحية، "
        f"والبروتين يدعم بناء العضلات مو الدهون)\n\n"
        f"راح ارسلك تذكير كل 3 ساعات تاكل وجبة. كل ما تاكل، بس ادزلي رقمين: "
        f"السعرات والبروتين (مثلا: 600 35). وبنهاية اليوم ارسلك ملخص كامل.\n\n"
        f"جاهز؟ ابدأ لول ما توصلك أول تذكير، أو سجل وجبة هسه! 🍽️"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("الغيت التسجيل. اكتب /start اذا تريد تعيده.")
    return ConversationHandler.END


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("زين، خلي نعدل بياناتك من جديد.\nشنو جنسك؟ اكتب: ذكر أو انثى")
    return GENDER


# ================== تسجيل وتعديل الوجبات (بدون ذكاء اصطناعي) ==================

async def meal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يستقبل رسالة نصية فيها رقمين (سعرات وبروتين). لو الرسالة رد (Reply) بالضبط
    على آخر تأكيد وجبة أرسله البوت، يعدل تلك الوجبة. غير هذا، يسجلها كوجبة جديدة.
    """
    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)

    if not user or not user["onboarded"]:
        await update.message.reply_text("خلي نسجل بياناتك أول. اكتب /start 🙏")
        return

    text = update.message.text.strip()
    parsed = parse_calories_protein(text)

    if not parsed:
        await update.message.reply_text(
            "ما لكيت أرقام بالرسالة 😅 ادزلي السعرات والبروتين بس هيج: 600 35"
        )
        return

    calories, protein = parsed

    last_meal_msg = LAST_MEAL_MESSAGE.get(chat_id)
    is_correction = (
        last_meal_msg is not None
        and update.message.reply_to_message is not None
        and update.message.reply_to_message.message_id == last_meal_msg["message_id"]
    )

    if is_correction:
        await _handle_meal_correction(update, chat_id, calories, protein, last_meal_msg, user)
    else:
        await _handle_new_meal(update, chat_id, calories, protein, user)


async def _handle_new_meal(update: Update, chat_id: int, calories: float, protein: float, user: dict):
    meal_id = db.add_meal(chat_id, today_str(), "وجبة", calories, protein)

    meals_today = db.get_meals_for_day(chat_id, today_str())
    total_calories = sum(m["calories"] for m in meals_today)
    total_protein = sum(m["protein"] for m in meals_today)

    sent_msg = await update.message.reply_text(
        f"✅ تسجلت الوجبة!\n\n"
        f"🔥 السعرات: {int(calories)}\n"
        f"💪 البروتين: {int(protein)} غرام\n\n"
        f"📊 مجموع اليوم: {int(total_calories)}/{int(user['calorie_target'])} سعرة، "
        f"{int(total_protein)}/{int(user['protein_target'])} غرام بروتين "
        f"({len(meals_today)} وجبة)\n\n"
        f"💬 لو غلط، رد (Reply) على هذي الرسالة بالأرقام الصحيحة."
    )

    LAST_MEAL_MESSAGE[chat_id] = {
        "message_id": sent_msg.message_id,
        "meal_id": meal_id,
        "calories": calories,
        "protein": protein,
    }


async def _handle_meal_correction(update: Update, chat_id: int, calories: float, protein: float,
                                   last_meal_msg: dict, user: dict):
    db.update_meal(last_meal_msg["meal_id"], calories, protein)

    meals_today = db.get_meals_for_day(chat_id, today_str())
    total_calories = sum(m["calories"] for m in meals_today)
    total_protein = sum(m["protein"] for m in meals_today)

    sent_msg = await update.message.reply_text(
        f"✅ تم التعديل!\n\n"
        f"🔥 السعرات: {int(calories)}\n"
        f"💪 البروتين: {int(protein)} غرام\n\n"
        f"📊 مجموع اليوم بعد التعديل: {int(total_calories)}/{int(user['calorie_target'])} سعرة، "
        f"{int(total_protein)}/{int(user['protein_target'])} غرام بروتين\n\n"
        f"💬 تكدر ترد على هذي الرسالة بالذات لو تحب تعدلها مرة ثانية."
    )

    LAST_MEAL_MESSAGE[chat_id] = {
        "message_id": sent_msg.message_id,
        "meal_id": last_meal_msg["meal_id"],
        "calories": calories,
        "protein": protein,
    }


# ================== أمر ملخص اليوم ==================

async def today_summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)
    if not user or not user["onboarded"]:
        await update.message.reply_text("سجل بياناتك أول بـ /start")
        return

    meals = db.get_meals_for_day(chat_id, today_str())
    total_calories = sum(m["calories"] for m in meals)
    total_protein = sum(m["protein"] for m in meals)
    calorie_target = user["calorie_target"]
    protein_target = user["protein_target"]

    lines = [f"📅 وجبات اليوم ({len(meals)}):"]
    for i, m in enumerate(meals, 1):
        lines.append(f"{i}. {int(m['calories'])} سعرة، {int(m['protein'])} غ بروتين")

    calorie_diff = total_calories - calorie_target
    protein_diff = total_protein - protein_target

    if not meals:
        status = "لسا ما سجلت اي وجبة اليوم 🍽️"
    else:
        calorie_status = (
            f"✅ حققت هدف السعرات (زايد {int(calorie_diff)})" if calorie_diff >= 0
            else f"⚠️ ناقصك {int(-calorie_diff)} سعرة"
        )
        protein_status = (
            f"✅ حققت هدف البروتين (زايد {int(protein_diff)} غ)" if protein_diff >= 0
            else f"⚠️ ناقصك {int(-protein_diff)} غ بروتين"
        )
        status = f"{calorie_status}\n{protein_status}"

    lines.append(
        f"\n🔥 السعرات: {int(total_calories)}/{int(calorie_target)}\n"
        f"💪 البروتين: {int(total_protein)}/{int(protein_target)} غرام"
    )
    lines.append(status)

    await update.message.reply_text("\n".join(lines))


def register_handlers(app):
    from telegram.ext import ConversationHandler

    onboarding_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("reset", reset_cmd)],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender_step)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_step)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height_step)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_step)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, activity_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(onboarding_conv)
    app.add_handler(CommandHandler("today", today_summary_cmd))
    # يجب يكون آخر هاندلر نصي، علمود ما يتعارض مع محادثة التسجيل (onboarding)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, meal_text_handler))
