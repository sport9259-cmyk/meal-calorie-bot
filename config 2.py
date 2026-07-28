import os
from dotenv import load_dotenv

load_dotenv()

# ================== إعدادات أساسية ==================
# التوكن مال بوت التليكرام (تحصل عليه من BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")

# مفتاح Google AI Studio (Gemini) لتحليل صور الوجبات وحساب السعرات
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "PUT_YOUR_GEMINI_API_KEY_HERE")

# المنطقة الزمنية (بغداد)
TIMEZONE = "Asia/Baghdad"

# ================== إعدادات التذكير ==================
# الساعات (بتوقيت بغداد، نظام 24 ساعة) الي بيها يوصلك تذكير "اكل وجبة"
# افتراضيا كل 3 ساعات من 9 صباحا الى 9 مساءا (5 تذكيرات باليوم)
REMINDER_HOURS = [9, 12, 15, 18, 21]

# وكت ارسال ملخص نهاية اليوم (24 ساعة)
DAILY_SUMMARY_HOUR = 23
DAILY_SUMMARY_MINUTE = 30

# فائض السعرات المطلوب يوميا لأجل زيادة الوزن (تسمين)
# 500 سعرة زيادة يوميا = تقريبا نص كيلو زيادة بالاسبوع (معدل آمن وصحي)
CALORIE_SURPLUS_FOR_GAIN = 500

# قاعدة البيانات
DB_PATH = os.getenv("DB_PATH", "meals.db")
