"""Seed 4 launch articles. Safe to re-run — skips if title already exists."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.database import get_conn

ARTICLES = [
    {
        "title": "The 3-Hour Pre-Game Meal: What to Eat Before You Compete",
        "summary": "The meal you eat 3 hours before a game is the single biggest lever you have on game-day performance. Here's exactly what to put on your plate.",
        "category": "gameday",
        "audience": "both",
        "read_time_min": 5,
        "author": "Purvi Shah MS RDN",
        "science_source": "ACSM Position Stand on Nutrition and Athletic Performance (2016)",
        "published_date": "2026-06-14",
        "is_active": 1,
        "body_markdown": """## Why the Pre-Game Meal Is Non-Negotiable

Your muscles run on glycogen — a stored form of carbohydrates. By the time you wake up on game day, overnight fasting has already drawn down your glycogen reserves by 20–30%. The pre-game meal is your opportunity to top them off before you step onto the field.

Research from the American College of Sports Medicine is unambiguous: athletes who eat a carbohydrate-rich meal 3–4 hours before competition sustain higher intensity for longer and make better decisions late in the game.

## What to Eat

**The ideal pre-game plate looks like this:**

- **Complex carbohydrates (50–60% of the plate):** Brown rice, whole-grain pasta, quinoa, or oatmeal. These digest steadily and keep blood sugar stable throughout the match.
- **Lean protein (20–25%):** Grilled chicken, turkey, eggs, or Greek yogurt. Protein slows digestion slightly — just enough to sustain energy without causing cramping.
- **Low fat, low fiber (rest of the plate):** Now is not the time for high-fat sauces or raw broccoli. Fat and fiber take too long to clear the stomach and divert blood flow away from your working muscles.

**Proven examples:**
- Turkey and provolone on whole-wheat bread + a banana
- Chicken breast with brown rice + steamed zucchini
- Scrambled eggs with whole-grain toast + orange slices

## The Timing Rule

Aim to finish eating **3 hours before kickoff**. This gives your stomach enough time to empty — solid meals need 2–4 hours to fully digest. If you eat too close to the game, blood flow splits between digestion and your muscles, which causes cramping and slows your first step.

**If you only have 1–2 hours:** Scale down to a small, simple-carb snack (a banana, toast with honey, pretzels). Skip fat and protein entirely.

## What to Avoid

- Fried foods or fast food (high fat → slow gastric emptying)
- High-fiber vegetables raw (bloating and cramping risk)
- Sugary drinks or candy (blood sugar spike + crash mid-game)
- Trying a new food on game day (if your body doesn't know it, game day isn't the time to find out)

## The Bottom Line

The pre-game meal isn't complicated. Build your plate around complex carbs, keep it low in fat and fiber, finish eating 3 hours before game time, and your legs will feel it when the second half starts.
""",
    },
    {
        "title": "The Recovery Window: Why the 30 Minutes After Training Are Everything",
        "summary": "Most athletes skip the most important nutritional window of the day. Here's what happens inside your muscles after training — and how to use it.",
        "category": "recovery",
        "audience": "both",
        "read_time_min": 4,
        "author": "Purvi Shah MS RDN",
        "science_source": "IOC Consensus Statement on Sports Nutrition (2015); Ivy & Portman, Nutrient Timing (2004)",
        "published_date": "2026-06-14",
        "is_active": 1,
        "body_markdown": """## What Happens in Your Muscles After Training

The moment training ends, two things happen simultaneously inside your body:

1. **Glycogen resynthesis begins** — your muscles urgently restock the carbohydrate fuel you just burned.
2. **Muscle protein breakdown slows** — if protein is available, your muscles start rebuilding damaged fibers immediately.

The catch: both processes are dramatically faster in the first 30 minutes post-exercise than at any other point in the day. This is because insulin sensitivity is at its peak right after training — cells are "open" and absorb nutrients far more efficiently.

Miss this window, and recovery still happens — it just takes hours longer and you go to bed with more muscle breakdown than necessary.

## The Magic Ratio

The research is clear: **3:1 to 4:1 carbohydrates to protein** triggers the optimal recovery response.

- Carbs restore glycogen stores
- Protein provides the building blocks (amino acids) for muscle repair
- Together, they produce a higher insulin response than either alone

**Practical targets within 30 minutes of finishing:**
- 30–60 g carbohydrates
- 15–25 g protein

## The Gold Standard: Chocolate Milk

Multiple randomized controlled trials have validated low-fat chocolate milk as an exceptional recovery drink for athletes. Its natural composition — roughly 4:1 carbs to protein, plus fluid and electrolytes — lines up almost exactly with what the research recommends. It's cheap, portable, and effective.

**Other solid options:**
- Greek yogurt with berries and a drizzle of honey
- Turkey wrap with a banana
- Smoothie: milk + banana + peanut butter

## Why Youth Athletes Miss This Window

The most common reason: no one is ready with food right after practice. The bag is in the car, dinner isn't until 7:30, and by the time the athlete eats, the window is gone.

The fix is simple: pack a recovery snack in the sports bag — a chocolate milk, a fruit pouch + string cheese, or a small peanut butter sandwich. It doesn't need to be a meal. It just needs to arrive within 30 minutes.

## The Bottom Line

Train hard. Recover harder. The 30 minutes after practice are the single most productive nutritional window of the day — and the easiest to miss. Build the habit now.
""",
    },
    {
        "title": "Iron and Athletic Performance: What Every Young Athlete Needs to Know",
        "summary": "Iron deficiency is the most common nutritional deficiency in adolescent athletes — and it's invisible until performance starts dropping. Here's what it looks like and how to fix it.",
        "category": "iron",
        "audience": "both",
        "read_time_min": 5,
        "author": "Purvi Shah MS RDN",
        "science_source": "Everett MD 2025; Pedlar et al., British Journal of Sports Medicine (2018)",
        "published_date": "2026-06-14",
        "is_active": 1,
        "body_markdown": """## Why Iron Matters for Athletes

Iron is what makes red blood cells work. Every red blood cell in your body contains hemoglobin — a protein built around iron — that carries oxygen from your lungs to your muscles. Less iron means fewer functioning red blood cells, which means less oxygen reaching working muscles during a game.

The result is unmistakable: fatigue arrives earlier, the legs feel heavy, and high-intensity efforts become harder to sustain.

## Who Is Most at Risk

Iron deficiency is the most common nutritional deficiency in adolescent athletes, but it hits some groups harder than others:

- **Female athletes:** Menstruation causes regular iron loss each month. Combined with the demands of training, female athletes need 15 mg of iron per day — well above the 8 mg recommended for non-athletes their age.
- **Runners and high-mileage athletes:** Foot-strike hemolysis (a process where repeated impact actually destroys red blood cells) creates an additional iron drain unique to running athletes.
- **Athletes following vegetarian or plant-based diets:** Plant-based iron (non-heme iron) is absorbed at 2–5% efficiency — significantly lower than the 15–35% absorption rate of meat-based (heme) iron.

Recent research from Everett MD (2025) found that **52% of female adolescent athletes** show signs of iron deficiency, most without any symptoms until performance is already compromised.

## What Iron Deficiency Looks Like

Early-stage deficiency (depleted stores, normal hemoglobin) has no visible symptoms — blood tests are the only way to catch it early. As it progresses:

- Persistent fatigue that sleep doesn't fix
- Decreased endurance and earlier onset of breathlessness during high-intensity efforts
- Pale inner eyelids or pale skin tone
- Difficulty concentrating during school or games
- Increased illness (iron plays a role in immune function)

## How to Build Iron Through Food

**Heme iron (most absorbable — from animal sources):**
- Lean beef, lamb
- Dark poultry meat (thighs, drumsticks)
- Oysters, clams, tuna

**Non-heme iron (plant-based — pair with vitamin C to boost absorption):**
- Lentils and beans (1 cup cooked = 6–7 mg iron)
- Tofu and tempeh
- Fortified cereals
- Spinach and dark leafy greens
- Pumpkin seeds

**The vitamin C pairing trick:** Non-heme iron absorption nearly doubles when consumed with a vitamin C source. Add orange slices to a lentil salad. Squeeze lemon on spinach. Drink orange juice with a fortified cereal.

**What blocks iron absorption:** Coffee, tea, and calcium supplements taken at the same time as iron-rich foods reduce absorption significantly. Time them apart.

## Should My Athlete Get Tested?

Yes — if your athlete shows any of the signs above, or if she's a female athlete with a heavy training load, an annual iron panel (serum ferritin + hemoglobin) is a smart preventive step. Ask your pediatrician at the next sports physical.

**AthFuelPath does not recommend iron supplementation without confirmed deficiency on a blood test.** Over-supplementation can cause toxicity, and supplementing without knowing baseline levels can mask the actual problem.

## The Bottom Line

Iron deficiency is silent, common, and correctable. Prioritize iron-rich foods — especially for female athletes. If fatigue, heavy legs, or dropping times persist despite adequate sleep and nutrition, get a blood panel.
""",
    },
    {
        "title": "Hydration 101: How to Stay Ahead of Thirst on Game Day",
        "summary": "By the time you feel thirsty, you're already 1–2% dehydrated — and your performance has already started to drop. Here's the hydration schedule that keeps youth athletes sharp from kickoff to final whistle.",
        "category": "hydration",
        "audience": "both",
        "read_time_min": 4,
        "author": "Purvi Shah MS RDN",
        "science_source": "American Academy of Pediatrics Policy Statement on Sports Drinks (2011); Casa et al., JSCR (2010)",
        "published_date": "2026-06-14",
        "is_active": 1,
        "body_markdown": """## The Thirst Problem

Thirst is a lagging indicator. By the time your brain registers thirst and signals you to drink, your body has already lost 1–2% of its body weight in fluid. At that level of dehydration, research shows:

- Reaction time slows by up to 9%
- Aerobic capacity drops by 5–10%
- Decision-making under pressure deteriorates

Youth athletes are especially vulnerable because they generate more body heat per kilogram of body weight than adults, sweat less efficiently in high heat, and are less likely to drink proactively during training.

## The Game-Day Hydration Schedule

Don't wait until kickoff. Build a hydration plan that starts the night before:

| Timing | Target |
|---|---|
| Night before | 16–24 oz of water with dinner |
| Morning of game | 16 oz of water with breakfast |
| 2–3 hours before kickoff | 8–16 oz of water |
| 30 minutes before kickoff | 8 oz of water |
| During the game | 4–8 oz every 15–20 minutes |
| Post-game | Sip water or chocolate milk freely until urine is pale yellow |

## Water vs. Sports Drinks: When Each Wins

**Water is sufficient for:**
- Training sessions under 60 minutes
- Practice in moderate heat with moderate sweat rates
- Everyday hydration throughout the day

**Sports drinks earn their place for:**
- Games or training over 75 minutes
- Hot and humid conditions (over 85°F)
- Tournament days with multiple games (sodium replacement becomes critical between games)
- Notably high sweat rates (visible sweat dripping, white salt stains on clothes)

Sports drinks that contain 6–8% carbohydrate concentration and 110–170 mg sodium per 8 oz are the most effective. Diluting 50/50 with water is a valid option for younger athletes sensitive to sweetness.

## The Urine Color Check

The simplest way to monitor hydration status is urine color:

- **Pale yellow (like lemonade):** Well hydrated — maintain your intake
- **Dark yellow (like apple juice):** Dehydrated — drink 16 oz now
- **Clear:** Overhydrated — ease up on water for the next hour

Overhydration (hyponatremia) is rare but real. Athletes who drink excessive amounts of plain water during prolonged events without any sodium intake can dilute blood sodium levels, causing nausea and fatigue. On multi-game tournament days, pair water with electrolyte intake.

## Signs Your Athlete Is Under-Hydrating

Watch for these during or after practice:
- Headache during or after training
- Muscle cramps, especially in calves and hamstrings
- Dizziness or lightheadedness when standing up quickly
- Irritability out of proportion to the situation
- Dark, strong-smelling urine post-practice

## The Bottom Line

Hydration is a game-day habit, not a half-time reaction. Start drinking the night before, follow the schedule above, and use urine color as your daily check-in. An athlete who arrives to kickoff well hydrated will outperform an equally fit athlete who started the day behind on fluids.
""",
    },
]


def run():
    conn = get_conn()
    inserted = 0
    skipped = 0
    for art in ARTICLES:
        existing = conn.execute(
            "SELECT id FROM articles WHERE title = %s", (art["title"],)
        ).fetchone()
        if existing:
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO articles
               (title, summary, body_markdown, category, audience,
                read_time_min, author, science_source, published_date, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                art["title"], art["summary"], art["body_markdown"],
                art["category"], art["audience"], art["read_time_min"],
                art["author"], art["science_source"], art["published_date"],
                art["is_active"],
            ),
        )
        inserted += 1
    conn.commit()
    conn.close()
    print(f"Seeded {inserted} articles, skipped {skipped} (already exist).")


if __name__ == "__main__":
    run()
