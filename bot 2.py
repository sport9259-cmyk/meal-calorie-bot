import logging
from telegram.ext import ApplicationBuilder

import database as db
from handlers import register_handlers
from scheduler import setup_scheduler
from config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    if BOT_TOKEN == "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE":
        raise SystemExit(
            "⚠️ لازم تحط توكن البوت! افتح config.py أو ملف .env وحط قيمة BOT_TOKEN."
        )

    db.init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    register_handlers(app)

    setup_scheduler(app)

    logger.info("البوت اشتغل ✅")
    app.run_polling()


if __name__ == "__main__":
    main()
