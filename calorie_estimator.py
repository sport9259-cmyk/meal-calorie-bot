import base64
import json
import re
import httpx

from config import GEMINI_API_KEY

# نموذج Gemini الحالي (سريع ورخيص/مجاني ضمن حد استخدام يومي سخي).
# لو صار خطأ 404 مستقبلا يعني هذا الاسم اتغير عند Google، حينها لازم يتحدث.
MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)

PROMPT = """أنت خبير تغذية دقيق. انظر لصورة الوجبة هذي بعناية وقدر لي:

1. تعرف على كل مكونات الوجبة (نوع الاكل، هل فيه رز/لحم/خضار/صلصة/زيت... الخ)
2. قدر حجم الحصة الفعلي من الصورة (صحن كامل كبير؟ حصة فردية صغيرة؟ عدة قطع؟)
3. احسب السعرات بناء على المكونات وحجم الحصة الكاملة الظاهرة بالصورة — لا تقلل التقدير،
   خصوصا للأطعمة المطبوخة بالزيت أو السمن أو المحشية (كالدولمة، البرياني، الرز باللحم)
   لأنها غالبا أعلى بالسعرات مما تبين بالنظر السريع.
4. اكتب وصف مختصر بالعربي لمكونات الوجبة (سطر وحد).

مهم جدا: رد فقط بصيغة JSON صافية بدون أي نص إضافي وبدون Markdown، بهذا الشكل بالضبط:
{"description": "...", "calories": 000}

اذا الصورة مو وجبة اكل واضحة، حط "calories": 0 و"description": "لم أستطع تحديد الوجبة بوضوح".
"""

REFINE_PROMPT_TEMPLATE = """أنت خبير تغذية. عندك تقدير سابق لوجبة:
- الوصف: {description}
- السعرات المقدرة: {calories}

المستخدم رد بهذا التوضيح أو التصحيح:
"{clarification}"

عدّل التقدير بناء على كلام المستخدم (مثلا لو كول الكمية أقل/أكثر، أو أضاف/شال مكون،
أو صحح نوع الاكل). لو كلامه ما يوضح شي محدد يغير الحساب، خله التقدير قريب من السابق.

رد فقط بصيغة JSON صافية بدون أي نص إضافي وبدون Markdown، بهذا الشكل بالضبط:
{{"description": "...", "calories": 000}}
"""


def _parse_response(raw_text: str) -> dict:
    cleaned = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        description = str(parsed.get("description", "وجبة")).strip()
        calories = float(parsed.get("calories", 0))
        return {"description": description, "calories": calories}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"description": "", "calories": 0.0}


async def _call_gemini(parts: list) -> str:
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
    }
    params = {"key": GEMINI_API_KEY}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GEMINI_URL, params=params, json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return ""


async def estimate_calories_from_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    يرسل صورة الوجبة الى Gemini مباشرة (Google AI Studio) ويرجع dict فيها
    description و calories. يرمي استثناء اذا فشل الطلب بالكامل.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    parts = [
        {"text": PROMPT},
        {"inline_data": {"mime_type": media_type, "data": b64_image}},
    ]

    raw_text = await _call_gemini(parts)
    result = _parse_response(raw_text)

    if not result["description"]:
        result["description"] = "تعذر تحليل الوجبة تلقائيا"

    return result


async def refine_estimate(description: str, calories: float, clarification: str) -> dict:
    """
    يعدل تقدير وجبة سابق بناء على توضيح نصي من المستخدم (محادثة نصية، بدون صورة).
    يرمي استثناء اذا فشل الطلب بالكامل.
    """
    prompt = REFINE_PROMPT_TEMPLATE.format(
        description=description, calories=int(calories), clarification=clarification
    )

    raw_text = await _call_gemini([{"text": prompt}])
    result = _parse_response(raw_text)

    if not result["description"]:
        # فشل التعديل -> خلي القيم الأصلية بدون تغيير
        return {"description": description, "calories": calories}

    return result
