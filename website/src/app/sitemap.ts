import type { MetadataRoute } from "next";
import { questionPages } from "@/content/questions";
import { SITE_URL } from "@/lib/site-url";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = SITE_URL;
  const pages = ["", "/parents", "/coaches", "/safety", "/our-story", "/faq", "/signup", "/privacy", "/terms", "/disclaimer"];
  return [
    /* /parents sits just under the homepage: it is the second entry point for
       the main audience and carries its own H1, title and intent rather than
       restating the homepage. Deliberately NO cross-canonical between the two —
       they are distinct pages answering distinct questions. */
    ...pages.map((p) => ({ url: `${base}${p}`, changeFrequency: "monthly" as const, priority: p === "" ? 1 : p === "/parents" ? 0.9 : 0.7 })),
    ...questionPages.map((q) => ({ url: `${base}/questions/${q.slug}`, changeFrequency: "monthly" as const, priority: 0.6 })),
  ];
}
