import { chromium } from "playwright";
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });

/* iPhone-ish. 844 is the full window; the visible page area is smaller once the
   browser chrome is there, so the CTA needs real headroom, not a hairline pass. */
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
await p.goto("http://localhost:3210/coaches", { waitUntil: "networkidle" });
/* The site sets scroll-behavior: smooth. Without this the scripted scroll is
   still animating when the assertion runs, and the sticky bar reads as broken
   when it is only late. */
await p.addStyleTag({ content: "html{scroll-behavior:auto!important}" });

console.log(await p.evaluate(() => {
  const out = [];
  const cta = document.querySelector(".coach-hero .btn");
  if (cta) {
    const r = cta.getBoundingClientRect();
    out.push(`hero CTA bottom at ${Math.round(r.bottom)}px of 844 — ${r.bottom <= 844 ? "IN first viewport" : "BELOW THE FOLD"}`);
  } else out.push("hero CTA: NOT FOUND");

  out.push(`hero dashboard peek visible: ${!!document.querySelector(".coach-hero__peek")?.getBoundingClientRect().height}`);

  const strip = document.querySelector(".dash__week-scroll");
  if (strip) out.push(`day strip scrolls: ${strip.scrollWidth > strip.clientWidth} (${strip.scrollWidth} > ${strip.clientWidth})`);

  const today = document.querySelector(".dash__week li[data-today]");
  out.push(`current day marked: ${!!today}`);

  const tiles = document.querySelectorAll(".dash__metrics > li");
  out.push(`metric tiles: ${tiles.length} (must be 2 — the onboarding tile is gone)`);

  const body = document.body.innerText;
  for (const banned of ["/18", "15/", "Not set up yet", "Families still to finish"]) {
    if (body.includes(banned)) out.push(`LEAK: page still contains "${banned}"`);
  }

  const bgs = new Set();
  document.querySelectorAll("section").forEach((s) => bgs.add(getComputedStyle(s).backgroundColor));
  out.push(`section background tokens: ${bgs.size} — ${[...bgs].join(" | ")}`);
  return out.join("\n");
}));

// sticky bar: absent at the top, present after the dashboard, gone once dismissed
const bar = () => p.evaluate(() => {
  const b = document.querySelector(".sticky-bar");
  return `${b ? b.classList.contains("show") : "NO BAR"} (scrollY=${Math.round(window.scrollY)})`;
});
console.log(`sticky bar at top of page: ${await bar()}`);
/* Scroll so the dashboard section's BOTTOM is above the viewport — that is the
   trigger. scrollIntoView({block:"end"}) leaves it still on screen and the bar
   correctly stays hidden, which read as a bug the first time. */
await p.evaluate(() => {
  const d = document.querySelector("#coach-dashboard").getBoundingClientRect();
  window.scrollTo(0, d.bottom + window.scrollY + 200);
});
await p.waitForTimeout(500);
console.log(`sticky bar past the dashboard: ${await bar()}`);
/* Capture BEFORE dismissing. Clicking the close button leaves focus on the now
   inert bar, the browser sends it to the top of the document, and the skip link
   paints itself over the page in the screenshot. */
await p.evaluate(() => window.scrollTo(0, 0));
await p.waitForTimeout(300);
await p.screenshot({ path: "/root/web/shots/coach-mobile.png", fullPage: true });

await p.evaluate(() => {
  const d = document.querySelector("#coach-dashboard").getBoundingClientRect();
  window.scrollTo(0, d.bottom + window.scrollY + 200);
});
await p.waitForTimeout(300);
await p.click(".sticky-bar__x").catch(() => console.log("dismiss button not clickable"));
await p.waitForTimeout(400);
console.log(`sticky bar after dismiss: ${await bar()}`);
const d = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const dp = await d.newPage();
await dp.goto("http://localhost:3210/coaches", { waitUntil: "networkidle" });
await dp.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } window.scrollTo(0, 0); });
await dp.waitForTimeout(600);
await dp.screenshot({ path: "/root/web/shots/coach-desktop.png", fullPage: true });
await b.close();
