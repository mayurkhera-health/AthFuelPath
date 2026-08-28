import type { EventName } from "@/lib/analytics";

/**
 * All marketing copy.
 *
 * VOICE: write like one parent talking to another. Short sentences. Plain words.
 * Say the thing, then stop. If a sentence would fit on any other company's site,
 * it is filler — cut it or make it specific.
 *
 * NEVER PUBLISH: calorie/macro/gram/percentage/weight/BMI figures · supplement
 * advice for under-18s · performance or health guarantees · the words "diet",
 * "restriction", "missed", "behind", "deficit", "failed" · invented testimonials,
 * statistics or "trusted by X families" · any placeholder text, badge or caption.
 *
 * ALWAYS: third person about the athlete when addressing a parent · sentence case ·
 * win-framed language ("coming up", never "missed").
 *
 * BANNED SHAPES (they read as machine-written):
 *  · em-dashes as a rhythm device — cap the whole file at about six, use full stops
 *  · "not just X, it's Y" and every antithesis pair
 *  · three-item lists used for cadence rather than because there are three things
 *  · trailing "-ing" clauses that explain what the sentence already said
 *  · puffery: seamless, robust, comprehensive, empower, unlock, journey, elevate
 *
 * Headline lengths: h1 ≤5 words / section headline ≤8 / sub-headline ≤28 /
 * card title ≤5 / card body ≤24 / button label 2–4.
 */

export const site = {
  name: "AthFuelPath",
  supportEmail: "support@athfuelpath.com",
  company: "Food Explorers LLC",
  location: "San Jose, California",
  price: "$14.99",
  priceUnit: "per athlete / month",
  trialDays: 7,
  disclaimer:
    "AthFuelPath gives you sports nutrition guidance to learn from. It is not medical nutrition therapy.",
};

/** One label per action, site-wide (spec §2). */
export const cta = {
  primary: "Join the waitlist",
  secondary: "See how it works",
  founder: "Meet the founder",
  allQuestions: "All questions",
  safety: "Read our youth data policy",
  login: "Log in",
};

/**
 * Required line under every primary CTA pair.
 *
 * WAITLIST MODE (2026-08-28). Signup is not open: the account-creation flow is
 * not wired and the app sends a 6-digit code, not the link this site used to
 * promise. Until that is real, every CTA leads to the waitlist and this line
 * must describe only what actually happens. No trial length, no price, no
 * "takes 4 minutes" — none of those are true yet.
 */
export const trialLine = "No card. No spam. One email when it opens.";

/* --------------------------------------------------------------- Waitlist
 * The /signup route in waitlist mode.
 *
 * The free-text question comes FIRST, before the email box, on purpose. It
 * reframes the form from "give us your address" to "tell us the problem", and
 * the parents who bother to answer are the ones worth hearing from. Email is
 * the only required field; every extra required field costs sign-ups.
 *
 * NEVER: a price, a trial length, a launch date, or any wording that implies
 * an account is being created. Nothing here may promise a thing that has not
 * been built — that is the whole reason this page replaced signup.
 */
export const waitlist = {
  eyebrow: "Not open yet",
  h1: "Tell us what's hard right now.",
  sub: "AthFuelPath isn't open to families yet. Leave your email and we'll tell you the day it is. If you answer the first question, Purvi reads every one.",
  fields: {
    pain: {
      label: "What's the hardest part of feeding your athlete right now?",
      hint: "A sentence is plenty. This is the most useful thing you can give us.",
      placeholder: "Late practices and nobody's hungry at 9pm…",
    },
    email: { label: "Your email", hint: "Where we send the one email." },
    parent: { label: "Your name", hint: "So Purvi knows who she is writing back to." },
    /**
     * A child's first name, on a public form, before any consent flow exists.
     * Deliberately optional, deliberately first-name-only, and deliberately
     * labelled so a parent can see it is not required. Do not make this
     * required, do not ask for a surname, and do not add date of birth — the
     * age band below is enough to segment on.
     */
    athlete: { label: "Your athlete's first name", hint: "Optional. First name is plenty." },
    age: { label: "Your athlete's age", options: ["Under 13", "13", "14", "15", "16", "17", "18 or older"] },
    club: { label: "Club or team", hint: "Optional. Helps us know where to start." },
    /**
     * The concierge offer, as one optional checkbox.
     *
     * NOT called a consultation, a session, or counselling: site.disclaimer
     * draws the line at "sports nutrition guidance, not medical nutrition
     * therapy", and those words cross it.
     *
     * Says NOTHING about price, on purpose. That is only safe because the box
     * is an expression of interest and the copy says so — "she'll be in touch"
     * means terms get settled in that conversation, not here. If this ever
     * becomes a booking rather than an enquiry, a price or an explicit "no
     * charge" has to appear with it, per the rule dietitian.billing follows.
     *
     * "A few each week" is load-bearing: this is one person working by hand,
     * and it caps expectations before twenty people tick the box.
     */
    oneToOne: {
      label: "I'd like Purvi to look at my athlete's week",
      hint: "Purvi Shah, MS, RDN does a few of these each week while we build. Tick this and she'll be in touch.",
    },
  },
  submit: "Join the waitlist",
  sending: "Sending…",
  /** Says only what actually happens. No account, no link, no timeline. */
  done: {
    h: "You're on the list.",
    p: "We'll email you when AthFuelPath opens to families. Nothing else, and nothing in between.",
    pAnswered: "Purvi reads every answer to that first question. If yours needs a reply, you'll get one.",
  },
  error: "That didn't send. Try again, or email us at",
};

/**
 * Sits above every FAQ on /faq. The Setup answers are written in the present
 * tense ("setup takes about four minutes") because they describe the product as
 * built — but nobody can reach it yet, so without this line a parent reads them
 * as an invitation and wonders why they cannot sign up. Remove this the day the
 * app opens, not before.
 */
export const faqNotice =
  "AthFuelPath isn't open to families yet. These answers describe how it works, so you know what you're joining the waitlist for.";

/* --------------------------------------------------------------- Coaches
 * /coaches — the Coaches Corner.
 *
 * The team dashboard is a CODED MOCK, not a capture of a shipped screen. Every
 * other product image on this site is a real screenshot; this one is drawn.
 * That is defensible only while the page frames it as early access, which it
 * does. Replace the mock with a real capture before a coach sees both.
 *
 * NEVER on this page: anything an individual athlete ate, any weight, any
 * suggestion a coach can see one athlete's plate. The whole proposition is
 * squad-level. safety.claims promises parents control what is visible and the
 * athlete is told what a parent sees — a coach is a third party neither of them
 * agreed to, so team aggregate is not a nicety, it is the constraint.
 *
 * NEVER: "available now", a login for coaches, or a date. Early access with a
 * first group of clubs is true. A ship date is not.
 */
export const coaches = {
  eyebrow: "Coaches & athletic directors",
  h1: "The part of the season you can't see.",
  sub: "You watch every session. You don't see the seven meals between them, and by the second game of a tournament that gap is the difference. AthFuelPath shows you how the team is fueling, without adding anything to your week.",
  chips: ["Nothing for you to set up", "Team totals only", "Soccer, 13–17"],

  points: {
    h2: "Three minutes a week. That's the whole ask.",
    sub: "Parents set it up. Athletes use it. You look when you want to.",
    items: [
      {
        n: "01",
        h: "You add nothing.",
        p: "No rosters to maintain, no data to enter, no app for your athletes to be nagged about. Families run it. You get the view.",
      },
      {
        n: "02",
        h: "Team totals, never a plate.",
        p: "You see how the squad is fueling as a group. What any one athlete ate stays between them and their parent.",
      },
      {
        n: "03",
        h: "Built around your fixtures.",
        p: "Tournament weekends and two-game days are where fueling decides the second half. The week you see is the week you scheduled.",
      },
    ],
  },

  dash: {
    badge: "Early access · opening to clubs this season",
    h2: "Your squad, at a glance.",
    sub: "One screen, team level only. Nothing about any one athlete's plate, and nothing for you to keep updated.",
    team: "Twin Creeks SC · U15 Boys",
    week: "Week of 8 Sep",
    metrics: [
      { label: "Fueling days followed", value: "78%", pct: 78, note: "Squad average, last 7 days" },
      { label: "Pre-game meal on time", value: "15", suffix: "/18", pct: 83, note: "Saturday's fixture" },
      /* The only number a coach can act on, and the only one that is not about
         eating at all — it is onboarding status. Keep it last and keep it amber. */
      { label: "Not set up yet", value: "3", pct: 17, note: "Families still to finish onboarding", warn: true },
    ],
    days: [
      { d: "MON", k: "Rest" }, { d: "TUE", k: "Train", train: true }, { d: "WED", k: "Train", train: true },
      { d: "THU", k: "Rest" }, { d: "FRI", k: "Train", train: true }, { d: "SAT", k: "Game", game: true },
      { d: "SUN", k: "Game", game: true },
    ],
    /** Load-bearing. This sentence is why a coach can forward the app to 18 families. */
    privacy: {
      h: "Team numbers only.",
      p: "Coaches never see an individual athlete's meals, weight or photos. Parents control what is shared, and their athlete is told what a parent can see.",
    },
  },

  form: {
    h2: "Bring it to your club.",
    sub: "We are opening the coach view to a first group of clubs this season. Tell us what your week looks like and what you would want on it, and we will bring you in early.",
    name: { label: "Your name" },
    club: { label: "Club, school or program" },
    role: { label: "Your role", options: ["Coach", "Athletic director", "Trainer", "Club admin"] },
    want: {
      label: "What would you want to see on it?",
      hint: "One line is plenty. It shapes what your club sees first.",
      placeholder: "Whether the squad ate before a 10am kickoff…",
    },
    email: { label: "Email", hint: "Purvi Shah, MS, RDN reads these herself." },
    submit: "Request early access",
    sending: "Sending…",
    done: {
      h: "Thanks — that's with us.",
      p: "Purvi will be in touch about bringing your club into the first group.",
    },
    error: "That didn't send. Try again, or email us at",
  },
};

export const nav = {
  links: [
    { label: "How It Works", href: "/#how-it-works" },
    { label: "For Parents", href: "/#for-parents" },
    { label: "Coaches", href: "/coaches" },
    { label: "Our Story", href: "/our-story" },
  ],
  /**
   * null while the app is closed to families (2026-08-28). Nobody has an
   * account, so a "Log in" link is a door onto an empty room. Header and the
   * mobile sheet both check for null — restore this line to bring it back.
   */
  login: null as { label: string; href: string } | null,
  primary: { label: cta.primary, href: "/signup" },
};

/* ------------------------------------------------------------------ S1 */
export const hero = {
  eyebrow: "Sports nutrition for soccer players 13–17",
  h1: "Fuel smarter. Play stronger.",
  sub: "Add their practices and games. AthFuelPath works out what your player should eat and when, around the day they actually have.",
  founder: {
    name: "Purvi Shah, MS, RDN",
    line: "Registered Dietitian and soccer mom. She built this around her own daughter's season.",
  },
  chips: ["Parents run it", "Soccer only", "Real food"],
};

/* ------------------------------------------------------------------ S3 */
export type AnswerRow = { time: string; label: string; note?: string; event?: boolean };
export type ParentQuestion = {
  q: string;
  badge: string;
  answer: string;
  rows: AnswerRow[];
  /** Long-form article, linked from /faq. Panel CTA is phase 3. */
  slug: string;
};

export const questions = {
  eyebrow: "Ask it. See the answer.",
  /**
   * Names a thing parents actually do rather than restating the value prop.
   * Deliberately NOT a two-clause balanced pair: hero.h1 is the one place that
   * shape is allowed to live, and it only reads as a signature while it is the
   * only one on the page.
   */
  h2: "The questions you Google at 4pm.",
  listNote: "Every answer is built from the schedule you already keep.",
  /** Times and food categories only — never a calorie, macro, gram or portion figure. */
  items: [
    {
      q: "What should she eat before a 5:30 practice?",
      badge: "Practice day · Tuesday",
      slug: "before-a-530-practice",
      answer: "A proper meal around 3:30. Then something small she already likes at 5. Put practice on her schedule and both show up on their own.",
      rows: [
        { time: "3:30 PM", label: "Pre-training meal", note: "Time to digest" },
        { time: "5:00 PM", label: "Pre-training snack", note: "Quick, familiar" },
        { time: "5:30 PM", label: "Soccer practice", note: "90 minutes", event: true },
        { time: "7:15 PM", label: "Recovery", note: "First window after" },
      ],
    },
    {
      q: "Did he eat enough after the game?",
      badge: "Game day · Saturday",
      slug: "after-the-game",
      answer: "Kids often aren't hungry after a hard game. Don't wait for hunger. Get something in within the hour, then a real dinner at home.",
      rows: [
        { time: "2:00 PM", label: "Final whistle", event: true },
        { time: "2:30 PM", label: "Recovery window", note: "Something now, not later" },
        { time: "4:00 PM", label: "Drive home", note: "Keep drinking" },
        { time: "6:30 PM", label: "Full dinner", note: "Rebuild for tomorrow" },
      ],
    },
    {
      q: "What do we pack for tournament weekend?",
      badge: "Tournament · 2 games",
      slug: "tournament-weekend",
      answer: "The gap between games decides how the second one goes. Pack food she already eats, sized to the day, the night before.",
      rows: [
        { time: "Night before", label: "Pack list ready", note: "Nothing bought at the field" },
        { time: "7:30 AM", label: "Game-day breakfast", note: "Before a 10:00 kickoff" },
        { time: "10:00 AM", label: "Game 1", event: true },
        { time: "1:30 PM", label: "Between-game fuel", note: "Sized to the gap" },
      ],
    },
    {
      q: "What should she eat between two games?",
      badge: "Two-game day",
      slug: "between-two-games",
      answer: "Start at the second kickoff and count backwards. Three hours means a small meal. Ninety minutes means a snack and steady drinking.",
      rows: [
        { time: "12:00 PM", label: "Game 1 ends", event: true },
        { time: "12:30 PM", label: "Small meal", note: "If the gap is 3 hours" },
        { time: "2:30 PM", label: "Snack + fluids", note: "90 minutes out" },
        { time: "4:00 PM", label: "Game 2", note: "Ready to go again" },
      ],
    },
  ] satisfies ParentQuestion[],
};

/* ------------------------------------------------------------------ S4 */
/** Live club-calendar integrations. Only add a name once the import actually works. */
export const providers = ["BYGA", "PlayMetrics"];
export const providersNote = "More club platforms are coming. Not on either one? You can add sessions by hand in a couple of taps.";

export const schedule = {
  eyebrow: "Schedule → fueling",
  h2: "Their soccer schedule becomes their food plan.",
  body: "Add practices, games and tournaments yourself, or pull in the club calendar you already use. AthFuelPath builds each day around when your player needs to eat.",
  chipsLabel: "Imports from",
  syncNote: "When the club moves a session, the day updates on its own.",
  weekLabel: "This week",
  weekNote: "Every session turns into a set of eating times, like the ones above.",
};

/**
 * The week as the app receives it. This section shows the INPUT — the schedule —
 * because the questions explorer above already shows the fueling day it produces.
 * Showing both was the same practice-day timeline twice, 800px apart.
 */
export type WeekEvent = { day: string; kind: string; time: string; windows: number; game?: boolean };

export const week: WeekEvent[] = [
  { day: "Mon", kind: "Practice", time: "5:30 PM", windows: 4 },
  { day: "Wed", kind: "Practice", time: "6:00 PM", windows: 4 },
  { day: "Sat", kind: "Game", time: "10:00 AM", windows: 4, game: true },
  { day: "Sun", kind: "Tournament", time: "8:00 AM", windows: 6, game: true },
];

/* ------------------------------------------------------------- S5 (cook) */
/**
 * What to cook this week. Markets what the app actually does today:
 * fueling moment → recipe choice → grocery list.
 *
 * Absorbed the standalone Meal Plan section on 2026-08-28. The two were the
 * same argument twice — pick recipes, get one grocery list — and Cook's own
 * closing strip already said so. The week view, "covered, no recipe needed"
 * and the free-text box now live here as points 03 and 04.
 *
 * NEVER: ingredient quantities (the product has none) · that the recipe list a
 * parent browses is filtered by the day's session — it is not. Only the
 * generated week uses event_type (api/routes/meal_plans.py); the picker filters
 * on allergies and food limits alone. The schedule shapes the plan, never the
 * recipes you scroll · allergy-safe / allergen-free · "know exactly what to
 * buy" · AI meal planning · any calorie/macro/gram.
 */
export type CookPoint = { n: string; h: string; p: string; labels?: string[]; safety?: string; p2?: string };
export type GroceryItem = { name: string; from?: string; atHome?: boolean };

export const cook = {
  eyebrow: "Every week, the same question",
  h2: "What should I cook this week?",
  h2b: "And can someone just make the grocery list?",
  /**
   * body opens on the problem, body2 answers it. Do not merge them: a parent
   * recognises the 6pm scramble before they recognise "weekly meal planning",
   * and the frames below have to be earned before they are shown.
   */
  body: "You get in late, your player has practice in an hour, and nothing in the fridge goes together. Sunday you had time. Wednesday you don't.",
  body2: "AthFuelPath puts all seven days on one screen, every eating window marked training or rest. Fill the ones that matter, and the ingredients from everything you picked turn into one list.",
  points: ([
    {
      n: "01",
      h: "Recipes that fit the moment.",
      p: "Before training. After a game. Tournament days. Plain old Tuesday dinner. Pick the moment and see meals that suit it.",
      labels: ["Pre-practice", "Pre-game", "Recovery", "Tournament", "Breakfast", "Dinner"],
    },
    {
      n: "02",
      h: "It knows what your athlete can't eat.",
      p: "AthFuelPath leaves out recipes that clash with the allergies and food limits saved on their profile.",
      /** Standing safety line — must sit directly beneath, never in a footer. */
      safety: "We filter using the allergies and food limits saved on your athlete's profile. Always read the labels yourself.",
    },
    {
      n: "03",
      h: "Your own food counts.",
      p: "AthFuelPath suggests. You decide. Nobody knows better than you what will actually get eaten.",
      p2: "Type in what you are actually cooking and it goes on the plan next to everything else.",
    },
    {
      n: "04",
      h: "Nothing to fill in twice.",
      p: "Some meals are already handled. Mark the window covered and the plan moves on without asking again.",
    },
  ] satisfies CookPoint[]) as CookPoint[],
  atHome: {
    h: "Already have it?",
    p: "Tick off what's in your kitchen already, so the list only shows what you still need to buy.",
  },
  /** Both are real controls on the week review sheet. Do not add a third. */
  weekNote: "You can see how much of the week is done at a glance, then print the plan or send it to whoever is cooking.",
  closing: {
    h: "From the plan to the dinner table.",
    p: "Pick meals they'll actually eat and start the week with one list.",
    flow: ["The week", "Recipes", "One list"],
  },
};

/* ------------------------------------------------------------------ S5b
 * AI Fuel Coach.
 *
 * BETA stays on the eyebrow and the pricing bullet for exactly as long as the
 * app shows BETA on the Fuel Coach screen. Remove from both at the same time.
 *
 * The transcript below is a WORD-FOR-WORD transcription of
 * public/screens/coach-chat.webp. It is the accessible + indexable copy of the
 * same exchange, so the image ships with alt="". If the screenshot is ever
 * replaced, retype this from the new capture. Never edit one without the other,
 * and never write a Coach answer that the product did not produce.
 */
export const coach = {
  eyebrow: "AI Fuel Coach · Beta",
  h2: "Fueling questions don't wait for a good time.",
  body: "At home, in the car, at a tournament. Ask what she should eat right now, and the answer knows her schedule and what she can't eat.",
  body2: "You get a real answer. Food you already have, or food you can buy from where you're standing.",
  situations: [
    { label: "Before practice", q: "She has practice in 45 minutes and she's hungry. What should she eat?" },
    { label: "After training", q: "He isn't hungry after practice. Does he still need to eat something?" },
    { label: "Eating out", q: "We're at Chipotle before tonight's game. What should she order?" },
  ],
  travel: {
    h: "Away for a tournament?",
    p: "Share your location with the question and the Fuel Coach can find real places to eat nearby, then help you think through the best choice for the day your athlete is having.",
    privacy: "Location is only requested when the question needs it.",
  },
  /** Word-for-word from public/screens/coach-chat.webp. Do not paraphrase. */
  transcript: {
    caption: "A real answer from the app, word for word.",
    question: "I have practice in 2 hrs. Recommend me something I can eat and also I am a little particular about food textures",
    intro: "Got it! Since Kabir's practice is in 2 hours, we'll focus on a full meal that's easy to digest and packed with carbs and protein, just like the Academy of Nutrition and Dietetics recommends. Since you mentioned texture preferences, I'll suggest options that are soft, mild, or easy to chew.",
    listHead: "Here's what to prepare for Kabir:",
    list: [
      { food: "Pasta with grilled chicken and a light tomato sauce", why: "soft, mild flavor, and easy to digest" },
      { food: "Oatmeal with banana slices and a drizzle of honey", why: "creamy texture, gentle on the stomach" },
      { food: "Whole grain toast with scrambled eggs and orange juice", why: "soft eggs, buttery toast, and smooth juice" },
    ],
    avoid: "Avoid anything fried, cheesy, or high in fiber (like raw veggies or beans) right before practice. They can cause stomach discomfort.",
    followUp: "Would you like a simple recipe for one of these? Or do you have any other texture preferences to keep in mind?",
    source: "Built around trusted sports-nutrition guidance.",
  },
  personas: "Both parents and athletes can use it, and the wording changes depending on who is asking.",
  /** Two sentences, on purpose. A parent wants one concrete promise, not a list
   *  of scope exclusions. Backed by the app's input/output filtering on
   *  weight-loss, calorie-restriction, medical, injury and under-18 supplement
   *  requests — do not widen this beyond what that filtering actually covers. */
  safety: {
    h: "It will never tell your athlete to eat less.",
    p: "Anything about weight, medicine or supplements goes to a real person instead of getting an answer from software.",
  },
};

/* ------------------------------------------------------------------ S6 */
export const steps = {
  eyebrow: "Getting set up",
  /** Three because the section contains exactly three steps. If a step is ever
   *  added or removed, this number changes with it. */
  h2: "Three things, then you're done.",
  sub: "About four minutes, once.",
  items: [
    {
      n: "01",
      title: "Tell us about your athlete",
      body: "Their age, their level, the season, and the food they actually eat.",
      chips: ["Age", "Level", "Season", "Allergies"],
      ex: { t: "Maya · 14 · Competitive · In-season", d: "No dairy · Likes pasta, rice bowls, smoothies" },
    },
    {
      n: "02",
      title: "Add their soccer schedule",
      body: "Practices, games and tournaments. Or just import the team calendar you already keep.",
      chips: ["Practice", "Game", "Tournament", "Conditioning"],
      ex: { t: "Club calendar imported", d: "18 sessions and 9 games through the season" },
    },
    {
      n: "03",
      title: "Follow the day",
      body: "Each day shows up with the eating times already on it. The meals you pick become your grocery list.",
      chips: ["What's next", "When", "What to eat"],
      ex: { t: "Time to fuel up — pre-game snack", d: "Next move at 8:30 AM · Kickoff 10:00" },
    },
  ],
};

/* ------------------------------------------------------------------ S8 */
export const proof = {
  h2: "Who stands behind this.",
  /**
   * Deliberately unnamed. Purvi is already in hero.founder and closing.trust;
   * a third mention reads as thin evidence dressed up as emphasis.
   *
   * Also deliberately "wrote the rules", not "writes the plans". Recipes are a
   * static catalogue and the weekly plan is assembled by
   * claude_ai.prompt6_weekly_meal_plan — she set the guidance, software applies
   * it. Do not upgrade this to a claim that an RDN authors each plan.
   */
  affiliation: "A Registered Dietitian wrote the rules this runs on.",
  /** Ship real quotes only. Empty array renders the authorship line alone. */
  quotes: [] as { text: string; name: string; club: string }[],
};

/* ------------------------------------------------------------------ S9 */
export const safety = {
  eyebrow: "Safety & privacy",
  h2: "Safe for a growing kid.",
  claims: [
    /**
     * The calorie line names its own exception on purpose. CoachMealCard.tsx renders
     * a Cal/P/C/F row for any meal described in Coach chat, regardless of role — a
     * dated, deliberate exception in the app (CLAUDE.md §14 rule 3, 2026-07-29).
     * An absolute "no calories anywhere" claim would be false. Do not restore it.
     */
    { t: "Not built around calorie counting", d: "Daily plans, recipes and reports are about fueling, never a calorie target. If your athlete asks the Fuel Coach about a meal they ate, it may show a nutrition breakdown." },
    { t: "No weight. No BMI. No body tracking.", d: "We don't collect it, show it or score it." },
    { t: "Never a diet. Never less food.", d: "Every step is about adding fuel, not taking it away." },
    { t: "No supplements for under-18s", d: "Food first, always. Supplement questions go to a dietitian." },
    { t: "You pick what you can see", d: "Meals, photos and the weekly report are each a setting you control." },
    { t: "Your athlete knows what you can see", d: "The app tells them plainly, in their own account." },
  ],
};

/* ------------------------------------------------------------------ S8b
 * Talk to a dietitian.
 *
 * Sourced from app/(app)/coach/dietitian.tsx: three session types, a request
 * form, then manual follow-up. The app itself says "payment will be collected
 * before the session" and "we'll reach out within 1-2 business days" — so this
 * is a paid add-on, NOT part of the subscription. Every line here has to keep
 * that true, because /pricing claims nothing is held back for a higher plan.
 * No price is stated anywhere in the app; do not invent one here.
 */
export const dietitian = {
  eyebrow: "Beyond the app",
  h2: "A real dietitian, when the app isn't enough.",
  body: "Most weeks the plan handles it. Some weeks it doesn't. A growth spurt. A rough tournament. A kid who won't eat before a 7am kickoff. When that happens you can book time with a registered sports dietitian, who reads your athlete's profile before the call and answers your questions.",
  points: [
    { h: "They know your athlete before you talk", p: "Age, position, level, training load, allergies. It all goes over with the request, so you're not spending the first ten minutes explaining." },
    { h: "Three ways to book", p: "Thirty minutes for one question. An hour to go through the whole week. Or a three-session pack that runs with a season." },
    { h: "Some questions need a person", p: "Supplements, medical needs, anything about your child's body. Those go to a human instead of software. That's on purpose." },
  ],
  /** The exception to "one plan, nothing held back" — must appear wherever the
   *  feature is sold, in the same visual weight as the offer itself. */
  billing: "You book and pay for sessions separately from your subscription. Ask for one in the app and we'll email you the time and the cost before anything is charged.",
  cta: "Join the waitlist",
};

/* ------------------------------------------------------------------ S10 */
export const plan = {
  eyebrow: "Pricing",
  h2: "One plan. Everything your athlete needs.",
  features: [
    "Set up around your own athlete",
    "A fueling plan for practices and games",
    "Game days and tournaments covered",
    "Weekly recipes and a grocery list",
    "Import your soccer calendar",
    "A weekly report for you",
    "AI Fuel Coach for parents & athletes (Beta)",
  ],
  /** Stated on the card itself — the one thing the subscription does not include. */
  addOn: "1:1 sessions with a registered dietitian are booked and paid for separately.",
  reassure: ["7 days free", "Cancel anytime", "Add another athlete anytime"],
  aside: {
    title: "Before you start",
    lines: [
      "Every question parents ask, in one place. Setup, safety and billing.",
      "What we collect, what your athlete is told, and what we never do.",
      "The trial runs 7 days. Cancel before it ends and you pay nothing.",
    ],
  },
};

/* ------------------------------------------------------------------ S11 */
export const closing = {
  h2: "Their next practice is already on the calendar.",
  sub: "Let's get their food sorted too.",
  /** One named person beats three participles. "Guided by parents" was
   *  unfalsifiable and therefore worth nothing as trust. */
  trust: "Built by a Registered Dietitian who is also a soccer mom. For players 13–17.",
};

/* ------------------------------------------------------------------ FAQ */
export type Faq = { q: string; a: string; group: "Setup" | "Safety" | "Billing"; event?: EventName };

export const faqs: Faq[] = [
  { group: "Setup", q: "What ages is AthFuelPath for?", a: "Soccer players aged 13 to 17. A parent or guardian creates the account and controls it." },
  { group: "Setup", q: "Is it only for soccer?", a: "Yes, for now. Everything is built around soccer: practices, games, tournaments and conditioning. Other sports may come later." },
  { group: "Setup", q: "How long does setup take?", a: "About four minutes. Your athlete's details, then their schedule. Or import the club calendar you already keep." },
  { group: "Setup", q: "Who uses the app, me or my athlete?", a: "Both of you, with separate logins. You set it up and see the weekly report. Your athlete sees their own day." },
  { group: "Setup", q: "Which calendars can I import?", a: "BYGA and PlayMetrics today, with more club platforms coming. If your club uses something else, you can add sessions by hand in a couple of taps. When a session moves, the day updates on its own." },
  { group: "Setup", q: "Can it help on tournament weekends?", a: "Yes. Several kickoffs, the food between games, and recovery afterwards are all part of the day." },
  {
    group: "Setup",
    q: "How does AthFuelPath suggest recipes?",
    a: "You pick the moment. Before training, after a game, tournament fueling, an everyday meal. AthFuelPath then shows recipes that suit it. It filters using the allergies and food limits saved on your athlete's profile. Always read the labels yourself.",
    event: "recipe_faq_open",
  },
  {
    group: "Setup",
    q: "Do I have to build the grocery list myself?",
    a: "No. Pick the recipes you want for the week and AthFuelPath gathers the ingredients into one list, grouped the way you shop. You can also tick off what you already have at home.",
    event: "grocery_faq_open",
  },
  { group: "Safety", q: "Does my athlete ever see numbers?", a: "AthFuelPath is not built around calorie counting. Daily plans, recipes and the weekly report focus on fueling rather than calorie targets. They do see a carb and protein target for the day, shown as a fuel gauge, because that is the guidance itself. It reads as fuel to add, never as a limit. If your athlete explicitly asks the Fuel Coach about a meal they ate, the Coach may give them a nutrition breakdown." },
  { group: "Safety", q: "Do you track weight or body composition?", a: "No. Weight and BMI are never tracked, shown or scored." },
  { group: "Safety", q: "Do you recommend supplements?", a: "No. AthFuelPath is food first, and it makes no supplement recommendations for athletes under 18." },
  { group: "Safety", q: "What can I see as a parent?", a: "You choose. Meals, photos and the weekly report are each a setting. Your athlete is told in the app what you can see." },
  { group: "Safety", q: "Is this medical advice?", a: "No. AthFuelPath gives sports nutrition guidance to learn from. It does not replace care from your own doctor." },
];

/**
 * Parked with the Fuel Coach section (2026-08-28). The section came off the
 * homepage, so these four were the only place on the site that explained a
 * feature nothing else mentioned. Restore them to `faqs` on the same day the
 * Coach section goes back up — not before, and not separately.
 *
 * NOTE: two Coach references deliberately remain live and must NOT be removed
 * with these. `safety.claims[0]` and the "Does my athlete ever see numbers?"
 * answer both name the Coach as the one place a nutrition breakdown can appear.
 * That is a disclosure, not marketing: deleting it would make the surrounding
 * no-calorie claim false.
 */
export const faqsParked: Faq[] = [
  { group: "Setup", q: "What can I ask the Fuel Coach?", a: "Practical fueling questions. What to eat before practice, how to recover after a game, what to pick while you're eating out, or how to handle food across a tournament weekend.", event: "ai_coach_faq_open" },
  { group: "Setup", q: "Can the Fuel Coach help while we're traveling?", a: "Yes. If you share your location for a nearby-food question, it can find restaurants around you and help you think through the options for the day your athlete is having.", event: "ai_coach_faq_open" },
  { group: "Setup", q: "Can both parents and athletes use it?", a: "Yes. Both can use it, and answers are worded differently depending on who is asking.", event: "ai_coach_faq_open" },
  { group: "Safety", q: "Is the Fuel Coach medical advice?", a: "No. It is built for everyday sports fueling. Medical, injury, weight-loss and anything outside that scope gets redirected to the right professional.", event: "ai_coach_faq_open" },
];

/* ---------------------------------------------------------------- Footer */
export const footer = {
  blurb: "Straightforward sports nutrition for young soccer players and the families behind them.",
  explore: [
    { label: "How it works", href: "/#how-it-works" },
    { label: "For parents", href: "/#for-parents" },
    { label: "Coaches", href: "/coaches" },
    { label: "Our story", href: "/our-story" },
    { label: "All questions", href: "/faq" },
  ],
  legal: [
    { label: "Youth data & privacy", href: "/privacy" },
    { label: "Safety commitments", href: "/safety" },
    { label: "Medical disclaimer", href: "/disclaimer" },
    { label: "Terms", href: "/terms" },
  ],
};
