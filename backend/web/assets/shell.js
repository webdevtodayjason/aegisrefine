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
          ["dashboard.html", "▤", "Datasets", "datasets"],
          ["marketplace.html", "⊞", "Marketplace", "marketplace"],
          ["certificate.html", "⛉", "Certificates", "certificate"],
        ]],
        ["ACCOUNT", [
          ["billing.html", "$", "Billing", "billing"],
          ["settings.html", "⚙", "Settings", "settings"],
        ]],
      ],
      foot: '<div class="label" style="margin-bottom:6px">Credits balance</div><div class="mono teal" style="font-size:19px;font-weight:600">$142.75</div>',
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
      ],
      foot: '<div style="display:flex;align-items:center;gap:10px"><span style="width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#00E5CC,#3A7BFF);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:700;color:#04100E">OP</span><div><div style="font-size:13px;font-weight:600">Ops Console</div><div class="mono amber" style="font-size:9.5px;letter-spacing:.12em">ADMINISTRATOR</div></div></div>',
      cross: '<a class="navlink" style="font-size:13px" href="dashboard.html">↩ Customer view</a>',
    },
  },
  personaOf: {
    dashboard: "refine", "new-order": "refine", datasets: "refine", "order-detail": "refine",
    certificate: "refine", marketplace: "refine", billing: "refine", settings: "refine",
    ops: "ops", approvals: "ops", "job-queue": "ops", "audit-log": "ops", policies: "ops",
    agents: "ops", customers: "ops", "customer-view": "ops",
  },
  alias: { "order-detail": "datasets", ops: "approvals" },  // detail pages highlight their nav parent
  sidebar(pk, active) {
    const p = this.personas[pk];
    let h = `<a class="brand" href="${p.home}"><img src="assets/shield.svg" alt="Aegis"><b>${p.brand}</b></a>`;
    for (const [head, items] of p.groups) {
      h += `<div class="navhead">${head}</div>`;
      for (const [href, ico, label, key] of items)
        h += `<a class="navlink ${key === active ? "active" : ""}" href="${href}"><span class="ico">${ico}</span> ${label}</a>`;
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
  },
};
