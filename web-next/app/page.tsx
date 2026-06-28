import Link from "next/link";
import { tryUrl } from "@/lib/api";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-x-hidden">
      {/* nav */}
      <nav className="sticky top-0 z-50 flex items-center justify-between gap-6 border-b border-line bg-bg/70 px-5 py-3.5 backdrop-blur sm:px-12">
        <div className="font-semibold tracking-wide">
          AEGIS <span className="text-teal">REFINE</span>
        </div>
        <div className="flex items-center gap-6 text-sm text-muted">
          <Link href="/how-it-works" className="hover:text-text">How it works</Link>
          <Link href="/pricing" className="hover:text-text">Pricing</Link>
          <Link href="/login" className="btn-teal px-4 py-2 text-sm">Launch app →</Link>
        </div>
      </nav>

      {/* hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-16 sm:px-12 sm:py-24 md:grid-cols-[1.15fr_.85fr]">
        <div>
          <div className="eyebrow mb-6 inline-flex items-center gap-2.5 rounded-full border border-teal-line bg-teal-dim px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-green shadow-[0_0_8px_#22C55E]" />
            REFINE + SYNTHESIZE · FLAT CAPPED QUOTE · SIGNED PROOF
          </div>
          <h1 className="mb-5 text-[clamp(44px,6vw,78px)] font-medium leading-[1.02] tracking-[-0.02em]">
            Messy data in.
            <br />
            <span className="text-teal">Signed training data out.</span>
          </h1>
          <p className="mb-8 max-w-[500px] text-[clamp(16px,1.6vw,19px)] leading-relaxed text-muted">
            Refine your data or synthesize new examples — one flat price, quoted up front and capped,
            with a certificate you can re-verify.
          </p>
          <div className="flex flex-wrap gap-3.5">
            <Link href="/new-order" className="btn-teal px-5 py-3 text-[15px]">Get my quote&nbsp;→</Link>
            <a href={tryUrl} className="btn-ghost px-5 py-3 text-[15px]">Try it instantly — no signup</a>
          </div>
          <div className="mt-10 flex flex-wrap gap-x-9 gap-y-3.5 border-t border-line pt-6">
            {[
              ["128.5K+", "RECORDS REFINED"],
              ["94.7/100", "QUALITY SCORE"],
              ["100%", "SIGNED & RE-VERIFIABLE"],
            ].map(([n, l]) => (
              <div key={l} className="flex flex-col gap-0.5">
                <span className="font-mono text-xl font-semibold text-teal">{n}</span>
                <span className="font-mono text-[10.5px] tracking-[0.14em] text-muted-2">{l}</span>
              </div>
            ))}
          </div>
        </div>

        {/* hero art: isometric refinement layers */}
        <div className="relative hidden aspect-square items-center justify-center md:flex">
          <div className="absolute h-72 w-72 animate-pulse rounded-full border border-teal/10" />
          <div className="absolute h-[360px] w-[360px] rounded-full border border-teal/[0.07]" />
          <div style={{ perspective: "1100px" }}>
            <div style={{ transformStyle: "preserve-3d", transform: "rotateX(58deg) rotateZ(45deg)" }} className="relative h-[200px] w-[200px]">
              {[0, 48, 96].map((z, i) => (
                <div
                  key={z}
                  className="absolute inset-0 border"
                  style={{
                    transform: `translateZ(${z}px)`,
                    borderColor: `rgba(0,229,204,${0.35 + i * 0.25})`,
                    background: `rgba(0,229,204,${0.04 + i * 0.03})`,
                    backgroundImage:
                      "linear-gradient(rgba(0,229,204,.2) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,204,.2) 1px,transparent 1px)",
                    backgroundSize: "25px 25px",
                    boxShadow: `0 0 ${30 + i * 15}px rgba(0,229,204,${0.15 + i * 0.12})`,
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
