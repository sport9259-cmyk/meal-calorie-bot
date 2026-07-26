import base64
import json
import re
import httpx

from config import OPENROUTER_API_KEY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# openrouter/free يختار تلقائيا نموذج مجاني يدعم تحليل الصور من بين عدة نماذج متوفرة،
# فهذا أكثر ثباتا من الاعتماد على نموذج واحد قد يوكف أو يتغير اسمه لاحقا
MODEL = "openrouter/free"

PROMPT = """أنت خبير تغذية. انظر لصورة الوجبة هذي وقدر لي:
1. وصف مختصر بالعربي لمكونات الوجبة (سطر وحد).
2. تقدير تقريبي للسعرات الحرارية الكلية (رقم واحد فقط، بالكيلو كالوري).

مهم جدا: رد فقط بصيغة JSON صافية بدون أي نص إضافي وبدون Markdown، بهذا الشكل بالضبط:
{"description": "...", "calories": 000}

اذا الصورة مو وجبة اكل واضحة، حط "calories": 0 و"description": "لم أستطع تحديد الوجبة بوضوح".
"""


async def estimate_calories_from_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    يرسل صورة الوجبة الى OpenRouter (مجاني) ويرجع dict فيها description و calories.
    يرمي استثناء اذا فشل الطلب أو تعذر تحليل الرد.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_uri = f"data:{media_type};base64,{b64_image}"

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        raw_text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raw_text = ""

    # تنظيف احتياطي بحال رجع نص فيه ```json ... ```
    cleaned = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(cleaned)
        description = str(parsed.get("description", "وجبة")).strip()
        calories = float(parsed.get("calories", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        # فشل التحليل -> نرجع قيمة افتراضية بدل ما البوت يوكف
        description = "تعذر تحليل الوجبة تلقائيا"
        calories = 0.0

    return {"description": description, "calories": calories}
