import type { MetadataRoute } from "next";
import { questionPages } from "@/content/questions";
import { SITE_URL } from "@/lib/site-url";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = SITE_URL;
  const pages = ["", "/safety", "/our-story", "/faq", "/signup", "/privacy", "/terms", "/disclaimer"];
  return [
    ...pages.map((p) => ({ url: `${base}${p}`, changeFrequency: "monthly" as const, priority: p === "" ? 1 : 0.7 })),
    ...questionPages.map((q) => ({ url: `${base}/questions/${q.slug}`, changeFrequency: "monthly" as const, priority: 0.6 })),
  ];
}
