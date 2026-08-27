import re
from datetime import datetime as _dt
from pydantic import BaseModel, field_validator
from typing import Literal, Optional, List

from api.services.activity_type_resolver import VALID_ACTIVITY_TYPES
from api.services.shopping_service import CATEGORY_ORDER as SHOPPING_CATEGORIES
from api.services.competition_level import validate_competition_level


def _normalize_start_time(v: Optional[str]) -> Optional[str]:
    """Coerce any time string to 24h HH:MM. Rejects unparseable input."""
    if not v:
        return v
    s = v.strip().upper().replace(" ", "")
    for fmt in ("%H:%M", "%I:%M%p"):
        try:
            return _dt.strptime(s, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError(f"start_time must be HH:MM or H:MMam/pm, got {v!r}")


def _normalize_intensity(v):
    if v is None or v == "":
        return None
    s = str(v).strip().lower()
    if s not in ("low", "medium", "high"):
        raise ValueError("intensity must be one of: low, medium, high")
    return s


class ParentCreate(BaseModel):
    full_name: str
    email: str
    consent_confirmed: bool = False


class ParentResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    consent_timestamp: str
    consent_confirmed: bool
    schedule_reminder_dismissed: bool = False
    created_at: str


class ParentProfileUpdate(BaseModel):
    full_name: str
    phone: Optional[str] = None

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v):
        return _validate_phone(v)


def _validate_phone(v: Optional[str]) -> Optional[str]:
    """Accept any formatting; require exactly 10 US digits when non-empty."""
    if v is None or v == "":
        return None
    digits = re.sub(r"\D", "", v)
    if len(digits) != 10:
        raise ValueError("phone must contain exactly 10 digits (US number)")
    return v


class AthleteCreate(BaseModel):
    parent_id: int
    first_name: str
    age: int
    gender: str  # Girl / Boy / Prefer not to say
    weight_lbs: float
    height_ft: int
    height_in: float
    position: Optional[str] = None  # Goalkeeper / Defender / Midfielder / Forward
    competition_level: Optional[str] = None  # recreational / competitive_club / elite_club (legacy values tolerated)
    sweat_profile: Optional[str] = None  # Light / Moderate / Heavy / Very Heavy
    allergies: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    supplement_use: Optional[str] = None
    season_phase: Optional[str] = None  # in_season / off_season / postseason (Fuel Gauge); default applied on write
    food_preferences: Optional[str] = None  # onboarding wizard: free-text likes/dislikes/textures → coach context
    date_of_birth: Optional[str] = None  # ISO YYYY-MM-DD; used by calc_age() for precision targets
    lifestyle_activity: str = "light"    # sedentary / light / moderate — drives lifestyle PAL in calc_tdee
    diet_pref: str = "omnivore"          # omnivore / vegetarian / vegan — drives DIET_PROT_MULT
    phone: Optional[str] = None          # US contact number; optional; validated to 10 digits

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v):
        return _validate_phone(v)

    @field_validator("competition_level")
    @classmethod
    def validate_competition_level_field(cls, v):
        return validate_competition_level(v)


class OnboardingAthlete(BaseModel):
    first_name: str
    age: int
    gender: str
    weight_lbs: float
    height_ft: int
    height_in: float
    position: Optional[str] = None
    competition_level: Optional[str] = None
    sweat_profile: Optional[str] = None
    allergies: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    supplement_use: Optional[str] = None
    season_phase: Optional[str] = None
    food_preferences: Optional[str] = None
    date_of_birth: Optional[str] = None
    lifestyle_activity: Optional[str] = None
    diet_pref: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v):
        return _validate_phone(v)

    @field_validator("competition_level")
    @classmethod
    def validate_competition_level_field(cls, v):
        return validate_competition_level(v)


class OnboardingComplete(BaseModel):
    parent: ParentCreate
    athlete: OnboardingAthlete


class AthleteResponse(BaseModel):
    id: int
    parent_id: int
    first_name: str
    age: int
    gender: str
    weight_lbs: float
    height_ft: int
    height_in: float
    position: Optional[str]
    competition_level: Optional[str]
    sweat_profile: Optional[str]
    allergies: Optional[str]
    dietary_restrictions: Optional[str]
    supplement_use: Optional[str]
    season_phase: Optional[str] = None
    food_preferences: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None
    lifestyle_activity: str = "light"
    diet_pref: str = "omnivore"
    schedule_reminder_dismissed: bool = False
    created_at: str

    @field_validator("lifestyle_activity", "diet_pref", "schedule_reminder_dismissed", mode="before")
    @classmethod
    def _coerce_null_to_default(cls, v, info):
        # DB rows created via onboarding can have these columns NULL; a NULL defeats
        # the field default (defaults apply only to MISSING keys) → ResponseValidationError.
        if v is None:
            return {"lifestyle_activity": "light", "diet_pref": "omnivore",
                    "schedule_reminder_dismissed": False}[info.field_name]
        return v


class EventCreate(BaseModel):
    athlete_id: int
    event_name: str
    event_type: str
    event_date: str  # YYYY-MM-DD
    start_time: Optional[str] = None  # HH:MM (24h)
    duration_hours: Optional[float] = None
    city: Optional[str] = None
    venue_name: Optional[str] = None   # Google Places name (e.g. "Mustang Soccer Complex")
    address: Optional[str] = None      # Google Places formatted_address
    latitude: Optional[float] = None   # precise venue coords for weather lookup
    longitude: Optional[float] = None
    intensity: Optional[str] = None  # low / medium / high; derived if omitted
    activity_type: Optional[str] = None  # 7 engine keys; None = untagged (2h default applies)
    uid: Optional[str] = None  # source ICS VEVENT UID; enables import dedup. None for manual events.
    source: Literal["manual"] = "manual"  # public POST only creates manual events; synced sources write directly to DB

    @field_validator("start_time", mode="before")
    @classmethod
    def normalize_start_time(cls, v):
        return _normalize_start_time(v)

    @field_validator("intensity", mode="before")
    @classmethod
    def normalize_intensity(cls, v):
        return _normalize_intensity(v)


class EventUpdate(BaseModel):
    event_name: Optional[str] = None
    event_type: Optional[str] = None
    event_date: Optional[str] = None  # YYYY-MM-DD
    start_time: Optional[str] = None  # HH:MM (24h)
    duration_hours: Optional[float] = None
    city: Optional[str] = None
    venue_name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    intensity: Optional[str] = None  # low / medium / high
    activity_type: Optional[str] = None  # 7 engine keys; None = untagged

    @field_validator("start_time", mode="before")
    @classmethod
    def normalize_start_time(cls, v):
        return _normalize_start_time(v)

    @field_validator("intensity", mode="before")
    @classmethod
    def normalize_intensity(cls, v):
        return _normalize_intensity(v)


class EventResponse(BaseModel):
    id: int
    athlete_id: int
    event_name: str
    event_type: str
    event_date: str
    start_time: Optional[str]
    duration_hours: Optional[float]
    city: Optional[str]
    venue_name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    intensity: Optional[str] = None
    activity_type: Optional[str] = None
    uid: Optional[str] = None
    source: Optional[str] = None
    created_at: str


class ActivityTypePatch(BaseModel):
    activity_type: str

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type(cls, v):
        if v not in VALID_ACTIVITY_TYPES:
            raise ValueError(f"activity_type must be one of {sorted(VALID_ACTIVITY_TYPES)}")
        return v


class MealLogCreate(BaseModel):
    athlete_id: int
    log_method: str  # photo / text / quick-select / restaurant / water
    description: Optional[str] = None
    calories: Optional[float] = None
    carbs_g: Optional[float] = None
    protein_g: Optional[float] = None
    fat_g: Optional[float] = None
    iron_mg: Optional[float] = None
    calcium_mg: Optional[float] = None
    water_oz: Optional[float] = None
    edamam_raw: Optional[str] = None


class MealLogResponse(BaseModel):
    id: int
    athlete_id: int
    logged_at: str
    log_method: str
    description: Optional[str]
    calories: Optional[float]
    carbs_g: Optional[float]
    protein_g: Optional[float]
    fat_g: Optional[float]
    iron_mg: Optional[float]
    calcium_mg: Optional[float]
    water_oz: Optional[float]


class SweatOutputRequest(BaseModel):
    athlete_id: int
    event_id: int
    city: Optional[str] = None  # optional override; event's stored location is preferred


class RecipeSwapRequest(BaseModel):
    athlete_id: int
    disliked_recipe: str
    meal_timing_category: str


class RecipeGenerateRequest(BaseModel):
    athlete_id: int
    category: str
    allergies: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None


class PhotoMealAnalyzeRequest(BaseModel):
    athlete_id: int
    image_base64: str
    image_media_type: Optional[str] = "image/jpeg"
    allergies: Optional[List[str]] = None


class VoiceMealAnalyzeRequest(BaseModel):
    athlete_id: int
    transcription: str
    allergies: Optional[List[str]] = None


class MealPlanSlotUpdate(BaseModel):
    plan_date: str
    slot_name: str
    recipe_id: str


class MealPlanLogSlot(BaseModel):
    plan_date: str
    slot_name: str


class MealPlanGenerateRequest(BaseModel):
    athlete_id: int
    week_start: str
    overwrite_existing: bool = False


class FuelIQQuizAnswer(BaseModel):
    # Was a bare str — any other value (typo, stale client, garbage) never
    # matched fueliq_questions.correct_option and was silently recorded as a
    # wrong answer instead of being rejected as malformed input.
    selected_option: Literal["a", "b", "c"]


class FuelIQLessonComplete(BaseModel):
    perfect_quiz: bool = False


class FuelIQDailyChallengeVerdict(BaseModel):
    # Same gap as FuelIQQuizAnswer above — matches
    # fueliq_daily_challenge_service._VALID_VERDICTS exactly.
    guess: Literal["real", "myth"]


class OTPRequest(BaseModel):
    email: str


class OTPVerify(BaseModel):
    email: str
    code: str


# ── Shopping / Fueling Essentials ─────────────────────────────────────────────

class ShoppingItemCreate(BaseModel):
    athlete_id: int
    week_start: str          # ISO Sunday-anchored date e.g. "2026-06-14"
    name: str
    category: str
    source: str = "suggested"   # suggested | custom | pack

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        # An unrecognized category silently created an invisible "ghost" item
        # — CATEGORY_ORDER is the fixed set every group-rendering loop
        # iterates, so anything else never appears in any group, with no
        # error to the caller and no way to find it again except by deleting it.
        if v not in SHOPPING_CATEGORIES:
            raise ValueError(f"category must be one of {SHOPPING_CATEGORIES}")
        return v


class ShoppingItemPatch(BaseModel):
    checked: bool


class ShoppingPref(BaseModel):
    athlete_id: int
    food_name: str
    preference: str          # disliked | allergic | liked
    category: Optional[str] = None   # required when preference == "liked"


class PersonalFood(BaseModel):
    athlete_id: int
    name: str
    category: str


