import type { MetadataRoute } from "next";
import { SITE_URL, IS_PRODUCTION_SITE } from "@/lib/site-url";

export default function robots(): MetadataRoute.Robots {
  // A staging or preview host must never be crawlable — otherwise it competes
  // with the real site for the same queries.
  if (!IS_PRODUCTION_SITE) return { rules: { userAgent: "*", disallow: "/" } };
  return { rules: { userAgent: "*", allow: "/", disallow: ["/api/"] }, sitemap: `${SITE_URL}/sitemap.xml` };
}
