import logging
from datetime import datetime, time
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from config import TIMEZONE, REMINDER_HOURS, DAILY_SUMMARY_HOUR, DAILY_SUMMARY_MINUTE

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


async def send_meal_reminder(app):
    users = db.get_all_onboarded_users()
    for user in users:
        try:
            await app.bot.send_message(
                chat_id=user["chat_id"],
                text="⏰ حان وكت وجبة! لا تنسى تاكل وادزلي السعرات والبروتين بعدين (مثلا: 600 35) 🍽️"
            )
        except Exception:
            logger.exception(f"فشل ارسال تذكير للمستخدم {user['chat_id']}")


async def send_daily_summary(app):
    users = db.get_all_onboarded_users()
    date_str = today_str()
    for user in users:
        try:
            meals = db.get_meals_for_day(user["chat_id"], date_str)
            total_calories = sum(m["calories"] for m in meals)
            total_protein = sum(m["protein"] for m in meals)
            calorie_target = user["calorie_target"]
            protein_target = user["protein_target"]
            calorie_diff = total_calories - calorie_target
            protein_diff = total_protein - protein_target

            if not meals:
                status = "ما سجلت اي وجبة اليوم 😕 حاول تسجل وجباتك بجاي باجر."
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

            text = (
                f"📊 ملخص اليوم:\n\n"
                f"🍽️ عدد الوجبات: {len(meals)}\n"
                f"🔥 السعرات: {int(total_calories)} / {int(calorie_target)}\n"
                f"💪 البروتين: {int(total_protein)} / {int(protein_target)} غرام\n\n"
                f"{status}"
            )
            await app.bot.send_message(chat_id=user["chat_id"], text=text)
        except Exception:
            logger.exception(f"فشل ارسال ملخص اليوم للمستخدم {user['chat_id']}")


def setup_scheduler(app):
    scheduler = AsyncIOScheduler(timezone=TZ)

    for hour in REMINDER_HOURS:
        scheduler.add_job(
            send_meal_reminder,
            CronTrigger(hour=hour, minute=0, timezone=TZ),
            args=[app],
            id=f"reminder_{hour}",
            replace_existing=True,
        )

    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=DAILY_SUMMARY_HOUR, minute=DAILY_SUMMARY_MINUTE, timezone=TZ),
        args=[app],
        id="daily_summary",
        replace_existing=True,
    )

    scheduler.start()
    return scheduler
