import { routeMetadata } from "@/lib/meta";
import { Hero } from "@/components/sections/Hero";
import { Questions } from "@/components/sections/Questions";
import { Schedule } from "@/components/sections/Schedule";
import { Steps } from "@/components/sections/Steps";
import { Cook } from "@/components/sections/Cook";
import { Coach } from "@/components/sections/Coach";
import { Dietitian } from "@/components/sections/Dietitian";
import { Proof } from "@/components/sections/Proof";
import { Safety } from "@/components/sections/Safety";
import { Plan } from "@/components/sections/Plan";
import { Closing } from "@/components/sections/Closing";

export const metadata = routeMetadata({
  title: "AthFuelPath — sports nutrition built around your soccer player's schedule",
  description:
    "AthFuelPath turns your player's practices, games and tournaments into personalised fueling guidance — so they know what to eat, when to eat, and why it matters. For soccer players 13–17.",
  path: "/",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
  bareTitle: true,
});

export default function Home() {
  return (
    <>
      <Hero />
      <Questions />
      <Schedule />
      <Steps />
      <Cook />
      <Coach />
      <Dietitian />
      <Proof />
      <Safety />
      <Plan />
      <Closing />
    </>
  );
}
