import type { MetadataRoute } from "next";
import { questionPages } from "@/content/questions";
import { SITE_URL } from "@/lib/site-url";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = SITE_URL;
  /* "/coaches" is deliberately absent (2026-08-29). The page still builds and
     still works — it was hidden from the nav and footer, not parked — so it
     stays reachable by direct link for a club Purvi sends it to. Dropping it
     here is what stops search engines putting strangers on a page that has been
     judged not ready for them. Add it back alongside the two links in site.ts,
     never on its own. */
  const pages = ["", "/parents", "/safety", "/our-story", "/faq", "/signup", "/privacy", "/terms", "/disclaimer"];
  return [
    /* /parents sits just under the homepage: it is the second entry point for
       the main audience and carries its own H1, title and intent rather than
       restating the homepage. Deliberately NO cross-canonical between the two —
       they are distinct pages answering distinct questions. */
    ...pages.map((p) => ({ url: `${base}${p}`, changeFrequency: "monthly" as const, priority: p === "" ? 1 : p === "/parents" ? 0.9 : 0.7 })),
    ...questionPages.map((q) => ({ url: `${base}/questions/${q.slug}`, changeFrequency: "monthly" as const, priority: 0.6 })),
  ];
}
