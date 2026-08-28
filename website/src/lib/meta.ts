import type { Metadata } from "next";
import { SITE_URL } from "@/lib/site-url";
import { site } from "@/content/site";

/**
 * Builds the og, twitter and canonical metadata block for one route. og:image falls
 * back to the home share card for routes that don't have their own (see
 * CHANGE 1 §1.2 in the redesign spec — only the named marketing routes ship
 * a bespoke image today).
 */
export function routeMetadata({
  title,
  description,
  path,
  image = "/og/home.jpg",
  imageAlt,
  bareTitle = false,
}: {
  title: string;
  description: string;
  path: string;
  image?: string;
  imageAlt: string;
  /** Set for routes (home) whose title is already the full brand string —
   *  skips the layout's "%s · AthFuelPath" template so it isn't duplicated. */
  bareTitle?: boolean;
}): Metadata {
  const url = `${SITE_URL}${path}`;
  const imageUrl = `${SITE_URL}${image}`;
  const ogTitle = bareTitle ? title : `${title} · ${site.name}`;
  return {
    title: bareTitle ? { absolute: title } : title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: ogTitle,
      description,
      url,
      type: "website",
      siteName: site.name,
      images: [{ url: imageUrl, width: 1200, height: 630, alt: imageAlt }],
    },
    twitter: {
      card: "summary_large_image",
      title: ogTitle,
      description,
      images: [imageUrl],
    },
  };
}
