import { LegalDoc } from "@/components/Legal";
import type { Section } from "@/content/legal";
import { routeMetadata } from "@/lib/meta";
export const metadata = routeMetadata({
  title: "Disclaimer",
  description: "AthFuelPath gives sports nutrition guidance to learn from. It is not medical nutrition therapy.",
  path: "/disclaimer",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

// Wording mirrors fuelup-mobile/components/shared/Disclaimer.tsx and the ToS warning.
const DISCLAIMER: Section[] = [
  { type: "warning", text: "AthFuelPath provides sports nutrition guidance by a Registered Dietitian Nutritionist. Not medical advice. Consult your doctor for personalized care." },
  { type: "body", text: "AthFuelPath provides educational food and nutrition guidance only. It is not medical nutrition therapy, medical advice, diagnosis, or treatment, and it does not replace a physician, registered dietitian, or other qualified health professional." },
  { type: "body", text: "AthFuelPath is not designed for weight loss, calorie restriction, or any restrictive dietary purpose. It follows a food-first approach and does not recommend supplements for athletes under 18." },
  { type: "body", text: "Always consult a qualified professional before making significant changes to a child's diet, especially where allergies, medical conditions, or disordered-eating concerns exist." },
  { type: "body", text: "Questions: support@athfuelpath.com · Food Explorers LLC · San Jose, California." },
];
export default function Disclaimer() { return <LegalDoc title="Disclaimer" sections={DISCLAIMER} />; }
