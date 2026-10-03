/* StoryForge character charts: family tree, relationship web and presence map.
   Plain SVG built by hand: no chart library to load. Layouts are computed ONCE for the
   whole book, so moving the chapter slider only reveals people and ties; nothing jumps. */
"use strict";

const Charts = (() => {
  const SVG = "http://www.w3.org/2000/svg";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const HOSTILE = new Set(["rival", "enemy"]);
  const linkClass = (e) => e.conflicts?.length ? "conflict" : e.category === "family" ? "family" : HOSTILE.has(e.kind) ? "hostile" : "bond";
  const short = (s, n = 18) => s.length > n ? s.slice(0, n - 1) + "…" : s;

  // -------------------------------------------------------------------------
  // Family tree layout
  // -------------------------------------------------------------------------
  function familyLayout(map) {
    const fam = map.edges.filter(e => ["parent", "spouse", "sibling"].includes(e.kind));
    const ids = [...new Set(fam.flatMap(e => [e.from, e.to]))];
    const parents = new Map(), spouses = new Map(), siblings = new Map();
    const add = (m, k, v) => { if (!m.has(k)) m.set(k, new Set()); m.get(k).add(v); };
    fam.forEach(e => {
      if (e.kind === "parent") add(parents, e.to, e.from);
      if (e.kind === "spouse") { add(spouses, e.from, e.to); add(spouses, e.to, e.from); }
      if (e.kind === "sibling") { add(siblings, e.from, e.to); add(siblings, e.to, e.from); }
    });
    // Generations: parent one row above child; spouses and siblings on the same row.
    const gen = new Map(), comp = new Map();
    let compNo = 0;
    for (const start of ids) {
      if (gen.has(start)) continue;
      const queue = [start];
      gen.set(start, 0); comp.set(start, compNo);
      while (queue.length) {
        const id = queue.shift(), g = gen.get(id);
        const step = (other, offset) => { if (!gen.has(other)) { gen.set(other, g + offset); comp.set(other, compNo); queue.push(other); } };
        fam.forEach(e => {
          if (e.kind === "parent" && e.from === id) step(e.to, 1);
          if (e.kind === "parent" && e.to === id) step(e.from, -1);
          if (e.kind !== "parent" && e.from === id) step(e.to, 0);
          if (e.kind !== "parent" && e.to === id) step(e.from, 0);
        });
      }
      compNo++;
    }
    const minGen = new Map();
    ids.forEach(id => minGen.set(comp.get(id), Math.min(minGen.get(comp.get(id)) ?? 0, gen.get(id))));
    ids.forEach(id => gen.set(id, gen.get(id) - minGen.get(comp.get(id))));

    // Order each row: children under their parents, spouses next to each other.
    const W = 150, H = 46, GAPX = 26, GAPY = 74;
    const x = new Map();
    const rows = Math.max(0, ...ids.map(id => gen.get(id))) + 1;
    const name = id => (map.people.find(p => p.id === id) || {}).name || "";
    let offset = 0;
    for (let c = 0; c < compNo; c++) {
      const members = ids.filter(id => comp.get(id) === c);
      let width = 0;
      for (let g = 0; g < rows; g++) {
        const row = members.filter(id => gen.get(id) === g);
        const key = id => {
          const ps = [...(parents.get(id) || [])].filter(p => x.has(p));
          if (ps.length) return ps.reduce((s, p) => s + x.get(p), 0) / ps.length;
          const sp = [...(spouses.get(id) || [])].find(s => x.has(s));
          return sp != null ? x.get(sp) + 1 : 1e9;
        };
        row.sort((a, b) => key(a) - key(b) || name(a).localeCompare(name(b)));
        // Siblings stay together; a married sibling goes at the edge of the group with the
        // spouse (who has no parents in the tree) just outside it.
        const pkey = id => [...(parents.get(id) || [])].filter(p => x.has(p)).sort().join(",");
        const ordered = [];
        const groups = new Map();
        row.forEach(id => { const k = pkey(id) || `solo-${id}`; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(id); });
        const outsideSpouse = id => [...(spouses.get(id) || [])].find(s => row.includes(s) && !pkey(s));
        groups.forEach((members, k) => {
          if (k.startsWith("solo-") && members.every(m => [...(spouses.get(m) || [])].some(s => row.includes(s) && pkey(s)))) return;
          const married = members.filter(m => outsideSpouse(m) != null);
          const single = members.filter(m => outsideSpouse(m) == null);
          const left = married.slice(1), right = married.slice(0, 1);
          left.forEach(m => { const sp = outsideSpouse(m); if (!ordered.includes(sp)) ordered.push(sp); ordered.push(m); });
          single.forEach(m => { if (!ordered.includes(m)) ordered.push(m); });
          right.forEach(m => { ordered.push(m); const sp = outsideSpouse(m); if (!ordered.includes(sp)) ordered.push(sp); });
        });
        row.forEach(id => { if (!ordered.includes(id)) ordered.push(id); });
        // Children of the same parents form a block centred under them (a spouse joins their
        // partner's block); blocks never overlap.
        const parentKey = id => [...(parents.get(id) || [])].filter(p => x.has(p)).sort().join(",");
        const blocks = [];
        ordered.forEach(id => {
          const partner = [...(spouses.get(id) || [])].find(s => blocks.length && blocks.at(-1).ids.includes(s));
          const k = partner != null && !parentKey(id) ? blocks.at(-1).key : parentKey(id);
          if (blocks.length && blocks.at(-1).key === k && (k || partner != null)) blocks.at(-1).ids.push(id);
          else blocks.push({ key: k, ids: [id] });
        });
        let cursor = offset;
        blocks.forEach(block => {
          const blockWidth = block.ids.length * (W + GAPX) - GAPX;
          const ps = block.key ? block.key.split(",").map(Number) : [];
          const centre = ps.length ? ps.reduce((s, p) => s + x.get(p) + W / 2, 0) / ps.length : null;
          let pos = Math.max(cursor, centre != null ? centre - blockWidth / 2 : cursor);
          block.ids.forEach(id => { x.set(id, pos); pos += W + GAPX; });
          cursor = pos;
        });
        width = Math.max(width, cursor - offset);
      }
      offset += width + 50;
    }
    const pos = new Map(ids.map(id => [id, { x: x.get(id) + 20, y: 20 + gen.get(id) * (H + GAPY) }]));
    return { pos, parents, spouses, siblings, W, H, width: offset + 10, height: 20 + rows * (H + GAPY) - GAPY + 30, fam };
  }

  function drawTree(svg, map, layout, asOf, selected) {
    const { pos, parents, W, H } = layout;
    const visible = e => e.first_chapter <= asOf;
    const shown = new Set();
    layout.fam.filter(visible).forEach(e => { shown.add(e.from); shown.add(e.to); });
    let out = "";
    const P = id => pos.get(id);
    const isConflict = e => (e.conflicts || []).some(c => c.first_chapter <= asOf);
    // spouses: double line between partners
    layout.fam.filter(e => e.kind === "spouse" && visible(e)).forEach(e => {
      const [a, b] = [P(e.from), P(e.to)].sort((p, q) => p.x - q.x);
      const y = a.y + H / 2, x1 = a.x + W, x2 = b.x;
      const cls = isConflict(e) ? "conflict" : "family";
      out += `<path class="link ${cls}" d="M${x1} ${y - 3} H${x2} M${x1} ${y + 3} H${x2}"><title>married</title></path>`;
    });
    // parent -> children, grouped by the set of parents
    const groups = new Map();
    layout.fam.filter(e => e.kind === "parent" && visible(e)).forEach(e => {
      const ps = [...parents.get(e.to)].filter(p => layout.fam.some(f => f.kind === "parent" && f.from === p && f.to === e.to && visible(f))).sort();
      const key = ps.join(",");
      if (!groups.has(key)) groups.set(key, { ps, kids: new Set(), conflict: false });
      groups.get(key).kids.add(e.to);
      if (isConflict(e)) groups.get(key).conflict = true;
    });
    groups.forEach(({ ps, kids, conflict }) => {
      const anchorX = ps.reduce((s, p) => s + P(p).x + W / 2, 0) / ps.length;
      const top = Math.max(...ps.map(p => P(p).y)) + H;
      const kidPos = [...kids].map(k => P(k));
      const busY = Math.min(...kidPos.map(k => k.y)) - 26;
      const xs = kidPos.map(k => k.x + W / 2).concat(anchorX);
      let d = `M${anchorX} ${ps.length === 2 && Math.abs(P(ps[0]).y - P(ps[1]).y) < 1 ? P(ps[0]).y + H / 2 + 3 : top} V${busY} M${Math.min(...xs)} ${busY} H${Math.max(...xs)}`;
      kidPos.forEach(k => { d += ` M${k.x + W / 2} ${busY} V${k.y}`; });
      out += `<path class="link ${conflict ? "conflict" : "family"}" d="${d}"/>`;
    });
    // siblings without a parent in the tree: bracket over them
    layout.fam.filter(e => e.kind === "sibling" && visible(e)).forEach(e => {
      const a = P(e.from), b = P(e.to);
      const sharedParent = [...(parents.get(e.from) || [])].some(p => (parents.get(e.to) || new Set()).has(p));
      if (sharedParent && !isConflict(e)) return;
      const [l, r] = [a, b].sort((p, q) => p.x - q.x);
      const y = Math.min(l.y, r.y) - (isConflict(e) ? 44 : 12);
      out += `<path class="link ${isConflict(e) ? "conflict" : "family"}" d="M${l.x + W / 2} ${l.y} V${y} H${r.x + W / 2} V${r.y}"><title>siblings</title></path>`;
      if (isConflict(e)) out += `<text class="edge-label" x="${(l.x + r.x + W) / 2}" y="${y - 6}" text-anchor="middle" fill="var(--red)">${esc(conflictText(e))}</text>`;
    });
    // people
    map.people.filter(p => pos.has(p.id) && shown.has(p.id)).forEach(p => {
      const { x, y } = P(p.id);
      const dead = p.died_chapter && p.died_chapter <= asOf;
      const isNew = p.first_chapter === asOf;
      const sub = dead ? `died in ch ${p.died_chapter}` : `from ch ${p.first_chapter}`;
      out += `<g class="node${dead ? " dead" : ""}${selected === p.id ? " selected" : ""}${isNew ? " new" : ""}" data-id="${p.id}" tabindex="0" role="button" aria-label="${esc(p.name)}, ${sub}">
        <rect x="${x}" y="${y}" width="${W}" height="${H}" rx="6"/>
        <text class="name" x="${x + 12}" y="${y + 20}">${esc(short(p.name))}</text>
        <text class="sub" x="${x + 12}" y="${y + 36}">${sub}</text></g>`;
    });
    svg.setAttribute("viewBox", `0 0 ${Math.max(layout.width, 640)} ${Math.max(layout.height, 160)}`);
    svg.innerHTML = out;
    return shown.size;
  }

  const NOUN = { parent: "parent", spouse: "married", sibling: "sibling", relative: "relative", friend: "friend",
                 ally: "ally", rival: "rival", enemy: "enemy", mentor: "mentor", employer: "employer", romance: "lovers" };
  const conflictText = e => {
    const c = (e.conflicts || [])[0];
    if (!c) return e.label;
    const t = `${NOUN[e.kind] || e.kind} or ${NOUN[c.kind] || c.kind}?`;
    return t[0].toUpperCase() + t.slice(1);
  };

  // -------------------------------------------------------------------------
  // Relationship web: deterministic force layout
  // -------------------------------------------------------------------------
  function webLayout(map) {
    const ids = [...new Set(map.edges.flatMap(e => [e.from, e.to]))].sort((a, b) => a - b);
    const n = ids.length, W = 900, H = Math.max(520, 140 + n * 22);
    const p = new Map(ids.map((id, i) => [id, { x: W / 2 + Math.cos(i * 2.399) * (60 + 9 * i), y: H / 2 + Math.sin(i * 2.399) * (60 + 9 * i), dx: 0, dy: 0 }]));
    const k = Math.sqrt((W * H) / Math.max(n, 1)) * 0.55;
    for (let it = 0; it < 420; it++) {
      const t = 18 * (1 - it / 420) + 0.5;
      p.forEach(a => { a.dx = 0; a.dy = 0; });
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        const a = p.get(ids[i]), b = p.get(ids[j]);
        let dx = a.x - b.x, dy = a.y - b.y; const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = (k * k) / d; dx /= d; dy /= d;
        a.dx += dx * f; a.dy += dy * f; b.dx -= dx * f; b.dy -= dy * f;
      }
      map.edges.forEach(e => {
        const a = p.get(e.from), b = p.get(e.to);
        let dx = a.x - b.x, dy = a.y - b.y; const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = (d * d) / k * (e.category === "family" ? 1.4 : 1); dx /= d; dy /= d;
        a.dx -= dx * f; a.dy -= dy * f; b.dx += dx * f; b.dy += dy * f;
      });
      p.forEach(a => {
        a.dx += (W / 2 - a.x) * 0.02 * k; a.dy += (H / 2 - a.y) * 0.02 * k;
        const d = Math.max(Math.hypot(a.dx, a.dy), 0.01);
        a.x += a.dx / d * Math.min(d, t); a.y += a.dy / d * Math.min(d, t);
      });
    }
    // fit into the box with a margin
    const xs = [...p.values()].map(v => v.x), ys = [...p.values()].map(v => v.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const sx = (W - 160) / Math.max(x1 - x0, 1), sy = (H - 100) / Math.max(y1 - y0, 1), s = Math.min(sx, sy, 1.6);
    p.forEach(v => { v.x = 80 + (v.x - x0) * s + ((W - 160) - (x1 - x0) * s) / 2; v.y = 50 + (v.y - y0) * s + ((H - 100) - (y1 - y0) * s) / 2; });
    return { pos: p, width: W, height: H };
  }

  function drawWeb(svg, map, layout, asOf, selected) {
    const visible = e => e.first_chapter <= asOf;
    const shown = new Set(map.edges.filter(visible).flatMap(e => [e.from, e.to]));
    const people = new Map(map.people.map(p => [p.id, p]));
    const radius = id => 9 + Math.min(14, Math.sqrt(people.get(id)?.fact_count || 1) * 2);
    let out = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="var(--graphite)"/></marker></defs>`;
    map.edges.filter(visible).forEach(e => {
      const a = layout.pos.get(e.from), b = layout.pos.get(e.to);
      const touches = selected == null || e.from === selected || e.to === selected;
      const conflict = (e.conflicts || []).some(c => c.first_chapter <= asOf);
      const cls = conflict ? "conflict" : linkClass({ ...e, conflicts: [] });
      // pull the line back to the circle edges so arrows are visible
      const d = Math.hypot(b.x - a.x, b.y - a.y) || 1, ra = radius(e.from) + 2, rb = radius(e.to) + 4;
      const x1 = a.x + (b.x - a.x) * ra / d, y1 = a.y + (b.y - a.y) * ra / d, x2 = b.x - (b.x - a.x) * rb / d, y2 = b.y - (b.y - a.y) * rb / d;
      const arrow = ["parent", "mentor", "employer"].includes(e.kind) ? ` marker-end="url(#arrow)"` : "";
      out += `<line class="link ${cls}${touches ? "" : " faded"}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"${arrow}><title>${esc(people.get(e.from)?.name)} ${esc(e.label)} ${esc(people.get(e.to)?.name)}</title></line>`;
      if (selected != null && touches) {
        out += `<text class="edge-label" x="${(a.x + b.x) / 2}" y="${(a.y + b.y) / 2 - 4}" text-anchor="middle"${conflict ? ' fill="var(--red)"' : ""}>${esc(conflict ? conflictText(e) : e.label)}</text>`;
      }
    });
    [...shown].forEach(id => {
      const p = people.get(id), v = layout.pos.get(id), r = radius(id);
      const dead = p.died_chapter && p.died_chapter <= asOf;
      const faded = selected != null && selected !== id && !map.edges.some(e => visible(e) && ((e.from === selected && e.to === id) || (e.to === selected && e.from === id)));
      out += `<g class="node${dead ? " dead" : ""}${selected === id ? " selected" : ""}" data-id="${id}" tabindex="0" role="button" aria-label="${esc(p.name)}"${faded ? ' opacity=".35"' : ""}>
        <circle cx="${v.x}" cy="${v.y}" r="${r}"/>
        <text class="name" x="${v.x}" y="${v.y + r + 16}" text-anchor="middle">${esc(short(p.name, 22))}</text>
        ${dead ? `<text class="sub" x="${v.x}" y="${v.y + r + 30}" text-anchor="middle">died in ch ${p.died_chapter}</text>` : ""}</g>`;
    });
    svg.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
    svg.innerHTML = out;
    return shown.size;
  }

  // -------------------------------------------------------------------------
  // Person panel (below either chart)
  // -------------------------------------------------------------------------
  function personPanel(map, id, asOf) {
    const p = map.people.find(x => x.id === id);
    if (!p) return "";
    const others = new Map(map.people.map(x => [x.id, x]));
    const ties = map.edges.filter(e => (e.from === id || e.to === id) && e.first_chapter <= asOf);
    const describe = e => {
      const other = others.get(e.from === id ? e.to : e.from);
      if (e.from === id) return `${e.label} ${other.name}`;
      const inverse = { parent: "child of", mentor: "student of", employer: "works for" }[e.kind] || e.label;
      return `${inverse} ${other.name}`;
    };
    return `<div class="person-panel" aria-live="polite">
      <h2>${esc(p.name)}</h2>
      <p class="hint" style="margin:0">${p.aliases.length > 1 ? `Also called ${p.aliases.filter(a => a !== p.name).map(esc).join(", ")}. ` : ""}First appears in chapter ${p.first_chapter}${p.died_chapter ? `, dies in chapter ${p.died_chapter}` : ""}.
        <a href="#/entity/${p.id}">Open in the story bible</a></p>
      ${ties.length ? `<ul class="ties">${ties.map(e => {
        const m = e.mentions.filter(x => x.chapter_number <= asOf);
        const clash = (e.conflicts || []).filter(c => c.first_chapter <= asOf);
        return `<li><strong>${esc(describe(e))}</strong> <span class="hint">(chapter ${m.map(x => x.chapter_number).join(", ")})</span>
          <q>${esc(m[0].quote)}</q>
          ${clash.map(c => `<div class="clash">The chapters disagree: chapter ${c.first_chapter} makes them ${esc(NOUN[c.kind] === "married" ? "married" : (NOUN[c.kind] || c.kind) + "s")} instead (“${esc(c.quote)}”).</div>`).join("")}</li>`;
      }).join("")}</ul>` : `<p class="hint">No relationships recorded yet at this point in the story.</p>`}
    </div>`;
  }

  // -------------------------------------------------------------------------
  // Presence map
  // -------------------------------------------------------------------------
  function presenceTable(data) {
    if (!data.entities.length) return `<div class="empty">Add chapters and the people, places and objects in them appear here.</div>`;
    const max = Math.max(1, ...data.entities.flatMap(e => Object.values(e.cells).map(c => c.facts)));
    const dot = (cell) => {
      if (!cell) return `<svg viewBox="0 0 26 26" aria-hidden="true"><circle cx="13" cy="13" r="1.6" fill="var(--rule)"/></svg>`;
      const r = 4 + 7 * Math.sqrt(cell.facts / max);
      return `<svg viewBox="0 0 26 26"><title>${cell.facts} facts${cell.issues ? `, ${cell.issues} open issue${cell.issues > 1 ? "s" : ""}` : ""}</title>
        <circle cx="13" cy="13" r="${r}" fill="${cell.issues ? "var(--red)" : "var(--pencil)"}" opacity=".85"/>
        ${cell.issues ? `<circle cx="13" cy="13" r="${Math.min(12, r + 3)}" fill="none" stroke="var(--red)" stroke-width="1.5"/>` : ""}</svg>`;
    };
    return `<div class="table-wrap presence"><table>
      <thead><tr><th>Who or what</th>${data.chapters.map(c => `<th class="ch"><a href="#/chapter/${encodeURIComponent(c.chapter_id)}" title="${esc(c.chapter_id)}">${c.chapter_number}</a></th>`).join("")}</tr></thead>
      <tbody>${data.entities.map(e => `<tr><th class="rowhead" scope="row"><a href="#/entity/${e.id}">${esc(e.name)}</a></th>
        ${data.chapters.map(c => `<td class="cell">${dot(e.cells[c.chapter_id])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="map-legend"><span><svg viewBox="0 0 34 12"><circle cx="8" cy="6" r="5" fill="var(--pencil)"/></svg>Appears (bigger means more facts)</span>
        <span><svg viewBox="0 0 34 12"><circle cx="8" cy="6" r="4" fill="var(--red)"/><circle cx="8" cy="6" r="5.5" fill="none" stroke="var(--red)"/></svg>Appears with an open issue</span></div>`;
  }

  // -------------------------------------------------------------------------
  // The page
  // -------------------------------------------------------------------------
  const LEGEND = `<div class="map-legend">
    <span><svg viewBox="0 0 34 12"><line x1="0" y1="6" x2="34" y2="6" class="link family"/></svg>Family</span>
    <span><svg viewBox="0 0 34 12"><line x1="0" y1="6" x2="34" y2="6" class="link bond"/></svg>Friend, ally, mentor, love</span>
    <span><svg viewBox="0 0 34 12"><line x1="0" y1="6" x2="34" y2="6" class="link hostile"/></svg>Rival or enemy</span>
    <span><svg viewBox="0 0 34 12"><line x1="0" y1="6" x2="34" y2="6" class="link conflict"/></svg>The chapters disagree</span>
    <span><svg viewBox="0 0 34 14"><rect x="2" y="1" width="30" height="12" rx="3" fill="var(--rule-soft)" stroke="var(--graphite)" stroke-dasharray="4 3"/></svg>Has died by this chapter</span></div>`;

  async function render(view, api, load, save) {
    const mode = load("storyforge-map-mode") || "tree";
    view.innerHTML = `<h1>Character map</h1>
      <p class="lede">Who is related to whom, as the story says it. Drag the slider to watch the cast and their ties grow chapter by chapter, or to share the map without spoiling the ending.</p>
      <div class="map-controls">
        <div class="segmented" role="group" aria-label="Chart">
          <button type="button" data-mode="tree" aria-pressed="${mode === "tree"}">Family tree</button>
          <button type="button" data-mode="web" aria-pressed="${mode === "web"}">Relationship web</button>
          <button type="button" data-mode="presence" aria-pressed="${mode === "presence"}">Who appears where</button></div>
        <div class="slider" id="slider-box"></div>
      </div>
      <div id="chart"><p><span class="spinner" aria-hidden="true"></span> Drawing…</p></div>`;
    view.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => { save("storyforge-map-mode", b.dataset.mode); render(view, api, load, save); });
    const box = view.querySelector("#chart");
    try {
      if (mode === "presence") {
        view.querySelector("#slider-box").remove();
        box.innerHTML = presenceTable(await api("/presence"));
        return;
      }
      const map = await api("/characters/map");
      if (!map.chapters.length) { box.innerHTML = `<div class="empty">Add a chapter to start the map.</div>`; return; }
      const layout = mode === "tree" ? familyLayout(map) : webLayout(map);
      const relevant = mode === "tree" ? layout.fam : map.edges;
      if (!relevant.length) {
        box.innerHTML = `<div class="empty">${mode === "tree" ? "No family ties have been recorded yet. When a chapter mentions parents, children, spouses or siblings, they're drawn here."
          : "No relationships have been recorded yet. Friendships, rivalries and family ties appear here as chapters mention them."}</div>`;
        return;
      }
      const chapters = map.chapters;
      let idx = chapters.length - 1, selected = null, timer = null;
      const sliderBox = view.querySelector("#slider-box");
      sliderBox.innerHTML = `<label for="as-of" class="sr-only">As of chapter</label>
        <button class="btn quiet small" id="play" aria-label="Play through the chapters">Play</button>
        <input type="range" id="as-of" min="0" max="${chapters.length - 1}" step="1" value="${idx}">
        <output for="as-of" id="as-of-out"></output>`;
      box.innerHTML = `<div class="chart-box"><svg xmlns="${SVG}" role="img" aria-label="${mode === "tree" ? "Family tree" : "Relationship web"}"></svg></div>${LEGEND}
        ${mode === "tree" ? `<p class="loners">Cousins, grandparents and other relatives are in the relationship web.</p>` : ""}<div id="panel"></div>`;
      const svg = box.querySelector("svg"), out = view.querySelector("#as-of-out"), range = view.querySelector("#as-of");
      const draw = () => {
        const asOf = chapters[idx].chapter_number;
        const count = (mode === "tree" ? drawTree : drawWeb)(svg, map, layout, asOf, selected);
        out.textContent = `As of chapter ${asOf}: ${count} ${count === 1 ? "person" : "people"}`;
        box.querySelector("#panel").innerHTML = selected != null ? personPanel(map, selected, asOf) : `<p class="hint" style="margin-top:1rem">Select a person to see every tie the story gives them, with the quotes.</p>`;
      };
      range.oninput = () => { idx = Number(range.value); draw(); };
      svg.addEventListener("click", (e) => { const g = e.target.closest(".node"); selected = g ? (Number(g.dataset.id) === selected ? null : Number(g.dataset.id)) : null; draw(); });
      svg.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.closest(".node")) { e.preventDefault(); e.target.closest(".node").dispatchEvent(new MouseEvent("click", { bubbles: true })); } });
      const playBtn = view.querySelector("#play");
      const stop = () => { clearInterval(timer); timer = null; playBtn.textContent = "Play"; };
      playBtn.onclick = () => {
        if (timer) return stop();
        if (idx >= chapters.length - 1) idx = 0;
        playBtn.textContent = "Pause"; range.value = idx; draw();
        timer = setInterval(() => {
          if (!document.body.contains(range)) return stop();
          idx++; range.value = idx; draw();
          if (idx >= chapters.length - 1) stop();
        }, matchMedia("(prefers-reduced-motion: reduce)").matches ? 2200 : 1200);
      };
      draw();
    } catch (err) { box.innerHTML = `<div class="notice error" role="alert">${esc(err.message)}</div>`; }
  }

  return { render, familyLayout, webLayout };
})();
