import logging
from datetime import datetime
import pytz

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters
)

import database as db
from nutrition import calculate_calorie_target
from calorie_estimator import estimate_calories_from_image
from config import TIMEZONE

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)

# حالات محادثة التسجيل (onboarding)
GENDER, WEIGHT, HEIGHT, AGE, ACTIVITY = range(5)


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


# ================== الأوامر الأساسية ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_chat.id)
    if user and user["onboarded"]:
        await update.message.reply_text(
            f"هلا بيك رجعت 👋\n"
            f"هدفك الحالي: {int(user['calorie_target'])} سعرة حرارية باليوم.\n"
            f"دز لي صورة وجبتك أي وكت وراح احسبلك السعرات.\n"
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

    target = calculate_calorie_target(
        gender=data["gender"],
        weight_kg=data["weight_kg"],
        height_cm=data["height_cm"],
        age=data["age"],
        activity_level=activity_level,
    )

    db.upsert_user_profile(
        chat_id=update.effective_chat.id,
        gender=data["gender"],
        weight_kg=data["weight_kg"],
        height_cm=data["height_cm"],
        age=data["age"],
        activity_level=activity_level,
        calorie_target=target,
    )

    await update.message.reply_text(
        f"تم ✅ هذا ملخص هدفك:\n\n"
        f"🎯 السعرات المطلوبة يوميا: {target} سعرة حرارية\n"
        f"(هذا رقم يشمل فائض 500 سعرة زيادة عن حاجتك الطبيعية علمود تزيد وزن بشكل تدريجي وصحي)\n\n"
        f"راح ارسلك تذكير كل 3 ساعات تاكل وجبة، وكل ما تاكل دز لي صورة الوجبة وراح احسبلك سعراتها. "
        f"وبنهاية اليوم ارسلك ملخص كامل.\n\n"
        f"جاهز؟ ابدأ لول ما توصلك أول تذكير، أو دز صورة وجبة هسه! 📸"
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


# ================== استقبال صور الوجبات ==================

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)

    if not user or not user["onboarded"]:
        await update.message.reply_text("خلي نسجل بياناتك أول. اكتب /start 🙏")
        return

    processing_msg = await update.message.reply_text("جاري تحليل الوجبة... 🔍")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        result = await estimate_calories_from_image(bytes(image_bytes))
        description = result["description"]
        calories = result["calories"]

        if calories <= 0:
            await processing_msg.edit_text(
                "ما كدرت افهم الوجبة بوضوح من الصورة 😕 حاول ترفع صورة أوضح أكثر تكدر تشوف فيها الاكل."
            )
            return

        db.add_meal(chat_id, today_str(), description, calories)

        meals_today = db.get_meals_for_day(chat_id, today_str())
        total_today = sum(m["calories"] for m in meals_today)

        await processing_msg.edit_text(
            f"✅ تسجلت الوجبة!\n\n"
            f"🍽️ الوصف: {description}\n"
            f"🔥 السعرات: {int(calories)} سعرة\n\n"
            f"📊 مجموع اليوم لحد الآن: {int(total_today)} سعرة "
            f"من أصل {int(user['calorie_target'])} ({len(meals_today)} وجبة)"
        )
    except Exception as e:
        logger.exception("فشل تحليل صورة الوجبة")
        await processing_msg.edit_text(
            "صار خطأ بتحليل الصورة 😅 جرب مرة ثانية بعد شوي."
        )


# ================== أمر ملخص اليوم ==================

async def today_summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)
    if not user or not user["onboarded"]:
        await update.message.reply_text("سجل بياناتك أول بـ /start")
        return

    meals = db.get_meals_for_day(chat_id, today_str())
    total = sum(m["calories"] for m in meals)
    target = user["calorie_target"]

    lines = [f"📅 وجبات اليوم ({len(meals)}):"]
    for i, m in enumerate(meals, 1):
        lines.append(f"{i}. {m['description']} — {int(m['calories'])} سعرة")

    diff = total - target
    if not meals:
        status = "لسا ما سجلت اي وجبة اليوم 🍽️"
    elif diff >= 0:
        status = f"✅ حققت هدفك! زايد {int(diff)} سعرة عن الرينج."
    else:
        status = f"⚠️ لسا ناقصك {int(-diff)} سعرة عن هدفك اليومي."

    lines.append(f"\n🔥 المجموع: {int(total)} / {int(target)} سعرة")
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
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
