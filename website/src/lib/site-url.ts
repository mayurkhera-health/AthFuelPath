/**
 * One source of truth for the canonical origin.
 *
 * Hardcoding https://athfuelpath.com meant every preview or staging deploy
 * emitted production canonicals and a production sitemap. Set
 * NEXT_PUBLIC_SITE_URL per environment; anything that is not the production
 * origin is served noindex so a staging host cannot get crawled and ranked.
 */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://athfuelpath.com").replace(/\/$/, "");
export const IS_PRODUCTION_SITE = SITE_URL === "https://athfuelpath.com";
