from config import CALORIE_SURPLUS_FOR_GAIN

ACTIVITY_FACTORS = {
    "low": 1.2,       # حركة قليلة / شغل مكتبي
    "medium": 1.55,   # نشاط متوسط / رياضة 3-4 مرات بالاسبوع
    "high": 1.725,    # نشاط عالي / رياضة يومية أو شغل بدني
}


def calculate_bmr(gender: str, weight_kg: float, height_cm: float, age: int) -> float:
    """معادلة Mifflin-St Jeor لحساب معدل الأيض الأساسي"""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == "male":
        return base + 5
    return base - 161


def calculate_calorie_target(gender: str, weight_kg: float, height_cm: float,
                              age: int, activity_level: str) -> float:
    """
    يحسب السعرات المطلوبة يوميا لأجل زيادة الوزن (تسمين):
    BMR × معامل النشاط + فائض السعرات
    """
    bmr = calculate_bmr(gender, weight_kg, height_cm, age)
    factor = ACTIVITY_FACTORS.get(activity_level, 1.55)
    maintenance = bmr * factor
    target = maintenance + CALORIE_SURPLUS_FOR_GAIN
    return round(target)


def calculate_protein_target(weight_kg: float) -> float:
    """
    يحسب هدف البروتين اليومي بالغرام لأجل بناء عضلات مع زيادة الوزن:
    1.8 غرام بروتين لكل كيلوغرام من وزن الجسم (معدل شائع ومناسب لهذا الهدف)
    """
    return round(weight_kg * 1.8)
