/**
 * Tests the two limiters in src/app/api/waitlist/route.ts.
 *
 * It does NOT retype them. The functions are cut out of the real file by text
 * and evaluated, so if someone edits the route the next run tests the edit. A
 * retyped copy would pass forever while the shipped code rotted.
 *
 * Why not hit the endpoint instead: deliver() only counts a send that actually
 * left the machine, and there is no Gmail from this container — locally every
 * submission fails at SMTP and the hourly counter never moves. Testing the real
 * ceiling therefore has to happen at the function.
 */
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("./src/app/api/waitlist/route.ts", import.meta.url), "utf8");

/* Everything from the first limiter constant to the end of mailBudgetSpent. */
const start = src.indexOf("const WINDOW_MS");
const end = src.indexOf("}", src.indexOf("function mailBudgetSpent")) + 1;
if (start < 0 || end < 10) throw new Error("could not locate the limiters — did the file change shape?");
/* Strip the only two bits of TypeScript in this range: the Map generic and the
   parameter/return annotations. Anything more elaborate belongs in a real
   transpile step, and if this ever needs one, that is the signal the limiters
   have outgrown living inside the route file. */
const code = src.slice(start, end)
  .replace(/new Map<[^>]*>/g, "new Map")
  .replace(/const sentAt: number\[\]/g, "const sentAt")
  .replace(/: (string|boolean)/g, "");

const { rateLimited, mailBudgetSpent, sentAt, hits, MAX_MAILS_PER_HOUR, MAX_PER_WINDOW } =
  await import(`data:text/javascript,${encodeURIComponent(
    code + "\nexport { rateLimited, mailBudgetSpent, sentAt, hits, MAX_MAILS_PER_HOUR, MAX_PER_WINDOW };"
  )}`);

let fails = 0;
const check = (name, cond) => { console.log(`${cond ? "  ok  " : "FAIL  "}${name}`); if (!cond) fails++; };

// 1. per-IP window
const ip = "1.2.3.4";
const blocked = [];
for (let i = 0; i < 8; i++) blocked.push(rateLimited(ip));
check(`per-IP: first ${MAX_PER_WINDOW} pass, rest blocked`,
  blocked.slice(0, MAX_PER_WINDOW).every((b) => !b) && blocked.slice(MAX_PER_WINDOW).every((b) => b));

// 2. a different address is unaffected
check("per-IP: a second address is not punished for the first", rateLimited("5.6.7.8") === false);

// 3. THE REGRESSION THIS FIX EXISTS FOR. Flood the map well past its ceiling
//    with fresh addresses, then confirm the blocked address is STILL blocked.
//    hits.clear() wiped it; so did least-recently-used eviction. Either way a
//    flood was a reset button.
for (let i = 0; i < 6000; i++) rateLimited(`10.0.${(i / 250) | 0}.${i % 250}`);
check("a 6,000-address flood does not reset a live counter", rateLimited(ip) === true);
check("and the map stays bounded through it", hits.size <= 5000);

// 4. the flood must not block strangers either — failing open for an untracked
//    address is the deliberate trade, so assert it rather than leave it to luck
check("a new address during the flood is not blocked", rateLimited("9.9.9.9") === false);

// 4. hourly ceiling
check("mail budget starts unspent", mailBudgetSpent() === false);
for (let i = 0; i < MAX_MAILS_PER_HOUR; i++) sentAt.push(Date.now());
check(`mail budget spent at ${MAX_MAILS_PER_HOUR}`, mailBudgetSpent() === true);

// 5. and it is a rolling window, not a latch
sentAt.length = 0;
sentAt.push(...Array.from({ length: MAX_MAILS_PER_HOUR }, () => Date.now() - 3_600_001));
check("hour-old sends expire out of the window", mailBudgetSpent() === false);
check("expired entries are dropped, not just ignored", sentAt.length === 0);

console.log(fails ? `\n${fails} FAILED` : "\nall passed");
process.exit(fails ? 1 : 0);
