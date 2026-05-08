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
      journal: "",
      publisher: "",     // "" = all; else group label e.g. "Nature"
      year: null,
      search: "",
    },
    sort: "year",
  };

  const els = {
    grid: document.getElementById("pubGrid"),
    search: document.getElementById("searchInput"),
    journal: document.getElementById("journalSelect"),
    sort: document.getElementById("sortSelect"),
    yearFilter: document.getElementById("yearFilter"),
    publisherTabs: document.getElementById("publisherTabs"),
    lastUpdated: document.getElementById("lastUpdated"),
    pubCount: document.getElementById("pubCount"),
    resultCount: document.getElementById("resultCount"),
    siteTitle: document.getElementById("siteTitle"),
    siteSubtitle: document.getElementById("siteSubtitle"),
    themeToggle: document.getElementById("themeToggle"),
  };

  // ─── Publisher / source-family mapping ─────────────────
  // Maps a journal source title to a display group. Patterns are matched in
  // order; the first hit wins. Anything unmatched falls into "Other".
  const PUBLISHER_GROUPS = [
    {
      label: "Nature",
      test: (j) => /\bnature\b/i.test(j) || /^communications\s+(earth|biology|materials|chemistry|physics|engineering)/i.test(j) || /^scientific reports$/i.test(j) || /^npj\b/i.test(j),
    },
    {
      label: "Science",
      test: (j) =>
        /^science$/i.test(j) ||
        /^science\s+(advances|signaling|robotics|translational|immunology)/i.test(j),
    },
    {
      label: "Cell",
      test: (j) =>
        /^cell\b/i.test(j) ||
        /^(current biology|one earth|joule|patterns|matter|chem|iscience|heliyon|trends in)/i.test(j),
    },
    {
      label: "PNAS",
      test: (j) =>
        /proceedings of the national academy/i.test(j) || /^pnas\b/i.test(j),
    },
    {
      label: "Elsevier",
      test: (j) =>
        /^(field crops research|agricultural systems|agricultural and forest meteorology|computers and electronics in agriculture|remote sensing of environment|science of the total environment|european journal of agronomy|soil & tillage research|soil and tillage research|environmental modelling.*software|environmental modeling.*software|geoderma|catena|ecological modelling|ecological modeling|agricultural water management|isprs journal of photogrammetry|international journal of applied earth observation|computers .+ geosciences|earth-?science reviews|advances in water resources|biosystems engineering|smart agricultural technology|computers and electronics|crop protection|european journal of soil science|land use policy|global ecology and conservation)$/i.test(
          j
        ),
    },
    {
      label: "Wiley",
      test: (j) =>
        /^(global change biology|new phytologist|plant cell .+environment|plant,? cell .+environment|ecology letters|journal of agronomy and crop science|food and energy security|gcb bioenergy|earth's future|journal of geophysical research|water resources research|geophysical research letters|journal of advances in modeling earth systems|land degradation .+development|hydrological processes|river research and applications)$/i.test(
          j
        ),
    },
    {
      label: "Springer",
      test: (j) =>
        /^(climatic change|biogeochemistry|theoretical and applied climatology|precision agriculture|nutrient cycling in agroecosystems|plant and soil|euphytica|regional environmental change|mitigation and adaptation strategies for global change|agronomy for sustainable development|food security|environmental monitoring and assessment|environmental science and pollution research|paddy and water environment|earth systems and environment|natural hazards|geoinformatica)$/i.test(
          j
        ),
    },
    {
      label: "Taylor & Francis",
      test: (j) =>
        /^(international journal of remote sensing|gisscience .+ remote sensing|gi science .+ remote sensing|geocarto international|remote sensing letters|international journal of digital earth|international journal of geographical information science|cartography and geographic information science|journal of land use science|international journal of agricultural sustainability|journal of sustainable agriculture|critical reviews in plant sciences|big earth data)$/i.test(
          j
        ),
    },
    {
      label: "IOP",
      test: (j) =>
        /^environmental research letters$/i.test(j) ||
        /^environmental research:\s/i.test(j),
    },
    {
      label: "MDPI",
      test: (j) =>
        /^(remote sensing|agronomy-basel|agronomy$|agriculture-basel|agriculture$|sustainability|land-basel|land$|water-basel|water$|atmosphere-basel|atmosphere$|sensors-basel|sensors$|drones-basel|drones$|forests$|plants-basel|plants$|ijgi$|isprs international journal of geo-information)$/i.test(
          j
        ),
    },
    {
      label: "Frontiers",
      test: (j) => /^frontiers in\b/i.test(j),
    },
    {
      label: "ACS",
      test: (j) =>
        /^journal of agricultural and food chemistry$/i.test(j) ||
        /^environmental science[\s&.]+(technology|letters)/i.test(j) ||
        /^acs\s/i.test(j),
    },
    {
      label: "IEEE",
      test: (j) =>
        /^ieee\b/i.test(j) ||
        /^proceedings of the ieee$/i.test(j),
    },
    {
      label: "AGU",
      test: (j) =>
        /\b(eos|earth and space science|agu advances)\b/i.test(j),
    },
    {
      label: "AMS",
      test: (j) =>
        /^(journal of climate|journal of hydrometeorology|monthly weather review|journal of applied meteorology|weather and forecasting|bulletin of the american meteorological society)$/i.test(
          j
        ),
    },
    {
      label: "Annual Reviews",
      test: (j) => /^annual review of\b/i.test(j),
    },
    {
      label: "Cambridge",
      test: (j) =>
        /^(journal of agricultural science|experimental agriculture|environment and development economics|weed science)$/i.test(
          j
        ),
    },
    {
      label: "Oxford",
      test: (j) =>
        /^(journal of experimental botany|tree physiology|plant physiology|bioscience|forestry|oxford open climate change)$/i.test(
          j
        ),
    },
    {
      label: "RSC",
      test: (j) =>
        /^environmental science:\s+(processes|water|advances|atmospheres|nano)/i.test(
          j
        ) || /^(green chemistry|food .+ function)$/i.test(j),
    },
    {
      label: "Sage",
      test: (j) =>
        /^(progress in physical geography|the holocene|outlook on agriculture)$/i.test(
          j
        ),
    },
    {
      label: "ESA",
      test: (j) => /^(ecology|ecological applications|ecosphere|frontiers in ecology and the environment|ecological monographs)$/i.test(j),
    },
    {
      label: "PLOS",
      test: (j) => /^plos\b/i.test(j),
    },
    {
      label: "Copernicus",
      test: (j) =>
        /^(biogeosciences|hydrology and earth system sciences|earth system science data|geoscientific model development|atmospheric chemistry and physics|the cryosphere|earth system dynamics|soil$|soil-eu|natural hazards and earth system sciences)$/i.test(
          j
        ),
    },
    {
      label: "arXiv",
      test: (j) => /^(arxiv|biorxiv|medrxiv|earth?xiv|chemrxiv)\b|preprint/i.test(j),
    },
  ];

  function publisherFor(journal) {
    const j = String(journal || "").trim();
    if (!j) return "Other";
    for (const g of PUBLISHER_GROUPS) {
      if (g.test(j)) return g.label;
    }
    return "Other";
  }

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

  // Render scientific text safely: HTML-escape everything, then re-enable
  // ONLY <sub>/<sup> (case-insensitive, no attributes). WoS returns these
  // as literal markup inside titles, abstracts and keywords (e.g. "CO<sub>2</sub>").
  function renderSciText(str) {
    return escapeHtml(str).replace(
      /&lt;(\/?)(sub|sup)&gt;/gi,
      (_, slash, tag) => `<${slash}${tag.toLowerCase()}>`
    );
  }

  // Strip <sub>/<sup> markers from a value before using it as a search /
  // sort key, so typing "CO2" matches "CO<sub>2</sub>".
  function stripSciTags(str) {
    if (str === null || str === undefined) return "";
    return String(str).replace(/<\/?(?:sub|sup)>/gi, "");
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
      populatePublishers();
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

  // ─── Publisher / source filter ──────────────────────────

  function populatePublishers() {
    const container = els.publisherTabs;
    if (!container) return;

    // Wipe out every tab except the static "All publishers" tab.
    container
      .querySelectorAll(".publisher-tab:not([data-publisher=''])")
      .forEach((b) => b.remove());

    const counts = new Map();
    state.publications.forEach((p) => {
      const g = publisherFor(p.journal);
      counts.set(g, (counts.get(g) || 0) + 1);
    });

    // Only show publishers that actually have papers. Order = canonical
    // PUBLISHER_GROUPS order, with "Other" last if present.
    const ordered = [];
    PUBLISHER_GROUPS.forEach((g) => {
      if ((counts.get(g.label) || 0) > 0) ordered.push(g.label);
    });
    if ((counts.get("Other") || 0) > 0) ordered.push("Other");

    ordered.forEach((label) => {
      const c = counts.get(label) || 0;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "publisher-tab";
      btn.dataset.publisher = label;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", "false");
      btn.innerHTML = `<span class="tab-label">${escapeHtml(label)}</span><span class="tab-count">${c}</span>`;
      container.appendChild(btn);
    });

    container.onclick = (e) => {
      const btn = e.target.closest(".publisher-tab");
      if (!btn) return;
      container.querySelectorAll(".publisher-tab").forEach((b) => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");
      state.filters.publisher = btn.dataset.publisher || "";
      render();
    };
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

    const yearLabel = document.createElement("span");
    yearLabel.className = "filter-strip-label";
    yearLabel.textContent = "Year";
    els.yearFilter.appendChild(yearLabel);

    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "year-chip is-active";
    allBtn.textContent = "All";
    allBtn.dataset.year = "";
    els.yearFilter.appendChild(allBtn);

    years.forEach((y) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "year-chip";
      btn.textContent = y;
      btn.dataset.year = y;
      els.yearFilter.appendChild(btn);
    });

    els.yearFilter.addEventListener("click", (e) => {
      const btn = e.target.closest(".year-chip");
      if (!btn) return;
      els.yearFilter
        .querySelectorAll(".year-chip")
        .forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.filters.year = btn.dataset.year || null;
      render();
    });
  }

  // ─── Filtering & sorting ────────────────────────────────

  function applyFilters(list) {
    const f = state.filters;
    const q = f.search.trim().toLowerCase();

    return list.filter((p) => {
      if (f.journal && p.journal !== f.journal) return false;
      if (f.publisher && publisherFor(p.journal) !== f.publisher) return false;
      if (f.year && String(p.year) !== String(f.year)) return false;

      if (q) {
        const hay = [
          stripSciTags(p.title),
          (p.authors || []).join(" "),
          (p.keywords || []).map(stripSciTags).join(" "),
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
        sorted.sort((a, b) =>
          stripSciTags(a.title || "").localeCompare(stripSciTags(b.title || ""))
        );
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
            .map((k) => `<span class="keyword-tag">${renderSciText(k)}</span>`)
            .join("")}</div>`
        : "";

    const abstractHtml = p.abstract
      ? `<button class="abstract-toggle" type="button" aria-expanded="false">Show abstract</button>
         <p class="pub-abstract">${renderSciText(p.abstract)}</p>`
      : "";

    const doiHtml = p.doi
      ? `<a class="pub-doi" href="https://doi.org/${encodeURIComponent(
          p.doi
        )}" target="_blank" rel="noopener">${escapeHtml(p.doi)}</a>`
      : `<span class="pub-doi" style="color: var(--text-mute); border:none">—</span>`;

    const badges = [];
    const publisher = publisherFor(p.journal);
    if (publisher && publisher !== "Other") {
      badges.push(
        `<span class="pub-publisher" data-publisher="${escapeHtml(publisher)}">${escapeHtml(publisher)}</span>`
      );
    }
    if (Array.isArray(p.sources) && p.sources.includes("journal")) {
      badges.push(`<span class="pub-source">Journal feed</span>`);
    }
    if (cites > 0) {
      badges.push(
        `<span class="pub-citations ${citeCls}">${cites} cite${cites === 1 ? "" : "s"}</span>`
      );
    }

    const card = document.createElement("article");
    card.className = "pub-card";
    card.style.animationDelay = `${Math.min(idx * 30, 600)}ms`;
    card.setAttribute(
      "aria-label",
      `${stripSciTags(p.title) || "Untitled"} (${p.year || "n.d."})`
    );

    card.innerHTML = `
      <div class="pub-card-header">
        <span class="pub-year">${escapeHtml(p.year || "n.d.")}</span>
        ${badges.join("")}
      </div>
      <h2 class="pub-title">${renderSciText(p.title || "Untitled")}</h2>
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
      toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        const expanded = card.classList.toggle("expanded");
        toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
        toggle.textContent = expanded ? "Hide abstract" : "Show abstract";
      });
    }

    // Whole-card → DOI link (skip clicks on inner buttons / anchors).
    if (p.doi) {
      const url = `https://doi.org/${encodeURIComponent(p.doi)}`;
      card.classList.add("is-clickable");
      card.setAttribute("role", "link");
      card.tabIndex = 0;
      card.addEventListener("click", (e) => {
        if (e.target.closest("a, button")) return;
        window.open(url, "_blank", "noopener,noreferrer");
      });
      card.addEventListener("keydown", (e) => {
        if (e.target.closest("a, button")) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          window.open(url, "_blank", "noopener,noreferrer");
        }
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

    const total = state.publications.length;
    const count = filtered.length;
    if (els.pubCount) {
      els.pubCount.textContent = `${total} ${total === 1 ? "paper" : "papers"}`;
    }
    if (els.resultCount) {
      els.resultCount.textContent =
        count === total
          ? `Showing all ${total}`
          : `Showing ${count} of ${total}`;
    }
  }

  // ─── Wire up controls ───────────────────────────────────

  function bindControls() {
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
