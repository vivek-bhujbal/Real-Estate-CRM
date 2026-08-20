import Link from "next/link";

export function AuthFrame({
  eyebrow,
  title,
  description,
  children,
  alternate
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  alternate: { prompt: string; label: string; href: string };
}) {
  return (
    <main className="auth-page">
      <section className="auth-aside" aria-label="Product introduction">
        <Link className="brand brand-light" href="/">
          <span className="brand-mark" aria-hidden="true">E</span>
          <span>EstateOps</span>
        </Link>
        <div className="auth-aside-copy">
          <p className="overline overline-light">Revenue operations, connected</p>
          <h2>One precise view from first inquiry to handover.</h2>
          <p>
            Manage relationships, inventory, approvals, and collections with clear ownership
            and an audit trail at every step.
          </p>
        </div>
        <p className="auth-aside-foot">Built for modern real estate teams</p>
      </section>
      <section className="auth-main">
        <div className="auth-mobile-brand">
          <span className="brand-mark" aria-hidden="true">E</span>
          <span>EstateOps</span>
        </div>
        <div className="auth-card">
          <p className="overline">{eyebrow}</p>
          <h1>{title}</h1>
          <p className="auth-description">{description}</p>
          {children}
          <p className="auth-alternate">
            {alternate.prompt} <Link href={alternate.href}>{alternate.label}</Link>
          </p>
        </div>
      </section>
    </main>
  );
}

