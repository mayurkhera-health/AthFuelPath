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
  primary: "Start free trial",
  secondary: "See how it works",
  founder: "Meet the founder",
  allQuestions: "All questions",
  safety: "Read our youth data policy",
  login: "Log in",
};

/** Required line under every primary CTA pair. */
export const trialLine = "Free for 7 days · Cancel anytime · Takes about 4 minutes to set up";

export const nav = {
  links: [
    { label: "How It Works", href: "/#how-it-works" },
    { label: "For Parents", href: "/#for-parents" },
    { label: "Pricing", href: "/pricing" },
    { label: "Our Story", href: "/our-story" },
  ],
  login: { label: cta.login, href: "/login" },
  primary: { label: cta.primary, href: "/signup" },
};

/* ------------------------------------------------------------------ S1 */
export const hero = {
  eyebrow: "Sports nutrition for soccer players 13–17",
  h1: "Fuel smarter. Play stronger.",
  sub: "Put in their practices and games. AthFuelPath works out what your player should eat, and when, around the day they actually have.",
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
  h2: "They train hard. Feeding them shouldn't be guesswork.",
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
 * NEVER: ingredient quantities (the product has none) · "chosen from your
 * soccer schedule" (not implemented) · allergy-safe / allergen-free ·
 * "know exactly what to buy" · AI meal planning · any calorie/macro/gram.
 */
export type CookPoint = { n: string; h: string; p: string; labels?: string[]; safety?: string; p2?: string };
export type GroceryItem = { name: string; from?: string; atHome?: boolean };

export const cook = {
  eyebrow: "From the field to the kitchen",
  h2: "What should I cook this week?",
  h2b: "And can someone just make the grocery list?",
  body: "Pick meals that suit the moment and work for your athlete. AthFuelPath pulls the ingredients from everything you chose into one grocery list.",
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
      h: "You pick what your family will eat.",
      p: "AthFuelPath suggests. You decide. Nobody knows better than you what will actually get eaten.",
      p2: "Choose your recipes for the week and the ingredients land in one list.",
    },
  ] satisfies CookPoint[]) as CookPoint[],
  atHome: {
    h: "Already have it?",
    p: "Tick off what's in your kitchen already, so the list only shows what you still need to buy.",
  },
  closing: {
    h: "From the plan to the dinner table.",
    p: "Pick meals they'll actually eat and start the week with one list.",
    flow: ["Fueling moment", "Recipe", "Grocery list"],
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
  body: "At home, heading to practice, or away at a tournament. Parents and athletes can ask a practical fueling question and get an answer built around their own athlete and the situation they're in.",
  body2: "From what to eat before practice to picking something while you're out, the Fuel Coach turns the question into a next step.",
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
  h2: "Sports nutrition, made simple.",
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
      body: "The app lays out what matters and when. The meals you pick become your grocery list.",
      chips: ["What's next", "When", "What to eat"],
      ex: { t: "Time to fuel up — pre-game snack", d: "Next move at 8:30 AM · Kickoff 10:00" },
    },
  ],
};



/* ------------------------------------------------------------------ S8 */
export const proof = {
  h2: "Who stands behind this.",
  affiliation: "Written by a Registered Dietitian Nutritionist · Built on sports nutrition guidance for growing athletes",
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
  cta: "Start free trial",
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
  trust: "Started by a Registered Dietitian · Guided by parents · Built for soccer players 13–17",
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
  { group: "Setup", q: "What can I ask the Fuel Coach?", a: "Practical fueling questions. What to eat before practice, how to recover after a game, what to pick while you're eating out, or how to handle food across a tournament weekend.", event: "ai_coach_faq_open" },
  { group: "Setup", q: "Can the Fuel Coach help while we're traveling?", a: "Yes. If you share your location for a nearby-food question, it can find restaurants around you and help you think through the options for the day your athlete is having.", event: "ai_coach_faq_open" },
  { group: "Setup", q: "Can both parents and athletes use it?", a: "Yes. Both can use it, and answers are worded differently depending on who is asking.", event: "ai_coach_faq_open" },
  { group: "Safety", q: "Is the Fuel Coach medical advice?", a: "No. It is built for everyday sports fueling. Medical, injury, weight-loss and anything outside that scope gets redirected to the right professional.", event: "ai_coach_faq_open" },
  { group: "Safety", q: "Does my athlete ever see numbers?", a: "AthFuelPath is not built around calorie counting. Daily plans, recipes and the weekly report focus on fueling rather than calorie targets. They do see a carb and protein target for the day, shown as a fuel gauge, because that is the guidance itself. It reads as fuel to add, never as a limit. If your athlete explicitly asks the Fuel Coach about a meal they ate, the Coach may give them a nutrition breakdown." },
  { group: "Safety", q: "Do you track weight or body composition?", a: "No. Weight and BMI are never tracked, shown or scored." },
  { group: "Billing", q: "Is a dietitian session included in the subscription?", a: "No. Your subscription covers the app. A 1:1 session with a registered sports dietitian is booked separately and priced per session. You ask for one in the app, and we email you the time and the cost before anything is charged." },
  { group: "Billing", q: "What does a dietitian session cover?", a: "Your athlete's profile goes over with the request, so the dietitian already knows them. Thirty minutes suits one specific question. An hour covers the whole week. A three-session pack runs with a season." },
  { group: "Safety", q: "Do you recommend supplements?", a: "No. AthFuelPath is food first, and it makes no supplement recommendations for athletes under 18." },
  { group: "Safety", q: "What can I see as a parent?", a: "You choose. Meals, photos and the weekly report are each a setting. Your athlete is told in the app what you can see." },
  { group: "Safety", q: "Is this medical advice?", a: "No. AthFuelPath gives sports nutrition guidance to learn from. It does not replace care from your own doctor." },
  { group: "Billing", q: "How much does it cost?", a: "$14.99 per athlete each month, after a 7-day free trial." },
  { group: "Billing", q: "What happens when the trial ends?", a: "Your plan starts automatically. Cancel any time before then and you pay nothing." },
  { group: "Billing", q: "Can I add a second athlete?", a: "Yes. Add another athlete from inside the app whenever you like." },
  { group: "Billing", q: "How do I cancel?", a: "From your account page, in one click. You keep access until the end of the period you've paid for." },
];

/* ---------------------------------------------------------------- Footer */
export const footer = {
  blurb: "Straightforward sports nutrition for young soccer players and the families behind them.",
  explore: [
    { label: "How it works", href: "/#how-it-works" },
    { label: "For parents", href: "/#for-parents" },
    { label: "Pricing", href: "/pricing" },
    { label: "Our story", href: "/our-story" },
    { label: "All questions", href: "/faq" },
    { label: "Log in", href: "/login" },
  ],
  legal: [
    { label: "Youth data & privacy", href: "/privacy" },
    { label: "Safety commitments", href: "/safety" },
    { label: "Medical disclaimer", href: "/disclaimer" },
    { label: "Terms", href: "/terms" },
  ],
};
