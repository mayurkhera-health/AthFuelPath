import Link from "next/link";
import { Bolt } from "./Icons";

export function Logo() {
  return (
    <Link href="/" className="logo" aria-label="AthFuelPath — home">
      <span className="logo__mark" aria-hidden><Bolt /></span>
      <span>AthFuelPath</span>
    </Link>
  );
}
