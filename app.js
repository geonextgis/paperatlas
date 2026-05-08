/* ============================================================
   app.js — Research-feed website logic
   ============================================================ */

(function () {
  "use strict";

  const DATA_URL = "./data/publications.json";
  const REPO_LINK = "https://github.com/";
  const THEME_KEY = "paperatlas-theme";

  const state = {
    publications: [],
    journalsOfInterest: [],
    filters: {
      type: "all",      // all | oa
      journal: "",
      year: null,
      search: "",
    },
    sort: "year",
  };

  const els = {
    grid: document.getElementById("pubGrid"),
    search: document.getElementById("searchInput"),
    pills: document.querySelectorAll(".pill"),
    journal: document.getElementById("journalSelect"),
    sort: document.getElementById("sortSelect"),
    yearFilter: document.getElementById("yearFilter"),
    lastUpdated: document.getElementById("lastUpdated"),
    pubCount: document.getElementById("pubCount"),
    siteTitle: document.getElementById("siteTitle"),
    siteSubtitle: document.getElementById("siteSubtitle"),
    themeToggle: document.getElementById("themeToggle"),
  };

  // ─── Utilities ──────────────────────────────────────────

  function debounce(fn, ms) {
    let t;
    return function () {
      clearTimeout(t);
      const args = arguments;
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatDate(iso) {
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso || "—";
      return d.toLocaleDateString("en-GB", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch (_) {
      return iso || "—";
    }
  }

  function citationClass(n) {
    const c = Number(n) || 0;
    if (c > 50) return "cite-hi";
    if (c > 10) return "cite-mid";
    return "cite-low";
  }

  // ─── Theme toggle ───────────────────────────────────────

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (_) {}
    if (els.themeToggle) {
      els.themeToggle.setAttribute(
        "title",
        theme === "light" ? "Switch to dark theme" : "Switch to light theme"
      );
    }
  }

  function bindThemeToggle() {
    if (!els.themeToggle) return;
    els.themeToggle.addEventListener("click", () => {
      const current =
        document.documentElement.getAttribute("data-theme") || "dark";
      setTheme(current === "light" ? "dark" : "light");
    });
    // Sync title attribute with whichever theme the inline pre-paint script set.
    const initial =
      document.documentElement.getAttribute("data-theme") || "dark";
    setTheme(initial);
  }

  // ─── Data load ──────────────────────────────────────────

  async function loadData() {
    try {
      const resp = await fetch(DATA_URL, { cache: "no-cache" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      state.publications = Array.isArray(data.publications)
        ? data.publications
        : [];
      state.journalsOfInterest = Array.isArray(data.journals_of_interest)
        ? data.journals_of_interest
        : [];

      els.lastUpdated.textContent = formatDate(data.updated_at);

      if (data.site && typeof data.site === "object") {
        if (data.site.title && els.siteTitle) {
          // Use only the first segment before " — " as the big title.
          const parts = String(data.site.title).split(" — ");
          els.siteTitle.textContent = parts[0];
          if (parts[1]) document.title = data.site.title;
        }
        if (data.site.subtitle && els.siteSubtitle) {
          els.siteSubtitle.textContent = data.site.subtitle;
        }
      }

      populateJournals();
      populateYears();
      render();
    } catch (err) {
      console.error("Failed to load publications:", err);
      els.lastUpdated.textContent = "—";
      els.grid.innerHTML = `
        <div class="error-state">
          <p><strong>Could not load publications.</strong></p>
          <p>The file <code>data/publications.json</code> is missing or unreachable.</p>
          <p>If you are the site owner, run the
            <a href="${REPO_LINK}" target="_blank" rel="noopener">GitHub Actions workflow</a>
            once to generate it.</p>
        </div>
      `;
    }
  }

  // ─── Journal dropdown ───────────────────────────────────

  function populateJournals() {
    const sel = els.journal;
    while (sel.options.length > 1) sel.remove(1);

    let journals = [];
    if (state.journalsOfInterest.length > 0) {
      journals = state.journalsOfInterest.slice();
    } else {
      const seen = new Set();
      state.publications.forEach((p) => {
        if (p.journal && !seen.has(p.journal)) {
          seen.add(p.journal);
          journals.push(p.journal);
        }
      });
    }
    journals.sort((a, b) => a.localeCompare(b));
    journals.forEach((j) => {
      const opt = document.createElement("option");
      opt.value = j;
      opt.textContent = j;
      sel.appendChild(opt);
    });
  }

  // ─── Year filter ────────────────────────────────────────

  function populateYears() {
    const seen = new Set();
    state.publications.forEach((p) => {
      const y = String(p.year || "").trim();
      if (y && /^\d{4}$/.test(y)) seen.add(y);
    });
    const years = Array.from(seen).sort((a, b) => Number(b) - Number(a));

    els.yearFilter.innerHTML = "";
    if (years.length === 0) return;

    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "year-pill active";
    allBtn.textContent = "All Years";
    allBtn.dataset.year = "";
    els.yearFilter.appendChild(allBtn);

    years.forEach((y) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "year-pill";
      btn.textContent = y;
      btn.dataset.year = y;
      els.yearFilter.appendChild(btn);
    });

    els.yearFilter.addEventListener("click", (e) => {
      const btn = e.target.closest(".year-pill");
      if (!btn) return;
      els.yearFilter
        .querySelectorAll(".year-pill")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.filters.year = btn.dataset.year || null;
      render();
    });
  }

  // ─── Filtering & sorting ────────────────────────────────

  function applyFilters(list) {
    const f = state.filters;
    const q = f.search.trim().toLowerCase();

    return list.filter((p) => {
      if (f.type === "oa" && !p.open_access) return false;
      if (f.journal && p.journal !== f.journal) return false;
      if (f.year && String(p.year) !== String(f.year)) return false;

      if (q) {
        const hay = [
          p.title,
          (p.authors || []).join(" "),
          (p.keywords || []).join(" "),
          p.journal,
          String(p.year || ""),
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function applySort(list) {
    const sorted = list.slice();
    switch (state.sort) {
      case "cited":
        sorted.sort(
          (a, b) => (Number(b.citations) || 0) - (Number(a.citations) || 0)
        );
        break;
      case "alpha":
        sorted.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
        break;
      case "year":
      default:
        sorted.sort((a, b) => {
          const ya = Number(a.year) || 0;
          const yb = Number(b.year) || 0;
          if (yb !== ya) return yb - ya;
          return (Number(b.citations) || 0) - (Number(a.citations) || 0);
        });
    }
    return sorted;
  }

  // ─── Rendering ──────────────────────────────────────────

  function renderCard(p, idx) {
    const authorsHtml = (p.authors && p.authors.length)
      ? p.authors.map(escapeHtml).join(", ")
      : "—";

    const cites = Number(p.citations) || 0;
    const citeCls = citationClass(cites);

    const journalMeta = [];
    if (p.volume) journalMeta.push(`vol. ${escapeHtml(p.volume)}`);
    if (p.issue) journalMeta.push(`no. ${escapeHtml(p.issue)}`);
    if (p.pages) journalMeta.push(escapeHtml(p.pages));
    const journalMetaHtml = journalMeta.length
      ? `<span class="pub-journal-meta">· ${journalMeta.join(" · ")}</span>`
      : "";

    const keywordsHtml =
      Array.isArray(p.keywords) && p.keywords.length
        ? `<div class="pub-keywords">${p.keywords
            .slice(0, 8)
            .map((k) => `<span class="keyword-tag">${escapeHtml(k)}</span>`)
            .join("")}</div>`
        : "";

    const abstractHtml = p.abstract
      ? `<button class="abstract-toggle" type="button" aria-expanded="false">Show abstract</button>
         <p class="pub-abstract">${escapeHtml(p.abstract)}</p>`
      : "";

    const doiHtml = p.doi
      ? `<a class="pub-doi" href="https://doi.org/${encodeURIComponent(
          p.doi
        )}" target="_blank" rel="noopener">${escapeHtml(p.doi)}</a>`
      : `<span class="pub-doi" style="color: var(--text-mute); border:none">—</span>`;

    const badges = [];
    if (Array.isArray(p.sources) && p.sources.includes("journal")) {
      badges.push(`<span class="pub-source">Journal feed</span>`);
    }
    if (p.open_access) badges.push(`<span class="pub-oa">Open Access</span>`);
    badges.push(
      `<span class="pub-citations ${citeCls}">${cites} cite${
        cites === 1 ? "" : "s"
      }</span>`
    );

    const card = document.createElement("article");
    card.className = "pub-card";
    card.style.animationDelay = `${Math.min(idx * 30, 600)}ms`;
    card.setAttribute(
      "aria-label",
      `${p.title || "Untitled"} (${p.year || "n.d."})`
    );

    card.innerHTML = `
      <div class="pub-card-header">
        <span class="pub-year">${escapeHtml(p.year || "n.d.")}</span>
        ${badges.join("")}
      </div>
      <h2 class="pub-title">${escapeHtml(p.title || "Untitled")}</h2>
      <p class="pub-authors">${authorsHtml}</p>
      <p class="pub-journal">${escapeHtml(p.journal || "—")}${journalMetaHtml}</p>
      ${keywordsHtml}
      ${abstractHtml}
      <div class="pub-footer">
        ${doiHtml}
      </div>
    `;

    const toggle = card.querySelector(".abstract-toggle");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const expanded = card.classList.toggle("expanded");
        toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
        toggle.textContent = expanded ? "Hide abstract" : "Show abstract";
      });
    }

    return card;
  }

  function render() {
    const filtered = applySort(applyFilters(state.publications));
    els.grid.innerHTML = "";

    if (filtered.length === 0) {
      els.grid.innerHTML = `<div class="empty-state">No publications match these filters.</div>`;
    } else {
      const frag = document.createDocumentFragment();
      filtered.forEach((p, i) => frag.appendChild(renderCard(p, i)));
      els.grid.appendChild(frag);
    }

    els.pubCount.textContent = `${filtered.length} of ${state.publications.length} publications`;
  }

  // ─── Wire up controls ───────────────────────────────────

  function bindControls() {
    els.pills.forEach((btn) => {
      btn.addEventListener("click", () => {
        els.pills.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.filters.type = btn.dataset.filter;
        render();
      });
    });

    els.journal.addEventListener("change", () => {
      state.filters.journal = els.journal.value;
      render();
    });

    els.sort.addEventListener("change", () => {
      state.sort = els.sort.value;
      render();
    });

    els.search.addEventListener(
      "input",
      debounce(() => {
        state.filters.search = els.search.value;
        render();
      }, 300)
    );
  }

  // ─── Init ───────────────────────────────────────────────

  bindThemeToggle();
  bindControls();
  loadData();
})();
