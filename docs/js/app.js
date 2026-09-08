(function () {
  "use strict";

  const fmtUSD0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const fmtUSD2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  const fmtInt = new Intl.NumberFormat("en-US");
  const fmtPct = (v, digits) => (v === null || v === undefined ? "—" : v.toFixed(digits === undefined ? 2 : digits) + "%");
  function pctDecimalsFor(maxVal) {
    if (maxVal >= 10) return 1;
    if (maxVal >= 1) return 2;
    if (maxVal >= 0.1) return 3;
    return 4;
  }

  // FEC.gov serves stable, guessable profile URLs straight from the same
  // committee/candidate IDs already in this dataset -- no lookup needed.
  const fecCommitteeUrl = (cmteId) => "https://www.fec.gov/data/committee/" + encodeURIComponent(cmteId) + "/";
  const fecCandidateUrl = (candId) => "https://www.fec.gov/data/candidate/" + encodeURIComponent(candId) + "/";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function colors() {
    return {
      general_purpose: cssVar("--series-1"),
      political_specific: cssVar("--series-2"),
      muted: cssVar("--text-muted"),
      grid: cssVar("--gridline"),
      text: cssVar("--text-secondary"),
      party: {
        Democratic: cssVar("--series-1"),
        Republican: cssVar("--series-8"),
        Other: cssVar("--series-7"),
        Independent: cssVar("--series-7"),
        Unknown: cssVar("--text-muted"),
      },
      incumbency: {
        Incumbent: cssVar("--series-1"),
        Challenger: cssVar("--series-2"),
        "Open seat": cssVar("--series-3"),
        Unknown: cssVar("--text-muted"),
      },
      chamber: {
        House: cssVar("--series-1"),
        Senate: cssVar("--series-2"),
      },
      seqAge: {
        "Under 40": cssVar("--seq-250"),
        "40-49": cssVar("--seq-350"),
        "50-59": cssVar("--seq-450"),
        "60-69": cssVar("--seq-550"),
        "70+": cssVar("--seq-650"),
        Unknown: cssVar("--text-muted"),
      },
    };
  }

  const VENDOR_GROUP_LABEL = { general_purpose: "General-purpose AI", political_specific: "Campaign-specific AI" };
  const AGE_ORDER = ["Under 40", "40-49", "50-59", "60-69", "70+", "Unknown"];
  const INCUMBENCY_ORDER = ["Incumbent", "Challenger", "Open seat", "Unknown"];
  const PARTY_ORDER = ["Democratic", "Republican", "Other", "Independent", "Unknown"];
  const CHAMBER_ORDER = ["House", "Senate"];
  const CATEGORY_LABELS = {
    advertising_creative: "Advertising / creative content",
    communications_copy: "Communications copy (email/text/scripts)",
    synthetic_media: "Synthetic media / deepfake-adjacent",
    research_strategy: "Research, polling & strategy",
    fundraising: "Fundraising",
    data_targeting: "Voter data & targeting",
    administrative_productivity: "Administrative / general productivity",
    unspecified: "Unspecified / generic",
  };
  const MIN_TOTAL_FOR_PCT_TABLE = 5000;

  let DATA = null;
  let vendorNameById = {};
  let vendorHomepageById = {};
  let vendorEraById = {};
  let includeLegacy = false;

  function eraFilterList() {
    return includeLegacy ? ["generative", "legacy"] : ["generative"];
  }

  function vendorLinksCell(vendorIds) {
    const frag = document.createDocumentFragment();
    vendorIds.forEach((vid, i) => {
      if (i > 0) frag.appendChild(document.createTextNode(", "));
      const name = vendorNameById[vid] || vid;
      const homepage = vendorHomepageById[vid];
      if (homepage) {
        frag.appendChild(el("a", { className: "entity-link", href: homepage, text: name, attrs: { target: "_blank", rel: "noopener" } }));
      } else {
        frag.appendChild(el("a", { className: "entity-link", href: "#/vendor/" + vid, text: name }));
      }
      if (vendorEraById[vid] === "legacy") {
        frag.appendChild(el("span", { className: "pill pill-legacy", text: "legacy" }));
      }
    });
    return frag;
  }
  const chartInstances = {};
  const viewModes = { breakdowns: "dollar", trends: "dollar" };
  const sortState = {
    dollar: { key: "ai_amount_high", dir: "desc" },
    pct: { key: "pct_ai", dir: "desc" },
    ieSpenders: { key: "amount", dir: "desc" },
    ieRecords: { key: "transaction_amt", dir: "desc" },
    pceRecords: { key: "transaction_amt", dir: "desc" },
  };
  const filterState = { cycle: "all", category: "all" };

  function catLabel(id) {
    return CATEGORY_LABELS[id] || id;
  }

  function makeChart(canvasId, config) {
    const el = document.getElementById(canvasId);
    if (!el) return null;
    if (chartInstances[canvasId]) {
      chartInstances[canvasId].destroy();
    }
    chartInstances[canvasId] = new Chart(el.getContext("2d"), config);
    return chartInstances[canvasId];
  }

  function tooltipBase() {
    return {
      mode: "index",
      intersect: false,
      backgroundColor: cssVar("--surface-1"),
      titleColor: cssVar("--text-primary"),
      bodyColor: cssVar("--text-secondary"),
      borderColor: cssVar("--border"),
      borderWidth: 1,
      padding: 10,
      usePointStyle: true,
    };
  }

  function legendBase() {
    return { labels: { color: cssVar("--text-secondary"), usePointStyle: true, pointStyle: "line", boxWidth: 24 } };
  }

  // ---- small DOM helpers (never innerHTML with data-derived text) ----
  function el(tag, opts) {
    opts = opts || {};
    const node = document.createElement(tag);
    if (opts.className) node.className = opts.className;
    if (opts.text !== undefined) node.textContent = opts.text;
    if (opts.href !== undefined) node.href = opts.href;
    if (opts.id !== undefined) node.id = opts.id;
    if (opts.attrs) Object.keys(opts.attrs).forEach((k) => node.setAttribute(k, opts.attrs[k]));
    (opts.children || []).forEach((c) => c && node.appendChild(c));
    return node;
  }

  function backLink() {
    return el("a", { tag: "a", href: "#/", className: "back-link", text: "← Back to dashboard" });
  }

  function statTile(label, value, sub) {
    return el("div", {
      className: "stat-tile",
      children: [
        el("div", { className: "label", text: label }),
        el("div", { className: "value", text: value }),
        sub ? el("div", { className: "sub", text: sub }) : null,
      ],
    });
  }

  // ---- generic sortable/plain table builder ----
  function buildTable(headers, rows, opts) {
    opts = opts || {};
    const table = el("table", { className: "data-table scroll-wrap" });
    const thead = el("thead");
    const trh = el("tr");
    headers.forEach((h) => {
      const th = el("th", { text: h.label });
      if (h.num) th.classList.add("num");
      if (h.sortKey) {
        th.classList.add("sortable");
        if (opts.sort && opts.sort.key === h.sortKey) {
          th.appendChild(el("span", { className: "sort-arrow", text: opts.sort.dir === "asc" ? "↑" : "↓" }));
        }
        th.addEventListener("click", () => opts.onSort && opts.onSort(h.sortKey));
      }
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    rows.forEach((r) => {
      const tr = el("tr");
      headers.forEach((h) => {
        const td = el("td");
        if (h.num) td.classList.add("num");
        if (h.cell) {
          const node = h.cell(r);
          if (node) td.appendChild(node);
          tr.appendChild(td);
          return;
        }
        const linkHref = h.link && h.link(r);
        if (linkHref) {
          const a = el("a", { className: "entity-link", href: linkHref, text: h.render ? h.render(r) : r[h.key] });
          if (h.external) {
            a.target = "_blank";
            a.rel = "noopener";
          }
          td.appendChild(a);
        } else {
          td.textContent = h.render ? h.render(r) : r[h.key];
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  function setPanelTable(panel, headers, rows) {
    const holder = document.querySelector('.table-holder[data-panel="' + panel + '"]');
    if (!holder) return;
    holder.innerHTML = "";
    holder.appendChild(buildTable(headers, rows));
  }

  function wireToggles() {
    document.querySelectorAll(".btn-table-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const panel = btn.getAttribute("data-toggle");
        const chartEl = document.querySelector('.chart-holder[data-panel="' + panel + '"]');
        const tableEl = document.querySelector('.table-holder[data-panel="' + panel + '"]');
        if (!chartEl || !tableEl) return;
        const showingTable = !tableEl.hidden;
        tableEl.hidden = showingTable;
        chartEl.hidden = !showingTable;
        btn.textContent = showingTable ? "View as table" : "View chart";
      });
    });
  }

  function wireLegacyToggle() {
    const input = document.getElementById("legacy-toggle-input");
    if (!input) return;
    input.checked = includeLegacy;
    input.addEventListener("change", () => {
      includeLegacy = input.checked;
      renderAll();
    });
  }

  function wireViewModeToggles() {
    document.querySelectorAll(".view-toggle").forEach((group) => {
      const key = group.getAttribute("data-toggle-group");
      group.querySelectorAll(".btn-view-mode").forEach((btn) => {
        btn.addEventListener("click", () => {
          viewModes[key] = btn.getAttribute("data-mode");
          group.querySelectorAll(".btn-view-mode").forEach((b) => b.classList.toggle("is-active", b === btn));
          if (key === "breakdowns") renderBreakdowns();
          if (key === "trends") renderTrends();
        });
      });
    });
  }

  function renderStats() {
    const meta = DATA.meta;
    const totalMatchedRows = Object.values(meta.matched_row_counts_by_cycle || {}).reduce((a, b) => a + b, 0);
    const eraFilter = eraFilterList();
    const shownVendors = DATA.vendors_overall.filter((v) => eraFilter.includes(v.era));
    const totalHighAmount = shownVendors.reduce((a, v) => a + v.amount_high, 0);
    const nGeneral = shownVendors.filter((v) => v.group === "general_purpose").length;
    const nPolitical = shownVendors.filter((v) => v.group === "political_specific").length;
    const nLegacyHidden = DATA.vendors_overall.filter((v) => v.era === "legacy" && v.amount_high > 0).length;

    const tiles = [
      { label: "AI vendors identified in disclosures", value: fmtInt.format(shownVendors.length), sub: nGeneral + " general-purpose · " + nPolitical + " campaign-specific" + (includeLegacy ? "" : " · " + nLegacyHidden + " legacy vendors hidden") },
      { label: "AI-related disbursement records found", value: fmtInt.format(totalMatchedRows), sub: "across " + meta.cycles.join(", ") + " cycles, all confidence tiers, all eras" },
      { label: "Total high-confidence AI spending", value: fmtUSD0.format(totalHighAmount), sub: (includeLegacy ? "all vendors" : "generative-era vendors only") + ", all committees, all cycles" },
      { label: "2026 House/Senate candidates paying OpenAI", value: fmtInt.format(meta.openai_high_confidence_house_senate_candidates_2026), sub: "high-confidence text match to OpenAI/ChatGPT in payee name, purpose, or memo" },
    ];

    const row = document.getElementById("stat-row");
    row.innerHTML = "";
    tiles.forEach((t) => row.appendChild(statTile(t.label, t.value, t.sub)));

    document.getElementById("coverage-callout").innerHTML =
      "<strong>Coverage:</strong> this pipeline scans itemized operating-expenditure (Schedule B) records from FEC bulk data for the " +
      meta.cycles.join(", ") +
      " two-year cycles, matches payee/purpose/memo text against a curated AI-vendor taxonomy, and joins matches to candidate party, chamber, incumbency status, and (where available) age. Disclosed spending likely understates actual AI use, since campaigns can pay through corporate cards, staff, or consultants without the vendor name ever appearing in a filing." +
      (includeLegacy
        ? " Legacy-era vendors (pre-generative-AI companies branded “AI”) are currently included, via the toggle above."
        : " " + nLegacyHidden + " legacy-era vendor" + (nLegacyHidden === 1 ? "" : "s") + " with disclosed spending are hidden by default (toggle above to include them) &mdash; see methodology.");

    document.getElementById("meta-line").textContent =
      "Data generated " + new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) + " UTC · cycles: " + meta.cycles.join(", ");
    document.getElementById("footer-generated").textContent = "Dataset last built " + meta.generated_at + ".";
  }

  function renderVendors() {
    const c = colors();
    const eraFilter = eraFilterList();
    const rows = DATA.vendors_overall.filter((v) => eraFilter.includes(v.era)).slice(0, 20);
    const labels = rows.map((r) => r.name + (r.era === "legacy" ? " (legacy)" : ""));
    const data = rows.map((r) => r.amount_high);
    const bg = rows.map((r) => (r.group === "general_purpose" ? c.general_purpose : c.political_specific));

    // Chart.js silently auto-skips y-axis category labels (and the bars
    // that go with them) when the container is too short for all of them --
    // with up to 20 vendors that quietly dropped half the chart. Size the
    // container to the data instead of trusting a fixed CSS height.
    const vendorsHolder = document.querySelector('.chart-holder[data-panel="vendors"]');
    if (vendorsHolder) vendorsHolder.style.height = Math.max(380, rows.length * 26) + "px";

    makeChart("chart-vendors", {
      type: "bar",
      data: { labels, datasets: [{ label: "High-confidence spending", data, backgroundColor: bg, borderRadius: 4, barThickness: 16 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        onClick: (evt, elements, chart) => {
          const pts = chart.getElementsAtEventForMode(evt, "nearest", { intersect: true }, false);
          if (pts.length) location.hash = "#/vendor/" + rows[pts[0].index].id;
        },
        onHover: (evt, elements) => {
          evt.native.target.style.cursor = elements.length ? "pointer" : "default";
        },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: function (ctx) {
                const r = rows[ctx.dataIndex];
                return [
                  fmtUSD0.format(r.amount_high) + " · " + fmtInt.format(r.count_high) + " records · " + fmtInt.format(r.distinct_committees_high) + " committees",
                  r.amount_medium > 0 ? "+" + fmtUSD0.format(r.amount_medium) + " lower-confidence signal" : "",
                  "Click to see vendor detail",
                ].filter(Boolean);
              },
              title: function (ctx) {
                const r = rows[ctx[0].dataIndex];
                return r.name + " (" + VENDOR_GROUP_LABEL[r.group] + ")";
              },
            },
          }),
        },
        scales: {
          x: { grid: { color: c.grid }, ticks: { color: c.text, callback: (v) => fmtUSD0.format(v) }, border: { display: false } },
          y: { grid: { display: false }, ticks: { color: c.text, autoSkip: false }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      "vendors",
      [
        { key: "name", label: "Vendor", link: (r) => "#/vendor/" + r.id },
        { key: "group", label: "Type" },
        { key: "era", label: "Era" },
        { key: "amount_high", label: "High-confidence $", num: true },
        { key: "count_high", label: "Records", num: true },
        { key: "amount_medium", label: "Lower-confidence $", num: true },
        { key: "website", label: "Website", link: (r) => r.website || null, external: true, render: (r) => (r.website ? "Visit ↗" : "—") },
      ],
      DATA.vendors_overall
        .filter((v) => eraFilter.includes(v.era))
        .map((r) => ({
          id: r.id,
          name: r.name,
          group: VENDOR_GROUP_LABEL[r.group] || r.group,
          era: r.era === "legacy" ? "Legacy (pre-generative AI)" : "Generative",
          amount_high: fmtUSD0.format(r.amount_high),
          count_high: fmtInt.format(r.count_high),
          amount_medium: fmtUSD0.format(r.amount_medium),
          website: r.homepage || "",
        }))
    );

    const legendHtml =
      '<span class="key"><span class="swatch" style="background:' + c.general_purpose + '"></span>General-purpose AI</span>' +
      '<span class="key"><span class="swatch" style="background:' + c.political_specific + '"></span>Campaign-specific AI</span>';
    const holder = document.querySelector('.chart-holder[data-panel="vendors"]');
    if (holder && !holder.previousElementSibling.classList.contains("legend-inline")) {
      const div = document.createElement("div");
      div.className = "legend-inline";
      div.innerHTML = legendHtml;
      holder.parentElement.insertBefore(div, holder);
    }
  }

  // Sums the per-(id, era) rows the pipeline emits into one row per id,
  // for whichever era(s) are currently included. distinct_candidates uses
  // the max across included eras rather than a sum, since summing could
  // double-count a candidate who has both generative- and legacy-era spend
  // in the same category once the toggle includes both.
  function aggregateByEra(rows, idKey, eraFilter) {
    const included = rows.filter((r) => eraFilter.includes(r.era));
    const byId = new Map();
    included.forEach((r) => {
      const id = r[idKey];
      const cur = byId.get(id) || { amount: 0, count: 0, distinct_candidates: 0 };
      cur.amount += r.amount;
      cur.count += r.count;
      cur.distinct_candidates = Math.max(cur.distinct_candidates, r.distinct_candidates || 0);
      byId.set(id, Object.assign({ [idKey]: id }, cur));
    });
    return Array.from(byId.values());
  }

  function renderUseCases() {
    const c = colors();
    const eraFilter = eraFilterList();
    const rows = aggregateByEra(DATA.use_categories, "id", eraFilter).sort((a, b) => b.amount - a.amount);
    const labels = rows.map((r) => catLabel(r.id));
    const data = rows.map((r) => r.amount);

    makeChart("chart-usecases", {
      type: "bar",
      data: { labels, datasets: [{ label: "Spending", data, backgroundColor: c.general_purpose, borderRadius: 4, barThickness: 18 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: function (ctx) {
                const r = rows[ctx.dataIndex];
                return fmtUSD0.format(r.amount) + " · " + fmtInt.format(r.count) + " records · " + fmtInt.format(r.distinct_candidates) + " candidates";
              },
            },
          }),
        },
        scales: {
          x: { grid: { color: c.grid }, ticks: { color: c.text, callback: (v) => fmtUSD0.format(v) }, border: { display: false } },
          y: { grid: { display: false }, ticks: { color: c.text, autoSkip: false }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      "usecases",
      [
        { key: "label", label: "Use case" },
        { key: "amount", label: "$", num: true },
        { key: "count", label: "Records", num: true },
        { key: "candidates", label: "Candidates", num: true },
      ],
      rows.map((r) => ({ label: catLabel(r.id), amount: fmtUSD0.format(r.amount), count: fmtInt.format(r.count), candidates: fmtInt.format(r.distinct_candidates) }))
    );

    const cross = DATA.use_category_by_vendor_group.filter((x) => eraFilter.includes(x.era));
    const catIds = rows.map((r) => r.id);
    const sumCross = (id, group) => cross.filter((x) => x.category === id && x.group === group).reduce((a, x) => a + x.amount, 0);
    const gp = catIds.map((id) => sumCross(id, "general_purpose"));
    const ps = catIds.map((id) => sumCross(id, "political_specific"));

    makeChart("chart-usecases-group", {
      type: "bar",
      data: {
        labels: catIds.map(catLabel),
        datasets: [
          { label: VENDOR_GROUP_LABEL.general_purpose, data: gp, backgroundColor: c.general_purpose, borderRadius: 4, barThickness: 14 },
          { label: VENDOR_GROUP_LABEL.political_specific, data: ps, backgroundColor: c.political_specific, borderRadius: 4, barThickness: 14 },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: Object.assign({ position: "top" }, legendBase()), tooltip: tooltipBase() },
        scales: {
          x: { stacked: true, grid: { color: c.grid }, ticks: { color: c.text, callback: (v) => fmtUSD0.format(v) }, border: { display: false } },
          y: { stacked: true, grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      "usecases-group",
      [
        { key: "label", label: "Use case" },
        { key: "gp", label: "General-purpose $", num: true },
        { key: "ps", label: "Campaign-specific $", num: true },
      ],
      catIds.map((id, i) => ({ label: catLabel(id), gp: fmtUSD0.format(gp[i]), ps: fmtUSD0.format(ps[i]) }))
    );
  }

  function stackedByGroupChart(canvasId, panel, rows, orderKey, order) {
    const c = colors();
    const mode = viewModes.breakdowns;
    const eraFilter = eraFilterList();
    const shown = rows.filter((r) => eraFilter.includes(r.era));
    // Category axis is kept stable across all rows (not just shown eras) so
    // toggling legacy vendors in/out doesn't make a bar disappear entirely --
    // it can still legitimately go to zero if all its spend was legacy-era.
    const cats = order.filter((k) => rows.some((r) => String(r[orderKey]) === k));
    const totals = cats.map((k) => {
      const r = rows.find((rr) => String(rr[orderKey]) === k);
      return r ? r.total_expenditure || 0 : 0;
    });
    const rawGp = cats.map((k) => shown.filter((r) => String(r[orderKey]) === k && r.vendor_group === "general_purpose").reduce((a, r) => a + r.amount, 0));
    const rawPs = cats.map((k) => shown.filter((r) => String(r[orderKey]) === k && r.vendor_group === "political_specific").reduce((a, r) => a + r.amount, 0));
    // Sum across the two vendor-group series (as before the era split), but
    // take the max across any duplicate era rows within one group so
    // toggling legacy vendors in doesn't double-count a candidate counted
    // under both a generative-era and legacy-era row for the same group.
    const countsForGroup = (k, group) => shown.filter((r) => String(r[orderKey]) === k && r.vendor_group === group).reduce((m, r) => Math.max(m, r.distinct_candidates), 0);
    const counts = cats.map((k) => countsForGroup(k, "general_purpose") + countsForGroup(k, "political_specific"));
    const gp = mode === "pct" ? rawGp.map((v, i) => (totals[i] ? (v / totals[i]) * 100 : 0)) : rawGp;
    const ps = mode === "pct" ? rawPs.map((v, i) => (totals[i] ? (v / totals[i]) * 100 : 0)) : rawPs;
    const displayLabels = cats.slice();
    const pctDigits = pctDecimalsFor(Math.max(0, ...gp.map((v, i) => v + ps[i])));
    const fmtAxis = mode === "pct" ? (v) => v.toFixed(pctDigits) + "%" : fmtUSD0.format;
    const fmtVal = mode === "pct" ? (v) => fmtPct(v, pctDigits) : fmtUSD0.format;

    makeChart(canvasId, {
      type: "bar",
      data: {
        labels: displayLabels,
        datasets: [
          { label: VENDOR_GROUP_LABEL.general_purpose, data: gp, backgroundColor: c.general_purpose, borderRadius: 4, barThickness: 28 },
          { label: VENDOR_GROUP_LABEL.political_specific, data: ps, backgroundColor: c.political_specific, borderRadius: 4, barThickness: 28 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: Object.assign({ position: "top" }, legendBase()),
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: (ctx) => ctx.dataset.label + ": " + fmtVal(ctx.parsed.y),
              footer: function (items) {
                const i = items[0].dataIndex;
                const lines = [fmtInt.format(counts[i]) + " distinct candidates"];
                if (mode === "pct") lines.push("of " + fmtUSD0.format(totals[i]) + " total spend");
                return lines;
              },
            },
          }),
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { stacked: true, grid: { color: c.grid }, ticks: { color: c.text, callback: fmtAxis }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      panel,
      [
        { key: "label", label: "Category" },
        { key: "gp", label: mode === "pct" ? "General-purpose %" : "General-purpose $", num: true },
        { key: "ps", label: mode === "pct" ? "Campaign-specific %" : "Campaign-specific $", num: true },
        { key: "candidates", label: "Distinct candidates", num: true },
      ],
      displayLabels.map((label, i) => ({ label, gp: fmtVal(gp[i]), ps: fmtVal(ps[i]), candidates: fmtInt.format(counts[i]) }))
    );
  }

  function renderBreakdowns() {
    stackedByGroupChart("chart-party", "party", DATA.by_party, "cand_party", PARTY_ORDER);
    stackedByGroupChart("chart-incumbency", "incumbency", DATA.by_incumbency, "ici", INCUMBENCY_ORDER);
    stackedByGroupChart("chart-chamber", "chamber", DATA.by_chamber, "office", CHAMBER_ORDER);
    stackedByGroupChart("chart-age", "age", DATA.by_age_bucket, "age_bucket", AGE_ORDER);
  }

  function lineChart(canvasId, panel, cycles, series, colorMap) {
    const c = colors();
    const mode = viewModes.trends;
    // `matches` can hold more than one row for the same cycle once the
    // legacy toggle is on (a generative-era row and a legacy-era row for
    // that cycle) -- amounts sum across them, but total_expenditure is the
    // same denominator repeated on each and must not be summed.
    const valueFor = (matches) => {
      if (!matches.length) return 0;
      const amount = matches.reduce((a, r) => a + r.amount, 0);
      if (mode === "pct") {
        const total = matches[0].total_expenditure;
        return total ? (amount / total) * 100 : 0;
      }
      return amount;
    };
    const datasets = Object.keys(series).map((name) => ({
      label: name,
      data: cycles.map((cy) => valueFor(series[name].filter((r) => Number(r.cycle) === cy))),
      borderColor: colorMap[name] || c.muted,
      backgroundColor: colorMap[name] || c.muted,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      pointBackgroundColor: colorMap[name] || c.muted,
      tension: 0.15,
      fill: false,
    }));
    const pctDigits = pctDecimalsFor(Math.max(0, ...datasets.flatMap((d) => d.data)));
    const fmtAxis = mode === "pct" ? (v) => v.toFixed(pctDigits) + "%" : fmtUSD0.format;
    const fmtVal = mode === "pct" ? (v) => fmtPct(v, pctDigits) : fmtUSD0.format;

    makeChart(canvasId, {
      type: "line",
      data: { labels: cycles.map(String), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: Object.assign({ position: "top" }, legendBase()), tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => ctx.dataset.label + ": " + fmtVal(ctx.parsed.y) } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtAxis }, border: { display: false } },
        },
      },
    });

    const headers = [{ key: "cycle", label: "Cycle" }].concat(Object.keys(series).map((name) => ({ key: name, label: name, num: true })));
    const rows = cycles.map((cy) => {
      const row = { cycle: cy };
      Object.keys(series).forEach((name) => {
        row[name] = fmtVal(valueFor(series[name].filter((rr) => Number(rr.cycle) === cy)));
      });
      return row;
    });
    setPanelTable(panel, headers, rows);
  }

  function renderTrends() {
    const c = colors();
    const cycles = DATA.meta.cycles.slice().sort((a, b) => a - b);
    const eraFilter = eraFilterList();

    lineChart(
      "chart-trend-overall",
      "trend-overall",
      cycles,
      {
        [VENDOR_GROUP_LABEL.general_purpose]: DATA.time_series.filter((r) => r.vendor_group === "general_purpose" && eraFilter.includes(r.era)),
        [VENDOR_GROUP_LABEL.political_specific]: DATA.time_series.filter((r) => r.vendor_group === "political_specific" && eraFilter.includes(r.era)),
      },
      { [VENDOR_GROUP_LABEL.general_purpose]: c.general_purpose, [VENDOR_GROUP_LABEL.political_specific]: c.political_specific }
    );

    const byParty = {};
    PARTY_ORDER.forEach((p) => {
      const rows = DATA.time_series_by_party.filter((r) => r.cand_party === p && eraFilter.includes(r.era));
      if (rows.length) byParty[p] = rows;
    });
    lineChart("chart-trend-party", "trend-party", cycles, byParty, c.party);

    const byInc = {};
    ["Incumbent", "Challenger", "Open seat"].forEach((k) => (byInc[k] = DATA.time_series_by_incumbency.filter((r) => r.ici === k && eraFilter.includes(r.era))));
    lineChart("chart-trend-incumbency", "trend-incumbency", cycles, byInc, c.incumbency);

    const byChamber = {};
    CHAMBER_ORDER.forEach((k) => (byChamber[k] = DATA.time_series_by_chamber.filter((r) => r.office === k && eraFilter.includes(r.era))));
    lineChart("chart-trend-chamber", "trend-chamber", cycles, byChamber, c.chamber);
  }

  function renderTopCommittees() {
    const source = includeLegacy ? DATA.top_committees_all_eras : DATA.top_committees;
    const rows = source.slice(0, 25);
    const container = document.getElementById("table-top-committees");
    container.innerHTML = "";
    container.appendChild(
      buildTable(
        [
          { key: "cmte_name", label: "Committee", render: (r) => r.cmte_name || r.cmte_id },
          { key: "amount", label: "AI-related spending", num: true, render: (r) => fmtUSD0.format(r.amount) },
          { key: "count", label: "Records", num: true, render: (r) => fmtInt.format(r.count) },
          { label: "FEC record", link: (r) => fecCommitteeUrl(r.cmte_id), external: true, render: () => "View ↗" },
        ],
        rows
      )
    );
  }

  // ---- Outside spending (section 6): independent expenditures (Schedule E)
  // and coordinated party expenditures (Schedule F) -- AI-vendor money spent
  // FOR or AGAINST a candidate by a Super PAC or party committee, not the
  // candidate's own campaign. Kept structurally separate from every other
  // section: these numbers should never be added to a candidate's own
  // reported spend above.
  function renderOutsideStats() {
    const eraFilter = eraFilterList();
    const ie = DATA.outside_spending.independent_expenditures || {};
    const pce = DATA.outside_spending.coordinated_party_expenditures || {};
    const ieVendors = (ie.vendor_rows || []).filter((v) => eraFilter.includes(v.era));
    const pceVendors = (pce.vendor_rows || []).filter((v) => eraFilter.includes(v.era));
    const ieAmount = ieVendors.reduce((a, v) => a + v.amount_high, 0);
    const pceAmount = pceVendors.reduce((a, v) => a + v.amount_high, 0);
    const ieCount = ieVendors.reduce((a, v) => a + v.count_high, 0);
    const pceCount = pceVendors.reduce((a, v) => a + v.count_high, 0);
    const tiles = [
      { label: "Independent-expenditure AI spend", value: fmtUSD0.format(ieAmount), sub: fmtInt.format(ieCount) + " matched high-confidence payments, all cycles" },
      { label: "Coordinated party-expenditure AI spend", value: fmtUSD0.format(pceAmount), sub: fmtInt.format(pceCount) + " matched high-confidence payments, all cycles" },
    ];
    const row = document.getElementById("outside-stat-row");
    row.innerHTML = "";
    tiles.forEach((t) => row.appendChild(statTile(t.label, t.value, t.sub)));
  }

  function renderIeVendorsChart() {
    const c = colors();
    const eraFilter = eraFilterList();
    const ie = DATA.outside_spending.independent_expenditures || {};
    const rows = (ie.vendor_rows || []).filter((v) => eraFilter.includes(v.era));
    const labels = rows.map((r) => r.name + (r.era === "legacy" ? " (legacy)" : ""));
    const data = rows.map((r) => r.amount_high);
    const bg = rows.map((r) => (r.group === "general_purpose" ? c.general_purpose : c.political_specific));

    const holder = document.querySelector('.chart-holder[data-panel="ie-vendors"]');
    if (holder) holder.style.height = Math.max(220, rows.length * 32) + "px";

    makeChart("chart-ie-vendors", {
      type: "bar",
      data: { labels, datasets: [{ label: "AI-related independent expenditures", data, backgroundColor: bg, borderRadius: 4, barThickness: 18 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: (ctx) => {
                const r = rows[ctx.dataIndex];
                return fmtUSD0.format(r.amount_high) + " · " + fmtInt.format(r.count_high) + " records";
              },
            },
          }),
        },
        scales: {
          x: { grid: { color: c.grid }, ticks: { color: c.text, callback: (v) => fmtUSD0.format(v) }, border: { display: false } },
          y: { grid: { display: false }, ticks: { color: c.text, autoSkip: false }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      "ie-vendors",
      [
        { key: "name", label: "Vendor", link: (r) => "#/vendor/" + r.id },
        { key: "group", label: "Type" },
        { key: "era", label: "Era" },
        { key: "amount_high", label: "High-confidence $", num: true },
        { key: "count_high", label: "Records", num: true },
      ],
      rows.map((r) => ({
        id: r.id,
        name: r.name,
        group: VENDOR_GROUP_LABEL[r.group] || r.group,
        era: r.era === "legacy" ? "Legacy (pre-generative AI)" : "Generative",
        amount_high: fmtUSD0.format(r.amount_high),
        count_high: fmtInt.format(r.count_high),
      }))
    );
  }

  function renderIeSpenders() {
    const ie = DATA.outside_spending.independent_expenditures || {};
    const rows = sortRows(ie.top_spenders || [], sortState.ieSpenders);
    const headers = withSort(
      "ieSpenders",
      [
        { label: "Spender", sortKey: "spender_name", render: (r) => r.spender_name },
        { label: "Type", sortKey: "cmte_type", render: (r) => r.cmte_type },
        { label: "AI-related IE spend", sortKey: "amount", num: true, render: (r) => fmtUSD0.format(r.amount) },
        { label: "Records", sortKey: "count", num: true, render: (r) => fmtInt.format(r.count) },
        { label: "Spender's total IE spend", sortKey: "total_ie_spend", num: true, render: (r) => (r.total_ie_spend ? fmtUSD0.format(r.total_ie_spend) : "—") },
        { label: "% of IE budget", sortKey: "pct_ai", num: true, render: (r) => fmtPct(r.pct_ai, 2) },
        { label: "FEC record", sortKey: null, link: (r) => fecCommitteeUrl(r.spender_id), external: true, render: () => "View ↗" },
      ],
      renderIeSpenders
    );
    const container = document.getElementById("table-ie-spenders");
    container.innerHTML = "";
    container.appendChild(buildTable(headers, rows, { sort: sortState.ieSpenders }));
  }

  function renderIeRecords() {
    const ie = DATA.outside_spending.independent_expenditures || {};
    const rows = sortRows(ie.records || [], sortState.ieRecords);
    const headers = withSort(
      "ieRecords",
      [
        { label: "Cycle", sortKey: "cycle", num: true, render: (r) => r.cycle },
        { label: "Candidate", sortKey: "cand_name", render: (r) => r.cand_name || "—", link: (r) => (r.cand_id ? "#/candidate/" + r.cand_id : null) },
        { label: "Support/Oppose", sortKey: "support_oppose", render: (r) => r.support_oppose },
        { label: "Spender", sortKey: "spender_name", render: (r) => r.spender_name },
        { label: "Vendor", sortKey: "vendor_name", cell: (r) => vendorLinksCell([r.vendor_id]) },
        { label: "Confidence", sortKey: "confidence", render: (r) => r.confidence },
        { label: "Amount", sortKey: "transaction_amt", num: true, render: (r) => fmtUSD0.format(r.transaction_amt) },
        { label: "Purpose", sortKey: null, render: (r) => r.purpose || "—" },
        { label: "FEC record", sortKey: null, link: (r) => fecCommitteeUrl(r.spender_id), external: true, render: () => "View ↗" },
      ],
      renderIeRecords
    );
    const container = document.getElementById("table-ie-records");
    container.innerHTML = "";
    container.appendChild(buildTable(headers, rows, { sort: sortState.ieRecords }));
  }

  function renderPceRecords() {
    const pce = DATA.outside_spending.coordinated_party_expenditures || {};
    const rows = sortRows(pce.records || [], sortState.pceRecords);
    const headers = withSort(
      "pceRecords",
      [
        { label: "Cycle", sortKey: "cycle", num: true, render: (r) => r.cycle },
        { label: "Party committee", sortKey: "cmte_name", render: (r) => r.cmte_name || r.cmte_id },
        { label: "Candidate benefited", sortKey: "cand_name", render: (r) => r.cand_name || "—", link: (r) => (r.cand_id ? "#/candidate/" + r.cand_id : null) },
        { label: "Vendor", sortKey: "vendor_name", cell: (r) => vendorLinksCell([r.vendor_id]) },
        { label: "Confidence", sortKey: "confidence", render: (r) => r.confidence },
        { label: "Amount", sortKey: "transaction_amt", num: true, render: (r) => fmtUSD0.format(r.transaction_amt) },
        { label: "FEC record", sortKey: null, link: (r) => fecCommitteeUrl(r.cmte_id), external: true, render: () => "View ↗" },
      ],
      renderPceRecords
    );
    const container = document.getElementById("table-pce-records");
    container.innerHTML = "";
    container.appendChild(buildTable(headers, rows, { sort: sortState.pceRecords }));
  }

  function renderOutsideSpending() {
    renderOutsideStats();
    renderIeVendorsChart();
    renderIeSpenders();
    renderIeRecords();
    renderPceRecords();
  }

  function renderMethodology() {
    const sources = document.getElementById("sources-list");
    sources.innerHTML = "";
    DATA.meta.sources.forEach((s) => sources.appendChild(el("li", { text: s })));
    const notes = document.getElementById("notes-list");
    notes.innerHTML = "";
    DATA.meta.methodology_notes.forEach((s) => notes.appendChild(el("li", { text: s })));
  }

  // ---- Leaderboards (section 5) ----
  function populateLeaderboardFilters() {
    const cycleSel = document.getElementById("filter-cycle");
    DATA.meta.cycles.forEach((cy) => cycleSel.appendChild(el("option", { text: String(cy), attrs: { value: String(cy) } })));
    const catSel = document.getElementById("filter-category");
    Object.keys(CATEGORY_LABELS).forEach((id) => catSel.appendChild(el("option", { text: catLabel(id), attrs: { value: id } })));
    cycleSel.addEventListener("change", () => {
      filterState.cycle = cycleSel.value;
      renderLeaderboards();
    });
    catSel.addEventListener("change", () => {
      filterState.category = catSel.value;
      renderLeaderboards();
    });
  }

  // Resolves each entity to the amount/count/pct/category/vendor fields for
  // the current legacy-vendor toggle state: the "_ex_legacy" variants by
  // default, or the all-eras fields when the toggle includes legacy vendors.
  function resolveEntityEra(e) {
    if (includeLegacy) {
      return Object.assign({ _isCandidate: e.entity_type === "candidate" }, e);
    }
    return Object.assign({}, e, {
      _isCandidate: e.entity_type === "candidate",
      ai_amount_high: e.ai_amount_high_ex_legacy,
      ai_count_high: e.ai_count_high_ex_legacy,
      pct_ai: e.pct_ai_ex_legacy,
      use_categories: e.use_categories_ex_legacy,
      vendor_ids: e.vendor_ids_ex_legacy,
    });
  }

  function filteredEntities() {
    return DATA.entities
      .map(resolveEntityEra)
      .filter((e) => {
        if (e.ai_amount_high <= 0) return false;
        if (filterState.cycle !== "all" && String(e.cycle) !== filterState.cycle) return false;
        if (filterState.category !== "all" && e.use_categories.indexOf(filterState.category) === -1) return false;
        return true;
      });
  }

  function entityLeaderboardHeaders(kind) {
    const sort = sortState[kind];
    const onSort = (key) => {
      if (sort.key === key) sort.dir = sort.dir === "asc" ? "desc" : "asc";
      else {
        sort.key = key;
        sort.dir = "desc";
      }
      renderLeaderboards();
    };
    return [
      { label: "Name", sortKey: "entity_name", onSort, link: (r) => (r._isCandidate ? "#/candidate/" + r.entity_id : null), render: (r) => r.entity_name },
      { label: "Type", sortKey: "entity_type", onSort, render: (r) => (r.entity_type === "candidate" ? "Candidate" : "Committee/PAC") },
      { label: "Party", sortKey: "cand_party", onSort, render: (r) => r.cand_party },
      { label: "Cycle", sortKey: "cycle", onSort, num: true, render: (r) => r.cycle },
      { label: "AI spend", sortKey: "ai_amount_high", onSort, num: true, render: (r) => fmtUSD0.format(r.ai_amount_high) },
      { label: "Total spend", sortKey: "total_expenditure", onSort, num: true, render: (r) => (r.total_expenditure ? fmtUSD0.format(r.total_expenditure) : "—") },
      { label: "% AI", sortKey: "pct_ai", onSort, num: true, render: (r) => fmtPct(r.pct_ai, 2) },
      { label: "Functional area", sortKey: null, render: (r) => r.use_categories.map(catLabel).join(", ") },
      { label: "Vendors", sortKey: null, cell: (r) => vendorLinksCell(r.vendor_ids) },
      {
        label: "FEC record",
        sortKey: null,
        link: (r) => (r.entity_type === "candidate" ? fecCandidateUrl(r.entity_id) : fecCommitteeUrl(r.entity_id)),
        external: true,
        render: () => "View ↗",
      },
    ];
  }

  function sortRows(rows, state) {
    const { key, dir } = state;
    const mult = dir === "asc" ? 1 : -1;
    return rows.slice().sort((a, b) => {
      let av = a[key], bv = b[key];
      if (av === null || av === undefined) av = -Infinity;
      if (bv === null || bv === undefined) bv = -Infinity;
      if (typeof av === "string") return av.localeCompare(bv) * mult;
      return (av - bv) * mult;
    });
  }

  // Wires header.onSort for every header with a sortKey, toggling
  // direction on repeat clicks and re-running `renderFn` on change --
  // shared by every sortable table outside the entity leaderboards.
  function withSort(kind, headers, renderFn) {
    const sort = sortState[kind];
    const onSort = (key) => {
      if (sort.key === key) sort.dir = sort.dir === "asc" ? "desc" : "asc";
      else {
        sort.key = key;
        sort.dir = "desc";
      }
      renderFn();
    };
    return headers.map((h) => (h.sortKey ? Object.assign({}, h, { onSort }) : h));
  }

  function renderLeaderboards() {
    const rows = filteredEntities();

    const dollarRows = sortRows(rows, sortState.dollar).slice(0, 40);
    const dollarContainer = document.getElementById("table-leaderboard-dollar");
    dollarContainer.innerHTML = "";
    dollarContainer.appendChild(buildTable(entityLeaderboardHeaders("dollar"), dollarRows, { sort: sortState.dollar }));

    const pctEligible = rows.filter((r) => r.total_expenditure >= MIN_TOTAL_FOR_PCT_TABLE && r.pct_ai !== null);
    const pctRows = sortRows(pctEligible, sortState.pct).slice(0, 40);
    const pctContainer = document.getElementById("table-leaderboard-pct");
    pctContainer.innerHTML = "";
    pctContainer.appendChild(buildTable(entityLeaderboardHeaders("pct"), pctRows, { sort: sortState.pct }));
  }

  // ---- Detail views (hash-routed) ----
  function showMainView() {
    document.getElementById("main-view").hidden = false;
    document.getElementById("detail-view").hidden = true;
  }

  function showDetailView() {
    document.getElementById("main-view").hidden = true;
    document.getElementById("detail-view").hidden = false;
    window.scrollTo(0, 0);
  }

  function detailCard(titleText, canvasId, noteText) {
    const card = el("div", { className: "card" });
    card.appendChild(el("h3", { text: titleText }));
    if (noteText) card.appendChild(el("p", { className: "note", text: noteText }));
    card.appendChild(el("div", { className: "chart-holder", children: [el("canvas", { id: canvasId })] }));
    return card;
  }

  function renderVendorDetail(id) {
    const view = document.getElementById("detail-view");
    view.innerHTML = "";
    const v = DATA.vendors_detail[id];
    const overall = DATA.vendors_overall.find((x) => x.id === id);
    view.appendChild(backLink());
    if (!v) {
      view.appendChild(el("p", { text: "Vendor not found." }));
      return;
    }
    const c = colors();

    const header = el("div", { className: "detail-header" });
    const h2 = el("h2", { text: v.name });
    h2.appendChild(el("span", { className: "pill", text: VENDOR_GROUP_LABEL[v.group] }));
    if (v.era === "legacy") h2.appendChild(el("span", { className: "pill pill-legacy", text: "Legacy (pre-generative AI)" }));
    header.appendChild(h2);
    if (v.homepage) {
      header.appendChild(el("a", { className: "entity-link", href: v.homepage, text: "Vendor website ↗", attrs: { target: "_blank", rel: "noopener" } }));
    }
    view.appendChild(header);
    view.appendChild(el("p", { className: "lede", text: "All figures are high-confidence text matches to this vendor's name/product across FEC disbursement records. See methodology for what \"high confidence\" means and its limits." }));
    if (v.era === "legacy") {
      view.appendChild(
        el("p", {
          className: "callout",
          text: "This vendor predates the generative-AI wave (see methodology). It's excluded from the site's charts and tables by default -- this page always shows its full history regardless of that toggle.",
        })
      );
    }

    const stats = el("div", { className: "detail-stat-row" });
    stats.appendChild(statTile("Total high-confidence spending", fmtUSD0.format(v.amount_high), fmtInt.format(v.count_high) + " disbursement records"));
    if (overall) stats.appendChild(statTile("Committees paying this vendor", fmtInt.format(overall.distinct_committees_high)));
    if (overall && overall.amount_medium > 0) {
      stats.appendChild(statTile("Lower-confidence signal (excluded above)", fmtUSD0.format(overall.amount_medium), "ambiguous word matches -- see methodology"));
    }
    view.appendChild(stats);

    const grid = el("div", { className: "card-grid" });
    grid.appendChild(detailCard("Spending over time", "detail-chart-ts"));
    grid.appendChild(detailCard("Top candidates using " + v.name, "detail-chart-cand", "Click a bar to open that candidate's page."));
    view.appendChild(grid);

    const grid2 = el("div", { className: "card-grid" });
    grid2.appendChild(detailCard("By party (House/Senate candidates)", "detail-chart-party"));
    grid2.appendChild(detailCard("By incumbency status", "detail-chart-ici"));
    view.appendChild(grid2);

    const cmteCard = el("div", { className: "card" });
    cmteCard.appendChild(el("h3", { text: "Top committees paying " + v.name }));
    cmteCard.appendChild(
      buildTable(
        [
          { label: "Committee", render: (r) => r.cmte_name || r.cmte_id },
          { label: "Amount", num: true, render: (r) => fmtUSD0.format(r.amount) },
          { label: "Records", num: true, render: (r) => fmtInt.format(r.count) },
          { label: "FEC record", link: (r) => fecCommitteeUrl(r.cmte_id), external: true, render: () => "View ↗" },
        ],
        v.top_committees
      )
    );
    view.appendChild(el("div", { className: "card-grid single", children: [cmteCard] }));

    // charts
    const cycles = v.time_series.map((r) => r.cycle).sort((a, b) => a - b);
    makeChart("detail-chart-ts", {
      type: "line",
      data: {
        labels: cycles.map(String),
        datasets: [
          {
            label: v.name,
            data: cycles.map((cy) => (v.time_series.find((r) => r.cycle === cy) || {}).amount || 0),
            borderColor: c.general_purpose,
            backgroundColor: c.general_purpose,
            borderWidth: 2,
            pointRadius: 4,
            tension: 0.15,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => fmtUSD0.format(ctx.parsed.y) } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
        },
      },
    });

    const byCand = v.by_candidate.slice(0, 15);
    makeChart("detail-chart-cand", {
      type: "bar",
      data: { labels: byCand.map((r) => r.cand_name), datasets: [{ data: byCand.map((r) => r.amount), backgroundColor: c.general_purpose, borderRadius: 4, barThickness: 14 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        onClick: (evt, elements, chart) => {
          const pts = chart.getElementsAtEventForMode(evt, "nearest", { intersect: true }, false);
          if (pts.length) location.hash = "#/candidate/" + byCand[pts[0].index].cand_id;
        },
        plugins: { legend: { display: false }, tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => fmtUSD0.format(ctx.parsed.x) } }) },
        scales: {
          x: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
          y: { grid: { display: false }, ticks: { color: c.text, autoSkip: false }, border: { display: false } },
        },
      },
    });

    makeChart("detail-chart-party", {
      type: "bar",
      data: {
        labels: v.by_party.map((r) => r.cand_party),
        datasets: [{ data: v.by_party.map((r) => r.amount), backgroundColor: v.by_party.map((r) => c.party[r.cand_party] || c.muted), borderRadius: 4, barThickness: 24 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => fmtUSD0.format(ctx.parsed.y) } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
        },
      },
    });

    makeChart("detail-chart-ici", {
      type: "bar",
      data: {
        labels: v.by_incumbency.map((r) => r.ici),
        datasets: [{ data: v.by_incumbency.map((r) => r.amount), backgroundColor: v.by_incumbency.map((r) => c.incumbency[r.ici] || c.muted), borderRadius: 4, barThickness: 24 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => fmtUSD0.format(ctx.parsed.y) } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
        },
      },
    });
  }

  function renderCandidateDetail(id) {
    const view = document.getElementById("detail-view");
    view.innerHTML = "";
    const cd = DATA.candidates_detail[id];
    view.appendChild(backLink());
    if (!cd) {
      view.appendChild(el("p", { text: "Candidate not found in the AI-spend dataset." }));
      return;
    }
    const c = colors();

    const header = el("div", { className: "detail-header" });
    const h2 = el("h2", { text: cd.name });
    h2.appendChild(el("span", { className: "pill", text: cd.party }));
    h2.appendChild(el("span", { className: "pill", text: cd.office }));
    header.appendChild(h2);
    header.appendChild(el("a", { className: "entity-link", href: fecCandidateUrl(cd.id), text: "FEC record ↗", attrs: { target: "_blank", rel: "noopener" } }));
    view.appendChild(header);
    const raceLink = el("a", { href: "#/race/" + cd.race_id, className: "entity-link", text: cd.office + " — " + cd.state + (cd.district ? "-" + cd.district : "") + " (see race)" });
    view.appendChild(el("p", { className: "lede", children: [raceLink] }));

    const stats = el("div", { className: "detail-stat-row" });
    stats.appendChild(statTile("Total AI spend (high confidence)", fmtUSD0.format(cd.amount_high), fmtInt.format(cd.count_high) + " records, all cycles"));
    stats.appendChild(statTile("Total reported expenditure", cd.total_expenditure ? fmtUSD0.format(cd.total_expenditure) : "—"));
    stats.appendChild(statTile("AI as % of total spend", fmtPct(cd.pct_ai, 3)));
    view.appendChild(stats);

    const ieOut = cd.outside_independent_expenditure;
    const pceOut = cd.outside_coordinated_party_expenditure;
    if (ieOut || pceOut) {
      const lines = [];
      if (ieOut && ieOut.support_amount > 0) lines.push(fmtUSD0.format(ieOut.support_amount) + " in independent expenditures supporting this candidate");
      if (ieOut && ieOut.oppose_amount > 0) lines.push(fmtUSD0.format(ieOut.oppose_amount) + " in independent expenditures opposing this candidate");
      if (pceOut && pceOut.amount > 0) lines.push(fmtUSD0.format(pceOut.amount) + " in party-coordinated spending on this candidate's behalf");
      const outsideVendorIds = Array.from(new Set([...(ieOut ? ieOut.vendor_ids : []), ...(pceOut ? pceOut.vendor_ids : [])]));
      const callout = el("div", { className: "callout" });
      const strong = el("strong", { text: "Outside AI-related spending (not this candidate's own committee): " });
      callout.appendChild(strong);
      callout.appendChild(document.createTextNode(lines.join("; ") + ". Vendor(s): "));
      callout.appendChild(vendorLinksCell(outsideVendorIds));
      callout.appendChild(document.createTextNode(" — see "));
      const jumpLink = el("a", { href: "#outside-spending", className: "entity-link", text: "outside spending" });
      jumpLink.addEventListener("click", (e) => {
        e.preventDefault();
        history.pushState(null, "", "#outside-spending");
        showMainView();
        document.getElementById("outside-spending").scrollIntoView({ behavior: "smooth" });
      });
      callout.appendChild(jumpLink);
      callout.appendChild(document.createTextNode(" section for detail."));
      view.appendChild(callout);
    }

    const grid = el("div", { className: "card-grid" });
    grid.appendChild(detailCard("Spending over time", "detail-chart-cycle"));
    grid.appendChild(detailCard("By vendor", "detail-chart-vendor"));
    view.appendChild(grid);

    const catCard = el("div", { className: "card" });
    catCard.appendChild(el("h3", { text: "By stated use / functional area" }));
    catCard.appendChild(
      buildTable(
        [
          { label: "Area", render: (r) => catLabel(r.id) },
          { label: "Amount", num: true, render: (r) => fmtUSD0.format(r.amount) },
          { label: "Records", num: true, render: (r) => fmtInt.format(r.count) },
        ],
        cd.by_category
      )
    );
    view.appendChild(el("div", { className: "card-grid single", children: [catCard] }));

    makeChart("detail-chart-cycle", {
      type: "line",
      data: {
        labels: cd.by_cycle.map((r) => String(r.cycle)),
        datasets: [
          { label: "AI spend", data: cd.by_cycle.map((r) => r.amount), borderColor: c.general_purpose, backgroundColor: c.general_purpose, borderWidth: 2, pointRadius: 4, tension: 0.15 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: (ctx) => fmtUSD0.format(ctx.parsed.y),
              footer: (items) => {
                const r = cd.by_cycle[items[0].dataIndex];
                return r.pct_ai !== null ? fmtPct(r.pct_ai, 3) + " of that cycle's spend" : "";
              },
            },
          }),
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
        },
      },
    });

    makeChart("detail-chart-vendor", {
      type: "bar",
      data: {
        labels: cd.by_vendor.map((r) => r.vendor_name + (r.era === "legacy" ? " (legacy)" : "")),
        datasets: [{ data: cd.by_vendor.map((r) => r.amount), backgroundColor: c.general_purpose, borderRadius: 4, barThickness: 16 }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        onClick: (evt, elements, chart) => {
          const pts = chart.getElementsAtEventForMode(evt, "nearest", { intersect: true }, false);
          if (pts.length) location.hash = "#/vendor/" + cd.by_vendor[pts[0].index].vendor_id;
        },
        plugins: { legend: { display: false }, tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => fmtUSD0.format(ctx.parsed.x) } }) },
        scales: {
          x: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
          y: { grid: { display: false }, ticks: { color: c.text, autoSkip: false }, border: { display: false } },
        },
      },
    });
  }

  function renderRaceDetail(id) {
    const view = document.getElementById("detail-view");
    view.innerHTML = "";
    const race = DATA.races[id];
    view.appendChild(backLink());
    if (!race) {
      view.appendChild(el("p", { text: "Race not found in the AI-spend dataset." }));
      return;
    }
    const header = el("div", { className: "detail-header" });
    header.appendChild(el("h2", { text: race.office + " — " + race.state + (race.district ? "-" + race.district : "") }));
    view.appendChild(header);
    view.appendChild(el("p", { className: "lede", text: "Candidates in this seat with at least one high-confidence AI-vendor disbursement, any cycle. This is not every candidate who ran — only those showing AI spend in this dataset." }));

    const card = el("div", { className: "card" });
    card.appendChild(
      buildTable(
        [
          { label: "Candidate", link: (r) => "#/candidate/" + r.cand_id, render: (r) => r.name },
          { label: "Party", render: (r) => r.party },
          { label: "Cycles", render: (r) => r.cycles.join(", ") },
          { label: "AI spend", num: true, render: (r) => fmtUSD0.format(r.amount_high) },
          { label: "% of total spend", num: true, render: (r) => fmtPct(r.pct_ai, 3) },
          { label: "FEC record", link: (r) => fecCandidateUrl(r.cand_id), external: true, render: () => "View ↗" },
        ],
        race.candidates
      )
    );
    view.appendChild(el("div", { className: "card-grid single", children: [card] }));
  }

  function parseHash() {
    const h = location.hash.replace(/^#\/?/, "");
    if (!h) return null;
    const parts = h.split("/");
    if (parts.length < 2) return null;
    return { type: parts[0], id: decodeURIComponent(parts.slice(1).join("/")) };
  }

  function router() {
    const parsed = parseHash();
    if (!parsed) {
      showMainView();
      return;
    }
    showDetailView();
    if (parsed.type === "vendor") renderVendorDetail(parsed.id);
    else if (parsed.type === "candidate") renderCandidateDetail(parsed.id);
    else if (parsed.type === "race") renderRaceDetail(parsed.id);
    else {
      document.getElementById("detail-view").innerHTML = "";
      document.getElementById("detail-view").appendChild(backLink());
    }
  }

  function renderAll() {
    renderStats();
    renderVendors();
    renderUseCases();
    renderBreakdowns();
    renderTrends();
    renderTopCommittees();
    renderLeaderboards();
    renderOutsideSpending();
    renderMethodology();
    router();
  }

  fetch("data/dashboard.json")
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((json) => {
      DATA = json;
      vendorNameById = {};
      vendorHomepageById = {};
      vendorEraById = {};
      DATA.vendors_overall.forEach((v) => {
        vendorNameById[v.id] = v.name;
        vendorEraById[v.id] = v.era;
        if (v.homepage) vendorHomepageById[v.id] = v.homepage;
      });
      wireToggles();
      wireLegacyToggle();
      wireViewModeToggles();
      populateLeaderboardFilters();
      renderAll();
      window.addEventListener("hashchange", router);
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
    })
    .catch((err) => {
      document.getElementById("meta-line").textContent = "Could not load dataset (" + err.message + ").";
      console.error(err);
    });
})();
