import Link from "next/link";

export default function AboutPage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8 text-sm leading-relaxed text-gray-700 dark:text-gray-300">
      <div>
        <Link href="/" className="text-xs underline">
          ← Back to scenarios
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">About Blackbox</h1>
      </div>

      <p>
        Blackbox is a mediation and forensics layer for AI agents — <strong>EDR for AI agents</strong>, not a
        guardrail and not a posture scanner. It does not primarily exist to prevent incidents. It exists to make
        them investigable: every model call and every tool call an agent makes transits Blackbox, which records it,
        verifies it, evaluates it against policy and behavioural baseline, and enforces decisions.
      </p>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">What detection actually claims</h2>
        <p>
          Blackbox surfaces <strong>ranked candidate triggers</strong>, never a single root cause, and it detects{" "}
          <strong>departure from declared scope</strong>, never intent. Detecting intent is an open research
          problem; detecting scope deviation is tractable. You will not see the words &ldquo;root cause&rdquo; or
          &ldquo;malicious intent&rdquo; anywhere in this system&apos;s output — anywhere you see a claim that
          sounds stronger than that, it&apos;s a bug, not a feature.
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Explicitly out of scope</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Runtime execution escape detection.</strong> Blackbox covers reasoning compromise (injected
            instructions) and privilege boundary escape (legitimate credentials used in unauthorised ways) fully.
            An agent acting entirely <em>outside</em> the mediated path — bypassing Blackbox altogether — needs
            eBPF-level visibility this build doesn&apos;t have. It is mitigated architecturally instead: agents hold
            no credentials (I3) and run with no network egress except to the mediator, so bypass is meant to be
            architecturally difficult, not just discouraged. It is not detected if it happens.
          </li>
          <li>
            <strong>Endpoint agents outside the cloud boundary.</strong> This build assumes agents run in the same
            network Blackbox mediates; an agent running on somebody&apos;s laptop, outside that boundary, is not
            covered.
          </li>
          <li>
            <strong>Multi-tenancy.</strong> Single tenant in this proof of concept. A control-plane/data-plane split
            for real multi-tenancy is documented as a direction, not built.
          </li>
          <li>
            <strong>SOC 2 controls, data residency.</strong> Not addressed here.
          </li>
          <li>
            <strong>Intent detection.</strong> See above — scope deviation only.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">The demo</h2>
        <p>
          Scenarios marked <span className="font-medium">Live</span> run a real model against a real, synthetic
          company (&ldquo;Northwind Support&rdquo;) through the real mediator. Nothing about the company, its
          customers, or its data is real. Scenarios marked <span className="font-medium">Recorded</span> are
          hand-captured traces from runs that worked — they are elaborately constructed and frequently don&apos;t
          fire reliably live, so they are never attempted live and are always labelled as recorded, never presented
          as if they just ran. A live attempt that errors, times out, or simply doesn&apos;t demonstrate anything
          falls back to the most recent trace that did, with a visible notice — this is a deliberate design choice
          (see Invariant I9), not a failure being hidden.
        </p>
      </section>
    </main>
  );
}
