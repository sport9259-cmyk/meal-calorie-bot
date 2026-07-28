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
                text="⏰ حان وكت وجبة! لا تنسى تاكل ودز لي صورتها بعدين علمود احسبلك السعرات 🍽️"
            )
        except Exception:
            logger.exception(f"فشل ارسال تذكير للمستخدم {user['chat_id']}")


async def send_daily_summary(app):
    users = db.get_all_onboarded_users()
    date_str = today_str()
    for user in users:
        try:
            meals = db.get_meals_for_day(user["chat_id"], date_str)
            total = sum(m["calories"] for m in meals)
            target = user["calorie_target"]
            diff = total - target

            if not meals:
                status = "ما سجلت اي وجبة اليوم 😕 حاول تسجل وجباتك بجاي باجر."
            elif diff >= 0:
                status = f"✅ حققت هدفك اليوم! زايد {int(diff)} سعرة عن الرينج المطلوب."
            else:
                status = f"⚠️ ناقصك {int(-diff)} سعرة عن هدفك اليومي. حاول تزيد وجبة خفيفة قبل النوم."

            text = (
                f"📊 ملخص اليوم:\n\n"
                f"🍽️ عدد الوجبات: {len(meals)}\n"
                f"🔥 مجموع السعرات: {int(total)} / {int(target)}\n\n"
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
