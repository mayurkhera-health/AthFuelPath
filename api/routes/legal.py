from datetime import datetime
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from api.database import get_conn
from api.services.knowledge_admin import require_knowledge_admin_key

router = APIRouter()

SEED_DOCUMENTS = [
    {
        "slug": "privacy-policy",
        "title": "Privacy Policy",
        "content": """# Privacy Policy

**Last updated:** July 2026

## Introduction

AthFuelPath ("we," "our," or "us"), operated by Food Explorers LLC of San Jose, California, is committed to protecting the privacy of young athletes and their families. This Privacy Policy explains how we collect, use, and safeguard information when you use the AthFuelPath application.

## Information We Collect

We collect only what is scientifically necessary to generate personalized nutrition guidance:

- **Parent/Guardian information:** Name and email address
- **Athlete information:** First name, age, gender, height, weight, food allergies, dietary restrictions, and competition/training schedule
- **Usage data:** Meals logged, hydration entries, and schedule information you enter into the app

We do **not** collect payment information, location data, or any information beyond what is needed to deliver nutrition guidance.

## How We Use Your Information

Your information is used solely to:

- Generate personalized daily nutrition targets based on your athlete's age, weight, and training schedule
- Provide meal timing recommendations aligned with practice and game days
- Calculate hydration needs and recovery protocols
- Display your athlete's nutrition progress over time

## Data Storage and Security

All data is stored securely. We use industry-standard encryption for data in transit and at rest. Athlete data is associated with a parent/guardian account and is never accessible to other users.

## Data Sharing

We do **not** sell, rent, or share your personal information with third parties for marketing purposes. Your data is never sold.

We may use aggregate, anonymized data (with no personally identifiable information) to improve the app.

## Children's Privacy

AthFuelPath is designed for youth athletes ages 13–17. All accounts are created and managed by a parent or guardian. We comply with applicable children's privacy laws including COPPA.

## Data Deletion

You may request complete deletion of all your data at any time by emailing **purvi@dietsandlife.com**. We will delete all records within 30 days.

## Contact

Questions about this Privacy Policy? Contact us at **purvi@dietsandlife.com**.
""",
    },
    {
        "slug": "terms-of-service",
        "title": "Terms of Service",
        "content": """# Terms of Service

**Last updated:** July 2026

## Acceptance of Terms

By creating an account and using AthFuelPath ("the App"), operated by Food Explorers LLC of San Jose, California, you agree to these Terms of Service. If you do not agree, please do not use the App.

## Description of Service

AthFuelPath provides educational food guidance and nutrition information for youth soccer athletes ages 13–17. All recommendations are based on published pediatric sports nutrition research.

## Account Eligibility

- Accounts must be created by a parent or legal guardian
- The athlete must be between 13 and 17 years of age
- You must provide accurate information during account setup

## Acceptable Use

You agree to use AthFuelPath only for its intended purpose: supporting the nutrition and fueling habits of a youth athlete. You agree **not** to:

- Create accounts for athletes outside the 13–17 age range
- Share login credentials with unauthorized users
- Attempt to access other users' data
- Use the App for any commercial purpose without written permission

## Subscription and Payments

[Subscription terms will be added here when applicable.]

## Limitation of Liability

AthFuelPath provides **educational food guidance only** — not medical nutrition therapy. We are not responsible for health outcomes resulting from following or not following app recommendations. Always consult a licensed healthcare provider for medical concerns.

To the maximum extent permitted by law, AthFuelPath's total liability for any claims arising from your use of the App shall not exceed the amount you paid for the App in the prior 12 months.

## Termination

We reserve the right to terminate or suspend accounts that violate these terms. You may delete your account at any time.

## Changes to Terms

We will notify users of material changes to these Terms via the email address on file. Continued use after notice constitutes acceptance of the updated Terms.

## Governing Law

These Terms are governed by the laws of the State of California, without regard to conflict of law principles.

## Contact

Questions? Contact us at **purvi@dietsandlife.com**.
""",
    },
    {
        "slug": "medical-disclaimer",
        "title": "Medical Disclaimer",
        "content": """# Medical Disclaimer

**Please read this disclaimer carefully before using AthFuelPath.**

## Not Medical Advice

AthFuelPath provides **educational food guidance only**. The information, recommendations, meal plans, nutrition targets, and hydration guidance provided by this application are for general educational purposes and do **not** constitute medical advice, medical nutrition therapy, or clinical dietary treatment.

## No Doctor-Patient Relationship

Use of AthFuelPath does not create a doctor-patient relationship, dietitian-client relationship, or any other professional healthcare relationship between you and AthFuelPath or its developers.

## Consult a Healthcare Professional

Before making significant changes to your athlete's diet, especially if your athlete has:

- A diagnosed medical condition (diabetes, celiac disease, food allergies, heart conditions, etc.)
- An eating disorder or history of disordered eating
- Unusual fatigue, unexplained weight loss, or other health concerns
- A need for specialized nutrition support

**Please consult a licensed physician, registered dietitian nutritionist (RDN), or other qualified healthcare provider.**

## Sources and Accuracy

AthFuelPath's nutrition recommendations are based on peer-reviewed research and guidelines from:

- Everett MD 2025
- American Academy of Pediatrics (AAP)
- American College of Sports Medicine (ACSM)
- Academy of Nutrition and Dietetics (AND)
- Boston Children's Hospital RDN guidelines

While we strive for accuracy, nutrition science evolves. Our recommendations may not reflect the most current research at all times. Always verify important health information with a qualified professional.

## Emergency Situations

If an athlete experiences any of the following, **stop all activity and seek immediate medical attention**:

- Fainting or loss of consciousness
- Chest pain or pressure
- Severe dizziness or inability to stand
- Signs of severe dehydration (confusion, no urination, rapid heartbeat)
- Symptoms of heat stroke

**Call 911 in a medical emergency.**

## Limitation

AthFuelPath is not a substitute for professional medical care. The creators and operators of AthFuelPath accept no liability for health outcomes based on the use or non-use of information provided in this application.
""",
    },
    {
        "slug": "youth-athlete-disclaimer",
        "title": "Youth Athlete Disclaimer",
        "content": """# Youth Athlete Disclaimer

## Who AthFuelPath Is For

AthFuelPath is designed exclusively for youth soccer athletes between the ages of **13 and 17 years**. All accounts are created and managed by a parent or legal guardian.

## Parental Responsibility

By creating an account, the parent or guardian confirms:

- Their athlete is between 13 and 17 years of age
- They have read and accepted the Medical Disclaimer
- They understand that AthFuelPath provides educational food guidance — not medical treatment
- They will consult a healthcare professional for any medical nutrition concerns
- They take responsibility for supervising their athlete's use of the App

## Age-Appropriate Guidance

All nutrition recommendations, calorie targets, macronutrient ranges, and hydration guidance are calculated using evidence-based formulas for the pediatric population. AthFuelPath does **not** apply adult nutrition guidelines to youth athletes.

Our recommendations account for:

- Growth and development needs of athletes ages 13–17
- The elevated energy demands of competitive youth soccer
- Age-specific iron, calcium, and bone development requirements
- Safe weight management principles — AthFuelPath does not support caloric restriction for weight loss in youth athletes

## Weight and Body Composition

AthFuelPath does **not** encourage, recommend, or support weight loss programs for youth athletes. Our calorie targets are set to support healthy performance, growth, and development.

If you have concerns about your athlete's weight or body composition, please consult a pediatrician or registered dietitian.

## Eating Concerns

If you observe signs of disordered eating — including food restriction, binge behaviors, extreme weight loss, or excessive concern with body weight — please immediately consult a healthcare professional. AthFuelPath is not equipped to address eating disorders.

## Data Privacy for Minors

We collect the minimum data necessary to provide personalized guidance. Athlete data is protected and never shared or sold. Parents may request data deletion at any time.

## Contact

For questions about youth athlete guidelines: **purvi@dietsandlife.com**
""",
    },
    {
        "slug": "ai-recommendations-disclaimer",
        "title": "AI Recommendations Disclaimer",
        "content": """# AI Recommendations Disclaimer

## AI-Assisted Features

AthFuelPath uses artificial intelligence (AI) — specifically Anthropic's Claude — to generate personalized nutrition blueprints, meal suggestions, and recovery guidance. This disclaimer explains how AI is used and its limitations.

## What AI Does in AthFuelPath

AI is used to:

- Generate personalized **Nutrition Blueprints** that explain a young athlete's daily targets in age-appropriate language
- Suggest **meal ideas** based on the athlete's dietary restrictions and food preferences
- Provide **explanations** of nutrition science in plain language

## What AI Does NOT Do

All numeric calculations — calorie targets, protein ranges, hydration needs, iron and calcium requirements — are computed by **deterministic Python functions** based on peer-reviewed formulas. The AI does not invent numbers, dosages, or medical values.

Specifically:

- Calorie targets use the Everett 2025 RMR formula × PAL multiplier
- Iron and calcium requirements use NIH Recommended Dietary Allowances (RDAs)
- Protein and carbohydrate ranges follow ACSM position stands
- Hydration targets are based on ACSM fluid replacement guidelines

The AI explains these results in human language — it does not calculate them.

## Limitations of AI-Generated Content

AI-generated content may occasionally:

- Contain inaccuracies or outdated information
- Misinterpret complex individual health situations
- Provide generic guidance that does not account for specific medical conditions

**AI-generated content in AthFuelPath is not a substitute for advice from a licensed registered dietitian, physician, or other qualified healthcare professional.**

## AI and Medical Decisions

AthFuelPath's AI is explicitly instructed to:

- Never provide medical diagnoses
- Never recommend supplements, medications, or treatments
- Refer users to healthcare professionals for any medical concerns
- Avoid guidance for athletes with conditions requiring clinical care

## Knowledge Base

AthFuelPath's AI answers are grounded in an approved knowledge base of peer-reviewed nutrition content. The AI is constrained to answer only from this approved content and will state when it does not have sufficient information.

## Questions

If you believe an AI-generated recommendation was inaccurate or harmful, please contact us immediately at **purvi@dietsandlife.com**.
""",
    },
]


def seed_legal_documents(conn) -> None:
    """Insert default documents if they don't exist. Also backfills any
    existing row still carrying the old pre-rebrand "Fueling2Win" content —
    those rows were auto-seeded from an earlier version of SEED_DOCUMENTS,
    never hand-edited, so overwriting them here is safe; a real admin edit
    via PUT /{slug} would no longer contain that string and is left alone."""
    for doc in SEED_DOCUMENTS:
        existing = conn.execute(
            "SELECT id, content FROM legal_documents WHERE slug = ?", (doc["slug"],)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO legal_documents (slug, title, content, updated_at) VALUES (?, ?, ?, ?)",
                (doc["slug"], doc["title"], doc["content"], datetime.utcnow().isoformat()),
            )
        elif "Fueling2Win" in existing["content"]:
            conn.execute(
                "UPDATE legal_documents SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                (doc["title"], doc["content"], datetime.utcnow().isoformat(), existing["id"]),
            )
    conn.commit()


class LegalUpdate(BaseModel):
    content: str


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/")
def list_legal_documents():
    conn = get_conn()
    try:
        seed_legal_documents(conn)
        rows = conn.execute(
            "SELECT slug, title, updated_at FROM legal_documents ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{slug}")
def get_legal_document(slug: str):
    conn = get_conn()
    try:
        seed_legal_documents(conn)
        row = conn.execute(
            "SELECT slug, title, content, updated_at FROM legal_documents WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Document '{slug}' not found.")
        return dict(row)
    finally:
        conn.close()


# ── Admin endpoint ────────────────────────────────────────────────────────────

@router.put("/{slug}")
def update_legal_document(
    slug: str,
    body: LegalUpdate,
    x_admin_key: Optional[str] = Header(None),
):
    """Update a legal document. Requires X-Admin-Key header."""
    require_knowledge_admin_key(x_admin_key)
    if not body.content.strip():
        raise HTTPException(400, "Content cannot be empty.")

    conn = get_conn()
    try:
        seed_legal_documents(conn)
        row = conn.execute(
            "SELECT id FROM legal_documents WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Document '{slug}' not found.")
        conn.execute(
            "UPDATE legal_documents SET content = ?, updated_at = ? WHERE slug = ?",
            (body.content.strip(), datetime.utcnow().isoformat(), slug),
        )
        conn.commit()
        return {"slug": slug, "updated_at": datetime.utcnow().isoformat(), "message": "Document updated."}
    finally:
        conn.close()
