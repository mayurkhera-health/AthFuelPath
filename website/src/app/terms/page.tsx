import { LegalDoc } from "@/components/Legal";
import { TERMS_OF_SERVICE } from "@/content/legal";
import { routeMetadata } from "@/lib/meta";
export const metadata = routeMetadata({
  title: "Terms of Service",
  description: "The terms that govern using AthFuelPath.",
  path: "/terms",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});
export default function Terms() { return <LegalDoc title="Terms of Service" sections={TERMS_OF_SERVICE} />; }
