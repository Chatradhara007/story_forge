/* StoryForge website. Plain JavaScript, no build step: served by the backend at /app/.
   To use a backend at another address, open  index.html?api=https://your-backend  */
"use strict";

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const view = document.getElementById("view");
const $ = (sel, root = document) => root.querySelector(sel);

const state = {
  config: { auth_required: false },
  user: null,
  token: load("storyforge-token"),
  books: [],
  book: null,
  chapters: [],
  pendingEdit: null,        // chapter to re-edit on the Add page
  watching: new Set(),      // job ids the sidebar is following
};

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
function load(key) { try { return localStorage.getItem(key); } catch { return null; } }
function save(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* optional */ } }
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const pretty = s => String(s ?? "").replace(/_/g, " ");
const plural = (n, one, many = one + "s") => `${n.toLocaleString()} ${n === 1 ? one : many}`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const sanitizeId = s => s.replace(/\.[^.]+$/, "").replace(/[\/\\?#]+/g, "-").trim().slice(0, 100);
const naturalSort = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });

class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }

async function api(path, options = {}) {
  const init = { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } };
  if (state.token) init.headers.Authorization = `Bearer ${state.token}`;
  if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
  let response;
  try {
    response = await fetch(API + path, init);
  } catch {
    throw new ApiError("Can't reach the StoryForge server. Check your connection, or that the backend is running.", 0);
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && state.config.auth_required && !path.startsWith("/auth/")) {
    signOut(true);
    throw new ApiError("Your session has ended. Please sign in again.", 401);
  }
  if (!response.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = detail.map(d => `${(d.loc || []).slice(-1)[0] || "input"}: ${d.msg}`).join("; ");
    throw new ApiError(detail || `The request failed (${response.status}).`, response.status);
  }
  return data;
}
const bookApi = (path, options) => api(`/projects/${state.book}${path}`, options);

function errorBox(err) { return `<div class="notice error" role="alert">${esc(err.message || err)}</div>`; }
function loading(text) { return `<p><span class="spinner" aria-hidden="true"></span> ${esc(text)}</p>`; }
function sevTag(sev) {
  const label = { high: "Serious", medium: "Worth a look", low: "Unsure" }[sev] || sev;
  return `<span class="tag ${esc(sev)}">${label}</span>`;
}
const KIND = { attribute: "Changed detail", status: "Impossible state", timeline: "Timeline conflict" };
const TYPE_TITLE = { character: "Characters", location: "Places", item: "Objects", event: "Events", other: "Other" };
const currentBook = () => state.books.find(b => b.id === state.book) || {};
function chapterLink(id, number) {
  return `<a href="#/chapter/${encodeURIComponent(id)}">${number != null ? `Chapter ${number}` : esc(id)}</a>`;
}
function setTitle(text) { document.title = text ? `${text} – StoryForge` : "StoryForge"; }

// ---------------------------------------------------------------------------
// sign in
// ---------------------------------------------------------------------------
function signOut(rerender = true) {
  state.token = null; state.user = null; save("storyforge-token", null);
  if (rerender) showLanding();
}

const WORDMARK = `<span class="wordmark"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M7 6h13a5 5 0 0 1 5 5v15H12a5 5 0 0 1-5-5z" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M11 13h10M11 18h7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>StoryForge</span>`;

function showOnly(id) {
  ["landing", "signin", "app"].forEach(x => { $("#" + x).hidden = x !== id; });
  window.scrollTo(0, 0);
}

function showLanding() {
  showOnly("landing");
  setTitle("");
  const c = state.config;
  const box = $("#landing");
  box.className = "landing";
  const cta = c.auth_required
    ? `<button class="btn" data-go="${c.registration_open ? "register" : "signin"}">${c.registration_open ? "Create your account" : "Sign in"}</button>
       ${c.registration_open ? `<button class="btn quiet" data-go="signin">I already have an account</button>` : ""}`
    : `<button class="btn" data-go="app">Open your books</button>`;
  box.innerHTML = `
    <header>${WORDMARK}${c.auth_required ? `<button class="btn quiet" data-go="signin">Sign in</button>` : ""}</header>
    <section class="hero">
      <div>
        <h1>Catch the continuity slips before your readers do.</h1>
        <p class="lead">Add your chapters as you write them. StoryForge keeps a story bible of every character, place and object,
          draws who is related to whom, and tells you the moment a new chapter disagrees with an earlier one, quoting both.</p>
        <div class="actions">${cta}</div>
      </div>
      <figure style="margin:0">
        <article class="issue sev-high">
          <div class="issue-head"><strong>Rook</strong><span class="kind">Timeline conflict</span></div>
          <p class="why">Rook is nine in chapter 1, and three years pass before chapter 3. He should be about twelve, but chapter 3 says fourteen.</p>
          <div class="facing">
            <div class="slip"><span class="where"><span>Chapter 1</span><span>earlier</span></span>Rook was <mark>nine</mark> that autumn</div>
            <div class="slip-arrow"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 10 C12 4, 20 4, 26 10 M26 10 l-5 -1 M26 10 l-1 -5 M26 22 C20 28, 12 28, 6 22 M6 22 l5 1 M6 22 l1 5" fill="none" stroke="#A8322D" stroke-width="2" stroke-linecap="round"/></svg></div>
            <div class="slip"><span class="where"><span>Chapter 3</span><span>later</span></span>Rook, <mark>fourteen</mark> now, carried the lamp</div>
          </div>
        </article>
        <figcaption class="hint" style="margin-top:1rem">The kind of slip it finds: an age that doesn't add up after a time skip.</figcaption>
      </figure>
    </section>
    <section class="points" aria-label="What it does">
      <div><h2>A story bible that keeps itself</h2><p>Every name a character goes by, everything the text says about them, and the chapter it says it in.</p></div>
      <div><h2>Mistakes shown side by side</h2><p>The two passages that disagree, with the clashing words marked. Keep what you meant on purpose; fix the rest.</p></div>
      <div><h2>Family trees that grow</h2><p>Drag through the chapters and watch marriages, rivalries and losses appear in the order your reader meets them.</p></div>
    </section>
    <footer>Your chapters stay private to your account.</footer>`;
  box.onclick = async (e) => {
    const go = e.target.closest("[data-go]")?.dataset.go;
    if (!go) return;
    if (go === "app") { save("storyforge-welcomed", "1"); await startApp(); }
    else showSignIn(go);
  };
}

function showSignIn(mode = "signin") {
  showOnly("signin");
  setTitle(mode === "register" ? "Create your account" : "Sign in");
  const box = $("#signin");
  const c = state.config;
  const registering = mode === "register";
  box.innerHTML = `
    <form class="signin-card" id="auth-form" novalidate>
      <p class="brand" style="margin-bottom:1.6rem"><span class="wordmark" style="display:flex;align-items:center;gap:.5rem"><svg viewBox="0 0 32 32" aria-hidden="true" style="width:1.6rem;height:1.6rem;color:var(--pencil)"><path d="M7 6h13a5 5 0 0 1 5 5v15H12a5 5 0 0 1-5-5z" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M11 13h10M11 18h7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>StoryForge</span></p>
      <h1 style="font-size:1.6rem">${registering ? "Create your account" : "Welcome back"}</h1>
      <p class="hint" style="margin:-.2rem 0 1.2rem">${registering ? "Your books and chapters are private to you." : "Sign in to get back to your books."}</p>
      ${registering ? `<div class="field"><label for="a-name">Your name <span class="hint">(optional)</span></label><input type="text" id="a-name" autocomplete="name"></div>` : ""}
      <div class="field"><label for="a-email">Email</label><input type="email" id="a-email" autocomplete="email" placeholder="you@example.com" required></div>
      <div class="field"><label for="a-pass">Password ${registering ? `<span class="hint">(at least 8 characters)</span>` : ""}</label>
        <input type="password" id="a-pass" autocomplete="${registering ? "new-password" : "current-password"}" required></div>
      ${registering && c.invite_required ? `<div class="field"><label for="a-invite">Invite code</label><input type="text" id="a-invite"></div>` : ""}
      <div id="auth-msg"></div>
      <div class="actions"><button class="btn" type="submit">${registering ? "Create account" : "Sign in"}</button>
        ${c.registration_open ? `<button class="btn quiet" type="button" id="switch">${registering ? "I already have an account" : "Create an account"}</button>` : ""}</div>
      <p style="margin:1.4rem 0 0;font-size:.9rem"><a href="#" id="to-welcome">Back to the welcome page</a></p>
    </form>`;
  $("#a-email").focus();
  $("#to-welcome").onclick = (e) => { e.preventDefault(); showLanding(); };
  const sw = $("#switch");
  if (sw) sw.onclick = () => showSignIn(registering ? "signin" : "register");
  $("#auth-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = { email: $("#a-email").value.trim(), password: $("#a-pass").value };
    if (!body.email || !body.password) { $("#auth-msg").innerHTML = errorBox("Enter your email and password."); return; }
    if (registering) { body.display_name = $("#a-name").value.trim() || null; const inv = $("#a-invite"); if (inv) body.invite_code = inv.value; }
    try {
      const r = await api(registering ? "/auth/register" : "/auth/login", { method: "POST", body });
      state.token = r.token; state.user = r.user; save("storyforge-token", r.token);
      if (!location.hash || location.hash === "#/") location.hash = "#/shelf";
      await startApp();
    } catch (err) { $("#auth-msg").innerHTML = errorBox(err); }
  };
}

function renderAccount(usage) {
  const box = $("#account");
  if (!state.user) { box.hidden = true; return; }
  box.hidden = false;
  const name = state.user.display_name || state.user.email;
  const limit = usage?.daily_chapter_limit;
  const used = usage?.chapters_today || 0;
  box.innerHTML = `<summary aria-label="Your account"><span class="avatar" aria-hidden="true">${esc(name.slice(0, 1).toUpperCase())}</span><span class="acct-name">${esc(name.split(" ")[0])}</span></summary>
    <div class="account-panel">
      <span class="who">${esc(name)}</span><span class="hint">${esc(state.user.email)}</span>
      ${limit ? `<p class="usage">${used} of ${limit} chapter checks used today
        <span class="usage-bar" aria-hidden="true"><span style="width:${Math.min(100, Math.round(used / limit * 100))}%"></span></span></p>` : ""}
      <button class="btn quiet small" id="sign-out" style="padding-left:0">Sign out</button>
    </div>`;
  $("#sign-out").onclick = () => { box.open = false; signOut(); };
  // The allowance changes as chapters are checked: refresh it whenever the menu opens.
  box.ontoggle = async () => {
    if (!box.open) return;
    try { const me = await api("/auth/me"); renderAccount(me); box.open = true; } catch { /* keep the old numbers */ }
  };
}

// ---------------------------------------------------------------------------
// books, sidebar, background activity
// ---------------------------------------------------------------------------
async function loadBooks() {
  ({ projects: state.books } = await api("/projects"));
  if (!state.books.some(b => b.id === state.book)) {
    const saved = Number(load("storyforge-book"));
    state.book = state.books.some(b => b.id === saved) ? saved : (state.books[0]?.id ?? null);
  }
  const select = $("#book-select");
  select.innerHTML = state.books.length
    ? state.books.map(b => `<option value="${b.id}">${esc(b.name)}</option>`).join("")
    : `<option value="">No books yet</option>`;
  select.value = state.book ?? "";
  select.disabled = !state.books.length;
}

function chooseBook(id) {
  state.book = id; save("storyforge-book", String(id));
  $("#book-select").value = id;
}

async function refreshSidebar(activeChapter) {
  const list = $("#chapter-list");
  const badge = $("#issue-count");
  document.querySelectorAll("[data-book-only]").forEach(el => { el.hidden = state.book == null; });
  $(".book-pick").hidden = !state.books.length;
  if (state.book == null) { badge.hidden = true; return; }
  try {
    ({ chapters: state.chapters } = await bookApi("/chapters"));
    list.innerHTML = state.chapters.length
      ? state.chapters.map(c => `<li><a href="#/chapter/${encodeURIComponent(c.chapter_id)}" ${c.chapter_id === activeChapter ? 'aria-current="page"' : ""}
          title="${esc(c.chapter_id)}: ${c.fact_count} facts${c.open_issue_count ? `, ${c.open_issue_count} open issues` : ""}">
          <span class="num">${c.chapter_number}</span><span class="cid">${esc(c.chapter_id)}</span>
          ${c.open_issue_count ? `<span class="flag" aria-label="${c.open_issue_count} open issues"></span>` : "<span></span>"}</a></li>`).join("")
      : `<li class="side-empty">No chapters yet. <a href="#/add">Add the first one</a>.</li>`;
    const open = state.chapters.reduce((n, c) => n + Number(c.open_issue_count || 0), 0);
    badge.hidden = open === 0;
    badge.textContent = open;
  } catch (err) {
    list.innerHTML = `<li class="side-empty">${esc(err.message)}</li>`;
  }
}

let activityTimer = null;
async function pollActivity() {
  clearTimeout(activityTimer);
  const box = $("#activity");
  if (state.book == null) { box.hidden = true; return; }
  let jobs = [];
  try { ({ jobs } = await bookApi("/jobs")); } catch { return; }
  const active = jobs.filter(j => j.status === "queued" || j.status === "running");
  const finished = jobs.filter(j => state.watching.has(j.id) && (j.status === "done" || j.status === "failed"));
  finished.forEach(j => state.watching.delete(j.id));
  active.forEach(j => state.watching.add(j.id));
  if (finished.length) {
    refreshSidebar(currentChapterInRoute());
    window.dispatchEvent(new CustomEvent("storyforge:jobs-finished"));
  }
  box.hidden = active.length === 0;
  if (active.length) {
    const j = active[0];
    box.innerHTML = `<span class="spinner" aria-hidden="true"></span>${j.kind === "recheck" ? "Re-checking" : "Checking"} ${esc(j.chapter_id || "")}${active.length > 1 ? ` and ${active.length - 1} more` : ""}`;
    box.title = active.map(x => `${x.chapter_id}: ${x.stage || x.status}`).join("\n");
    activityTimer = setTimeout(pollActivity, 3000);
  }
}
function followJob(jobId) { if (jobId) { state.watching.add(jobId); setTimeout(pollActivity, 600); } }

/** Poll one job until it finishes. onUpdate(job) is called on every poll. */
async function watchJob(jobId, onUpdate) {
  let delay = 900;
  for (;;) {
    let job;
    try { job = await bookApi(`/jobs/${jobId}`); }
    catch (err) { if (err.status === 0) { await sleep(3000); continue; } throw err; }
    onUpdate?.(job);
    if (job.status === "done") return job;
    if (job.status === "failed") throw new Error(job.error || "The job failed.");
    await sleep(delay);
    delay = Math.min(delay * 1.25, 3000);
  }
}

function progressBox(title, job) {
  const pct = Math.round((job?.progress || 0) * 100);
  return `<div class="progress" role="status"><strong>${esc(title)}</strong>
    <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><span style="width:${Math.max(pct, 3)}%"></span></div>
    <div class="stage">${esc(job ? (job.status === "queued" ? "Waiting for the book to be free" : job.stage || "") : "Starting")}</div></div>`;
}

// ---------------------------------------------------------------------------
// issue cards (shared by several pages)
// ---------------------------------------------------------------------------
function highlight(quote, value) {
  const q = esc(quote), v = esc(value);
  const i = v ? q.toLowerCase().indexOf(v.toLowerCase()) : -1;
  return i < 0 ? q : q.slice(0, i) + "<mark>" + q.slice(i, i + v.length) + "</mark>" + q.slice(i + v.length);
}

function issueCard(c, { actions = true, showSeverity = true } = {}) {
  const arrow = `<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 10 C12 4, 20 4, 26 10 M26 10 l-5 -1 M26 10 l-1 -5 M26 22 C20 28, 12 28, 6 22 M6 22 l5 1 M6 22 l1 5" fill="none" stroke="#A8322D" stroke-width="2" stroke-linecap="round"/></svg>`;
  const source = c.source && c.source !== "checker" ? `<span class="tag plain">${c.source === "story clock" ? "Found by the story clock" : "Found by the safety net"}</span>` : "";
  const note = c.status === "dismissed"
    ? (c.dismiss_reason ? `You dismissed this: ${esc(c.dismiss_reason)}` : c.review_note ? esc(c.review_note) : "Dismissed.")
    : c.status === "resolved" ? esc(c.review_note || "Resolved.") : "";
  const canonBtn = c.conflicting_fact_id && !c.conflicting_pinned && c.status === "open"
    ? `<button class="btn quiet small" data-pin="${c.conflicting_fact_id}" title="The earlier version is how it should be">Keep the earlier version as canon</button>` : "";
  return `
  <article class="issue sev-${esc(c.severity || "medium")} is-${esc(c.status)}" data-issue="${c.id ?? ""}">
    <div class="issue-head"><strong>${esc(c.entity)}</strong><span class="kind">${KIND[c.contradiction_type] || esc(c.contradiction_type)}</span>
      ${showSeverity ? sevTag(c.severity || "medium") : ""}${c.conflicting_pinned ? `<span class="tag canon">Breaks a canon fact</span>` : ""}${source}</div>
    <p class="why">${esc(c.explanation)}</p>
    ${note ? `<p class="note">${note}</p>` : ""}
    <div class="facing">
      <div class="slip"><span class="where">${chapterLink(c.conflicting_chapter_id, c.conflicting_chapter_number)}<span>earlier</span></span>${highlight(c.conflicting_quote, c.conflicting_value)}</div>
      <div class="slip-arrow">${arrow}</div>
      <div class="slip"><span class="where">${chapterLink(c.new_chapter_id, c.new_chapter_number)}<span>later</span></span>${highlight(c.new_quote, c.new_value)}</div>
    </div>
    ${actions && c.id != null ? `<div class="actions">
      ${c.status === "open" ? `<button class="btn quiet small" data-dismiss="${c.id}">It's intentional</button>${canonBtn}`
                            : c.status === "dismissed" ? `<button class="btn quiet small" data-reopen="${c.id}">Reopen</button>` : ""}
    </div><div class="dismiss-slot"></div>` : ""}
  </article>`;
}

/** Wire up dismiss / reopen / canon buttons inside a container. after() re-renders. */
function bindIssueActions(root, after) {
  root.onclick = async (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    const card = t.closest(".issue");
    try {
      if (t.dataset.dismiss) {
        const slot = $(".dismiss-slot", card);
        slot.innerHTML = `<form class="dismiss-form"><label class="sr-only" for="why-${t.dataset.dismiss}">Why it's fine</label>
          <input type="text" id="why-${t.dataset.dismiss}" placeholder="Why it's fine (optional, e.g. she dyed her hair)">
          <button class="btn small" type="submit">Dismiss</button><button class="btn quiet small" type="button" data-cancel>Cancel</button></form>`;
        const form = $("form", slot);
        $("input", form).focus();
        $("[data-cancel]", form).onclick = () => { slot.innerHTML = ""; };
        form.onsubmit = async (ev) => {
          ev.preventDefault();
          try {
            await bookApi(`/contradictions/${t.dataset.dismiss}`, { method: "PATCH", body: { status: "dismissed", reason: $("input", form).value.trim() || null } });
            await refreshSidebar(); after();
          } catch (err) { slot.insertAdjacentHTML("beforeend", errorBox(err)); }
        };
      } else if (t.dataset.reopen) {
        await bookApi(`/contradictions/${t.dataset.reopen}`, { method: "PATCH", body: { status: "open" } });
        await refreshSidebar(); after();
      } else if (t.dataset.pin) {
        await bookApi(`/facts/${t.dataset.pin}`, { method: "PATCH", body: { pinned: true } });
        after();
      }
    } catch (err) { card.insertAdjacentHTML("beforeend", errorBox(err)); }
  };
}

// ---------------------------------------------------------------------------
// pages
// ---------------------------------------------------------------------------
async function pageOverview() {
  const b = currentBook();
  setTitle(b.name);
  view.innerHTML = `<h1>${esc(b.name)}</h1><div id="ov">${loading("Loading…")}</div>`;
  const box = $("#ov");
  try {
    const o = await bookApi("/overview");
    if (!o.chapters) {
      box.innerHTML = `<div class="empty"><p>This book has no chapters yet. Add the first one and StoryForge starts building its memory of the story.</p>
        <a class="btn" href="#/add">Add chapters</a></div>`;
      return;
    }
    const high = o.open_by_severity.high || 0;
    const people = o.entities.character || 0, places = o.entities.location || 0;
    box.innerHTML = `
      <p class="summary">${plural(o.chapters, "chapter")}, about ${plural(o.words, "word")}. StoryForge has noted <b>${plural(o.facts, "fact")}</b>
        about ${plural(people, "character")} and ${plural(places, "place")}.
        ${o.open_issues ? `There ${o.open_issues === 1 ? "is" : "are"} <b>${plural(o.open_issues, "open issue")}</b>${high ? (high === o.open_issues ? (high === 1 ? ", and it's serious" : ", all of them serious") : `, ${high} of them serious`) : ""}.` : "Every chapter agrees with the others."}</p>
      ${o.open_issues ? `<div class="actions" style="margin:-.8rem 0 1.8rem"><a class="btn" href="#/issues">Review issues</a></div>` : ""}
      <h2 class="section">Chapters</h2>
      <div class="ribbon" id="ribbon"></div>
      <div class="legend"><span><i style="background:var(--pencil-wash)"></i>Length</span><span><i style="background:var(--red)"></i>Open issues</span></div>
      <div class="two-col">
        <section><h2 class="section">Most flagged</h2>
          ${o.most_flagged.length ? `<ul class="plain-list">${o.most_flagged.map(([name, n]) =>
            `<li><span style="font-family:var(--serif)">${esc(name)}</span><span>${plural(n, "issue")}</span></li>`).join("")}</ul>`
            : `<p class="hint">Nothing is flagged right now.</p>`}
        </section>
        <section><h2 class="section">Recent work</h2>
          ${o.jobs.length ? `<ul class="plain-list">${o.jobs.map(j =>
            `<li><span>${j.kind === "recheck" ? "Re-checked" : "Checked"} ${esc(j.chapter_id || "")}</span>
             <span class="${j.status === "failed" ? "tag high" : "hint"}">${j.status === "done" ? ago(j.updated_at) : j.status === "failed" ? "failed" : "in progress"}</span></li>`).join("")}</ul>`
            : `<p class="hint">Chapters you add or re-check appear here.</p>`}
          ${o.dismissed || o.resolved ? `<p class="hint" style="margin-top:1rem">${plural(o.dismissed, "dismissed issue")} and ${o.resolved} resolved are kept under <a href="#/issues">Issues</a>.</p>` : ""}
        </section>
      </div>`;
    const maxWords = Math.max(...state.chapters.map(c => c.word_count || 1), 1);
    $("#ribbon").innerHTML = state.chapters.map(c => {
      const h = 18 + 70 * (c.word_count || 0) / maxWords;
      const err = Math.min(h, (c.open_issue_count || 0) * 8);
      return `<a href="#/chapter/${encodeURIComponent(c.chapter_id)}" title="${esc(c.chapter_id)}: ${plural(c.word_count || 0, "word")}, ${plural(Number(c.open_issue_count || 0), "open issue")}">
        <span class="col" style="height:${h}px">${err ? `<span class="err" style="height:${err}px"></span>` : ""}</span><span class="lbl">${c.chapter_number}</span></a>`;
    }).join("");
  } catch (err) { box.innerHTML = errorBox(err); }
}

function pageAdd() {
  setTitle("Add chapters");
  const b = currentBook();
  const edit = state.pendingEdit; state.pendingEdit = null;
  const nextNumber = (state.chapters.at(-1)?.chapter_number || 0) + 1;
  view.innerHTML = `
    <h1>${edit ? `Edit ${esc(edit.chapter_id)}` : "Add chapters"}</h1>
    <p class="lede">${edit ? "Change the text and check it again. Later chapters are re-checked automatically afterwards."
      : `Paste a chapter or upload a stack of text files. Each one is read, matched to the people and places already in <i>${esc(b.name)}</i>, and checked against everything before it. Expect a minute or two per chapter.`}</p>
    ${edit ? "" : `<div class="toolbar"><div class="segmented" role="group" aria-label="How to add">
      <button type="button" data-mode="paste" aria-pressed="true">Paste text</button><button type="button" data-mode="upload" aria-pressed="false">Upload files</button></div></div>`}
    <div id="mode-paste">
      <div class="row">
        <div class="field"><label for="cid">Chapter name <span class="hint">(re-using a name replaces that chapter)</span></label>
          <input type="text" id="cid" autocomplete="off" value="${esc(edit?.chapter_id || `ch${nextNumber}`)}"></div>
        <div class="field"><label for="cnum">Number</label><input type="number" id="cnum" min="1" value="${edit?.chapter_number || nextNumber}"></div>
      </div>
      <div class="field"><label for="ctext">Chapter text</label><textarea id="ctext">${esc(edit?.text || "")}</textarea></div>
      <div class="actions"><button class="btn" id="submit">${edit ? "Save and re-check" : "Check chapter"}</button></div>
    </div>
    <div id="mode-upload" hidden>
      <div class="dropzone" id="drop" tabindex="0" role="button" aria-label="Choose chapter files">
        Drop .txt or .md files here, or choose them. One file per chapter; they're added in filename order.
        <input type="file" id="files" accept=".txt,.md,text/plain" multiple hidden></div>
      <div id="file-list"></div>
    </div>
    <div id="result"></div>`;

  view.querySelectorAll("[data-mode]").forEach(btn => btn.onclick = () => {
    view.querySelectorAll("[data-mode]").forEach(x => x.setAttribute("aria-pressed", String(x === btn)));
    $("#mode-paste").hidden = btn.dataset.mode !== "paste";
    $("#mode-upload").hidden = btn.dataset.mode !== "upload";
  });

  $("#submit").onclick = async () => {
    const result = $("#result");
    const body = { chapter_id: $("#cid").value.trim(), text: $("#ctext").value };
    const num = $("#cnum").value;
    if (num) body.chapter_number = Number(num);
    if (!body.chapter_id || !body.text.trim()) { result.innerHTML = errorBox("Give the chapter a name and paste its text."); return; }
    if (/[\/\\?#]/.test(body.chapter_id)) { result.innerHTML = errorBox("Chapter names can't contain / \\ ? or #."); return; }
    $("#submit").disabled = true;
    try {
      const { job_id } = await bookApi("/chapters/jobs", { method: "POST", body });
      result.innerHTML = progressBox(`Checking ${body.chapter_id}`);
      const job = await watchJob(job_id, j => { result.innerHTML = progressBox(`Checking ${body.chapter_id}`, j); });
      showIngestResult(result, job.result);
      followJob(job.result.recheck_job_id);
      refreshSidebar();
    } catch (err) { result.innerHTML = errorBox(err); }
    finally { $("#submit").disabled = false; }
  };

  if (!edit) setupUpload(nextNumber);
}

function showIngestResult(box, r) {
  const open = r.contradictions.filter(c => c.status === "open");
  const setAside = r.contradictions.length - open.length;
  const linked = r.entity_links.filter(l => l.method === "AI match" || l.method === "name match");
  box.innerHTML = `
    <div class="notice ok">Saved as chapter ${r.chapter_number}. ${plural(r.facts.length, "fact")} noted,
      ${open.length ? `<strong>${plural(open.length, "possible mistake")}</strong>.` : "no mistakes found."}
      ${setAside ? `The double-check set aside ${setAside} more that looked like normal story changes (see Issues, Dismissed).` : ""}
      ${r.rechecking_chapters?.length ? `Re-checking ${plural(r.rechecking_chapters.length, "later chapter")} in the background.` : ""}</div>
    ${r.time_note ? `<p class="hint">When it's set: ${esc(r.time_note)}</p>` : ""}
    ${open.length ? `<h2 class="section">Possible mistakes</h2>${open.map(c => issueCard({ ...c, entity: c.entity }, { actions: false })).join("")}
      <p class="hint">Dismiss or keep these on the <a href="#/issues">Issues</a> page.</p>` : ""}
    ${linked.length ? `<h2 class="section">Names matched to earlier chapters</h2><ul>${linked.map(l =>
      `<li>“${esc(l.name)}” is ${esc(l.canonical_name)} <span class="hint">(${l.method === "AI match" ? `AI, ${Math.round(l.confidence * 100)}% sure` : "same name"})</span></li>`).join("")}</ul>` : ""}
    <div class="actions"><a class="btn quiet" href="#/chapter/${encodeURIComponent(r.chapter_id)}">See every fact from this chapter</a></div>`;
}

function setupUpload(nextNumber) {
  const drop = $("#drop"), input = $("#files"), list = $("#file-list");
  let files = [];
  const pick = () => input.click();
  drop.onclick = pick;
  drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); accept([...e.dataTransfer.files]); };
  input.onchange = () => accept([...input.files]);

  async function accept(chosen) {
    chosen = chosen.filter(f => /\.(txt|md)$/i.test(f.name) || f.type === "text/plain").sort((a, b) => naturalSort(a.name, b.name));
    if (!chosen.length) { list.innerHTML = errorBox("Choose plain-text files (.txt or .md)."); return; }
    files = await Promise.all(chosen.map(async (f, i) => ({ name: sanitizeId(f.name) || `ch${nextNumber + i}`, number: nextNumber + i, text: await f.text(), state: "waiting" })));
    render();
  }
  function render(running = false) {
    list.innerHTML = `
      <div class="table-wrap" style="margin-top:1rem"><table><thead><tr><th>Number</th><th>Chapter name</th><th>Words</th><th>Status</th></tr></thead><tbody>
      ${files.map((f, i) => `<tr><td><input type="number" min="1" value="${f.number}" data-num="${i}" ${running ? "disabled" : ""} aria-label="Number for ${esc(f.name)}" style="width:5rem"></td>
        <td><input type="text" value="${esc(f.name)}" data-name="${i}" ${running ? "disabled" : ""} aria-label="Name for chapter ${f.number}"></td>
        <td>${f.text.split(/\s+/).filter(Boolean).length.toLocaleString()}</td>
        <td class="queue"><span class="state ${f.state.startsWith("done") ? "done" : f.state.startsWith("failed") ? "failed" : ""}">${esc(f.state)}</span></td></tr>`).join("")}
      </tbody></table></div>
      ${files.every(f => f.state.startsWith("done")) ? "" : `<div class="actions"><button class="btn" id="run-all" ${running ? "disabled" : ""}>Check ${plural(files.filter(f => !f.state.startsWith("done")).length, "chapter")}</button>
        <span class="hint">Chapters are checked one after another, in number order.</span></div>`}
      <div id="upload-progress"></div>`;
    list.querySelectorAll("[data-num]").forEach(el => el.onchange = () => { files[el.dataset.num].number = Number(el.value); });
    list.querySelectorAll("[data-name]").forEach(el => el.onchange = () => { files[el.dataset.name].name = sanitizeId(el.value); });
    const run = $("#run-all");
    if (run) run.onclick = runAll;
  }
  async function runAll() {
    files.sort((a, b) => a.number - b.number);
    render(true);
    const prog = () => $("#upload-progress");
    let found = 0;
    for (const f of files) {
      if (f.state.startsWith("done")) continue;
      f.state = "checking"; render(true);
      try {
        const { job_id } = await bookApi("/chapters/jobs", { method: "POST", body: { chapter_id: f.name, text: f.text, chapter_number: f.number } });
        const job = await watchJob(job_id, j => { prog().innerHTML = progressBox(`Checking ${f.name}`, j); });
        const open = job.result.contradictions.filter(c => c.status === "open").length;
        found += open;
        f.state = open ? `done, ${plural(open, "issue")}` : "done";
        followJob(job.result.recheck_job_id);
      } catch (err) {
        f.state = `failed: ${err.message}`;
        if (err.status === 429) { render(); prog().innerHTML = errorBox(err); refreshSidebar(); return; }
      }
      render(true);
      refreshSidebar();
    }
    render();
    prog().innerHTML = `<div class="notice ok">All chapters checked. ${found ? `${plural(found, "possible mistake")} found. <a href="#/issues">Review issues</a>` : "No mistakes found."}</div>`;
  }
}

async function pageIssues() {
  setTitle("Issues");
  const prefs = JSON.parse(load("storyforge-issue-view") || "{}");
  const status = prefs.status ?? "open", group = prefs.group || "severity";
  const seg = (name, value, options) => `<div class="segmented" role="group" aria-label="${name}">${options.map(([v, label]) =>
    `<button type="button" data-${name}="${v}" aria-pressed="${v === value}">${label}</button>`).join("")}</div>`;
  view.innerHTML = `
    <h1>Issues</h1>
    <p class="lede">Each card shows two passages that can't both be true. If you meant it, mark it intentional and it stays quiet, even after re-checks. Otherwise fix the chapter and check it again.</p>
    <div class="toolbar">
      <div class="group"><span>Show</span>${seg("status", status, [["open", "Open"], ["dismissed", "Dismissed"], ["resolved", "Resolved"], ["", "All"]])}</div>
      <div class="group"><span>Group by</span>${seg("group", group, [["severity", "Severity"], ["entity", "Character"], ["chapter", "Chapter"]])}</div>
    </div>
    <div id="issues">${loading("Loading issues…")}</div>`;
  const remember = (change) => { save("storyforge-issue-view", JSON.stringify({ status, group, ...change })); pageIssues(); };
  view.querySelectorAll("[data-status]").forEach(b => b.onclick = () => remember({ status: b.dataset.status }));
  view.querySelectorAll("[data-group]").forEach(b => b.onclick = () => remember({ group: b.dataset.group }));
  const box = $("#issues");
  try {
    const { contradictions } = await bookApi("/contradictions" + (status ? `?status=${status}` : ""));
    if (!contradictions.length) {
      box.innerHTML = `<div class="empty">${status === "open" ? "No open issues. Every chapter agrees with the ones before it." : "Nothing here."}</div>`;
      return;
    }
    const order = { high: 0, medium: 1, low: 2 };
    const groups = new Map();
    const keyOf = c => group === "severity" ? c.severity : group === "entity" ? c.entity : `Chapter ${c.new_chapter_number}: ${c.new_chapter_id}`;
    [...contradictions].sort((a, b) => group === "chapter" ? a.new_chapter_number - b.new_chapter_number
      : group === "severity" ? order[a.severity] - order[b.severity] : a.entity.localeCompare(b.entity))
      .forEach(c => { const k = keyOf(c); groups.set(k, [...(groups.get(k) || []), c]); });
    const title = k => group === "severity" ? { high: "Serious", medium: "Worth a look", low: "Unsure" }[k] || k : esc(k);
    box.innerHTML = [...groups].map(([k, items]) => `
      <section class="issue-group"><h2 class="section">${title(k)} <span class="count-pill quiet">${items.length}</span></h2>
        ${items.map(c => issueCard(c, { showSeverity: group !== "severity" })).join("")}</section>`).join("");
    bindIssueActions(box, pageIssues);
  } catch (err) { box.innerHTML = errorBox(err); }
}

async function pageBible() {
  setTitle("Story bible");
  view.innerHTML = `<h1>Story bible</h1>
    <p class="lede">Everyone and everything your story has mentioned so far, under every name they go by. Open an entry for the full record, chapter by chapter.</p>
    <div class="field" style="max-width:22rem"><label for="ent-filter" class="sr-only">Filter by name</label>
      <input type="text" id="ent-filter" placeholder="Filter by name"></div>
    <div id="entities">${loading("Loading…")}</div>`;
  const box = $("#entities");
  try {
    const { entities } = await bookApi("/entities");
    const render = (term) => {
      const t = term.toLowerCase();
      if (!entities.length) { box.innerHTML = `<div class="empty">Add a chapter and its people, places and things appear here.</div>`; return; }
      const shown = entities.filter(e => !t || e.aliases.concat(e.canonical_name).some(n => n.toLowerCase().includes(t)));
      if (!shown.length) { box.innerHTML = `<div class="empty">No names match “${esc(term)}”.</div>`; return; }
      box.innerHTML = Object.keys(TYPE_TITLE).filter(type => shown.some(e => e.entity_type === type)).map(type => {
        const items = shown.filter(e => e.entity_type === type).sort((a, b) => naturalSort(a.canonical_name.replace(/^(the|a|an)\s+/i, ""), b.canonical_name.replace(/^(the|a|an)\s+/i, "")));
        const letters = new Map();
        items.forEach(e => { const L = (e.canonical_name.replace(/^(the|a|an)\s+/i, "")[0] || "#").toUpperCase(); letters.set(L, [...(letters.get(L) || []), e]); });
        return `<section class="index-type"><h2 class="section">${TYPE_TITLE[type]} <span class="count-pill quiet">${items.length}</span></h2>
          ${[...letters].map(([L, es]) => `<div class="index-letter" aria-hidden="true">${esc(L)}</div><ul class="index-entries">${es.map(e => {
            const others = e.aliases.filter(a => a.toLowerCase() !== e.canonical_name.toLowerCase());
            return `<li><a href="#/entity/${e.id}">${esc(e.canonical_name)}</a>${others.length ? ` <span class="aka">also ${others.map(esc).join(", ")}</span>` : ""} <span class="hint">(${e.fact_count})</span></li>`;
          }).join("")}</ul>`).join("")}</section>`;
      }).join("");
    };
    render("");
    $("#ent-filter").oninput = (e) => render(e.target.value);
  } catch (err) { box.innerHTML = errorBox(err); }
}

async function pageEntity(id) {
  view.innerHTML = loading("Loading…");
  try {
    const [entity, { entities }] = await Promise.all([bookApi(`/entities/${id}`), bookApi("/entities")]);
    setTitle(entity.canonical_name);
    const byAttr = new Map();
    entity.facts.forEach(f => byAttr.set(f.attribute, [...(byAttr.get(f.attribute) || []), f]));
    const compatible = entities.filter(e => e.id !== entity.id && (e.entity_type === entity.entity_type || [e.entity_type, entity.entity_type].includes("other")));
    const typeName = (TYPE_TITLE[entity.entity_type] || entity.entity_type).replace(/s$/, "").toLowerCase();
    view.innerHTML = `
      <a class="back" href="#/bible">Story bible</a> <a class="back" href="#/map" style="margin-left:1rem">Character map</a>
      <h1>${esc(entity.canonical_name)}</h1>
      <p class="lede">A ${esc(typeName)} with ${plural(entity.fact_count, "fact")} across the story. Pin a fact as canon when it's how things really are: later chapters that disagree are flagged as serious.</p>
      <label>Known as</label>
      <div class="names">${entity.aliases.map(a => `<span class="name-chip">${esc(a)}${entity.aliases.length > 1
        ? `<button title="This name is someone else: split it off" aria-label="Split off ${esc(a)}" data-detach="${esc(a)}">×</button>` : ""}</span>`).join("")}</div>
      ${compatible.length ? `<div class="inline-form"><div><label for="merge-with">Same as another entry? <span class="hint">Merge it into ${esc(entity.canonical_name)}</span></label>
        <select id="merge-with"><option value="">Choose an entry</option>${compatible.map(o => `<option value="${o.id}">${esc(o.canonical_name)}</option>`).join("")}</select></div>
        <button class="btn" id="merge">Merge</button></div>` : ""}
      <div id="entity-msg"></div>
      <h2 class="section">What the story says</h2>
      ${entity.facts.length ? `<div class="sheet"><dl>${[...byAttr].map(([attr, facts]) => `
        <div class="attr"><dt>${esc(pretty(attr))}</dt><dd>${facts.map(f => `
          <div class="val"><span class="v">${esc(f.value)}</span>
            <small>${chapterLink(f.chapter_id, f.chapter_number)}${f.entity.toLowerCase() !== entity.canonical_name.toLowerCase() ? `, as “${esc(f.entity)}”` : ""}</small>
            ${f.pinned ? `<span class="tag canon">Canon</span>` : ""}
            <button class="btn quiet small" data-pin="${f.fact_id}" data-on="${f.pinned ? "0" : "1"}">${f.pinned ? "Unpin" : "Pin as canon"}</button></div>`).join("")}</dd></div>`).join("")}
      </dl></div>` : `<div class="empty">No facts are left for this entry.</div>`}`;
    const msg = $("#entity-msg");
    view.querySelectorAll("[data-detach]").forEach(b => b.onclick = async () => {
      const name = b.dataset.detach;
      if (!confirm(`Split “${name}” off into its own entry? Facts written under that name go with it, and the affected chapters are re-checked.`)) return;
      try { const r = await bookApi(`/entities/${entity.id}/detach`, { method: "POST", body: { name } }); followJob(r.recheck_job_id); pageEntity(r.kept.id); }
      catch (err) { msg.innerHTML = errorBox(err); }
    });
    const merge = $("#merge");
    if (merge) merge.onclick = async () => {
      const other = $("#merge-with").value;
      if (!other) { msg.innerHTML = errorBox("Choose the entry to merge in."); return; }
      try {
        const r = await bookApi("/entities/merge", { method: "POST", body: { keep_entity_id: entity.id, merge_entity_id: Number(other) } });
        followJob(r.recheck_job_id);
        await pageEntity(entity.id);
        $("#entity-msg").innerHTML = `<div class="notice ok">Merged. The chapters that mention them are being re-checked with the combined facts.</div>`;
      } catch (err) { msg.innerHTML = errorBox(err); }
    };
    view.querySelectorAll("[data-pin]").forEach(b => b.onclick = async () => {
      try { await bookApi(`/facts/${b.dataset.pin}`, { method: "PATCH", body: { pinned: b.dataset.on === "1" } }); pageEntity(entity.id); }
      catch (err) { msg.innerHTML = errorBox(err); }
    });
  } catch (err) { view.innerHTML = errorBox(err); }
}

async function pageTimeline() {
  setTitle("Timeline");
  const order = load("storyforge-timeline") || "reading";
  view.innerHTML = `<h1>Timeline</h1>
    <p class="lede">${order === "story" ? "Events in story time: flashbacks come first, or wherever you've placed a chapter on its page."
      : "Events in the order the reader meets them."}</p>
    <div class="toolbar"><div class="segmented" role="group" aria-label="Order">
      <button type="button" data-order="reading" aria-pressed="${order === "reading"}">Reading order</button>
      <button type="button" data-order="story" aria-pressed="${order === "story"}">Story order</button></div></div>
    <div id="tl">${loading("Loading…")}</div>`;
  view.querySelectorAll("[data-order]").forEach(b => b.onclick = () => { save("storyforge-timeline", b.dataset.order); pageTimeline(); });
  const box = $("#tl");
  try {
    const { events } = await bookApi(`/timeline?order=${order}`);
    if (!events.length) { box.innerHTML = `<div class="empty">No events yet. They appear here as you add chapters.</div>`; return; }
    const groups = [];
    events.forEach(e => {
      const last = groups.at(-1);
      if (last && last.id === e.chapter_id) last.items.push(e);
      else groups.push({ id: e.chapter_id, num: e.chapter_number, note: e.time_note, items: [e] });
    });
    box.innerHTML = `<ol class="timeline">${groups.map(g => `
      <li class="${(g.note || "").startsWith("flashback") ? "flashback" : ""}"><span class="ch" aria-hidden="true">${g.num}</span>
        <h3><a href="#/chapter/${encodeURIComponent(g.id)}">${esc(g.id)}</a></h3>${g.note ? `<p class="when">${esc(g.note)}</p>` : ""}
        ${g.items.map(e => `<div class="event"><span class="what">${esc(e.canonical_name || e.entity)}</span>: ${esc(pretty(e.attribute))}, ${esc(e.value)}
          <q>${esc(e.source_quote)}</q></div>`).join("")}</li>`).join("")}</ol>`;
  } catch (err) { box.innerHTML = errorBox(err); }
}

function pageAsk() {
  setTitle("Ask");
  view.innerHTML = `<h1>Ask about your story</h1>
    <p class="lede">Ask the way you'd ask a co-writer: “What colour are Ines's eyes?” or “Who has been injured so far?”. Answers come only from your chapters, with the chapter for each.</p>
    <form class="ask-row" id="ask-form"><label class="sr-only" for="q">Your question</label><input type="text" id="q" placeholder="Who knew about the brass key?"><button class="btn" type="submit">Ask</button></form>
    <div id="answer"></div>`;
  $("#q").focus();
  $("#ask-form").onsubmit = async (e) => {
    e.preventDefault();
    const question = $("#q").value.trim();
    const box = $("#answer");
    if (!question) return;
    box.innerHTML = loading("Looking through the story…");
    try {
      const r = await bookApi("/ask", { method: "POST", body: { question } });
      box.innerHTML = `<div class="answer">${esc(r.answer)}</div>
        ${r.sources.length ? `<h2 class="section">Facts used</h2><ul class="sources">${r.sources.map(s =>
          `<li>${chapterLink(s.chapter_id, s.chapter_number)}: ${esc(s.canonical_name || s.entity)}, ${esc(pretty(s.attribute))}: ${esc(s.value)}</li>`).join("")}</ul>` : ""}`;
    } catch (err) { box.innerHTML = errorBox(err); }
  };
}

async function pageChapters() {
  setTitle("Chapters");
  const b = currentBook();
  view.innerHTML = `<div class="shelf-head"><h1>Chapters</h1><a class="btn" href="#/add">Add chapters</a></div>
    <p class="lede">Every chapter of <i>${esc(b.name)}</i> in reading order, with when it's set and what needs attention.</p>
    <div id="ch-table"></div>`;
  const box = $("#ch-table");
  if (!state.chapters.length) {
    box.innerHTML = `<div class="empty"><p>No chapters yet. Paste one, or upload a stack of text files at once.</p><a class="btn" href="#/add">Add chapters</a></div>`;
    return;
  }
  box.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>No.</th><th>Chapter</th><th>When it's set</th><th>Words</th><th>Facts</th><th>Open issues</th></tr></thead>
    <tbody>${state.chapters.map(c => `<tr>
      <td style="font:600 1rem var(--serif);color:var(--pencil)">${c.chapter_number}</td>
      <td><a href="#/chapter/${encodeURIComponent(c.chapter_id)}" style="font-family:var(--serif)">${esc(c.chapter_id)}</a></td>
      <td class="hint">${esc(c.time_note || "")}</td>
      <td>${Number(c.word_count || 0).toLocaleString()}</td><td>${c.fact_count}</td>
      <td>${Number(c.open_issue_count) ? `<span class="tag high">${c.open_issue_count}</span>` : `<span class="hint">None</span>`}</td></tr>`).join("")}</tbody></table></div>`;
}

async function pageChapter(chapterId) {
  view.innerHTML = loading("Loading chapter…");
  try {
    const [ch, { contradictions }] = await Promise.all([
      bookApi(`/chapters/${encodeURIComponent(chapterId)}`), bookApi("/contradictions?status=open")]);
    setTitle(ch.chapter_id);
    const mine = contradictions.filter(c => c.new_chapter_id === ch.chapter_id || c.conflicting_chapter_id === ch.chapter_id);
    const words = ch.text.split(/\s+/).filter(Boolean).length;
    const pos = state.chapters.findIndex(c => c.chapter_id === ch.chapter_id);
    const prev = state.chapters[pos - 1], next = state.chapters[pos + 1];
    const step = (c, label) => c ? `<a href="#/chapter/${encodeURIComponent(c.chapter_id)}">${label} ${c.chapter_number}: ${esc(c.chapter_id)}</a>` : "<span></span>";
    view.innerHTML = `
      <nav class="actions" style="justify-content:space-between;margin:0 0 1rem;font-size:.92rem" aria-label="Other chapters">${step(prev, "Previous: chapter")}${step(next, "Next: chapter")}</nav>
      <h1>Chapter ${ch.chapter_number}: ${esc(ch.chapter_id)}</h1>
      <div class="meta-grid"><span><b>${plural(words, "word")}</b></span><span><b>${plural(ch.facts.length, "fact")}</b> noted</span>
        ${ch.time_note ? `<span>When it's set: <b>${esc(ch.time_note)}</b></span>` : ""}</div>
      <div class="chapter-text">${esc(ch.text)}</div>
      <div class="actions">
        <button class="btn" id="edit">Edit and re-check</button>
        <button class="btn quiet" id="recheck">Re-check without changes</button>
        <button class="btn danger" id="delete-chapter">Delete chapter</button>
      </div>
      <div id="ch-msg"></div>
      <details style="margin-top:1rem"><summary>Place this chapter in story time</summary>
        <p class="hint">For the story-order timeline. Chapters are sorted by this number; leave it empty to let StoryForge decide (flashbacks go first).</p>
        <div class="inline-form"><div><label for="story-order">Story position</label><input type="number" step="0.5" id="story-order" value="${ch.story_order ?? ""}" style="width:8rem"></div>
          <button class="btn" id="save-order">Save position</button></div></details>
      ${mine.length ? `<h2 class="section">Open issues involving this chapter</h2><div id="ch-issues">${mine.map(c => issueCard(c)).join("")}</div>` : ""}
      <h2 class="section">Facts from this chapter</h2>
      <p class="hint">Fix anything the AI got wrong. Warnings based on a corrected fact are closed and the chapter is re-checked.</p>
      ${ch.facts.length ? `<div class="table-wrap"><table>
        <thead><tr><th>Who or what</th><th>Detail</th><th>Value</th><th>From the text</th><th><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${ch.facts.map(f => `<tr data-fact="${f.fact_id}" class="${f.pinned ? "pinned" : ""}">
          <td>${f.entity_id ? `<a href="#/entity/${f.entity_id}">${esc(f.canonical_name || f.entity)}</a>` : esc(f.entity)}${f.canonical_name && f.canonical_name !== f.entity ? `<br><small class="hint">as “${esc(f.entity)}”</small>` : ""}
            ${f.pinned ? `<br><span class="tag canon">Canon</span>` : ""}</td>
          <td class="f-attr">${esc(pretty(f.attribute))}</td><td class="f-val">${esc(f.value)}</td>
          <td class="quote">${esc(f.source_quote)}</td>
          <td class="tools"><button class="btn quiet small" data-pin="${f.fact_id}" data-on="${f.pinned ? 0 : 1}">${f.pinned ? "Unpin" : "Pin"}</button><button class="btn quiet small" data-edit="${f.fact_id}">Edit</button><button class="btn danger small" data-del="${f.fact_id}">Delete</button></td>
        </tr>`).join("")}</tbody></table></div>` : `<div class="empty">No facts were found in this chapter.</div>`}`;
    const msg = $("#ch-msg");
    const issuesBox = $("#ch-issues");
    if (issuesBox) bindIssueActions(issuesBox, () => pageChapter(chapterId));
    $("#edit").onclick = () => { state.pendingEdit = ch; location.hash = "#/add"; };
    $("#recheck").onclick = async () => {
      try { const r = await bookApi(`/chapters/${encodeURIComponent(ch.chapter_id)}/recheck`, { method: "POST" });
        followJob(r.job_id); msg.innerHTML = `<div class="notice">Re-checking in the background. Issues update when it's done.</div>`; }
      catch (err) { msg.innerHTML = errorBox(err); }
    };
    $("#delete-chapter").onclick = async () => {
      if (!confirm(`Delete ${ch.chapter_id} and everything taken from it? Later chapters are re-checked without it.`)) return;
      try { const r = await bookApi(`/chapters/${encodeURIComponent(ch.chapter_id)}`, { method: "DELETE" });
        followJob(r.recheck_job_id); await refreshSidebar(); location.hash = "#/overview"; }
      catch (err) { msg.innerHTML = errorBox(err); }
    };
    $("#save-order").onclick = async () => {
      const v = $("#story-order").value;
      try { await bookApi(`/chapters/${encodeURIComponent(ch.chapter_id)}`, { method: "PATCH", body: { story_order: v === "" ? null : Number(v) } });
        msg.innerHTML = `<div class="notice ok">Story position saved.</div>`; }
      catch (err) { msg.innerHTML = errorBox(err); }
    };
    view.querySelector("tbody")?.addEventListener("click", async (e) => {
      const t = e.target.closest("button");
      if (!t) return;
      const row = t.closest("tr");
      try {
        if (t.dataset.pin) {
          await bookApi(`/facts/${t.dataset.pin}`, { method: "PATCH", body: { pinned: t.dataset.on === "1" } });
          pageChapter(chapterId);
        } else if (t.dataset.del) {
          if (!confirm("Delete this fact? Warnings based on it are closed.")) return;
          const r = await bookApi(`/facts/${t.dataset.del}`, { method: "DELETE" });
          followJob(r.recheck_job_id); pageChapter(chapterId); refreshSidebar(chapterId);
        } else if (t.dataset.edit) {
          const attr = $(".f-attr", row), val = $(".f-val", row);
          attr.innerHTML = `<input type="text" value="${esc(attr.textContent.replace(/ /g, "_"))}" aria-label="Detail">`;
          val.innerHTML = `<input type="text" value="${esc(val.textContent)}" aria-label="Value">`;
          t.textContent = "Save"; delete t.dataset.edit; t.dataset.save = row.dataset.fact;
          $("input", val).focus();
        } else if (t.dataset.save) {
          const [attribute, value] = [...row.querySelectorAll("input")].map(i => i.value.trim());
          if (!attribute || !value) { msg.innerHTML = errorBox("A fact needs both a detail and a value."); return; }
          const r = await bookApi(`/facts/${t.dataset.save}`, { method: "PATCH", body: { attribute, value } });
          followJob(r.recheck_job_id); pageChapter(chapterId);
        }
      } catch (err) { msg.innerHTML = errorBox(err); }
    });
  } catch (err) { view.innerHTML = errorBox(err); }
}

const COVERS = ["sage", "slate", "plum", "ochre", "oxblood", "moss", "ink"];
const KINDS = { novel: "Novel", novella: "Novella", "short stories": "Short stories", screenplay: "Screenplay", serial: "Serial", other: "Other" };
const coverOf = b => b.cover_color || COVERS[b.id % COVERS.length];
function initials(name) {
  const words = name.replace(/^(the|a|an)\s+/i, "").split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "?").slice(0, 2)).toUpperCase();
}
function ago(when) {
  if (!when) return "";
  const s = (Date.now() - new Date(when)) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 14) return `${Math.round(s / 86400)} days ago`;
  return new Date(when).toLocaleDateString();
}
function bookForm(b = {}) {
  const color = b.cover_color || COVERS[(state.books.length + 1) % COVERS.length];
  return `
    <div class="row"><div class="field"><label for="bf-name">Title</label><input type="text" id="bf-name" maxlength="120" value="${esc(b.name || "")}"></div>
      <div class="field"><label for="bf-kind">Kind</label><select id="bf-kind">${Object.entries(KINDS).map(([v, l]) => `<option value="${v}" ${v === (b.kind || "novel") ? "selected" : ""}>${l}</option>`).join("")}</select></div></div>
    <div class="field"><label for="bf-syn">What it's about <span class="hint">(optional, shown on the cover card)</span></label>
      <textarea id="bf-syn" style="min-height:5rem">${esc(b.synopsis || "")}</textarea></div>
    <div class="field"><span style="display:block;font-weight:700;font-size:.9rem;margin-bottom:.4rem" id="bf-color-label">Cover colour</span>
      <div class="swatches" role="radiogroup" aria-labelledby="bf-color-label">${COVERS.map(c => `<label><input type="radio" name="bf-color" value="${c}" ${c === color ? "checked" : ""} aria-label="${c}"><span class="cover-${c}"></span></label>`).join("")}</div></div>`;
}
const readBookForm = (root) => ({
  name: $("#bf-name", root).value.trim(), kind: $("#bf-kind", root).value,
  synopsis: $("#bf-syn", root).value.trim() || null, cover_color: $("input[name=bf-color]:checked", root)?.value || null,
});

async function pageShelf() {
  setTitle("Your books");
  await loadBooks();
  view.innerHTML = `
    <div class="home">
      <section>
        <div class="shelf-head"><h1>Your books</h1>
          <div class="actions" style="margin:0"><label for="sort" class="sr-only">Sort books</label>
            <select id="sort" style="width:auto">${[["recent", "Recently edited"], ["az", "Alphabetical"], ["issues", "Most open issues"]].map(([v, l]) =>
              `<option value="${v}" ${v === (load("storyforge-sort") || "recent") ? "selected" : ""}>${l}</option>`).join("")}</select>
            <button class="btn" id="new-book-btn">New book</button></div></div>
        <div id="new-book" hidden class="new-book"><h2 class="section" style="margin-top:0">Start a new book</h2>${bookForm()}
          <div id="nb-msg"></div><div class="actions"><button class="btn" id="nb-create">Create book</button><button class="btn quiet" id="nb-cancel">Cancel</button></div></div>
        <div class="shelf" id="shelf"></div>
      </section>
      <aside class="recent" aria-labelledby="recent-h"><h2 id="recent-h">Recent work</h2><div id="recent">${loading("Loading…")}</div></aside>
    </div>`;
  const shelf = $("#shelf"), form = $("#new-book");
  const sorted = () => {
    const by = load("storyforge-sort") || "recent";
    return [...state.books].sort(by === "az" ? (a, b) => naturalSort(a.name, b.name)
      : by === "issues" ? (a, b) => b.open_issue_count - a.open_issue_count
      : (a, b) => new Date(b.last_edited || b.created_at) - new Date(a.last_edited || a.created_at));
  };
  const render = () => {
    shelf.innerHTML = state.books.length ? sorted().map(b => {
      const open = Number(b.open_issue_count), serious = Number(b.high_issue_count);
      return `<article class="book-card ${b.id === state.book ? "current" : ""}" data-book="${b.id}">
        <div class="cover cover-${coverOf(b)}" aria-hidden="true">${esc(initials(b.name))}</div>
        <div class="book-body">
          <h2>${esc(b.name)}</h2>
          <span class="kind">${KINDS[b.kind] || "Novel"}, ${plural(Number(b.chapter_count), "chapter")}${b.word_count > 1 ? `, ${Number(b.word_count).toLocaleString()} words` : ""}</span>
          ${b.synopsis ? `<p class="synopsis">${esc(b.synopsis)}</p>` : ""}
          <span class="status ${!Number(b.chapter_count) ? "" : open ? "bad" : "ok"}">${!Number(b.chapter_count) ? "No chapters yet" : open ? `${plural(open, "open issue")}${serious ? `, ${serious} serious` : ""}` : "Every chapter agrees"}</span>
          <div class="book-foot"><button class="btn small" data-open="${b.id}">Open</button>
            <button class="btn quiet small" data-edit="${b.id}">Edit details</button>
            <button class="btn quiet small" data-export="${b.id}">Export</button>
            <button class="btn danger small" data-delete="${b.id}">Delete</button></div>
          <div class="edit-slot"></div>
        </div></article>`;
    }).join("") : `<div class="empty">Start your first book. Add its chapters and StoryForge keeps track of every character, place and promise in it.</div>`;
  };
  render();
  $("#sort").onchange = (e) => { save("storyforge-sort", e.target.value); render(); };
  $("#new-book-btn").onclick = () => { form.hidden = false; $("#bf-name", form).focus(); };
  $("#nb-cancel").onclick = () => { form.hidden = true; };
  $("#nb-create").onclick = async () => {
    const body = readBookForm(form);
    if (!body.name) { $("#nb-msg").innerHTML = errorBox("Give the book a title."); return; }
    try {
      const b = await api("/projects", { method: "POST", body });
      chooseBook(b.id); await loadBooks(); location.hash = "#/add";
    } catch (err) { $("#nb-msg").innerHTML = errorBox(err); }
  };
  if (!state.books.length) form.hidden = false;
  shelf.onclick = async (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    const card = t.closest(".book-card");
    const b = state.books.find(x => x.id === Number(card.dataset.book));
    try {
      if (t.dataset.open) { chooseBook(b.id); location.hash = "#/overview"; }
      else if (t.dataset.edit) {
        const slot = $(".edit-slot", card);
        if (slot.innerHTML) { slot.innerHTML = ""; return; }
        slot.innerHTML = `<div style="margin-top:.8rem">${bookForm(b).replace(/id="bf-/g, `id="bf-`)}<div class="msg"></div>
          <div class="actions"><button class="btn small" data-save="1">Save details</button></div></div>`;
        $("[data-save]", slot).onclick = async () => {
          const body = readBookForm(slot);
          if (!body.name) { $(".msg", slot).innerHTML = errorBox("Give the book a title."); return; }
          try { await api(`/projects/${b.id}`, { method: "PATCH", body }); await loadBooks(); render(); }
          catch (err) { $(".msg", slot).innerHTML = errorBox(err); }
        };
      } else if (t.dataset.export) {
        const lore = await api(`/projects/${b.id}/export`);
        const url = URL.createObjectURL(new Blob([JSON.stringify(lore, null, 2)], { type: "application/json" }));
        const a = Object.assign(document.createElement("a"), { href: url, download: `${b.name.replace(/[^\w-]+/g, "_")}.storyforge.json` });
        document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
      } else if (t.dataset.delete) {
        if (!confirm(`Delete “${b.name}” and everything in it (${plural(Number(b.chapter_count), "chapter")}, their facts, characters and issues)? This can't be undone.`)) return;
        await api(`/projects/${b.id}`, { method: "DELETE" });
        if (b.id === state.book) state.book = null;
        await loadBooks(); render(); refreshSidebar();
      }
    } catch (err) { card.insertAdjacentHTML("beforeend", errorBox(err)); }
  };
  try {
    const { activity } = await api("/activity");
    $("#recent").innerHTML = activity.length ? `<ol>${activity.map(a => `<li><span class="dot cover-${a.cover_color || COVERS[a.project_id % COVERS.length]}" aria-hidden="true"></span>
        <span>${a.status === "failed" ? "Couldn't check" : a.kind === "recheck" ? "Re-checked" : "Checked"} ${esc(a.chapter_id || "")} in <i>${esc(a.project_name)}</i>${a.status === "done" && a.kind === "ingest" ? (Number(a.issues_found) ? `<span style="color:var(--red)">, ${plural(Number(a.issues_found), "issue")} found</span>` : ", all consistent") : a.status === "running" || a.status === "queued" ? ", in progress" : ""}
        <time datetime="${a.updated_at}">${ago(a.updated_at)}</time></span></li>`).join("")}</ol>`
      : `<p class="hint" style="margin:0">When you add or re-check chapters, they appear here.</p>`;
  } catch (err) { $("#recent").innerHTML = errorBox(err); }
}

// ---------------------------------------------------------------------------
// routing
// ---------------------------------------------------------------------------
function currentChapterInRoute() {
  const [page, arg] = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  return page === "chapter" ? arg : null;
}

let routeToken = 0;
async function route() {
  const mine = ++routeToken;
  let [page, arg] = (location.hash.replace(/^#\/?/, "") || "shelf").split("/").map(decodeURIComponent);
  if (state.book == null) page = "shelf";
  const navPage = { entity: "bible", chapter: "chapters", add: "chapters", books: "shelf" }[page] ?? page;
  document.querySelectorAll("#nav a, #nav summary").forEach(a => {
    if (a.dataset.page === navPage) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $("#chapters-dd").open = false;
  $("#account").open = false;
  $("#nav [aria-current]")?.scrollIntoView({ inline: "center", block: "nearest" });
  await refreshSidebar(page === "chapter" ? arg : null);
  if (mine !== routeToken) return;
  const pages = { shelf: pageShelf, books: pageShelf, chapters: pageChapters, overview: pageOverview, add: pageAdd, issues: pageIssues, bible: pageBible,
                  timeline: pageTimeline, ask: pageAsk,
                  map: () => { setTitle("Character map"); return Charts.render(view, bookApi, load, save); } };
  if (page === "entity" && arg) await pageEntity(arg);
  else if (page === "chapter" && arg) await pageChapter(arg);
  else await (pages[page] || pageOverview)();
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
document.addEventListener("click", (e) => {
  document.querySelectorAll("#chapters-dd[open], #account[open]").forEach(d => { if (!d.contains(e.target)) d.open = false; });
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll("#chapters-dd[open], #account[open]").forEach(d => { d.open = false; d.querySelector("summary").focus(); });
});
window.addEventListener("storyforge:jobs-finished", () => {
  const page = location.hash.replace(/^#\/?/, "").split("/")[0];
  if (page === "issues" || page === "overview") route();
});
document.addEventListener("visibilitychange", () => { if (!document.hidden && state.watching.size) pollActivity(); });
$("#book-select").onchange = (e) => {
  chooseBook(Number(e.target.value));
  if (location.hash === "#/overview") route(); else location.hash = "#/overview";
  pollActivity();
};

async function startApp() {
  showOnly("app");
  try {
    const me = await api("/auth/me");
    if (me.user) state.user = me.user;
    renderAccount(me);
    await loadBooks();
  } catch (err) {
    if (err.status === 401) return showLanding();
    view.innerHTML = errorBox(err);
    return;
  }
  await route();
  pollActivity();
}

(async function boot() {
  try { state.config = await api("/auth/config"); }
  catch (err) { showOnly("app"); view.innerHTML = errorBox(err); return; }
  // The welcome page comes first: before signing in, or on a first visit when sign-in is off.
  if (state.config.auth_required ? !state.token : !load("storyforge-welcomed") && !location.hash) showLanding();
  else await startApp();
})();
