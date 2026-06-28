"use client";

// Shared app shell (refine persona) — ported from the static site's assets/shell.js.
// Sidebar (brand + WORKSPACE/ACCOUNT nav + signed-in identity) and topbar (crumb + cross
// link) wrap every authed page; {children} render in the main content area. Built with the
// design tokens so it matches the dark-teal static look 1:1.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { me, logout } from "@/lib/api";

type NavItem = { href: string; icon: string; label: string };
type NavGroup = { head: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  {
    head: "WORKSPACE",
    items: [
      { href: "/dashboard", icon: "▦", label: "Dashboard" },
      { href: "/new-order", icon: "＋", label: "New order" },
      { href: "/certificate", icon: "⛉", label: "Certificates" },
    ],
  },
  {
    head: "ACCOUNT",
    items: [
      { href: "/billing", icon: "$", label: "Billing" },
      { href: "/settings", icon: "⚙", label: "Settings" },
    ],
  },
];

// Order-detail pages live under /orders but highlight their nav parent (Dashboard),
// mirroring the static shell's alias map.
function isActive(href: string, pathname: string): boolean {
  if (pathname === href || pathname.startsWith(`${href}/`)) return true;
  if (href === "/dashboard" && pathname.startsWith("/orders")) return true;
  return false;
}

// Crumb: the active item's label (root "aegis / <label>"), falling back to a cleaned slug.
function crumbFor(pathname: string): string {
  for (const g of GROUPS) {
    for (const it of g.items) if (isActive(it.href, pathname)) return it.label.toLowerCase();
  }
  const seg = pathname.split("/").filter(Boolean)[0];
  return seg ? seg.replace(/-/g, " ") : "dashboard";
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [who, setWho] = useState("Loading…");

  // Pull the real signed-in identity into the foot card (email; "Not signed in" on error).
  useEffect(() => {
    let alive = true;
    me()
      .then((u) => alive && setWho(u.email))
      .catch(() => alive && setWho("Not signed in"));
    return () => {
      alive = false;
    };
  }, []);

  // POST logout, then bounce to the login page regardless of outcome.
  async function signOut() {
    try {
      await logout();
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <div className="grid min-h-screen grid-cols-[244px_1fr]">
      {/* sidebar */}
      <aside className="sticky top-0 flex h-screen flex-col overflow-auto border-r border-line bg-panel-2 px-3.5 py-[18px]">
        <Link href="/dashboard" className="flex items-center gap-2.5 px-2 pb-[18px] pt-1.5">
          <b className="font-mono text-[13.5px] font-semibold tracking-[0.14em]">
            AEGIS<span className="text-teal">&nbsp;REFINE</span>
          </b>
        </Link>

        {GROUPS.map((group) => (
          <div key={group.head} className="contents">
            <div className="px-2.5 pb-1.5 pt-3.5 font-mono text-[9.5px] tracking-[0.16em] text-muted-3">
              {group.head}
            </div>
            {group.items.map((item) => {
              const active = isActive(item.href, pathname);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={[
                    "flex items-center gap-[11px] rounded-[7px] border px-2.5 py-[9px] text-[13.5px] transition-all",
                    active
                      ? "border-teal-line bg-teal-dim text-teal"
                      : "border-transparent text-muted hover:bg-white/[0.04] hover:text-text",
                  ].join(" ")}
                >
                  <span className="inline-block w-4 text-center">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}

        {/* Sign out lives in the ACCOUNT group but is an action, not a route. */}
        <button
          type="button"
          onClick={signOut}
          className="flex items-center gap-[11px] rounded-[7px] border border-transparent px-2.5 py-[9px] text-left text-[13.5px] text-muted transition-all hover:bg-white/[0.04] hover:text-text"
        >
          <span className="inline-block w-4 text-center">⏻</span>
          Sign out
        </button>

        {/* signed-in identity */}
        <div className="mt-auto rounded-[10px] border border-line bg-panel p-3.5">
          <div className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
            Signed in
          </div>
          <div className="break-all font-mono text-[12px] text-muted-2">{who}</div>
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-line bg-bg/80 px-[clamp(20px,3vw,38px)] py-3.5 backdrop-blur-[12px]">
          <div className="font-mono text-[12px] text-muted-2">
            aegis / <span className="text-text">{crumbFor(pathname)}</span>
          </div>
          <Link href="/" className="font-mono text-[13px] text-muted transition-colors hover:text-text">
            ↗ aegisrefine.com
          </Link>
        </header>
        <div className="p-[clamp(22px,3vw,38px)]">{children}</div>
      </div>
    </div>
  );
}
