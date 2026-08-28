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
/**
 * Two places only: the homepage hero and /signup, where the email is actually
 * handed over. It used to sit under the closing CTA of six pages, which made it
 * the most repeated sentence on the site — a reassurance a reader has already
 * accepted stops reassuring and starts sounding anxious.
 *
 * Rule: this line goes where someone is about to type their address, not
 * wherever there is a button.
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
    /**
     * The options run wider than the product does, and the hint says so.
     *
     * Every other statement of the audience on this site is "13–17". This
     * select offered "Under 13" and "18 or older" with nothing explaining why,
     * which reads either as an oversight or as an implied claim that the
     * product serves them. It serves neither.
     *
     * The out-of-range options stay because removing them makes the answers
     * WORSE, not cleaner: a parent of an 11-year-old would round to "13" or
     * skip the field, and we would never learn that younger families are
     * asking. The hint is what makes keeping them honest.
     */
    age: {
      label: "Your athlete's age",
      hint: "AthFuelPath is built for 13–17. Tell us anyway — it helps us see who is waiting.",
      options: ["Under 13", "13", "14", "15", "16", "17", "18 or older"],
    },
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
  /**
   * This form had no link to the privacy policy at all until 2026-08-28, while
   * the coach form did — and this is the form that asks for a child's first
   * name. /privacy now opens with a section describing exactly these fields,
   * so the link lands somewhere that answers the question it raises.
   *
   * Names the athlete's first name explicitly. A parent about to type their
   * child's name should be told where it goes at that moment, not left to find
   * out by reading a policy they had no reason to open.
   */
  privacyNote: {
    a: "We use this to tell you when AthFuelPath opens, and nothing else. Your athlete's first name is optional. See our",
    link: "privacy notice",
    href: "/privacy",
  },
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
 * /coaches — for coaches and athletic directors.
 *
 * COPY ORDER, everywhere on this page: coach benefit first, product mechanism
 * second, privacy third. Never open on "coaches can't see individual meals" —
 * a reader has to want the thing before a safeguard means anything.
 *
 * The dashboard is a CODED MOCK, not a capture of a shipped screen. Every other
 * product image on this site is a real screenshot. That is defensible only
 * while the page frames it as early access, which it does. Replace it with a
 * real capture before a coach sees both.
 *
 * NEVER on this page: an individual athlete's meals, weight or photos · any
 * suggestion a coach can see one athlete's plate · calorie or macro language ·
 * a performance guarantee · fear framing · a ship date · a price.
 *
 * ONE CTA LABEL on this page: "Request Coach Access". Not "join the waitlist",
 * not "request early access". The nav button swaps to it on this route only.
 */
export const coaches = {
  ctaLabel: "Request Coach Access",

  hero: {
    eyebrow: "Coaches & athletic directors",
    h1: "The part of the season you can't see.",
    /** Two paragraphs on purpose: the problem, then what you get. */
    p1: "You plan the training. You set the lineup. But you can't see whether your players are fueling for the week you've planned.",
    /* Shortened: "before training, games and tournament weekends" was the third
       appearance of that list on this page, and the privacy clause is made
       properly in the trust section rather than four times in passing. */
    p2: "AthFuelPath gives you a simple team-level view, so you can spot fueling gaps before they show up on the pitch, without adding work to your week.",
    /* The chip states the range. /coaches said only "youth soccer", so a coach
       with a U12 squad had no way to tell whether the product covered them. */
    chips: ["Parents set it up", "Team-level only", "Nothing new to manage", "Built for players 13–17"],
    secondary: "See what coaches see",
  },

  effort: {
    h2: "Three minutes a week. That's the whole ask.",
    sub: "Parents set it up. Athletes use it. You look when you want to.",
    items: [
      { n: "01", h: "Nothing new to manage.", p: "No roster maintenance. No meal logging. No chasing athletes. Families set up their own accounts." },
      /* The privacy clause was cut from this card. Section 5 makes the same
         promise at length; saying it twice here read as defensive. */
      { n: "02", h: "See the squad, not the individual.", p: "Understand how the team is fueling as a group, week to week." },
      { n: "03", h: "Built around your schedule.", p: "Training Tuesday. Game Saturday. Tournament weekend. Fueling guidance adjusts around the week you have already planned." },
    ],
  },

  why: {
    h2: "You coach the game. We help with what happens between sessions.",
    sub: "AthFuelPath gives families the guidance to fuel around the schedule you have already created, and gives you just enough visibility to understand how the squad is doing.",
    /* All three headings are verb-led and address the coach. The previous set
       mixed an outcome ("Better prepared athletes"), an action ("Spot team-wide
       gaps") and a state ("You stay the coach"), so the three did not read as
       one list. Keep the parallelism if these are ever rewritten. */
    items: [
      { icon: "calendar", h: "Fuel the week you planned", p: "Families get guidance built around your actual training and match schedule — practices, fixtures, tournament weekends." },
      { icon: "trend", h: "See where the squad slips", p: "Spot the moments the group tends to miss — pre-game timing, tournament days, the drive home — as a team pattern, not a player list." },
      { icon: "whistle", h: "Nudge the whole team at once", p: "Send the squad a fueling reminder for Saturday in one tap. No follow-up, no chasing, no individual conversations." },
    ],
  },

  dash: {
    badge: "Early access · opening to clubs this season",
    h2: "Your squad, at a glance.",
    /* The privacy clause was cut from this line. It said "Team-level patterns
       only. No individual meals, weights or photos" — which the hero says
       above it and the trust section says below it in full. Five assertions of
       one promise on a single page reads as insisting rather than explaining. */
    sub: "See whether your squad is fueling for the week ahead, in seconds, with nothing for you to maintain.",
    team: "Twin Creeks SC · U15 Boys",
    /**
     * Two states, switched by tabs. The point is to show the dashboard is worth
     * looking at twice in a week, not to build a demo. Keep it to two.
     *
     * DISPLAY RULES for anything a coach can see. These are not style choices:
     *   - No raw counts and no denominators. "Most of the squad", never 15/18.
     *     A denominator invites a coach to work out which three.
     *   - No individual names, no leaderboard, no ranking between athletes.
     *   - Nothing that frames non-participating families as a gap or a to-do.
     *     The "Not set up yet · 3 families" tile was removed for this reason and
     *     must not come back, as a count or as a percentage.
     *   - Anything families reported themselves is labelled as self-reported.
     *     Never present it as measured.
     * The tabs are named for the moment, not the weekday, so the two states read
     * as one week seen twice rather than two different weeks.
     */
    states: [
      {
        id: "tue",
        tab: "Early week",
        week: "Week of 8 Sep",
        today: "TUE",
        metrics: [
          { label: "Fueling days followed", value: "78%", pct: 78, note: "Self-reported by families, last 7 days" },
          { label: "Pre-game meal on time", value: "Most of the squad", pct: 83, note: "Last Saturday's fixture" },
        ],
        read: {
          h: "Week looks on track",
          p: "Most of the squad is following their fueling days ahead of Saturday's fixture.",
        },
      },
      {
        id: "fri",
        tab: "Pre-game",
        week: "Week of 8 Sep",
        today: "FRI",
        metrics: [
          { label: "Fueling days followed", value: "81%", pct: 81, note: "Self-reported by families, last 7 days" },
          { label: "Pre-game prep done", value: "About half the squad", pct: 50, note: "For tomorrow's 10am kickoff" },
        ],
        read: {
          h: "Pre-game fueling needs attention",
          p: "About half the squad has not completed tomorrow's pre-game preparation. A reminder at tonight's session would land.",
        },
      },
    ],
    days: [
      { d: "MON", k: "Rest" }, { d: "TUE", k: "Train", train: true }, { d: "WED", k: "Train", train: true },
      { d: "THU", k: "Rest" }, { d: "FRI", k: "Train", train: true }, { d: "SAT", k: "Game", game: true },
      { d: "SUN", k: "Game", game: true },
    ],
    readTitle: "What this tells you",
    /** No diagnosis, no promise. It names a pattern and hands the individual
     *  guidance back to the app, which is exactly the division of labour the
     *  whole page is selling. */
    readFoot: "You see the pattern. AthFuelPath handles the individual guidance.",
    /**
     * The one thing a coach does with what they just read, so the panel ends in
     * an action rather than an observation.
     *
     * This is drawn, not wired — the whole dashboard is. It renders as part of
     * the mock and is deliberately NOT a real button: a control that looks live
     * and does nothing when a coach presses it is worse than a picture of one.
     * When the product ships this, make it a real button here and delete this
     * paragraph.
     */
    action: "Send the squad this week's pre-game reminder",
  },

  trust: {
    h2: "Built for teams. Designed around athlete privacy.",
    sub: "Coaches see team-level patterns, never an individual athlete's meals, weight, photos or personal nutrition history.",
    /**
     * ONE item, not three. Cut on 2026-08-28.
     *
     * "Team-level insights" and "Athlete privacy" were both restatements of the
     * `sub` directly above them — the sub already says coaches see team-level
     * patterns and never an athlete's meals, weight or photos, so the list was
     * the section explaining itself and then repeating itself.
     *
     * What survives is the only idea the sub does not contain: the family, not
     * the club, decides. Before adding an item here, check it says something
     * `sub` does not.
     */
    items: [
      { h: "Parents decide, not the club", p: "Parents stay in control of their athlete's information and whether they take part at all." },
    ],
    /** Factual, and matches proof.affiliation on the homepage. She wrote the
     *  guidance the app applies. Do not upgrade this to "reviews every plan". */
    credibility: {
      label: "Nutrition guidance",
      p: "The fueling guidance in AthFuelPath was written by a Registered Dietitian who works with youth athletes.",
      name: "Purvi Shah, MS, RDN",
      role: "Founder · Registered Dietitian Nutritionist",
    },
  },

  form: {
    h2: "Bring AthFuelPath to your squad.",
    sub: "We are opening Coach Access to a small group of youth soccer clubs this season. Early clubs help shape the coach experience and get direct access to our team as it rolls out.",
    note: "No commitment. Tell us about your club and we will follow up personally.",
    /* No pricing line here, deliberately. There was one — "Free for clubs
       during early access. Families choose whether to subscribe." — and it was
       removed: nothing on this site should state a price, for clubs or for
       families, until that is settled. If a coach asks, Purvi answers in the
       reply. Do not reintroduce a price without Mayur's say-so. */
    /** Answers the question every coach asks next: what do I actually have to
     *  do, and what am I signing my families up for. */
    how: {
      h: "How it works for your club",
      p: "We send you a club invite link and a short parent explainer. Families decide for themselves whether to join — participation is always optional.",
    },
    name: { label: "Your name" },
    club: { label: "Club, school or program" },
    /** No default selection. A pre-ticked "Coach" meant every athletic director
     *  and trainer who did not look closely came through as a coach. */
    role: { label: "Your role", options: ["Coach", "Athletic Director", "Trainer", "Club Admin"] },
    email: { label: "Email" },
    submit: "Request Coach Access",
    sending: "Sending…",
    /** Errors name the fix, not the failure. "Invalid input" tells a coach
     *  nothing they can act on. */
    errors: {
      name: "Enter the name we should use when we reply",
      email: "Enter an email we can reply to",
      role: "Choose the closest match to your role",
    },
    privacyNote: {
      a: "We'll only use this to contact you about Coach Access. See our",
      link: "privacy notice",
      href: "/privacy",
    },
    done: {
      /**
       * NO TIMELINE. This said "within two business days" and was removed on
       * 2026-08-28: replies come from one person working by hand, and a clock
       * on the page is a promise she has to keep on the worst week as well as
       * the best. Put a number back only when someone is accountable for it.
       */
      h: "Request received.",
      p: "We'll be in touch with early-access details for your club.",
    },
    /**
     * Asked AFTER the request is recorded, never before. The answer is the most
     * useful thing on this page, and it is also the field most likely to make a
     * coach abandon the form. Post-submission it can cost nothing.
     */
    research: {
      h: "One quick question",
      p: "What's the biggest fueling challenge you see with your athletes?",
      placeholder: "They come to Saturday games straight from a 7am wake-up with nothing in them…",
      submit: "Send",
      skip: "Skip",
      thanks: "Thank you — that goes straight to Purvi.",
    },
    error: "That didn't send. Try again, or email us at",
  },
};

/* ------------------------------------------------------------- Our Story
 * /our-story — the founder story.
 *
 * This page's job is trust, not features. Five chapters, in this order and no
 * other: who built it → why it became personal → how one family's fix became a
 * product → what it holds to → a personal close. The waitlist CTA is the
 * outcome of that trust, not the point of the page.
 *
 * NEVER on this page: product screenshots · statistics · testimonials · club
 * logos · feature grids · timelines · stock photography · a second CTA before
 * the close · nutrition instruction. The founder story carries the credibility;
 * anything that makes this look like a product page weakens it.
 *
 * The positioning line appears ONCE, in `belief`. Do not restate it in the
 * hero, the origin section or the close.
 *
 * Credentials appear ONCE, in the identity card. After that they are
 * demonstrated by the story rather than repeated.
 */
export const ourStory = {
  hero: {
    eyebrow: "Our story",
    h1: "A dietitian built this for her own daughter.",
    p1: "Purvi Shah spent years helping families make nutrition practical. Then her own daughter started playing competitive soccer, and the problem became personal.",
    p2: "Practices after school. Early games. Tournament weekends. Long drives home. She needed guidance that understood the schedule of a young athlete.",
    portraitAlt: "Purvi Shah, founder of AthFuelPath, sitting at an outdoor table",
    card: {
      name: "Purvi Shah, MS, RDN",
      /** Her credential string exactly as the rest of the site uses it. Do not
       *  add CSSD or any other credential here without confirming she holds it. */
      role: "Registered Dietitian Nutritionist · Soccer mom · Founder",
      line: "Building the kind of youth-sports nutrition support she wanted for her own family.",
    },
  },

  personal: {
    eyebrow: "When it became personal",
    h2: "Knowing what to do was one thing. Making it work at home was another.",
    body: [
      "When Purvi's daughter started playing competitive soccer, nutrition stopped being something she only explained professionally.",
      "It became the 6:00 PM kickoff after a full school day. The early tournament game. The cooler packed in a hotel room. The long drive home when everyone was hungry.",
      "She knew what a young athlete needed. The harder question was making it work in real family life.",
    ],
    /** The signature visual element of this section. Editorial statements with a
     *  green rule, never cards — they are the parent's problem and the origin of
     *  the company at the same time. */
    questions: [
      "What should my athlete eat today?",
      "When should they eat it?",
      "What changes because practice is tonight, or there are two games tomorrow?",
    ],
    /** Measured on purpose. "Too much of" — not "all of". */
    close1: "Too much of the nutrition guidance Purvi encountered was built around numbers, written with adults in mind, or disconnected from the day in front of a young athlete.",
    close2: "So she started turning what she knew into something her daughter could actually use.",
  },

  origin: {
    eyebrow: "How AthFuelPath started",
    h2: "It started with one athlete. The problem wasn't unique to her.",
    body: [
      "What started as a way to help her own daughter didn't stay a one-family problem for long.",
      "At practices, games and tournaments, Purvi kept hearing versions of the same questions from other parents. What should they eat before practice? What changes on game day? What do we pack for a tournament? How do we help them recover without turning food into another thing to stress about?",
      "AthFuelPath grew out of what she was already doing at home, taking an athlete's actual soccer schedule and turning it into a simple plan for the day.",
    ],
    statement: { a: "Built first for one daughter.", b: "Designed now for families like hers." },
    /** Deliberately low priority. A visitor who now understands the story may
     *  want to see what was built; this is not a second CTA. */
    link: { label: "See how that idea became AthFuelPath", href: "/#how-it-works" },
  },

  belief: {
    /** The one positioning statement on the site. Stated once, here, and never
     *  restated in a variation elsewhere on the page. */
    a: "Nutrition science wasn't missing.",
    b: "Families needed a simpler way to use it.",
    sub: "AthFuelPath is about making sound nutrition guidance easier for young athletes and their families to use in everyday life.",
    eyebrow: "What we hold to",
    h2: "The principles behind AthFuelPath.",
    /** Parallel convictions, not sequential steps. Never number these, never
     *  add icons, never imply an order. */
    items: [
      { h: "Young athletes aren't small adults.", p: "Growing bodies need guidance that respects growth, development and the demands of youth sport." },
      { h: "The schedule matters.", p: "A practice day, a rest day and a tournament weekend shouldn't all look the same." },
      { h: "Start with food.", p: "Everyday food should do the heavy lifting. Supplements aren't the starting point." },
      { h: "Parents need practical guidance.", p: "Helping your athlete eat well shouldn't require a nutrition degree, or turn food into another source of family stress." },
    ],
  },

  close: {
    /**
     * NULL UNTIL PURVI APPROVES THE WORDING. Publishing an invented quote
     * attributed to a real person is not something to do on anyone's behalf,
     * and the spec that asked for this section said so explicitly.
     *
     * Working draft awaiting her approval or her own words — prefer hers, even
     * if less polished:
     *
     *   "I didn't want my daughter thinking about nutrition all day. I wanted
     *    her to know what to do, do it, and get back to being a kid who loves
     *    playing soccer."
     *
     * To publish, replace null with:
     *   { text: "…", name: "Purvi Shah, MS, RDN", role: "Founder, AthFuelPath" }
     * The close renders correctly either way.
     */
    quote: null as { text: string; name: string; role: string } | null,
    h2: "Built for the young athlete in your family.",
    sub: "AthFuelPath turns the week ahead into simple, practical fueling guidance young athletes and parents can actually follow.",
    /**
     * There was a "See how it works" link here pointing at /#how-it-works.
     * Removed: `origin.link` sends the reader to exactly the same place earlier
     * on this page, with better reason ("See how that idea became
     * AthFuelPath"), and the identical label was also the homepage hero's
     * secondary button. Two links to one destination on one page, and the same
     * four words on two pages.
     */
    secondary: null as { label: string; href: string } | null,
  },
};

export const nav = {
  links: [
    /**
     * "For Parents" now points at a real route.
     *
     * It was briefly removed on 2026-08-28 on the reasoning that the homepage
     * IS the parents page, so a nav item promising a parents page was promising
     * a destination that did not exist. That reasoning was right about the
     * problem and wrong about the fix.
     *
     * The split is by FUNNEL STAGE, not audience. The homepage stays
     * parent-voiced and does recognition: the problem, the mechanism, and that
     * it is safe for a kid, in under a minute. /parents does consideration —
     * it answers the five objections that stop an interested parent from
     * signing up. /coaches is a different buyer entirely.
     *
     * Consequence worth stating: do NOT neuter the homepage into
     * audience-neutral product copy to justify the split.
     */
    { label: "How It Works", href: "/#how-it-works" },
    { label: "For Parents", href: "/parents" },
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
  /**
   * The homepage shows the first THREE. All four stay in this array because
   * /parents runs the full set and each one also has its own /questions/[slug]
   * page linked from /faq — deleting the fourth here would break both.
   *
   * The fourth ("between two games") is the one that goes, because it overlaps
   * the tournament question directly: same weekend, same problem, a narrower
   * slice. Keep the homepage set at three; this section is the hook, and a
   * fourth near-identical option costs recognition rather than adding it.
   */
  homeCount: 3,
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
  /* Does not re-list "practices, games and tournaments". The hero says it, the
     setup card below says it, and the chips in this very section name the
     session types. Three statements of the same sentence sat within one screen
     of each other on this page. */
  body: "Pull in the club calendar you already use, or add sessions by hand. From there the week fills itself in.",
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
      /* The chips directly below name the session types. Spelling them out in
         the body too made this the third copy of the same sentence on the page. */
      body: "Import the team calendar you already keep, or add sessions one at a time.",
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

/* ------------------------------------------------------------------ S5
 * Core capabilities — an INDEX of what is inside, not a demo.
 *
 * Replaces the "What should I cook this week?" block, which was the largest
 * thing on the homepage: four numbered sub-sections, two phone frames, chip
 * rows and a closing strip. That block now lives on /parents, where a reader
 * has already decided they are interested and will read it.
 *
 * GUARDRAIL: these are not feature cards with screenshots inside. If a card
 * grows past roughly 280px tall, cut copy — do not grow the card.
 */
export const capabilities = {
  eyebrow: "Built around their week",
  h2: "Everything their soccer week needs.",
  items: [
    { icon: "sun", label: "Today's Fuel Plan", h: "Know what fits the day.", p: "Simple guidance before, between and after soccer." },
    { icon: "bowl", label: "Recipes That Fit", h: "Food that works with the schedule.", p: "Meals and snacks matched to the moment and their preferences." },
    /* The Fuel Coach section was hidden from this page in August. It returns
       here as a one-line card only — a much smaller claim than the section —
       on Mayur's explicit call. The four parked Coach FAQs stay parked. */
    { icon: "chat", label: "Fuel Coach", h: "Ask when real life gets complicated.", p: "Practical guidance when the plan doesn't quite fit the day." },
    { icon: "cart", label: "Grocery Planning", h: "Turn the plan into food at home.", p: "Know what needs to be bought, and what's already in the kitchen." },
  ],
  cta: { label: "Explore AthFuelPath for parents", href: "/parents" },
};

/* ------------------------------------------------------------------ S9
 * Trust strip — compressed.
 *
 * This was a six-claim section, then three. It is three short points now, and
 * it stays on the HOMEPAGE on purpose: for a nutrition product aimed at minors,
 * "is this a diet app" is a first-thirty-seconds objection, not a
 * consideration-stage one. The fuller version is /parents#safety and the full
 * account is /safety — three depths of one promise, each linked to the next.
 *
 * The Fuel Coach nutrition-breakdown disclosure is NOT in this compressed
 * version. It lives on /parents#safety, on /safety, and in the FAQ. If those
 * three ever lose it, it has to come back here.
 */
export const safety = {
  eyebrow: "Safety & privacy",
  h2: "Built for growing athletes.",
  sub: "AthFuelPath is about fueling, growth and recovery — not dieting or changing an athlete's body.",
  secondary: "Practical sports nutrition guidance, with access to a registered dietitian when your family needs more support.",
  links: [
    { label: "Our approach for parents", href: "/parents#safety" },
    { label: "Youth data & safety", href: "/safety" },
  ],
  /**
   * THREE claims, not six. Cut on 2026-08-28.
   *
   * "No supplements for under-18s", "You pick what you can see" and "Your
   * athlete knows what you can see" moved out. All three are on /safety in
   * fuller form, and the link below this section goes there. The homepage
   * states the boundary; /safety proves it. Stating all six here made this the
   * first of three places on the site that listed the same commitments.
   *
   * These three earn their place: the calorie line carries a disclosure, the
   * weight line is the one parents actually fear, and "never less food" is the
   * only one of the six that is a promise about intent rather than data.
   */
  claims: [
    /**
     * The calorie line names its own exception on purpose. CoachMealCard.tsx renders
     * a Cal/P/C/F row for any meal described in Coach chat, regardless of role — a
     * dated, deliberate exception in the app (CLAUDE.md §14 rule 3, 2026-07-29).
     * An absolute "no calories anywhere" claim would be false. Do not restore it.
     */
    { t: "No calorie counting", d: "Plans and recipes are about fueling, not hitting a number." },
    { t: "No weight or BMI tracking", d: "We don't collect it, show it, or score it." },
    { t: "Never a diet", d: "Every step is about adding fuel, not taking it away." },
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

/* ------------------------------------------------------------------ S11
 * PARKED with the homepage's closing section (2026-08-28). Nothing renders this
 * today — /parents, /safety, /faq and /questions each write their own close
 * with their own headline, which is what keeps two pages from ending
 * identically. Kept because restoring the homepage close is one import and one
 * line in page.tsx, and because `trust` is the only place the audience is
 * stated at the foot of the homepage. See _parked/Closing.tsx.
 */
export const closing = {
  h2: "Their next practice is already on the calendar.",
  sub: "Let's get their food sorted too.",
  /**
   * Does NOT repeat the credential. `hero.founder.line` at the top of this same
   * page already says "Registered Dietitian and soccer mom, she built this
   * around her own daughter's season", beside her photograph. Saying it again
   * at the bottom was the third assertion of one credential on one page, and
   * the weakest, because there is no face next to it.
   *
   * What is left is the fact the hero does not carry: who it is for.
   */
  trust: "For soccer players 13–17, and the parents doing the shopping.",
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
  /**
   * The Safety group is deliberately two questions, not five.
   *
   * "Do you track weight or body composition?", "Do you recommend supplements?"
   * and "What can I see as a parent?" were removed on 2026-08-28. Each one was
   * a shortened restatement of a card on /safety, and two were near-verbatim —
   * "Weight and BMI are never tracked, shown or scored" against /safety's
   * "Weight and BMI are not collected for tracking, never shown back to your
   * athlete, and never scored or trended". A parent reading the homepage, then
   * /safety, then the FAQ was told the same six commitments three times in
   * three voices, which reads as insisting rather than explaining.
   *
   * /safety is the single full account. Anything cut from here belongs there
   * first. Do not re-add a safety FAQ that /safety already answers.
   */
  {
    group: "Safety",
    q: "Does my athlete ever see numbers?",
    /* Stays because of its last sentence. This is the Fuel Coach disclosure —
       the one place a nutrition breakdown can reach a young athlete — and
       deleting it would leave the surrounding no-calorie claim false. It is a
       disclosure, not marketing. See the note on faqsParked. */
    a: "AthFuelPath is not built around calorie counting. Daily plans, recipes and the weekly report focus on fueling rather than calorie targets. They do see a carb and protein target for the day, shown as a fuel gauge, because that is the guidance itself. It reads as fuel to add, never as a limit. If your athlete explicitly asks the Fuel Coach about a meal they ate, the Coach may give them a nutrition breakdown.",
  },
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

/* --------------------------------------------------------------- Parents
 * /parents — the consideration page.
 *
 * WHAT THIS PAGE IS FOR. The homepage does recognition: a parent who has never
 * heard of AthFuelPath learns the problem, the mechanism and that it is safe
 * for a kid. This page is for the parent who is already interested and is now
 * looking for a reason to say no:
 *   1. Is this another app I have to run?
 *   2. Will my athlete use it, or will I be nagging?
 *   3. Is the guidance right for a 14-year-old?
 *   4. What about her allergy?
 *   5. Can I trust this?
 * Benefit-led and objection-led. Not a nutrition-science page.
 *
 * THE RULE THAT KEEPS THIS PAGE HONEST: nothing here may be a second copy of a
 * homepage module. Where a concept appears on both, the version here is
 * shorter or deeper, differently headlined, and linked. `schedule` is the
 * clearest case — the homepage owns the full schedule module, and this page
 * gets three lines and no schedule UI.
 */
export const parents = {
  hero: {
    eyebrow: "For parents of youth athletes",
    h1: "You manage the schedule. We'll help with the fuel.",
    p: "Practice after school. Games on weekends. Tournaments that start at 8am. AthFuelPath turns your athlete's real schedule into simple guidance for what to eat, when to eat, and what to have ready.",
    secondary: { label: "See how it works", href: "/#how-it-works" },
  },

  /** Leads the page, so /parents opens on something the homepage does not have. */
  lead: {
    eyebrow: "One less thing",
    h2: "One less thing to figure out.",
    p: "Soccer already comes with enough logistics. Food shouldn't become another daily planning exercise.",
    moments: [
      { when: "Before school", q: "What breakfast makes sense today?" },
      { when: "After school", q: "What can they eat before practice?" },
      { when: "After practice", q: "What if dinner isn't ready yet?" },
      { when: "Tournament day", q: "What do we pack for six hours at the field?" },
    ],
    close: "AthFuelPath works around the schedule you already have.",
  },

  /** A bridge, not a section. The homepage owns the schedule module in full. */
  schedule: {
    h2: "Add the schedule once. Let AthFuelPath work around it.",
    flow: ["Schedule", "AthFuelPath", "Today's plan"],
    steps: [
      { h: "Add the schedule", p: "Practices, games, tournaments and other training." },
      { h: "AthFuelPath works out the timing", p: "Fueling guidance adjusts around what's happening that day." },
      { h: "Your athlete sees what to do", p: "Simple, age-appropriate guidance through their day." },
    ],
  },

  /**
   * The section the homepage cannot carry, and the answer to "will I have to
   * run this?". Reads as growing independence, never as a curriculum: no
   * progress bars, no levels, no education framing.
   */
  independence: {
    eyebrow: "Building better habits",
    h2: "They can start owning it.",
    p: "You shouldn't have to remind your athlete what to eat before every practice. AthFuelPath gives them a plan they can follow themselves, while keeping you in the picture.",
    stages: [
      { n: "01", t: "They see today's plan." },
      { n: "02", t: "They understand why it matters." },
      { n: "03", t: "They build the habit." },
    ],
  },

  /** Migrated off the homepage. Six long explanations restructured into four. */
  table: {
    eyebrow: "From the plan to the table",
    h2: "Dinner shouldn't require another decision.",
    p: "AthFuelPath recommends meals and snacks that fit their schedule, food preferences and what's happening that day.",
    points: [
      { n: "01", h: "Recipes fit the moment", p: "Pre-practice, game-day, recovery and everyday meals." },
      /* The allergy caveat is carried over verbatim from the homepage block and
         must not be softened. It is a safety line, not marketing. */
      { n: "02", h: "Their food limits are already there", p: "Allergies and food preferences saved on the profile are applied automatically. Always read the labels yourself." },
      { n: "03", h: "Your own food counts", p: "Add the meals your family already makes instead of changing everything." },
      { n: "04", h: "Turn it into a grocery list", p: "Take the week's plan from screen to shopping list — and tick off what's already in the kitchen." },
    ],
  },

  /**
   * Migrated off the homepage. AthFuelPath and the Fuel Coach are never
   * positioned as medical care, diagnosis, treatment, or a replacement for a
   * dietitian or physician. `dietitian.billing` and `dietitian.points` are
   * reused verbatim from the homepage block — do not reword them here.
   */
  person: {
    eyebrow: "When the app isn't enough",
    h2: "Sometimes you need a person, not another app.",
    p: "Most weeks the plan handles it. Sometimes it doesn't — a growth spurt, a rough tournament, a kid who won't eat before a 7am kickoff.",
  },

  /** The fuller version of the homepage trust strip. /safety is fuller still. */
  safe: {
    eyebrow: "Designed for growing athletes",
    h2: "Fueling their sport. Not changing their body.",
    cards: [
      { h: "No calorie counting", p: "Daily plans, recipes and reports are about fueling, not hitting a calorie target. If your athlete asks the Fuel Coach about a meal, it may show a nutrition breakdown." },
      { h: "No weight or BMI tracking", p: "We don't collect it, show it, or score it." },
      { h: "Never a diet", p: "Food isn't sorted into good and bad, and athletes are never encouraged to eat less." },
      { h: "Age-appropriate guidance", p: "Built around what a growing athlete needs, not scaled-down adult advice." },
    ],
    note: { h: "Parents stay connected.", p: "AthFuelPath helps athletes build independence without cutting parents out." },
    link: { label: "Read our youth data policy", href: "/privacy" },
  },

  /**
   * SIX questions, not seven. "What does it cost?" is deliberately absent:
   * nothing on this site states or implies a price until pricing is settled,
   * which is the same call that removed the pricing line from /coaches. If that
   * changes, this is where the answer goes.
   */
  faq: {
    eyebrow: "Parents ask",
    h2: "A few things you may be wondering.",
    items: [
      { q: "What age is AthFuelPath designed for?", a: "Soccer players aged 13 to 17. A parent or guardian creates the account and controls it." },
      { q: "Does my athlete use the app, or do I?", a: "Both of you, with separate logins. You set it up and see the weekly report. Your athlete sees their own day." },
      { q: "Does AthFuelPath count calories or track weight?", a: "No. Weight and BMI are never collected, shown or scored, and plans are built around fueling rather than a calorie target. Food isn't sorted into good and bad, and an athlete is never encouraged to eat less." },
      { q: "Can it handle allergies and food preferences?", a: "Yes. Allergies and food limits are saved on your athlete's profile during setup, and recipe suggestions are filtered against them automatically. Always read the labels yourself." },
      /* Answers strictly to what ships. Soccer only, said plainly. */
      { q: "What if my athlete plays more than one sport?", a: "AthFuelPath is built for soccer today — practices, games, tournaments and conditioning. Other sports may come later, and the guidance is not tuned for them yet." },
      { q: "Is this a replacement for a dietitian?", a: "No. AthFuelPath gives everyday sports nutrition guidance to learn from. When your family needs more, you can book time with a registered dietitian, and anything medical goes to a person rather than software." },
    ],
  },

  /** Same component as the homepage close, different headline on purpose. */
  close: {
    h2: "You've got the schedule handled. Let us take the food.",
    sub: "Join the waitlist and we'll email you when it opens.",
    trust: "Built for soccer players 13–17 and the parents helping them get there.",
  },
};

/* ---------------------------------------------------------------- Footer */
export const footer = {
  blurb: "Straightforward sports nutrition for young soccer players and the families behind them.",
  explore: [
    { label: "How it works", href: "/#how-it-works" },
    { label: "For parents", href: "/parents" },
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
