import base64
import json
import re
import httpx

from config import OPENROUTER_API_KEY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# نموذجين ثابتين مجانيين (مؤكدين حاليا) — لو صار خطأ 404 مستقبلا يعني
# أحدهم صار غير متوفر مجانا (القائمة تتغير عند OpenRouter بين فترة وأخرى)
PRIMARY_MODEL = "google/gemma-4-31b-it:free"
FALLBACK_MODEL = "qwen/qwen2.5-vl-3b-instruct:free"

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


def _build_payload(model: str, content) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 300,
    }


async def _call_model(client: httpx.AsyncClient, model: str, content, headers: dict) -> str:
    payload = _build_payload(model, content)
    resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        return ""


def _parse_response(raw_text: str) -> dict:
    cleaned = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        description = str(parsed.get("description", "وجبة")).strip()
        calories = float(parsed.get("calories", 0))
        return {"description": description, "calories": calories}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"description": "", "calories": 0.0}


async def estimate_calories_from_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    يرسل صورة الوجبة الى OpenRouter (نموذج ثابت مجاني + احتياطي عند الفشل)
    ويرجع dict فيها description و calories. يرمي استثناء اذا فشل الطلب بالكامل.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_uri = f"data:{media_type};base64,{b64_image}"

    content = [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": image_data_uri}},
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        raw_text = await _call_model(client, PRIMARY_MODEL, content, headers)
        result = _parse_response(raw_text)

        # لو الأول فشل يفهم الصورة أو رجع رد فاضي، جرب النموذج الاحتياطي مرة وحدة
        if result["calories"] <= 0 or not result["description"]:
            raw_text = await _call_model(client, FALLBACK_MODEL, content, headers)
            fallback_result = _parse_response(raw_text)
            if fallback_result["calories"] > 0:
                return fallback_result

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

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        raw_text = await _call_model(client, PRIMARY_MODEL, prompt, headers)
        result = _parse_response(raw_text)

        if not result["description"]:
            raw_text = await _call_model(client, FALLBACK_MODEL, prompt, headers)
            result = _parse_response(raw_text)

    if not result["description"]:
        # فشل التعديل -> خلي القيم الأصلية بدون تغيير
        return {"description": description, "calories": calories}

    return result
