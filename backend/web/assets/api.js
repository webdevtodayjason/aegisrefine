// Aegis backend client — same-origin, per API_CONTRACT.md
const Aegis = {
  async _req(method, path, body, headers) {
    const opt = { method, headers: Object.assign({ "Content-Type": "application/json" }, headers || {}) };
    if (body !== undefined) opt.body = JSON.stringify(body);
    const r = await fetch(path, opt);
    const txt = await r.text(); let data; try { data = JSON.parse(txt); } catch { data = txt; }
    if (!r.ok) throw new Error(typeof data === "object" ? (data.detail || JSON.stringify(data)) : data);
    return data;
  },
  createCheckout(dataset_url, email) { return this._req("POST", "/jobs/", { dataset_url, email }); },
  simulatePaid(dataset_url, email) { return this._req("POST", "/dev/simulate-payment", { dataset_url, email }); },
  listJobs(limit) { return this._req("GET", `/jobs/?limit=${limit || 50}`); },
  getJob(jobId) { return this._req("GET", `/jobs/${jobId}`); },
  process(jobId, sample, hard_doc) { return this._req("POST", `/jobs/${jobId}/process`, { sample, hard_doc }); },
  approve(ticketId, adminKey, who) { return this._req("POST", `/admin/gate/${ticketId}/approve`, undefined, { "X-Admin-Key": adminKey, "X-Admin-User": who || "operator" }); },
  reject(ticketId, adminKey, who) { return this._req("POST", `/admin/gate/${ticketId}/reject`, undefined, { "X-Admin-Key": adminKey, "X-Admin-User": who || "operator" }); },
  execute(ticketId, adminKey) { return this._req("POST", `/admin/gate/${ticketId}/execute`, undefined, { "X-Admin-Key": adminKey }); },
  tickets(adminKey) { return this._req("GET", "/admin/gate/tickets", undefined, { "X-Admin-Key": adminKey }); },
  receipt(jobId) { return this._req("GET", `/admin/jobs/${jobId}/receipt`); },
  complete(jobId, output) { return this._req("POST", `/jobs/${jobId}/complete`, { output }); },
  aar(jobId) { return this._req("GET", `/jobs/${jobId}/aar`); },
  verify(jobId) { return this._req("GET", `/jobs/${jobId}/verify`); },
  activity(limit) { return this._req("GET", `/activity?limit=${limit || 40}`); },
};
// tiny query-string job id helper for pages that take ?job=N
Aegis.jobParam = () => new URLSearchParams(location.search).get("job");
