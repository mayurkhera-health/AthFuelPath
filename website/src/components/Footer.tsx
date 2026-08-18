import Link from "next/link";
import { Logo } from "./ui/Logo";
import { footer, site } from "@/content/site";

export function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer__grid">
          <div className="footer__brand">
            <Logo />
            <p style={{ marginTop: "var(--s4)", maxWidth: "34ch" }}>{footer.blurb}</p>
            <p style={{ marginTop: "var(--s4)" }}><a href={`mailto:${site.supportEmail}`}>{site.supportEmail}</a></p>
          </div>
          <nav aria-labelledby="f-explore">
            <h2 id="f-explore">Explore</h2>
            <ul>{footer.explore.map((l) => <li key={l.href}><Link href={l.href}>{l.label}</Link></li>)}</ul>
          </nav>
          <nav aria-labelledby="f-legal">
            <h2 id="f-legal">Legal &amp; safety</h2>
            <ul>{footer.legal.map((l) => <li key={l.href}><Link href={l.href}>{l.label}</Link></li>)}</ul>
          </nav>
        </div>
        <div className="footer__bottom">
          <span>© {new Date().getFullYear()} {site.company} · {site.location}</span>
          <span>{site.disclaimer}</span>
        </div>
      </div>
    </footer>
  );
}
