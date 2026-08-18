/** One short page per parent question. Search surface + proof of competence (spec §3). */
export type QuestionPage = {
  slug: string; title: string; h1: string; intro: string;
  sections: { h: string; p: string; list?: string[] }[];
  closing: string;
};

export const questionPages: QuestionPage[] = [
  {
    slug: "before-a-530-practice",
    title: "What to eat before a 5:30 soccer practice",
    h1: "What should she eat before a 5:30 practice?",
    intro: "School lets out at three. Training starts at half five. That gap in the middle is the one most families get wrong, and it's almost never because anyone is feeding their kid badly. The timing is just working against you.",
    sections: [
      { h: "The two-part answer", p: "Most young players do best with a real meal about two hours before training, then something small and familiar around half an hour out. The meal does the heavy lifting. The snack tops up the tank and settles nerves." },
      { h: "What the meal looks like", p: "Something they already eat. Build it on a starchy base with some protein and a bit of fruit. Stick to what they know. Right before a session is the wrong time to try a new food.", list: ["A rice or pasta bowl with chicken", "A sandwich with fruit on the side", "Last night's leftovers and a glass of milk"] },
      { h: "What the top-up looks like", p: "Small, quick, no effort. A banana. A granola bar. An applesauce pouch. A few crackers. If they get nervous before training, keep this one very light." },
      { h: "After training", p: "That first hour after the whistle matters more than most parents expect. Something in the car works fine. Chocolate milk, a sandwich, some fruit. Then a proper dinner once you're home." },
    ],
    closing: "AthFuelPath puts these times around your athlete's real session, so nobody is doing the maths at 3pm.",
  },
  {
    slug: "after-the-game",
    title: "Did he eat enough after the game?",
    h1: "Did he eat enough after the game?",
    intro: "This is the question that shows up on the drive home, right after your player says they're not hungry. Here's the thing: after hard effort, hunger is a bad guide to what a growing body actually needs.",
    sections: [
      { h: "Why they're not hungry", p: "Hard effort and heat both switch off hunger for a while. A player can finish ninety minutes genuinely not wanting food and still need it. That's why the clock is a better cue than appetite." },
      { h: "The hour that matters", p: "Get something in within about an hour of the final whistle, then a full meal once you're home. If solid food sounds awful to them, the first thing can be a drink." },
      { h: "Easy things that travel", p: "Keep the car stocked and the decision makes itself.", list: ["Chocolate milk or a fruit smoothie", "A sandwich you made before you left", "Fruit, pretzels or a yoghurt pouch"] },
      { h: "How to tell it worked", p: "Look at tomorrow, not tonight. Steady energy at school and a normal appetite at breakfast are the signs worth watching." },
    ],
    closing: "AthFuelPath puts the recovery window on the schedule with the game, so it's there before the whistle even goes.",
  },
  {
    slug: "tournament-weekend",
    title: "What to pack for a soccer tournament weekend",
    h1: "What do we pack for tournament weekend?",
    intro: "Two or three games in a day. A cooler. A hotel room with no kitchen. And a schedule that keeps moving. Tournament food is a logistics problem long before it's a nutrition one.",
    sections: [
      { h: "Pack for the gaps", p: "The meals mostly sort themselves out. What decides how your player feels in the second half of game two is what they ate in the four hours between kickoffs." },
      { h: "The cooler list", p: "Familiar, portable, easy to eat sitting in a camp chair.", list: ["Sandwiches made the night before", "Pretzels, crackers or rice cakes", "Fruit that travels well: oranges, grapes, bananas", "Chocolate milk in a cold pack", "Plenty of water, plus a sports drink on hot days"] },
      { h: "Between games", p: "Something light and familiar soon after the first game. Then a slightly bigger top-up a couple of hours before the next kickoff. Heavy or unfamiliar food between games is the classic mistake." },
      { h: "The hotel breakfast", p: "Have a plan before you walk in. A starchy base, some protein, some fruit. Eat early enough that it settles before warm-ups." },
    ],
    closing: "AthFuelPath builds the whole tournament day around every kickoff on the schedule, gaps included.",
  },
  {
    slug: "between-two-games",
    title: "What to eat between two soccer games",
    h1: "What should she eat between two games?",
    intro: "The gap between games is the hardest call of the day. Too little and the second game falls apart. Too much, or the wrong thing, and it falls apart a different way.",
    sections: [
      { h: "Count backwards from kickoff", p: "How much they eat depends entirely on how long they've got. Three hours is a small meal. Ninety minutes is a snack. Forty-five minutes is a few bites and a drink." },
      { h: "Short gap, under 90 minutes", p: "Light, familiar, mostly starchy. Pretzels, a banana, an applesauce pouch, a few crackers. Sip fluids steadily rather than downing a lot at once." },
      { h: "Long gap, three hours or more", p: "A small meal is fine here, and usually better. A sandwich, a rice bowl, pasta. The same food that works before any session, in a smaller portion." },
      { h: "Hot days", p: "When it's hot, fluids matter as much as food, and appetite drops even further. Cold, wet things often go down when nothing else will. Fruit, yoghurt, a smoothie." },
    ],
    closing: "AthFuelPath sizes the between-games window to the real gap on your athlete's schedule.",
  },
];

export const bySlug = (slug: string) => questionPages.find((q) => q.slug === slug);
