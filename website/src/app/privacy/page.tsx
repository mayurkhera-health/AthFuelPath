import { LegalDoc } from "@/components/Legal";
import { PRIVACY_POLICY } from "@/content/legal";
import { routeMetadata } from "@/lib/meta";
export const metadata = routeMetadata({
  title: "Privacy Policy",
  description: "What AthFuelPath collects, what your athlete is told, and what you control as a parent.",
  path: "/privacy",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});
export default function Privacy() { return <LegalDoc title="Privacy Policy" sections={PRIVACY_POLICY} />; }
