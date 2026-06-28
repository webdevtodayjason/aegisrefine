// Shared app shell — TWO distinct personas, matching the blueprints:
//   refine = the CUSTOMER workspace (AEGIS REFINE)
//   ops    = the OPERATOR / super-admin console (AEGIS OPS)
// Pages just call AppShell.mount(activeKey, crumb); the persona is inferred from the key.
const AppShell = {
  personas: {
    refine: {
      brand: 'AEGIS<span class="teal">&nbsp;REFINE</span>', home: "dashboard.html",
      groups: [
        ["WORKSPACE", [
          ["dashboard.html", "▦", "Dashboard", "dashboard"],
          ["new-order.html", "＋", "New order", "new-order"],
          ["marketplace.html", "⊞", "Marketplace", "marketplace"],
          ["certificate.html", "⛉", "Certificates", "certificate"],
        ]],
        ["ACCOUNT", [
          ["billing.html", "$", "Billing", "billing"],
          ["settings.html", "⚙", "Settings", "settings"],
          ["#", "⏻", "Sign out", "logout"],
        ]],
      ],
      // Real signed-in identity (filled by loadMe() on mount) — not a fake credits balance.
      foot: '<div class="label" style="margin-bottom:6px">Signed in</div><div class="mono muted2" id="shellWho" style="font-size:12px;word-break:break-all">Loading…</div>',
      cross: '<a class="navlink" style="font-size:13px" href="../">↗ aegisrefine.com</a>',
    },
    ops: {
      brand: 'AEGIS<span class="teal">&nbsp;OPS</span>', home: "ops.html",
      groups: [
        ["OPERATIONS", [
          ["ops.html", "⛉", "Approvals", "approvals"],
          ["job-queue.html", "≡", "Job queue", "job-queue"],
          ["audit-log.html", "▤", "Audit log", "audit-log"],
          ["policies.html", "◷", "Policies", "policies"],
          ["agents.html", "△", "Agents", "agents"],
        ]],
        ["CRM", [
          ["customers.html", "⊞", "Customers", "customers"],
          ["dashboard.html", "↩", "Customer view", "customer-view"],
        ]],
        ["ACCOUNT", [
          ["#", "⏻", "Sign out", "logout"],
        ]],
      ],
      foot: '<div style="display:flex;align-items:center;gap:10px"><span style="width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#00E5CC,#3A7BFF);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:700;color:#04100E">OP</span><div><div style="font-size:13px;font-weight:600">Ops Console</div><div class="mono amber" style="font-size:9.5px;letter-spacing:.12em">ADMINISTRATOR</div></div></div>',
      cross: '<a class="navlink" style="font-size:13px" href="dashboard.html">↩ Customer view</a>',
    },
  },
  personaOf: {
    dashboard: "refine", "new-order": "refine", "order-detail": "refine",
    certificate: "refine", marketplace: "refine", billing: "refine", settings: "refine",
    ops: "ops", approvals: "ops", "job-queue": "ops", "audit-log": "ops", policies: "ops",
    agents: "ops", customers: "ops", "customer-view": "ops",
  },
  alias: { "order-detail": "dashboard", ops: "approvals" },  // detail pages highlight their nav parent
  // POST logout, then bounce to the login page regardless of outcome.
  logout: () => fetch("/auth/logout", { method: "POST", credentials: "include" })
    .finally(() => { location.href = "/login.html"; }),
  // Pull the real signed-in identity into the refine foot card (#shellWho); ops has no such slot.
  loadMe() {
    const el = document.getElementById("shellWho");
    if (!el) return;
    fetch("/auth/me", { credentials: "include" })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(me => { el.textContent = (me && me.email) ? me.email : "Not signed in"; })
      .catch(() => { el.textContent = "Not signed in"; });
  },
  sidebar(pk, active) {
    const p = this.personas[pk];
    let h = `<a class="brand" href="${p.home}"><img src="assets/shield.svg" alt="Aegis"><b>${p.brand}</b></a>`;
    for (const [head, items] of p.groups) {
      h += `<div class="navhead">${head}</div>`;
      for (const [href, ico, label, key] of items) {
        const cls = `navlink ${key === active ? "active" : ""}`;
        h += key === "logout"
          ? `<a class="${cls}" href="#" onclick="AppShell.logout();return false"><span class="ico">${ico}</span> ${label}</a>`
          : `<a class="${cls}" href="${href}"><span class="ico">${ico}</span> ${label}</a>`;
      }
    }
    return h + `<div class="sidecard">${p.foot}</div>`;
  },
  topbar(pk, crumb) {
    const root = pk === "ops" ? "ops" : "aegis";
    return `<div class="crumb">${root} / <span style="color:var(--text)">${crumb}</span></div>${this.personas[pk].cross}`;
  },
  mount(active, crumb) {
    const pk = this.personaOf[active] || "refine";
    const hl = this.alias[active] || active;
    const s = document.getElementById("sidebar"); if (s) s.innerHTML = this.sidebar(pk, hl);
    const t = document.getElementById("topbar"); if (t) t.innerHTML = this.topbar(pk, crumb);
    this.loadMe();
  },
};
