import { chromium } from "playwright";
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
/* Routes that actually exist today. /how-it-works, /for-parents, /pricing and
   /login were in this list long after they were folded away or parked — and a
   404 page passes every check here, so a stale list reports ALL PASS on pages
   nobody is testing. Add a route here the same commit you add the page. */
const PAGES = ["/", "/safety", "/our-story", "/coaches", "/faq", "/signup", "/questions/before-a-530-practice", "/privacy", "/terms", "/disclaimer"];
const WIDTHS = [320, 390, 768, 1024, 1440];
const fails = [];
for (const w of WIDTHS) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } });
  for (const u of PAGES) {
    const p = await ctx.newPage();
    await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });
    await p.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
    const r = await p.evaluate(() => {
      const out = {};
      const bad = /MOCK UI|REPLACE WITH CAPTURE|PHOTO PLACEHOLDER|lorem|placeholder/i;
      out.overflow = document.documentElement.scrollWidth - window.innerWidth;
      out.placeholder = bad.test(document.body.innerText);
      // hard floor is now 15px (eyebrows and device art excepted)
      out.tiny = [];
      document.querySelectorAll("p,span,li,a,button,small,label,div").forEach(el => {
        if (el.children.length) return;
        const t = (el.textContent || "").trim(); if (!t) return;
        const fs = parseFloat(getComputedStyle(el).fontSize);
        if (fs < 15 && !el.closest(".device") && !el.classList.contains("eyebrow") && !el.closest(".eyebrow")) out.tiny.push(`${fs}px ${t.slice(0,28)}`);
      });
      out.small = [];
      if (window.innerWidth < 1024) {
        document.querySelectorAll("a,button,input,select,[role=tab]").forEach(el => {
          /* A visually-hidden radio or checkbox inside a label is not the tap
             target — the label is, and it is what a finger actually lands on.
             Measure that instead of the 1px input, but do NOT simply skip it:
             if the label is small the control is still unreachable. */
          const rc = el.getBoundingClientRect();
          /* Not a target for anyone: hidden from assistive tech AND out of the
             tab order. Both conditions, deliberately — a control that is only
             aria-hidden is still reachable by keyboard and must still pass.
             This is what lets the spam honeypot through. */
          if (el.closest('[aria-hidden="true"]') && el.getAttribute("tabindex") === "-1") return;
          const lab = el.closest("label");
          const hidden = (el.tagName === "INPUT" && lab && (rc.width <= 2 || rc.height <= 2));
          const box = hidden ? lab.getBoundingClientRect() : rc;
          if (!box.width || !box.height) return;
          const inProse = el.tagName === "A" && el.parentElement && /^(P|SPAN|LI|LABEL)$/.test(el.parentElement.tagName);
          if (inProse || el.closest(".footer__bottom") || el.closest(".prose") || el.closest(".check")) return;
          if (box.height < 44) out.small.push(`${Math.round(box.height)}px ${(el.textContent||lab?.textContent||el.tagName).trim().slice(0,24)}`);
        });
      }
      // measure: no body copy over 68ch
      out.wide = [];
      // measure a real "0" glyph rather than estimating
      const probe = document.createElement("span");
      probe.textContent = "0".repeat(10);
      probe.style.cssText = "position:absolute;visibility:hidden;white-space:pre";
      document.querySelectorAll(".body,.prose p,.acc__panel p").forEach(el => {
        if (!el.textContent.trim()) return;
        probe.style.font = getComputedStyle(el).font;
        el.appendChild(probe);
        const chPx = probe.getBoundingClientRect().width / 10;
        const ch = el.getBoundingClientRect().width / chPx;
        probe.remove();
        if (ch > 68.5) out.wide.push(`${Math.round(ch)}ch ${el.textContent.trim().slice(0,20)}`);
      });
      const bgs = new Set();
      document.querySelectorAll("section, .footer, .form-page__aside, .form-page__main, .panel__half").forEach(el => bgs.add(getComputedStyle(el).backgroundColor));
      out.bgs = [...bgs]; out.h1 = document.querySelectorAll("h1").length;
      return out;
    });
    /* Every page here was audited in ONE state — whatever renders on load. A
       tab that is not selected is never measured, and that hid a real bug: the
       tournament question on the homepage overflowed 320px by 12px, but only
       while it was the selected tab. Click through every tablist and re-check
       overflow in each state. */
    const tabs = await p.$$('[role="tab"]');
    for (let t = 1; t < tabs.length; t++) {
      await tabs[t].click().catch(() => {});
      await p.waitForTimeout(220);
      const o = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (o > 0) {
        const label = (await tabs[t].textContent())?.trim().slice(0, 24);
        fails.push(`${w} ${u} OVERFLOW +${o} in tab "${label}"`);
      }
    }
    if (tabs.length) await tabs[0].click().catch(() => {});

    const tag = `${w} ${u}`;
    if (r.overflow > 0) fails.push(`${tag} OVERFLOW +${r.overflow}`);
    if (r.placeholder) fails.push(`${tag} PLACEHOLDER`);
    if (r.tiny.length) fails.push(`${tag} <15px: ${[...new Set(r.tiny)].slice(0,3).join(" | ")}`);
    if (r.small.length) fails.push(`${tag} TAP<44: ${[...new Set(r.small)].slice(0,4).join(" | ")}`);
    if (r.wide.length) fails.push(`${tag} MEASURE: ${[...new Set(r.wide)].slice(0,3).join(" | ")}`);
    if (r.h1 !== 1) fails.push(`${tag} H1 ${r.h1}`);
    if (r.bgs.length > 3) fails.push(`${tag} BG ${r.bgs.join(",")}`);
    await p.close();
  }
  await ctx.close();
}
console.log(fails.length ? fails.join("\n") : "ALL PASS");
await b.close();
