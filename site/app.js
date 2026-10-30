// MouZe website: gallery, search and live "try this cursor" on the page.
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("site-data").textContent);
  const $ = (id) => document.getElementById(id);
  const live = $("live-cursors");
  const grid = $("grid");
  const search = $("search");
  const chips = $("chips");
  const bySlug = new Map(data.skins.map((s) => [s.slug, s]));
  const month = String(new Date().getMonth() + 1);
  const inSeason = new Set(data.seasons[month] || []);
  let filter = "all";
  let current = null;

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 2200);
  }

  // ---------------------------------------------------------------- filters
  const seasonal = data.skins.filter((s) => s.tags.some((t) => inSeason.has(t)));
  const filters = [
    ["all", "All", data.skins.length],
    ...(seasonal.length ? [["season", "In season", seasonal.length]] : []),
    ["picks", "Staff picks", data.skins.filter((s) => s.pick).length],
    ["animated", "Animated", data.skins.filter((s) => s.animated).length],
    ...data.categories.map((c) => [`cat:${c}`, c, data.skins.filter((s) => s.category === c).length]),
  ].filter(([, , n]) => n > 0);

  for (const [key, label, n] of filters) {
    const b = document.createElement("button");
    b.className = "chip";
    b.type = "button";
    b.setAttribute("role", "tab");
    b.dataset.key = key;
    b.innerHTML = `${label}<span class="n">${n}</span>`;
    b.addEventListener("click", () => { filter = key; render(); });
    chips.append(b);
  }

  function matches(s, q) {
    if (filter === "season" && !s.tags.some((t) => inSeason.has(t))) return false;
    if (filter === "picks" && !s.pick) return false;
    if (filter === "animated" && !s.animated) return false;
    if (filter.startsWith("cat:") && s.category !== filter.slice(4)) return false;
    if (!q) return true;
    const hay = `${s.name} ${s.category} ${s.tags.join(" ")} ${s.description}`.toLowerCase();
    return q.split(/\s+/).every((w) => hay.includes(w));
  }

  // ---------------------------------------------------------------- cards
  const cards = new Map();
  for (const s of data.skins) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "card";
    b.title = s.description || s.name;
    b.setAttribute("aria-pressed", "false");
    const img = document.createElement("img");
    img.src = s.thumb;
    img.alt = "";
    img.loading = "lazy";
    img.width = img.height = 48;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = s.name;
    const cat = document.createElement("span");
    cat.className = "cat";
    cat.textContent = s.category;
    b.append(img, name, cat);
    if (s.animated) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "animated";
      b.append(badge);
    }
    b.addEventListener("click", () => tryOn(s));
    cards.set(s.slug, b);
  }

  function render() {
    const q = search.value.trim().toLowerCase();
    const shown = data.skins.filter((s) => matches(s, q));
    grid.replaceChildren(...shown.map((s) => cards.get(s.slug)));
    if (!shown.length) {
      const e = document.createElement("div");
      e.className = "empty";
      e.textContent = "No skins match. Try another word or category.";
      grid.append(e);
    }
    $("result-count").textContent = `${shown.length} skin${shown.length === 1 ? "" : "s"}`;
    for (const c of chips.children) c.setAttribute("aria-selected", String(c.dataset.key === filter));
  }
  search.addEventListener("input", render);

  // ---------------------------------------------------------------- trying a skin
  function tryOn(s, quiet) {
    if (current) cards.get(current.slug)?.setAttribute("aria-pressed", "false");
    current = s;
    live.href = s ? s.css : "data:text/css,";
    $("now-name").textContent = s ? s.name : "Your normal cursor";
    $("now-thumb").src = s ? s.thumb : "icon.png";
    $("copy-cmd").disabled = !s;
    $("reset").disabled = !s;
    const dl = $("dl-web");
    if (s) {
      dl.href = s.zip;
      dl.setAttribute("download", "");
      dl.removeAttribute("aria-disabled");
      cards.get(s.slug)?.setAttribute("aria-pressed", "true");
    } else {
      dl.removeAttribute("href");
      dl.setAttribute("aria-disabled", "true");
    }
    store.set("mouze-try", s ? s.slug : null);
    history.replaceState(null, "", s ? `#try=${s.slug}` : location.pathname);
    if (s && !quiet) toast(`Now using ${s.name}. Move your mouse around!`);
  }

  $("reset").addEventListener("click", () => tryOn(null));
  $("copy-cmd").addEventListener("click", async () => {
    if (!current) return;
    const cmd = `mouze apply "${current.name}"`;
    try {
      await navigator.clipboard.writeText(cmd);
      toast(`Copied: ${cmd}`);
    } catch {
      prompt("Copy this command:", cmd);
    }
  });

  // ---------------------------------------------------------------- community
  const cgrid = $("community-grid");
  const entries = (data.community && data.community.skins) || [];
  if (!entries.length) {
    cgrid.innerHTML = '<p class="dim">No community skins yet. Be the first!</p>';
  }
  for (const e of entries) {
    const card = document.createElement("article");
    card.className = "ccard";
    const img = document.createElement("img");
    img.src = e.preview || "icon.png";
    img.alt = `${e.name} cursor preview`;
    img.loading = "lazy";
    const body = document.createElement("div");
    body.className = "body";
    const h = document.createElement("h3");
    h.textContent = e.name;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = [e.author && `by ${e.author}`, e.category, e.license, e.animated ? "animated" : ""]
      .filter(Boolean).join(" · ");
    const desc = document.createElement("p");
    desc.className = "dim small";
    desc.style.margin = "0";
    desc.textContent = e.description || "";
    const actions = document.createElement("div");
    actions.className = "actions";
    const dl = document.createElement("a");
    dl.className = "btn small";
    dl.href = e.url;
    dl.setAttribute("download", "");
    dl.textContent = "Download .mouzeskin";
    actions.append(dl);
    body.append(h, meta, desc, actions);
    card.append(img, body);
    cgrid.append(card);
  }

  // ---------------------------------------------------------------- start
  const fromHash = (location.hash.match(/^#try=([\w-]+)/) || [])[1];
  const initial = bySlug.get(fromHash) || bySlug.get(store.get("mouze-try"));
  render();
  if (initial) tryOn(initial, true);
})();
