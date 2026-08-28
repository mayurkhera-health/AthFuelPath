import { SignupForm } from "./SignupForm";
import { trialLine } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Start free trial",
  description: "Create your parent account and set up your athlete's fueling path.",
  path: "/signup",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

export default function SignupPage() {
  return (
    <div className="form-page">
      <aside className="form-page__aside surface-dark">
        <span className="eyebrow">Getting started</span>
        <h2 className="h3">Their schedule is already set. Let&apos;s build the fueling around it.</h2>
        <ol className="mini-steps">
          <li><span className="n">1</span><span>Create your parent account here.</span></li>
          <li><span className="n">2</span><span>Open the app and add your athlete.</span></li>
          <li><span className="n">3</span><span>They get their own login. You get the weekly report.</span></li>
        </ol>
        <p className="notice notice--dark">{trialLine}</p>
      </aside>
      <div className="form-page__main"><SignupForm /></div>
    </div>
  );
}
