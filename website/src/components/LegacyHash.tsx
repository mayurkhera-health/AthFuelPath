"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Sends legacy homepage anchors to the page that replaced them.
 *
 * "For Parents" was a nav anchor (/#for-parents) before /parents existed, and
 * links using it may be in an email, a text message or someone's bookmarks.
 *
 * A server-side 301 cannot do this: a URL fragment is never sent to the server,
 * so /#for-parents arrives at the origin as "/" and there is nothing to
 * redirect on. It has to be handled in the browser, which is the only place
 * that can see the hash.
 *
 * replace(), not push(), so the back button returns to wherever the person came
 * from rather than bouncing them through the redirect again.
 */
const MOVED: Record<string, string> = {
  "#for-parents": "/parents",
  "#parents": "/parents",
};

export function LegacyHash() {
  const router = useRouter();
  useEffect(() => {
    const to = MOVED[window.location.hash];
    if (to) router.replace(to);
  }, [router]);
  return null;
}
