(function () {
  "use strict";

  const fmtUSD0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const fmtUSD2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  const fmtInt = new Intl.NumberFormat("en-US");
  const fmtPct = (v, digits) => (v === null || v === undefined ? "—" : v.toFixed(digits === undefined ? 2 : digits) + "%");
  // Democratic-vs-Republican spending ratio for one vendor: `dem_rep_ratio`
  // is null whenever either side is exactly zero (see party_split() in
  // build_dataset.py), so those cases are spelled out instead of showing
  // an infinite or zero ratio.
  function fmtPartyRatio(r) {
    const ratio = r.dem_rep_ratio;
    if (ratio !== null && ratio !== undefined) {
      return ratio >= 1 ? ratio.toFixed(2) + "× D" : (1 / ratio).toFixed(2) + "× R";
    }
    if (r.dem_amount > 0) return "All D";
    if (r.rep_amount > 0) return "All R";
    return "—";
  }
  // Numeric proxy for sorting the same D:R ratio buildPartyRatio renders as
  // text: a finite ratio sorts on its own value, "All D" (no Republican
  // spending at all) sorts above every finite ratio, "All R" (no Democratic
  // spending) sorts below every finite ratio, and no data sorts last via
  // sortRows' existing null handling.
  function partyRatioSortValue(r) {
    if (r.dem_rep_ratio !== null && r.dem_rep_ratio !== undefined) return r.dem_rep_ratio;
    if (r.dem_amount > 0) return Infinity;
    if (r.rep_amount > 0) return 0;
    return null;
  }
  // FEC dates come through as "MM/DD/YYYY" strings, which sort wrong as
  // plain text (e.g. "01/09/2026" < "12/12/2025" alphabetically). Rows that
  // need a sortable date carry this alongside the display string.
  function mdySortValue(str) {
    if (!str) return null;
    const parts = str.split("/");
    if (parts.length !== 3) return null;
    const [m, d, y] = parts.map(Number);
    if (!m || !d || !y) return null;
    return y * 10000 + m * 100 + d;
  }
  // A small colored badge for a medium-confidence (ambiguous-word) match,
  // vs. plain muted text for high confidence -- so a reader scanning the
  // Confidence column doesn't have to read every cell's text closely.
  function confidencePill(conf) {
    if (conf === "medium") return el("span", { className: "pill pill-medium-confidence", text: "Lower confidence" });
    return el("span", { className: "text-muted", text: "High confidence" });
  }
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

  // ---- sequential color scale for the vendor co-occurrence heatmap:
  // interpolates through the site's existing single-hue blue ramp
  // (page background at t=0 so "no overlap" reads as blank, then the same
  // --seq-250..--seq-650 steps already used for the age-bucket chart) so
  // no new palette is introduced for one chart. ----
  function hexToRgb(hex) {
    const h = hex.replace("#", "");
    const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    const v = parseInt(n, 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  function seqScale(t) {
    const stops = [cssVar("--page-plane"), cssVar("--seq-250"), cssVar("--seq-350"), cssVar("--seq-450"), cssVar("--seq-550"), cssVar("--seq-650")].map(hexToRgb);
    const clamped = Math.max(0, Math.min(1, t));
    const pos = clamped * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(pos));
    const f = pos - i;
    const [r1, g1, b1] = stops[i];
    const [r2, g2, b2] = stops[i + 1];
    const rgb = [Math.round(r1 + (r2 - r1) * f), Math.round(g1 + (g2 - g1) * f), Math.round(b1 + (b2 - b1) * f)];
    // Perceptual luminance decides label color: dark text on the light
    // early stops, white text once the fill gets dark enough to need it.
    const luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
    return { bg: "rgb(" + rgb.join(",") + ")", fg: luminance > 0.6 ? cssVar("--text-primary") : "#fff" };
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
  const MAX_DETAIL_RECORDS = 300; // must match MAX_DETAIL_RECORDS in pipeline/build_dataset.py

  let DATA = null;
  let vendorNameById = {};
  let vendorHomepageById = {};
  let vendorEraById = {};
  const stateVendorEraById = {}; // stateId -> {vendorId: era}
  const MAX_DETAIL_RECORDS_MA = 300; // must match MAX_DETAIL_RECORDS in pipeline/build_dataset_ma.py and pipeline/lib/build_state_dataset.py
  let includeLegacy = false;
  let searchIndex = [];
  const stateSearchIndex = {}; // stateId -> []
  let searchFilterType = "all";

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
  // A single vendor, always linked internally to its detail page (unlike
  // vendorLinksCell, which prefers an external homepage when known) --
  // for a records table's Vendor column, where clicking through to compare
  // vendors matters more than a quick homepage visit. Still tags a legacy
  // vendor, since a candidate's own records mix eras the toggle never
  // filters (that page always shows full history).
  function vendorNameCell(vendorId, vendorName) {
    const frag = document.createDocumentFragment();
    frag.appendChild(el("a", { className: "entity-link", href: "#/vendor/" + vendorId, text: vendorName }));
    if (vendorEraById[vendorId] === "legacy") {
      frag.appendChild(el("span", { className: "pill pill-legacy", text: "legacy" }));
    }
    return frag;
  }
  // Same idea as vendorLinksCell, but always links internally to a state
  // tab's own vendor detail page (#/<stateId>/vendor/<id>) rather than
  // preferring an external homepage -- these are the parallel arrays a
  // matched state record carries (vendor_ids/vendor_names), not a single id.
  function stateVendorLinksCell(stateId, vendorIds, vendorNames) {
    const frag = document.createDocumentFragment();
    const eraById = stateVendorEraById[stateId] || {};
    vendorIds.forEach((vid, i) => {
      if (i > 0) frag.appendChild(document.createTextNode(", "));
      frag.appendChild(el("a", { className: "entity-link", href: "#/" + stateId + "/vendor/" + vid, text: vendorNames[i] || vid }));
      if (eraById[vid] === "legacy") {
        frag.appendChild(el("span", { className: "pill pill-legacy", text: "legacy" }));
      }
    });
    return frag;
  }
  const chartInstances = {};
  const viewModes = { breakdowns: "dollar", trends: "dollar", stateTrends: "dollar" };
  const sortState = {
    vendors: { key: "amount_high", dir: "desc" },
    dollar: { key: "ai_amount_high", dir: "desc" },
    pct: { key: "pct_ai", dir: "desc" },
    ieSpenders: { key: "amount", dir: "desc" },
    ieRecords: { key: "transaction_amt", dir: "desc" },
    pceRecords: { key: "transaction_amt", dir: "desc" },
    vendorCommittees: { key: "amount_high", dir: "desc" },
    vendorRecords: { key: "amount", dir: "desc" },
    candidateRecords: { key: "amount", dir: "desc" },
    stateVendorFilers: { key: "amount", dir: "desc" },
    stateVendorRecords: { key: "amount", dir: "desc" },
    stateCandidateRecords: { key: "amount", dir: "desc" },
    compare: { key: "volume", dir: "desc" },
  };
  // Off by default site-wide (persists across vendor pages, like the legacy
  // toggle): the "Top committees" and "Individual disbursements" tables on
  // a vendor detail page only show ambiguous-word (medium-confidence)
  // matches when this is on.
  let vendorDetailShowLowConf = false;
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
      const th = el("th", { text: h.label, attrs: h.title ? { title: h.title } : undefined });
      if (h.num) th.classList.add("num");
      if (h.sortKey) {
        th.classList.add("sortable");
        if (opts.sort && opts.sort.key === h.sortKey) {
          th.appendChild(el("span", { className: "sort-arrow", text: opts.sort.dir === "asc" ? "↑" : "↓" }));
        }
        const onSort = h.onSort || opts.onSort;
        th.addEventListener("click", () => onSort && onSort(h.sortKey));
      }
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    rows.forEach((r) => {
      const tr = el("tr");
      if (opts.rowClass) {
        const cls = opts.rowClass(r);
        if (cls) tr.className = cls;
      }
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

  function setPanelTable(panel, headers, rows, opts) {
    const holder = document.querySelector('.table-holder[data-panel="' + panel + '"]');
    if (!holder) return;
    holder.innerHTML = "";
    holder.appendChild(buildTable(headers, rows, opts));
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
      // Shared toggle, every tab: re-render whichever state or Compare is
      // currently on screen so it shows the new setting immediately rather
      // than stale content from before the toggle changed. (Only the
      // active state has live DOM in the shared #state-view container --
      // a different state's cached data, if any, has nothing to re-render.)
      if (STATE_IDS.indexOf(currentDataset) !== -1 && STATE_DATA[currentDataset]) renderStateView(currentDataset);
      if (currentDataset === "compare" && STATES_DATA) renderCompareView();
      if (currentDataset === "states" && STATES_DATA) renderStatesView();
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

  // Shared by both tabs' header meta-line, which is one DOM element (not
  // rebuilt per dataset) -- whichever tab is active decides what it says,
  // so switching tabs must actively overwrite it rather than leaving
  // Federal's text showing while Massachusetts is on screen.
  function metaLineTextFederal() {
    const meta = DATA.meta;
    return "Data generated " + new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) + " UTC · cycles: " + meta.cycles.join(", ");
  }
  function metaLineTextState(stateId) {
    const meta = STATE_DATA[stateId].meta;
    return (
      "Data generated " +
      new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) +
      " UTC · covers " +
      meta.date_range.start +
      " through " +
      (meta.date_range.end || "present")
    );
  }
  function metaLineTextCompare() {
    const fedStr = "Federal: generated " + new Date(DATA.meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) + " UTC";
    if (!STATES_DATA) return fedStr + " · States: loading…";
    const statesStr = "States: generated " + new Date(STATES_DATA.meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) + " UTC";
    return fedStr + " · " + statesStr;
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

    if (currentDataset !== "ma") document.getElementById("meta-line").textContent = metaLineTextFederal();
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

    const vendorTableRows = sortRows(
      DATA.vendors_overall
        .filter((v) => eraFilter.includes(v.era))
        .map((r) =>
          Object.assign({}, r, {
            group_label: VENDOR_GROUP_LABEL[r.group] || r.group,
            era_label: r.era === "legacy" ? "Legacy (pre-generative AI)" : "Generative",
            party_ratio_value: partyRatioSortValue(r),
          })
        ),
      sortState.vendors
    );
    const vendorHeaders = withSort(
      "vendors",
      [
        { label: "Vendor", sortKey: "name", link: (r) => "#/vendor/" + r.id, render: (r) => r.name },
        { label: "Type", sortKey: "group_label", render: (r) => r.group_label },
        { label: "Era", sortKey: "era_label", render: (r) => r.era_label },
        { label: "High-confidence $", sortKey: "amount_high", num: true, render: (r) => fmtUSD0.format(r.amount_high) },
        { label: "Records", sortKey: "count_high", num: true, render: (r) => fmtInt.format(r.count_high) },
        { label: "Lower-confidence $", sortKey: "amount_medium", num: true, render: (r) => fmtUSD0.format(r.amount_medium) },
        { label: "D:R ratio", sortKey: "party_ratio_value", num: true, render: (r) => fmtPartyRatio(r) },
        { label: "Website", sortKey: null, link: (r) => r.homepage || null, external: true, render: (r) => (r.homepage ? "Visit ↗" : "—") },
      ],
      renderVendors
    );
    setPanelTable("vendors", vendorHeaders, vendorTableRows, { sort: sortState.vendors });

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

    renderVendorCooccurrence();
  }

  // Vendor x vendor heatmap: DATA.vendor_cooccurrence is fixed (top 15
  // generative-era vendors, computed once in the pipeline -- see its
  // methodology note), so this doesn't depend on the era toggle or any
  // view mode; it just needs to run once per full render.
  function renderVendorCooccurrence() {
    const mount = document.getElementById("vendor-matrix-holder");
    if (!mount) return;
    const co = DATA.vendor_cooccurrence;
    if (!co || !co.vendor_ids || !co.vendor_ids.length) {
      mount.innerHTML = "";
      return;
    }
    mount.innerHTML = "";

    const cellByPair = {};
    co.cells.forEach((c) => (cellByPair[c.vendor_a + "|" + c.vendor_b] = c));

    const table = el("table", { className: "matrix-table" });
    const thead = el("thead");
    const headRow = el("tr");
    headRow.appendChild(el("th", { className: "matrix-corner" }));
    co.vendor_ids.forEach((vid, i) => {
      headRow.appendChild(el("th", { className: "matrix-col-label", children: [el("span", { text: co.vendor_names[i] })] }));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = el("tbody");
    co.vendor_ids.forEach((rowId, ri) => {
      const tr = el("tr");
      tr.appendChild(el("th", { className: "matrix-row-label", text: co.vendor_names[ri] + " (" + fmtInt.format(co.committee_counts[ri]) + ")" }));
      co.vendor_ids.forEach((colId, ci) => {
        const isDiagonal = rowId === colId;
        const cell = cellByPair[rowId + "|" + colId];
        const td = el("td", { className: "matrix-cell" + (isDiagonal ? " is-diagonal" : "") });
        if (isDiagonal) {
          td.textContent = "—";
          td.title = co.vendor_names[ri] + ": " + fmtInt.format(co.committee_counts[ri]) + " paying committees";
        } else if (cell) {
          const { bg, fg } = seqScale(cell.jaccard);
          td.style.background = bg;
          td.style.color = fg;
          td.textContent = cell.jaccard > 0 ? Math.round(cell.jaccard * 100) + "%" : "—";
          td.title = co.vendor_names[ri] + " × " + co.vendor_names[ci] + ": " + fmtPct(cell.jaccard * 100, 1) + " Jaccard (" + fmtInt.format(cell.count_both) + " of " + fmtInt.format(co.committee_counts[ri] + co.committee_counts[ci] - cell.count_both) + " combined committees pay both)";
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    mount.appendChild(el("div", { className: "matrix-wrap", children: [table] }));
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

    if (DATA.weekly_histogram) {
      renderWeeklyHistogram("chart-trend-weekly", "trend-weekly", DATA.weekly_histogram, c.general_purpose, c.muted);
    }
  }

  // ---- weekly disclosure-timeline histogram: shared by the Federal
  // "trends" section and the Massachusetts tab. `histogram` is
  // {expenditures: [{week, count, amount}], reports_filed: [{week, count}]}
  // -- two independently-binned series (see build_dataset.py /
  // build_dataset_ma.py), unioned onto one sorted week axis here so a week
  // with only one of the two series still gets a zero-height bar for the
  // other rather than being dropped. ----
  function renderWeeklyHistogram(canvasId, panel, histogram, expColor, repColor) {
    const c = colors();
    const expByWeek = {};
    histogram.expenditures.forEach((r) => (expByWeek[r.week] = r));
    const repByWeek = {};
    histogram.reports_filed.forEach((r) => (repByWeek[r.week] = r));
    const weeks = Array.from(new Set([...Object.keys(expByWeek), ...Object.keys(repByWeek)])).sort();

    const fmtWeekLabel = (wk) => new Date(wk + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    const labels = weeks.map(fmtWeekLabel);

    makeChart(canvasId, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Expenditures",
            data: weeks.map((wk) => (expByWeek[wk] ? expByWeek[wk].count : 0)),
            backgroundColor: expColor,
            borderRadius: 2,
          },
          {
            label: "Reports filed",
            data: weeks.map((wk) => (repByWeek[wk] ? repByWeek[wk].count : 0)),
            backgroundColor: repColor,
            borderRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: Object.assign({ position: "top" }, legendBase()),
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              title: (ctx) => "Week of " + ctx[0].label,
              label: (ctx) => {
                if (ctx.dataset.label === "Expenditures") {
                  const row = expByWeek[weeks[ctx.dataIndex]];
                  return "Expenditures: " + fmtInt.format(ctx.parsed.y) + (row ? " (" + fmtUSD2.format(row.amount) + ")" : "");
                }
                return "Reports filed: " + fmtInt.format(ctx.parsed.y);
              },
            },
          }),
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, precision: 0 }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      panel,
      [
        { label: "Week of" },
        { label: "Expenditures", num: true },
        { label: "Amount", num: true },
        { label: "Reports filed", num: true },
      ].map((h, i) => Object.assign(h, { key: ["week", "expenditures", "amount", "reports"][i] })),
      weeks
        .slice()
        .reverse()
        .map((wk) => ({
          week: fmtWeekLabel(wk),
          expenditures: fmtInt.format(expByWeek[wk] ? expByWeek[wk].count : 0),
          amount: fmtUSD2.format(expByWeek[wk] ? expByWeek[wk].amount : 0),
          reports: fmtInt.format(repByWeek[wk] ? repByWeek[wk].count : 0),
        }))
    );
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

  // ---- Universal search (candidates / vendors / races) ----
  const SEARCH_TYPE_LABEL = { candidate: "Candidate", vendor: "Vendor", race: "Race" };
  const SEARCH_RESULT_LIMIT = 20;

  function buildSearchIndex() {
    searchIndex = [];
    Object.values(DATA.candidates_detail || {}).forEach((cd) => {
      const loc = [cd.state, cd.district].filter(Boolean).join("-");
      searchIndex.push({
        type: "candidate",
        label: cd.name,
        sub: [cd.party, cd.office, loc].filter(Boolean).join(" · "),
        searchText: [cd.name, cd.party, cd.office, cd.state, loc].filter(Boolean).join(" ").toLowerCase(),
        href: "#/candidate/" + cd.id,
      });
    });
    (DATA.vendors_overall || []).forEach((v) => {
      searchIndex.push({
        type: "vendor",
        label: v.name,
        sub: (VENDOR_GROUP_LABEL[v.group] || v.group) + (v.era === "legacy" ? " · legacy" : ""),
        searchText: [v.name, v.group, v.era].filter(Boolean).join(" ").toLowerCase(),
        href: "#/vendor/" + v.id,
      });
    });
    Object.values(DATA.races || {}).forEach((race) => {
      const loc = race.state + (race.district ? "-" + race.district : "");
      const nCand = (race.candidates || []).length;
      searchIndex.push({
        type: "race",
        label: (DATA.office_labels[race.office] || race.office) + " — " + loc,
        sub: nCand + " candidate" + (nCand === 1 ? "" : "s"),
        searchText: [race.office, race.state, loc, ...(race.candidates || []).map((c) => c.name)].filter(Boolean).join(" ").toLowerCase(),
        href: "#/race/" + race.id,
      });
    });
  }

  // Same shape as buildSearchIndex(), for a state tab: its "filers"
  // (almost always candidate committees) indexed as "candidate" for
  // consistency with the Federal tab's labeling, plus that state's
  // vendors. No "race" type -- state candidates aren't grouped into
  // races here.
  function buildStateSearchIndex(stateId) {
    const data = STATE_DATA[stateId];
    const index = [];
    Object.values(data.filers_detail || {}).forEach((f) => {
      index.push({
        type: "candidate",
        label: f.name,
        sub: f.party,
        searchText: [f.name, f.party].filter(Boolean).join(" ").toLowerCase(),
        href: "#/" + stateId + "/candidate/" + f.id,
      });
    });
    (data.vendors || []).forEach((v) => {
      index.push({
        type: "vendor",
        label: v.name,
        sub: (VENDOR_GROUP_LABEL[v.group] || v.group) + (v.era === "legacy" ? " · legacy" : ""),
        searchText: [v.name, v.group, v.era].filter(Boolean).join(" ").toLowerCase(),
        href: "#/" + stateId + "/vendor/" + v.id,
      });
    });
    stateSearchIndex[stateId] = index;
  }

  const SEARCH_TYPE_ORDER = ["candidate", "vendor", "race"];

  function runSearch(query) {
    const results = document.getElementById("search-results");
    const q = query.trim().toLowerCase();
    if (!q) {
      results.hidden = true;
      results.innerHTML = "";
      return;
    }
    const activeIndex = STATE_IDS.indexOf(currentDataset) !== -1 ? stateSearchIndex[currentDataset] || [] : searchIndex;
    const byType = { candidate: [], vendor: [], race: [] };
    activeIndex.forEach((item) => {
      if (searchFilterType !== "all" && item.type !== searchFilterType) return;
      if (item.searchText.indexOf(q) === -1) return;
      byType[item.type].push(item);
    });
    const sortWithin = (a, b) => {
      const aStarts = a.label.toLowerCase().startsWith(q) ? 0 : 1;
      const bStarts = b.label.toLowerCase().startsWith(q) ? 0 : 1;
      if (aStarts !== bStarts) return aStarts - bStarts;
      return a.label.localeCompare(b.label);
    };
    // Grouped by type (fixed order) so results read as clean sections
    // rather than interleaving candidates/vendors/races by label text.
    // Capped tighter per type when showing all three at once.
    const perTypeLimit = searchFilterType === "all" ? 6 : SEARCH_RESULT_LIMIT;

    results.innerHTML = "";
    let totalMatches = 0;
    SEARCH_TYPE_ORDER.forEach((type) => {
      const list = byType[type].sort(sortWithin);
      totalMatches += list.length;
      if (!list.length) return;
      results.appendChild(el("div", { className: "search-group-label", text: SEARCH_TYPE_LABEL[type] }));
      list.slice(0, perTypeLimit).forEach((item) => {
        const row = el("a", {
          className: "search-result",
          href: item.href,
          children: [el("span", { className: "search-result-label", text: item.label }), el("span", { className: "search-result-sub", text: item.sub })],
        });
        row.addEventListener("click", closeSearchResults);
        results.appendChild(row);
      });
      if (list.length > perTypeLimit) {
        const n = list.length - perTypeLimit;
        results.appendChild(el("div", { className: "search-empty", text: n + " more " + SEARCH_TYPE_LABEL[type].toLowerCase() + " match" + (n === 1 ? "" : "es") + " — refine your search" }));
      }
    });
    if (!totalMatches) {
      results.appendChild(el("div", { className: "search-empty", text: "No matches." }));
    }
    results.hidden = false;
  }

  function closeSearchResults() {
    const results = document.getElementById("search-results");
    results.hidden = true;
    const input = document.getElementById("global-search-input");
    input.value = "";
  }

  function wireSearch() {
    const input = document.getElementById("global-search-input");
    const results = document.getElementById("search-results");
    input.addEventListener("input", () => runSearch(input.value));
    input.addEventListener("focus", () => {
      if (input.value.trim()) runSearch(input.value);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeSearchResults();
        input.blur();
      }
    });
    document.querySelectorAll(".search-filter-chips .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        searchFilterType = btn.getAttribute("data-filter");
        document.querySelectorAll(".search-filter-chips .chip").forEach((b) => b.classList.toggle("is-active", b === btn));
        runSearch(input.value);
        input.focus();
      });
    });
    document.addEventListener("click", (e) => {
      if (!document.getElementById("search-bar-wrap").contains(e.target)) {
        results.hidden = true;
      }
    });
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

  // ---- dataset tabs: Federal (FEC) and each state (a separate disclosure
  // system) are all separate datasets, never merged. Exactly one is
  // visible at a time; every card in each carries its own context pill
  // (see tagCardsWithPill) so which dataset a given chart belongs to is
  // never ambiguous. ----
  const FEDERAL_TITLE = "AI Use in Federal Campaign Disclosures";
  const FEDERAL_SUBTITLE_1 =
    "A read of federal campaign-finance disclosures for U.S. House and Senate candidates, looking for payments to AI vendors and how that spending breaks down by vendor, stated purpose, party, incumbency, candidate age, and chamber — and how each of those has changed across recent election cycles.";
  const COMPARE_TITLE = "AI Vendors: Federal vs. States";
  const COMPARE_SUBTITLE_1 =
    "Every AI vendor found on Federal or any covered state tab, side by side: what each is disclosed to have spent on federal House/Senate races vs. each of Massachusetts, Washington, Colorado, and California's state races, combined spend volume, and a recent-momentum signal — plus what campaigns actually use each tool for, and a population-scaled national projection built from the four states.";
  const STATES_TITLE = "AI Use in State Campaign Disclosures, Combined";
  const STATES_SUBTITLE_1 =
    "Every state this site covers — Massachusetts, Washington, Colorado, and California — unioned into one view: combined AI-vendor spend by vendor, a combined year-over-year trend, and a state-by-state leaderboard. Every figure here is a real sum of each state's own disclosed records, not an estimate (for a population-scaled national projection built from these same four states, see the Compare tab).";

  // One entry per state tab. Each state's dashboard JSON is built by its
  // own pipeline (build_dataset_ma.py, or the shared
  // pipeline/lib/build_state_dataset.py for wa/co/ca) but rendered by the
  // same generic functions below -- adding a 5th state means adding one
  // entry here (plus its own fetch/parse/build_dataset_<id>.py and a tab
  // button + CSS accent-color pair), not writing a new render module.
  const STATE_CONFIGS = [
    {
      id: "ma",
      label: "Massachusetts",
      tabSub: "State races · OCPF",
      sourceShort: "OCPF",
      dataFile: "data/dashboard_ma.json",
      title: "AI Use in Massachusetts Campaign Disclosures",
      subtitle1:
        "A read of Massachusetts OCPF campaign-finance disclosures for state candidates, looking for payments to the same AI-vendor taxonomy tracked on the Federal tab. This is a separate dataset from a different disclosure system — smaller in scale, with its own itemization rules — and is not directly comparable dollar-for-dollar with the federal figures.",
      bannerSourceLabel: "OCPF, the state's own campaign-finance disclosure system",
      cycleWindowNote: " (the 2024 and 2026 cycles)",
      footerSource:
        "Source data: Massachusetts Office of Campaign and Political Finance (ocpf.us), via its public API. This is an independent analysis and is not affiliated with OCPF or any campaign or vendor named here.",
      legacyToggleSub:
        "Off by default: companies founded before generative AI existed but still branded “AI” (e.g. CallTime.AI, Grammarly, Otter.ai) are excluded from the vendor chart and table below by default. Their own vendor pages are always visible.",
    },
    {
      id: "wa",
      label: "Washington",
      tabSub: "State races · PDC",
      sourceShort: "PDC",
      dataFile: "data/dashboard_wa.json",
      title: "AI Use in Washington Campaign Disclosures",
      subtitle1:
        "A read of Washington Public Disclosure Commission (PDC) campaign-finance disclosures for state candidates and committees, looking for payments to the same AI-vendor taxonomy tracked on the Federal tab. This is a separate dataset from a different disclosure system, with its own itemization rules, and is not directly comparable dollar-for-dollar with the federal figures.",
      bannerSourceLabel: "the Washington Public Disclosure Commission (PDC), the state's own campaign-finance disclosure system",
      cycleWindowNote: "",
      footerSource:
        "Source data: Washington Public Disclosure Commission (data.wa.gov), via its public Socrata API. This is an independent analysis and is not affiliated with the PDC or any campaign or vendor named here.",
      legacyToggleSub:
        "Off by default: companies founded before generative AI existed but still branded “AI” are excluded from the vendor chart and table below by default. Their own vendor pages are always visible.",
    },
    {
      id: "co",
      label: "Colorado",
      tabSub: "State races · TRACER",
      sourceShort: "TRACER",
      dataFile: "data/dashboard_co.json",
      title: "AI Use in Colorado Campaign Disclosures",
      subtitle1:
        "A read of Colorado TRACER (Secretary of State) campaign-finance disclosures for state candidates and committees, looking for payments to the same AI-vendor taxonomy tracked on the Federal tab. Colorado's bulk export carries no party-affiliation field, so every record here shows as Unknown party. This is a separate dataset and is not directly comparable dollar-for-dollar with the federal figures.",
      bannerSourceLabel: "TRACER, the Colorado Secretary of State's campaign-finance disclosure system",
      cycleWindowNote: "",
      footerSource:
        "Source data: Colorado TRACER (tracer.sos.colorado.gov), via its public bulk data downloads. This is an independent analysis and is not affiliated with the Colorado Secretary of State or any campaign or vendor named here.",
      legacyToggleSub:
        "Off by default: companies founded before generative AI existed but still branded “AI” are excluded from the vendor chart and table below by default. Their own vendor pages are always visible.",
    },
    {
      id: "ca",
      label: "California",
      tabSub: "State races · CAL-ACCESS",
      sourceShort: "CAL-ACCESS",
      dataFile: "data/dashboard_ca.json",
      title: "AI Use in California Campaign Disclosures",
      subtitle1:
        "A read of California CAL-ACCESS (Secretary of State) campaign-finance disclosures for state candidates and committees, looking for payments to the same AI-vendor taxonomy tracked on the Federal tab. CAL-ACCESS's raw data carries no party-affiliation field, so every record here shows as Unknown party. This is a separate dataset and is not directly comparable dollar-for-dollar with the federal figures.",
      bannerSourceLabel: "CAL-ACCESS, the California Secretary of State's campaign-finance disclosure system",
      cycleWindowNote: "",
      footerSource:
        "Source data: California Secretary of State (CAL-ACCESS), via its daily bulk database export. This is an independent analysis and is not affiliated with the California Secretary of State or any campaign or vendor named here.",
      legacyToggleSub:
        "Off by default: companies founded before generative AI existed but still branded “AI” are excluded from the vendor chart and table below by default. Their own vendor pages are always visible.",
    },
  ];
  const STATE_CONFIG_BY_ID = {};
  STATE_CONFIGS.forEach((c) => (STATE_CONFIG_BY_ID[c.id] = c));
  const STATE_IDS = STATE_CONFIGS.map((c) => c.id);

  let currentDataset = "federal";

  // Federal excludes legacy vendors from every chart/table below the
  // toggle; each state tab only has one such vendor-listing card
  // (renderStateVendorsCard) to filter, so its wording says so rather than
  // overclaiming "every chart and table" -- a state tab has no
  // #methodology anchor to link to, and the Compare tab's single table is
  // the only thing its own toggle affects.
  function updateLegacyToggleText(tab) {
    const sub = document.querySelector(".legacy-toggle-sub");
    if (!sub) return;
    const stateCfg = STATE_CONFIG_BY_ID[tab];
    if (stateCfg) {
      sub.innerHTML = stateCfg.legacyToggleSub;
    } else if (tab === "compare" || tab === "states") {
      sub.innerHTML =
        "Off by default: companies founded before generative AI existed but still branded “AI” (e.g. Amplify.ai, Grammarly, Otter.ai) are excluded from the table below by default.";
    } else {
      sub.innerHTML =
        "Off by default: companies founded before generative AI existed but still branded “AI” (e.g. Amplify.ai, Grammarly, Otter.ai) are excluded from every chart and table below. Their own vendor pages are always visible — see <a href=\"#methodology\">methodology</a>.";
    }
  }

  function activateDataset(tab) {
    currentDataset = tab;
    const stateCfg = STATE_CONFIG_BY_ID[tab];
    const isState = !!stateCfg;
    const isCompare = tab === "compare";
    const isStatesCombined = tab === "states";
    const isOffMain = isState || isCompare || isStatesCombined;
    updateLegacyToggleText(tab);

    document.body.setAttribute("data-active-dataset", tab);
    document.querySelectorAll(".dataset-tab[data-dataset]").forEach((btn) => {
      const active = btn.getAttribute("data-dataset") === tab;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    updateStateDropdownTrigger(stateCfg);

    document.getElementById("page-toc").hidden = isOffMain;
    document.getElementById("footer-source-federal").hidden = isOffMain;
    const footerState = document.getElementById("footer-source-state");
    footerState.hidden = !isState;
    if (isState) footerState.textContent = stateCfg.footerSource;
    document.getElementById("footer-source-compare").hidden = !isCompare;
    document.getElementById("footer-source-states").hidden = !isStatesCombined;

    document.title = isState ? stateCfg.title : isCompare ? COMPARE_TITLE : isStatesCombined ? STATES_TITLE : FEDERAL_TITLE;
    document.getElementById("page-h1").textContent = isState ? stateCfg.title : isCompare ? COMPARE_TITLE : isStatesCombined ? STATES_TITLE : FEDERAL_TITLE;
    document.getElementById("page-subtitle-1").textContent = isState ? stateCfg.subtitle1 : isCompare ? COMPARE_SUBTITLE_1 : isStatesCombined ? STATES_SUBTITLE_1 : FEDERAL_SUBTITLE_1;
    document.getElementById("page-subtitle-2").hidden = isOffMain;

    // The search bar covers Federal and each state's candidates/vendors
    // (see runSearch(), which picks searchIndex vs. stateSearchIndex off
    // currentDataset); Compare and the combined States tab have no entity
    // pages of their own (they only link out to Federal/state vendor
    // pages), so it's simplest to hide the bar there rather than pick one
    // dataset's index for it.
    const hideSearch = isCompare || isStatesCombined;
    document.getElementById("search-bar-wrap").hidden = hideSearch;
    if (!hideSearch) {
      const raceChip = document.querySelector('.search-filter-chips .chip[data-filter="race"]');
      if (raceChip) raceChip.hidden = isState;
      document.getElementById("global-search-input").placeholder = isState ? "Search candidates, vendors…" : "Search candidates, vendors, races…";
      if (isState && searchFilterType === "race") {
        searchFilterType = "all";
        document.querySelectorAll(".search-filter-chips .chip").forEach((b) => b.classList.toggle("is-active", b.getAttribute("data-filter") === "all"));
      }
    }
    document.getElementById("search-results").hidden = true;
    document.getElementById("global-search-input").value = "";

    document.getElementById("main-view").hidden = isOffMain;
    document.getElementById("detail-view").hidden = isOffMain;
    document.getElementById("state-view").hidden = !isState;
    document.getElementById("state-detail-view").hidden = true;
    document.getElementById("compare-view").hidden = !isCompare;
    document.getElementById("states-view").hidden = !isStatesCombined;
    document.getElementById("states-detail-view").hidden = true;

    if (isState) {
      document.getElementById("meta-line").textContent = STATE_DATA[tab] ? metaLineTextState(tab) : "Loading " + stateCfg.label + " dataset…";
      window.scrollTo(0, 0);
      ensureStateData(tab);
    } else if (isCompare) {
      document.getElementById("meta-line").textContent = metaLineTextCompare();
      window.scrollTo(0, 0);
      if (STATES_DATA && PROJECTION_DATA) {
        renderCompareView();
      } else {
        const view = document.getElementById("compare-view");
        view.innerHTML = "";
        view.appendChild(el("p", { className: "lede", text: "Loading states dataset…" }));
        ensureCompareData();
      }
    } else if (isStatesCombined) {
      document.getElementById("meta-line").textContent = STATES_DATA ? metaLineTextStates() : "Loading combined states dataset…";
      window.scrollTo(0, 0);
      ensureStatesData();
    } else {
      document.getElementById("meta-line").textContent = metaLineTextFederal();
    }
  }

  function wireDatasetTabs() {
    // [data-dataset] excludes the "State" dropdown trigger itself (see
    // wireStateDropdown), which opens/closes the menu below it rather than
    // navigating anywhere on its own.
    document.querySelectorAll(".dataset-tab[data-dataset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-dataset");
        location.hash = tab === "federal" ? "#/" : "#/" + tab;
      });
    });
  }

  // The trigger shows which state is active (label, sub-label, and accent
  // color, the same --accent/--accent-soft convention every other tab
  // uses) when one of the four is selected, and resets to a generic
  // "State ▾ / Pick a state" prompt otherwise -- called from
  // activateDataset() with that tab's STATE_CONFIGS entry, or null.
  function updateStateDropdownTrigger(stateCfg) {
    const trigger = document.getElementById("state-dropdown-trigger");
    if (!trigger) return;
    const label = document.getElementById("state-dropdown-trigger-label");
    const sub = document.getElementById("state-dropdown-trigger-sub");
    trigger.classList.toggle("is-active", !!stateCfg);
    trigger.setAttribute("aria-selected", stateCfg ? "true" : "false");
    if (stateCfg) {
      trigger.style.setProperty("--accent", "var(--" + stateCfg.id + "-accent)");
      trigger.style.setProperty("--accent-soft", "var(--" + stateCfg.id + "-accent-soft)");
      label.textContent = stateCfg.label;
      sub.textContent = stateCfg.tabSub;
    } else {
      trigger.style.removeProperty("--accent");
      trigger.style.removeProperty("--accent-soft");
      label.textContent = "State";
      sub.textContent = "Pick a state";
    }
  }

  // Toggle-on-click, close on an outside click, Escape, or picking a
  // state (that last case via each menu button's own click, which also
  // triggers wireDatasetTabs()'s navigation listener on the same button --
  // both listeners fire independently, no conflict).
  function wireStateDropdown() {
    const trigger = document.getElementById("state-dropdown-trigger");
    const menu = document.getElementById("state-dropdown-menu");
    if (!trigger || !menu) return;
    const closeMenu = () => {
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    };
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = menu.hidden;
      menu.hidden = !willOpen;
      trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
    });
    menu.querySelectorAll(".dataset-tab").forEach((btn) => btn.addEventListener("click", closeMenu));
    document.addEventListener("click", (e) => {
      if (!menu.hidden && !menu.contains(e.target) && e.target !== trigger) closeMenu();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !menu.hidden) {
        closeMenu();
        trigger.focus();
      }
    });
  }

  // One-time pass: stamp every federal card's <h3> with a context pill.
  // The federal card markup is static (never rebuilt), so this only needs
  // to run once; state cards are built fresh by renderStateView() each
  // time and include their pill directly.
  function tagFederalCardsWithPill() {
    document.querySelectorAll("#main-view .card > h3").forEach((h3) => {
      h3.appendChild(el("span", { className: "dataset-pill dataset-pill-federal", text: "Federal · FEC" }));
    });
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
      stats.appendChild(
        statTile("Lower-confidence signal", fmtUSD0.format(overall.amount_medium), "ambiguous word matches, excluded from every chart on this page but included (tagged) in the tables below -- see methodology")
      );
    }
    view.appendChild(stats);

    const grid = el("div", { className: "card-grid" });
    grid.appendChild(detailCard("Spending over time", "detail-chart-ts"));
    grid.appendChild(detailCard("Top candidates using " + v.name, "detail-chart-cand", "Click a bar to open that candidate's page."));
    view.appendChild(grid);

    const grid2 = el("div", { className: "card-grid" });
    grid2.appendChild(
      detailCard(
        "Party split",
        "detail-chart-party",
        "Democratic vs. Republican: " +
          fmtPartyRatio(v) +
          (v.dem_rep_ratio !== null ? " -- ratio of Democratic to Republican spending" : "") +
          ". Only House/Senate candidate committees have a reliable party; \"PACs, committees & other offices\" is everything else (party committees, PACs, non-House/Senate candidates), so the slices add up to this vendor's full high-confidence total."
      )
    );
    grid2.appendChild(detailCard("By incumbency status", "detail-chart-ici"));
    view.appendChild(grid2);

    if (v.time_series_by_party && v.time_series_by_party.length) {
      const partyTrendGrid = el("div", { className: "card-grid single" });
      partyTrendGrid.appendChild(detailCard("Party spending over time", "detail-chart-party-trend"));
      view.appendChild(partyTrendGrid);
    }

    // Both tables below default to high-confidence-only, matching every
    // chart on this page; the toggle bar reveals ambiguous-word matches in
    // both at once, each clearly tagged (a pill in Lower-confidence $ / the
    // Confidence column, plus a tinted row) rather than blended in
    // silently. Rebuilding just this container (not the whole page) keeps
    // the toggle and header-click sorting snappy.
    const confSection = el("div");
    view.appendChild(confSection);

    function renderConfidenceSection() {
      confSection.innerHTML = "";

      const toggleId = "vendor-lowconf-toggle";
      const toggleInput = el("input", { attrs: { type: "checkbox", id: toggleId } });
      toggleInput.checked = vendorDetailShowLowConf;
      toggleInput.addEventListener("change", () => {
        vendorDetailShowLowConf = toggleInput.checked;
        renderConfidenceSection();
      });
      // A <label> wrapper (not a plain <span>) matters here: clicking the
      // slider visual hits that span, not the absolutely-positioned input
      // underneath it, but a <label> forwards a click anywhere inside it to
      // the form control it wraps -- same structure as the legacy toggle.
      const toggleSwitch = el("label", { className: "toggle-switch", children: [toggleInput, el("span", { className: "toggle-slider", attrs: { "aria-hidden": "true" } })] });
      const toggleLabel = el("label", {
        className: "confidence-toggle-label",
        attrs: { for: toggleId },
        children: [
          document.createTextNode("Include lower-confidence matches"),
          el("span", {
            className: "confidence-toggle-sub",
            text: "Off by default: ambiguous word matches (e.g. a person literally named “Claude”) are hidden from the two tables below. Turn on to see them too, clearly tagged — see methodology.",
          }),
        ],
      });
      confSection.appendChild(el("div", { className: "confidence-toggle-bar", children: [toggleSwitch, toggleLabel] }));

      const cmteRowsAll = v.top_committees.map((r) => Object.assign({}, r, { cmte_display: r.cmte_name || r.cmte_id }));
      const cmteRows = sortRows(
        cmteRowsAll.filter((r) => vendorDetailShowLowConf || r.amount_high > 0),
        sortState.vendorCommittees
      );
      const cmteCard = el("div", { className: "card" });
      cmteCard.appendChild(el("h3", { text: "Top committees paying " + v.name }));
      cmteCard.appendChild(
        el("p", {
          className: "note",
          text: vendorDetailShowLowConf
            ? "Includes lower-confidence (ambiguous-word) matches -- a committee whose only match is an ambiguous word is tagged and still shows up here."
            : "High-confidence matches only. Turn on the toggle above to include ambiguous-word matches too.",
        })
      );
      const cmteHeaders = withSort(
        "vendorCommittees",
        [
          { label: "Committee", sortKey: "cmte_display", render: (r) => r.cmte_display },
          { label: "High-confidence $", sortKey: "amount_high", num: true, render: (r) => fmtUSD0.format(r.amount_high) },
          vendorDetailShowLowConf
            ? {
                label: "Lower-confidence $",
                sortKey: "amount_medium",
                num: true,
                cell: (r) =>
                  r.amount_medium > 0
                    ? el("span", { className: "pill pill-medium-confidence", text: fmtUSD0.format(r.amount_medium) })
                    : document.createTextNode("—"),
              }
            : null,
          { label: "Records", sortKey: "count", num: true, render: (r) => fmtInt.format(r.count) },
          { label: "FEC record", sortKey: null, link: (r) => fecCommitteeUrl(r.cmte_id), external: true, render: () => "View ↗" },
        ].filter(Boolean),
        renderConfidenceSection
      );
      cmteCard.appendChild(
        buildTable(cmteHeaders, cmteRows, { sort: sortState.vendorCommittees, rowClass: (r) => (r.amount_high === 0 ? "row-medium-confidence" : null) })
      );
      confSection.appendChild(el("div", { className: "card-grid single", children: [cmteCard] }));

      if (v.records && v.records.length) {
        const recRowsAll = v.records.map((r) => Object.assign({}, r, { display_name: r.cand_name || r.cmte_name || "", date_sort: mdySortValue(r.date) }));
        const recRows = sortRows(
          recRowsAll.filter((r) => vendorDetailShowLowConf || r.confidence === "high"),
          sortState.vendorRecords
        );
        const recordsCard = el("div", { className: "card" });
        recordsCard.appendChild(el("h3", { text: "Individual disbursements" }));
        recordsCard.appendChild(
          el("p", {
            className: "note",
            text:
              "The stated purpose FEC has on file for each specific payment, largest first" +
              (vendorDetailShowLowConf ? ", including lower-confidence (ambiguous-word) matches -- see the Confidence column" : " (high-confidence matches only)") +
              (v.records.length >= MAX_DETAIL_RECORDS ? " (capped at " + fmtInt.format(MAX_DETAIL_RECORDS) + " records)" : "") +
              ".",
          })
        );
        const recHeaders = withSort(
          "vendorRecords",
          [
            { label: "Date", sortKey: "date_sort", render: (r) => r.date },
            { label: "Candidate / committee", sortKey: "display_name", link: (r) => (r.cand_id ? "#/candidate/" + r.cand_id : null), render: (r) => r.display_name || "—" },
            { label: "Amount", sortKey: "amount", num: true, render: (r) => fmtUSD2.format(r.amount) },
            vendorDetailShowLowConf ? { label: "Confidence", sortKey: "confidence", cell: (r) => confidencePill(r.confidence) } : null,
            { label: "Stated purpose", sortKey: "purpose", render: (r) => r.purpose || "—" },
          ].filter(Boolean),
          renderConfidenceSection
        );
        recordsCard.appendChild(
          buildTable(recHeaders, recRows, { sort: sortState.vendorRecords, rowClass: (r) => (r.confidence === "medium" ? "row-medium-confidence" : null) })
        );
        confSection.appendChild(el("div", { className: "card-grid single", children: [recordsCard] }));
      }
    }

    renderConfidenceSection();

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

    // v.by_party only covers House/Senate candidate committees, which is
    // usually well short of amount_high (PACs, party committees, and
    // non-House/Senate candidates carry no reliable party). Add that gap
    // back as an explicit "Other" slice so the pie's total always
    // reconciles with the vendor's full high-confidence spend instead of
    // silently only covering part of it.
    const partySlices = v.by_party.filter((r) => r.amount > 0).slice();
    if (v.other_amount > 0) {
      partySlices.push({ cand_party: "PACs, committees & other offices", amount: v.other_amount });
    }
    makeChart("detail-chart-party", {
      type: "pie",
      data: {
        labels: partySlices.map((r) => r.cand_party),
        datasets: [{ data: partySlices.map((r) => r.amount), backgroundColor: partySlices.map((r) => c.party[r.cand_party] || c.muted) }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: Object.assign({ position: "bottom" }, legendBase()),
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: (ctx) => {
                const total = partySlices.reduce((a, r) => a + r.amount, 0);
                return ctx.label + ": " + fmtUSD0.format(ctx.parsed) + " (" + fmtPct((ctx.parsed / total) * 100, 1) + ")";
              },
            },
          }),
        },
      },
    });

    if (v.time_series_by_party && v.time_series_by_party.length) {
      const partyCycles = Array.from(new Set(v.time_series_by_party.map((r) => r.cycle))).sort((a, b) => a - b);
      const seriesByParty = {};
      ["Democratic", "Republican"].forEach((p) => (seriesByParty[p] = v.time_series_by_party.filter((r) => r.party === p)));
      makeChart("detail-chart-party-trend", {
        type: "line",
        data: {
          labels: partyCycles.map(String),
          datasets: Object.keys(seriesByParty)
            .filter((p) => seriesByParty[p].length)
            .map((p) => ({
              label: p,
              data: partyCycles.map((cy) => (seriesByParty[p].find((r) => r.cycle === cy) || {}).amount || 0),
              borderColor: c.party[p],
              backgroundColor: c.party[p],
              borderWidth: 2,
              pointRadius: 4,
              tension: 0.15,
            })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: Object.assign({ position: "top" }, legendBase()),
            tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => ctx.dataset.label + ": " + fmtUSD0.format(ctx.parsed.y) } }),
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
            y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
          },
        },
      });
    }

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

    if (cd.records && cd.records.length) {
      const recordsCard = el("div", { className: "card" });
      recordsCard.appendChild(el("h3", { text: "Individual disbursements" }));
      recordsCard.appendChild(
        el("p", {
          className: "note",
          text:
            "The stated purpose FEC has on file for each specific payment, largest first" +
            (cd.records.length >= MAX_DETAIL_RECORDS ? " (capped at " + fmtInt.format(MAX_DETAIL_RECORDS) + " records)" : "") +
            ".",
        })
      );
      const recRows = sortRows(
        cd.records.map((r) => Object.assign({}, r, { date_sort: mdySortValue(r.date) })),
        sortState.candidateRecords
      );
      const recHeaders = withSort(
        "candidateRecords",
        [
          { label: "Date", sortKey: "date_sort", render: (r) => r.date },
          { label: "Vendor", sortKey: "vendor_name", cell: (r) => vendorNameCell(r.vendor_id, r.vendor_name) },
          { label: "Amount", sortKey: "amount", num: true, render: (r) => fmtUSD2.format(r.amount) },
          { label: "Stated purpose", sortKey: "purpose", render: (r) => r.purpose || "—" },
        ],
        () => renderCandidateDetail(id)
      );
      recordsCard.appendChild(buildTable(recHeaders, recRows, { sort: sortState.candidateRecords }));
      view.appendChild(el("div", { className: "card-grid single", children: [recordsCard] }));
    }

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

  // ---- Massachusetts (OCPF) tab ----
  const STATE_DATA = {}; // stateId -> dataset json, null until loaded
  const stateLoadPromises = {}; // stateId -> in-flight fetch Promise

  // MA's own pipeline (build_dataset_ma.py) predates the shared
  // pipeline/lib/build_state_dataset.py aggregator and names a filer's id
  // "filer_cpf_id" (OCPF's own term); every other state's shared
  // aggregator calls the same field "filer_id". Normalized once here, at
  // load time, so every render function below only ever reads "filer_id"
  // regardless of which state's data it's looking at.
  function normalizeStateData(stateId, data) {
    if (stateId !== "ma") return data;
    (data.notable_records || []).forEach((r) => {
      if (r.filer_id === undefined) r.filer_id = r.filer_cpf_id;
    });
    Object.values(data.vendors_detail || {}).forEach((v) => {
      (v.by_filer || []).forEach((r) => {
        if (r.filer_id === undefined) r.filer_id = r.filer_cpf_id;
      });
    });
    return data;
  }

  // MA's meta.records_scanned is {expenditures, subvendor} (OCPF's own
  // subcontractor-disclosure layer has no equivalent elsewhere); every
  // other state's shared aggregator writes a plain total instead.
  function totalRecordsScanned(meta) {
    const rs = meta.records_scanned;
    return typeof rs === "object" ? rs.expenditures + rs.subvendor : rs;
  }

  function stateYearRangeLabel(meta) {
    const startYear = meta.date_range.start.slice(0, 4);
    const endYear = meta.date_range.end ? meta.date_range.end.slice(0, 4) : "present";
    return startYear === endYear ? startYear : startYear + "–" + endYear;
  }

  function stateCardTitle(stateId, text) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    return el("h3", {
      children: [
        document.createTextNode(text),
        el("span", {
          className: "dataset-pill",
          text: cfg.label + " · " + cfg.sourceShort,
          attrs: { style: "--accent:var(--" + stateId + "-accent);--accent-soft:var(--" + stateId + "-accent-soft)" },
        }),
      ],
    });
  }

  // Which state sub-route to show once the dataset finishes loading -- set
  // by route() right before activateDataset(stateId) triggers
  // ensureStateData(), since the fetch is async and the hash could point
  // straight at a detail page on a cold load (a shared link to a state
  // vendor/candidate page).
  let pendingStateSubroute = "";

  // Fetches (or awaits an in-flight fetch of) one state's dataset with no
  // router/view side effects, so both that state's own tab (ensureStateData,
  // below) and the Compare tab (ensureCompareData, which pins to "ma" --
  // see its own comment) can share one in-flight request instead of racing
  // two fetches if a user switches tabs before the first one lands.
  function loadStateData(stateId) {
    if (STATE_DATA[stateId]) return Promise.resolve(STATE_DATA[stateId]);
    if (!stateLoadPromises[stateId]) {
      const cfg = STATE_CONFIG_BY_ID[stateId];
      stateLoadPromises[stateId] = fetch(cfg.dataFile)
        .then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then((json) => {
          STATE_DATA[stateId] = normalizeStateData(stateId, json);
          stateVendorEraById[stateId] = {};
          json.vendors.forEach((v) => (stateVendorEraById[stateId][v.id] = v.era));
          buildStateSearchIndex(stateId);
          if (currentDataset === stateId) document.getElementById("meta-line").textContent = metaLineTextState(stateId);
          if (currentDataset === "compare") document.getElementById("meta-line").textContent = metaLineTextCompare();
          return STATE_DATA[stateId];
        })
        .catch((err) => {
          console.error(err);
          throw err;
        });
    }
    return stateLoadPromises[stateId];
  }

  function ensureStateData(stateId) {
    if (STATE_DATA[stateId]) {
      stateRouter(stateId, pendingStateSubroute);
      return;
    }
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const view = document.getElementById("state-view");
    document.getElementById("state-detail-view").hidden = true;
    view.hidden = false;
    view.innerHTML = "";
    view.appendChild(el("p", { className: "lede", text: "Loading " + cfg.label + " dataset…" }));
    loadStateData(stateId)
      .then(() => stateRouter(stateId, pendingStateSubroute))
      .catch((err) => {
        view.innerHTML = "";
        view.appendChild(el("p", { className: "lede", text: "Could not load " + cfg.label + " dataset (" + err.message + ")." }));
      });
  }

  // Population-based national projection (see pipeline/build_projection.py)
  // -- scales this project's four covered states' spend/candidate/vendor
  // counts up to the full U.S. population. Shown only on the Compare tab,
  // so it's fetched alongside the Massachusetts dataset in
  // ensureCompareData(), not on page load.
  let PROJECTION_DATA = null;
  let projectionLoadPromise = null;

  function loadProjectionData() {
    if (PROJECTION_DATA) return Promise.resolve(PROJECTION_DATA);
    if (!projectionLoadPromise) {
      projectionLoadPromise = fetch("data/dashboard_projection.json")
        .then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then((json) => {
          PROJECTION_DATA = json;
          return PROJECTION_DATA;
        })
        .catch((err) => {
          console.error(err);
          throw err;
        });
    }
    return projectionLoadPromise;
  }

  // The Compare tab is Federal vs. every covered state at once (see
  // buildCompareRows() below), so it loads the same combined
  // dashboard_states.json the States tab uses rather than any single
  // state's own dataset. The population projection below it draws on all
  // four covered states regardless, since it's built from their own
  // dashboard JSON files ahead of time by pipeline/build_projection.py,
  // not fetched live here.
  function ensureCompareData() {
    Promise.all([loadStatesData(), loadProjectionData()])
      .then(() => {
        if (currentDataset === "compare") renderCompareView();
      })
      .catch((err) => {
        if (currentDataset !== "compare") return;
        const view = document.getElementById("compare-view");
        view.innerHTML = "";
        view.appendChild(el("p", { className: "lede", text: "Could not load states dataset (" + err.message + ")." }));
      });
  }

  // Combined multi-state tab (see pipeline/build_dataset_states.py): a
  // real union of the four covered states' own disclosed records, not an
  // estimate -- a single self-contained dataset (docs/data/dashboard_states.json)
  // rather than four separate fetches, since the build step already did
  // the combining server-side.
  let STATES_DATA = null;
  let statesLoadPromise = null;

  function loadStatesData() {
    if (STATES_DATA) return Promise.resolve(STATES_DATA);
    if (!statesLoadPromise) {
      statesLoadPromise = fetch("data/dashboard_states.json")
        .then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then((json) => {
          STATES_DATA = json;
          if (currentDataset === "states") document.getElementById("meta-line").textContent = metaLineTextStates();
          if (currentDataset === "compare") document.getElementById("meta-line").textContent = metaLineTextCompare();
          return STATES_DATA;
        })
        .catch((err) => {
          console.error(err);
          throw err;
        });
    }
    return statesLoadPromise;
  }

  // Which States sub-route to show once both datasets finish loading --
  // set by route() right before activateDataset("states"), mirroring
  // pendingStateSubroute for the individual state tabs.
  let pendingStatesSubroute = "";

  // The States tab's own vendor detail page (see renderStatesVendorDetail)
  // shows a population-scaled national projection alongside each vendor's
  // real combined-states total, so it needs PROJECTION_DATA loaded too --
  // fetched in parallel with the states dataset itself, the same pattern
  // ensureCompareData() already uses for Massachusetts + the projection.
  function ensureStatesData() {
    if (STATES_DATA && PROJECTION_DATA) {
      statesRouter(pendingStatesSubroute);
      return;
    }
    const view = document.getElementById("states-view");
    document.getElementById("states-detail-view").hidden = true;
    view.hidden = false;
    view.innerHTML = "";
    view.appendChild(el("p", { className: "lede", text: "Loading combined states dataset…" }));
    Promise.all([loadStatesData(), loadProjectionData()])
      .then(() => statesRouter(pendingStatesSubroute))
      .catch((err) => {
        view.innerHTML = "";
        view.appendChild(el("p", { className: "lede", text: "Could not load combined states dataset (" + err.message + ")." }));
      });
  }

  function metaLineTextStates() {
    const meta = STATES_DATA.meta;
    return "Data generated " + new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) + " UTC · " + meta.covered_states.length + " states covered";
  }

  function stateBackLink(stateId) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    return el("a", { href: "#/" + stateId, className: "back-link", text: "← Back to " + cfg.label + " dashboard" });
  }

  // Mirrors federalRouter(): "" shows the main state dashboard,
  // "vendor/<id>" and "candidate/<id>" (that state's filer -- almost
  // always a candidate committee) show a detail page in #state-detail-view
  // instead. Only one state's markup is ever mounted in the shared
  // #state-view/#state-detail-view containers at a time.
  function stateRouter(stateId, sub) {
    const mainView = document.getElementById("state-view");
    const detailView = document.getElementById("state-detail-view");
    if (!sub) {
      detailView.hidden = true;
      mainView.hidden = false;
      renderStateView(stateId);
      window.scrollTo(0, 0);
      return;
    }
    mainView.hidden = true;
    detailView.hidden = false;
    const parts = sub.split("/");
    const type = parts[0];
    const id = decodeURIComponent(parts.slice(1).join("/"));
    if (type === "vendor") renderStateVendorDetail(stateId, id);
    else if (type === "candidate") renderStateCandidateDetail(stateId, id);
    else {
      detailView.innerHTML = "";
      detailView.appendChild(stateBackLink(stateId));
      detailView.appendChild(el("p", { text: "Page not found." }));
    }
    window.scrollTo(0, 0);
  }

  function renderStateVendorsCard(stateId) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const data = STATE_DATA[stateId];
    const c = colors();
    const eraFilter = eraFilterList();
    const shownVendors = data.vendors.filter((v) => eraFilter.includes(v.era));
    const nLegacyHidden = data.vendors.filter((v) => v.era === "legacy" && v.amount_high > 0).length;
    const rows = shownVendors.slice(0, 20);
    const labels = rows.map((r) => r.name + (r.era === "legacy" ? " (legacy)" : ""));
    const chartData = rows.map((r) => r.amount_high);

    const card = el("div", { className: "card" });
    const toolbar = el("div", { className: "card-toolbar" });
    const toggleBtn = el("button", { className: "btn-table-toggle", text: "View as table" });
    toolbar.appendChild(toggleBtn);
    card.appendChild(toolbar);
    card.appendChild(stateCardTitle(stateId, "AI-related expenditures by vendor, " + stateYearRangeLabel(data.meta)));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "Every " + cfg.sourceShort + " expenditure record statewide for the window, matched against the same taxonomy used on the Federal tab." +
          (includeLegacy ? " Legacy-era vendors are currently included, via the toggle above." : " " + nLegacyHidden + " legacy-era vendor" + (nLegacyHidden === 1 ? "" : "s") + " with disclosed spending are hidden by default (toggle above to include them)."),
      })
    );

    const chartHolder = el("div", { className: "chart-holder tall" });
    chartHolder.style.height = Math.max(320, rows.length * 26) + "px";
    const canvas = el("canvas", { id: "chart-state-vendors" });
    chartHolder.appendChild(canvas);
    const tableHolder = el("div", { className: "table-holder", attrs: { hidden: "" } });
    card.appendChild(chartHolder);
    card.appendChild(tableHolder);

    toggleBtn.addEventListener("click", () => {
      const showingTable = !tableHolder.hidden;
      tableHolder.hidden = showingTable;
      chartHolder.hidden = !showingTable;
      toggleBtn.textContent = showingTable ? "View as table" : "View chart";
    });

    tableHolder.appendChild(
      buildTable(
        [
          { label: "Vendor", link: (r) => "#/" + stateId + "/vendor/" + r.id, render: (r) => r.name },
          { label: "Type", render: (r) => VENDOR_GROUP_LABEL[r.group] || r.group },
          { label: "Era", render: (r) => r.era },
          { label: "High-confidence $", num: true, render: (r) => fmtUSD2.format(r.amount_high) },
          { label: "Lower-confidence $", num: true, render: (r) => (r.amount_medium > 0 ? fmtUSD2.format(r.amount_medium) : "—") },
          { label: "Records", num: true, render: (r) => fmtInt.format(r.records) },
          { label: "Filers", num: true, render: (r) => fmtInt.format(r.filers) },
          { label: "D:R ratio", num: true, render: (r) => fmtPartyRatio(r) },
        ],
        shownVendors
      )
    );

    setTimeout(() => {
      makeChart("chart-state-vendors", {
        type: "bar",
        data: { labels, datasets: [{ label: "Disclosed spend", data: chartData, backgroundColor: cssVar("--" + stateId + "-accent"), borderRadius: 4, barThickness: 16 }] },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          onClick: (evt, elements, chart) => {
            const pts = chart.getElementsAtEventForMode(evt, "nearest", { intersect: true }, false);
            if (pts.length) location.hash = "#/" + stateId + "/vendor/" + rows[pts[0].index].id;
          },
          onHover: (evt, elements) => {
            evt.native.target.style.cursor = elements.length ? "pointer" : "default";
          },
          plugins: {
            legend: { display: false },
            tooltip: Object.assign(tooltipBase(), {
              callbacks: {
                label: (ctx) => {
                  const r = rows[ctx.dataIndex];
                  return [
                    fmtUSD2.format(r.amount_high) + " · " + fmtInt.format(r.records) + " records · " + fmtInt.format(r.filers) + " filers",
                    r.amount_medium > 0 ? "+" + fmtUSD2.format(r.amount_medium) + " lower-confidence signal" : "",
                  ].filter(Boolean);
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
    }, 0);

    return card;
  }

  function renderStateTrendCard(stateId) {
    const data = STATE_DATA[stateId];
    const card = el("div", { className: "card" });

    function renderContent() {
      card.innerHTML = "";
      const c = colors();
      // Legacy-vendor toggle picks between each year's all-eras figures and
      // its "_ex_legacy" (generative-only) ones -- same rule as every other
      // era-filtered Federal chart: a record counts as generative if at
      // least one of its matched vendors is generative-era.
      const rows = data.time_series.map((r) =>
        includeLegacy
          ? r
          : { year: r.year, total: r.total_ex_legacy, records: r.records_ex_legacy, total_expenditure: r.total_expenditure_ex_legacy }
      );
      const mode = viewModes.stateTrends;

      const toolbar = el("div", { className: "view-toggle", attrs: { "data-toggle-group": "state-trends" } });
      const dollarBtn = el("button", { className: "btn-view-mode" + (mode === "dollar" ? " is-active" : ""), text: "$ amount" });
      const pctBtn = el("button", { className: "btn-view-mode" + (mode === "pct" ? " is-active" : ""), text: "% of total spend" });
      dollarBtn.addEventListener("click", () => {
        viewModes.stateTrends = "dollar";
        renderContent();
      });
      pctBtn.addEventListener("click", () => {
        viewModes.stateTrends = "pct";
        renderContent();
      });
      toolbar.appendChild(dollarBtn);
      toolbar.appendChild(pctBtn);
      card.appendChild(toolbar);

      card.appendChild(stateCardTitle(stateId, "Disclosed AI-vendor spending by year"));
      card.appendChild(
        el("p", {
          className: "note",
          text:
            (mode === "pct"
              ? "AI-vendor spend as a share of that year's total reported spend by the filers who used an AI vendor that year."
              : "") + (includeLegacy ? " All eras, all matched vendors." : " Generative-era vendors only -- toggle above to include legacy-era vendors."),
        })
      );
      const chartHolder = el("div", { className: "chart-holder" });
      chartHolder.appendChild(el("canvas", { id: "chart-state-trend" }));
      card.appendChild(chartHolder);

      const values = rows.map((r) => (mode === "pct" ? (r.total_expenditure > 0 ? (r.total / r.total_expenditure) * 100 : 0) : r.total));
      const pctDigits = pctDecimalsFor(Math.max(0, ...values));
      const fmtAxis = mode === "pct" ? (v) => v.toFixed(pctDigits) + "%" : fmtUSD0.format;
      const fmtVal = mode === "pct" ? (v) => fmtPct(v, pctDigits) : fmtUSD0.format;

      setTimeout(() => {
        makeChart("chart-state-trend", {
          type: "line",
          data: {
            labels: rows.map((r) => String(r.year)),
            datasets: [
              {
                label: "Disclosed AI-vendor spend",
                data: values,
                borderColor: cssVar("--" + stateId + "-accent"),
                backgroundColor: cssVar("--" + stateId + "-accent"),
                tension: 0.25,
                pointRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: Object.assign(tooltipBase(), {
                callbacks: {
                  label: (ctx) => {
                    const r = rows[ctx.dataIndex];
                    const base = fmtVal(values[ctx.dataIndex]) + " · " + fmtInt.format(r.records) + " records";
                    return mode === "pct" ? base + " · " + fmtUSD0.format(r.total) + " of " + fmtUSD0.format(r.total_expenditure) : base;
                  },
                },
              }),
            },
            scales: {
              x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
              y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtAxis }, border: { display: false } },
            },
          },
        });
      }, 0);
    }

    renderContent();
    return card;
  }

  // A vendor's own detail page has its own party split (see
  // renderStateVendorDetail); this page-level pie/line pair covers overall
  // Democratic-vs-Republican AI-vendor spend across every matched record,
  // not broken out per vendor.
  function renderStatePartyPieCard(stateId) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const data = STATE_DATA[stateId];
    const c = colors();
    const ps = includeLegacy ? data.party_split : data.party_split_ex_legacy;
    const filersShown = includeLegacy ? data.stats.filers_with_ai_spend : data.stats.filers_with_ai_spend_ex_legacy;
    const card = el("div", { className: "card" });
    card.appendChild(stateCardTitle(stateId, "Party split"));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "Democratic vs. Republican, by filer party (" + cfg.sourceShort + "'s own filer record, not a text match): " +
          fmtPartyRatio({ dem_amount: ps.dem_amount, rep_amount: ps.rep_amount, dem_rep_ratio: ps.dem_rep_ratio }) +
          (ps.dem_rep_ratio !== null ? " ratio of Democratic to Republican spending." : ".") +
          " " +
          fmtInt.format(ps.filers_with_known_party) +
          " of " +
          fmtInt.format(filersShown) +
          " matched filers have a known major-party affiliation" +
          (includeLegacy ? "" : " (generative-era vendors only)") +
          ".",
      })
    );
    const chartHolder = el("div", { className: "chart-holder" });
    chartHolder.appendChild(el("canvas", { id: "chart-state-party-pie" }));
    card.appendChild(chartHolder);

    setTimeout(() => {
      const slices = [
        { party: "Democratic", amount: ps.dem_amount },
        { party: "Republican", amount: ps.rep_amount },
      ].filter((s) => s.amount > 0);
      makeChart("chart-state-party-pie", {
        type: "pie",
        data: {
          labels: slices.map((s) => s.party),
          datasets: [{ data: slices.map((s) => s.amount), backgroundColor: slices.map((s) => c.party[s.party] || c.muted) }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: Object.assign({ position: "bottom" }, legendBase()),
            tooltip: Object.assign(tooltipBase(), {
              callbacks: {
                label: (ctx) => {
                  const total = slices.reduce((a, s) => a + s.amount, 0);
                  return ctx.label + ": " + fmtUSD2.format(ctx.parsed) + " (" + fmtPct((ctx.parsed / total) * 100, 1) + ")";
                },
              },
            }),
          },
        },
      });
    }, 0);

    return card;
  }

  function renderStatePartyTrendCard(stateId) {
    const data = STATE_DATA[stateId];
    const c = colors();
    const rows = (includeLegacy ? data.time_series_by_party : data.time_series_by_party_ex_legacy) || [];
    const card = el("div", { className: "card" });
    card.appendChild(stateCardTitle(stateId, "Party spending over time"));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "Democratic vs. Republican AI-vendor spend by year, same filer-party lookup as the pie chart." +
          (includeLegacy ? "" : " Generative-era vendors only."),
      })
    );
    const chartHolder = el("div", { className: "chart-holder" });
    chartHolder.appendChild(el("canvas", { id: "chart-state-party-trend" }));
    card.appendChild(chartHolder);

    setTimeout(() => {
      const years = Array.from(new Set(rows.map((r) => r.year))).sort((a, b) => a - b);
      const seriesByParty = {};
      ["Democratic", "Republican"].forEach((p) => (seriesByParty[p] = rows.filter((r) => r.party === p)));
      makeChart("chart-state-party-trend", {
        type: "line",
        data: {
          labels: years.map(String),
          datasets: Object.keys(seriesByParty)
            .filter((p) => seriesByParty[p].length)
            .map((p) => ({
              label: p,
              data: years.map((y) => (seriesByParty[p].find((r) => r.year === y) || {}).amount || 0),
              borderColor: c.party[p],
              backgroundColor: c.party[p],
              borderWidth: 2,
              pointRadius: 4,
              tension: 0.15,
            })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: Object.assign({ position: "top" }, legendBase()),
            tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => ctx.dataset.label + ": " + fmtUSD2.format(ctx.parsed.y) } }),
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
            y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
          },
        },
      });
    }, 0);

    return card;
  }

  // OCPF-only: no other state's disclosure system carries a real filed
  // date on each report the way OCPF does, so this card only ever renders
  // for stateId === "ma" (gated by data.weekly_histogram existing at all
  // -- see renderStateView).
  function renderStateWeeklyCard(stateId) {
    const data = STATE_DATA[stateId];
    const card = el("div", { className: "card" });
    const toolbar = el("div", { className: "card-toolbar" });
    const toggleBtn = el("button", { className: "btn-table-toggle", text: "View as table" });
    toolbar.appendChild(toggleBtn);
    card.appendChild(toolbar);
    card.appendChild(stateCardTitle(stateId, "Weekly disclosure timeline"));
    card.appendChild(
      el("p", {
        className: "note",
        text: "Every matched expenditure, all confidence tiers and eras (not filtered by the legacy-vendor toggle), binned by week: when the expenditure itself happened vs. when OCPF's own record shows the covering report was filed (a real filed date from OCPF, not an approximation).",
      })
    );
    const chartHolder = el("div", { className: "chart-holder", attrs: { "data-panel": "state-weekly" } });
    chartHolder.appendChild(el("canvas", { id: "chart-state-weekly" }));
    const tableHolder = el("div", { className: "table-holder", attrs: { "data-panel": "state-weekly", hidden: "" } });
    card.appendChild(chartHolder);
    card.appendChild(tableHolder);

    toggleBtn.addEventListener("click", () => {
      const showingTable = !tableHolder.hidden;
      tableHolder.hidden = showingTable;
      chartHolder.hidden = !showingTable;
      toggleBtn.textContent = showingTable ? "View as table" : "View chart";
    });

    setTimeout(() => {
      renderWeeklyHistogram("chart-state-weekly", "state-weekly", data.weekly_histogram, cssVar("--" + stateId + "-accent"), cssVar("--text-muted"));
    }, 0);

    return card;
  }

  function renderStateNotableCard(stateId) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const data = STATE_DATA[stateId];
    const card = el("div", { className: "card" });
    card.appendChild(stateCardTitle(stateId, "Individual disclosed payments, largest first"));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "Every matched record's own " + cfg.sourceShort + " filing is one click away via the source link. Unlike the charts above, this table is NOT filtered by the legacy-vendor toggle -- it always shows every confidence tier and era (see the Vendor and Confidence columns), so every disclosed payment stays auditable.",
      })
    );
    card.appendChild(
      buildTable(
        [
          { label: "Date", render: (r) => r.date },
          { label: "Filer", link: (r) => "#/" + stateId + "/candidate/" + r.filer_id, render: (r) => r.filer_name },
          { label: "Party", render: (r) => r.filer_party },
          { label: "Vendor", cell: (r) => stateVendorLinksCell(stateId, r.vendor_ids, r.vendor_names) },
          { label: "Confidence", cell: (r) => confidencePill(r.confidences.indexOf("medium") !== -1 ? "medium" : "high") },
          { label: "Amount", num: true, render: (r) => fmtUSD2.format(r.amount) },
          { label: "Purpose", render: (r) => r.purpose || "—" },
          { label: "Source", link: (r) => r.source_link, external: true, render: (r) => (r.source_link ? "View ↗" : "—") },
        ],
        data.notable_records
      )
    );
    return card;
  }

  function stateDetailCard(titleText, canvasId, noteText) {
    const card = el("div", { className: "card" });
    card.appendChild(el("h3", { text: titleText }));
    if (noteText) card.appendChild(el("p", { className: "note", text: noteText }));
    card.appendChild(el("div", { className: "chart-holder", children: [el("canvas", { id: canvasId })] }));
    return card;
  }

  function renderStateVendorDetail(stateId, id) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const view = document.getElementById("state-detail-view");
    view.innerHTML = "";
    const v = STATE_DATA[stateId].vendors_detail[id];
    view.appendChild(stateBackLink(stateId));
    if (!v) {
      view.appendChild(el("p", { text: "Vendor not found in the " + cfg.label + " AI-spend dataset." }));
      return;
    }
    const c = colors();
    const accent = cssVar("--" + stateId + "-accent");

    const header = el("div", { className: "detail-header" });
    const h2 = el("h2", { text: v.name });
    h2.appendChild(el("span", { className: "pill", text: VENDOR_GROUP_LABEL[v.group] || v.group }));
    if (v.era === "legacy") h2.appendChild(el("span", { className: "pill pill-legacy", text: "Legacy (pre-generative AI)" }));
    header.appendChild(h2);
    if (v.homepage) {
      header.appendChild(el("a", { className: "entity-link", href: v.homepage, text: "Vendor website ↗", attrs: { target: "_blank", rel: "noopener" } }));
    }
    view.appendChild(header);
    view.appendChild(
      el("p", { className: "lede", text: "Every " + cfg.sourceShort + " expenditure record naming this vendor, statewide, for the " + stateYearRangeLabel(STATE_DATA[stateId].meta) + " window. See methodology for what counts as a match." })
    );

    const stats = el("div", { className: "detail-stat-row" });
    stats.appendChild(statTile("Total disclosed spending", fmtUSD0.format(v.total), fmtInt.format(v.records_count) + " disbursement records"));
    stats.appendChild(statTile("Filers paying this vendor", fmtInt.format(v.filers_count)));
    view.appendChild(stats);

    const grid = el("div", { className: "card-grid" });
    grid.appendChild(stateDetailCard("Spending over time", "state-detail-chart-ts"));
    grid.appendChild(stateDetailCard("Party split", "state-detail-chart-party", "Democratic vs. Republican, by filer party. “Unknown” is filers " + cfg.sourceShort + " doesn't mark with a major-party affiliation, so the slices add up to this vendor's full total."));
    view.appendChild(grid);

    if (v.time_series_by_party && v.time_series_by_party.length) {
      view.appendChild(el("div", { className: "card-grid single", children: [stateDetailCard("Party spending over time", "state-detail-chart-party-trend")] }));
    }

    const filerRowsAll = v.by_filer.map((r) => Object.assign({}, r));
    const filerRows = sortRows(filerRowsAll, sortState.stateVendorFilers);
    const filerHeaders = withSort(
      "stateVendorFilers",
      [
        { label: "Filer", sortKey: "filer_name", link: (r) => "#/" + stateId + "/candidate/" + r.filer_id, render: (r) => r.filer_name },
        { label: "Party", sortKey: "filer_party", render: (r) => r.filer_party },
        { label: "Amount", sortKey: "amount", num: true, render: (r) => fmtUSD2.format(r.amount) },
        { label: "Records", sortKey: "count", num: true, render: (r) => fmtInt.format(r.count) },
      ],
      () => renderStateVendorDetail(stateId, id)
    );
    const filerCard = el("div", { className: "card" });
    filerCard.appendChild(el("h3", { text: "Filers paying " + v.name }));
    filerCard.appendChild(buildTable(filerHeaders, filerRows, { sort: sortState.stateVendorFilers }));
    view.appendChild(el("div", { className: "card-grid single", children: [filerCard] }));

    if (v.records && v.records.length) {
      const recRowsAll = v.records.map((r) => Object.assign({}, r, { date_sort: mdySortValue(r.date) }));
      const recRows = sortRows(recRowsAll, sortState.stateVendorRecords);
      const recHeaders = withSort(
        "stateVendorRecords",
        [
          { label: "Date", sortKey: "date_sort", render: (r) => r.date },
          { label: "Filer", sortKey: "filer_name", link: (r) => "#/" + stateId + "/candidate/" + r.filer_id, render: (r) => r.filer_name },
          { label: "Party", sortKey: "filer_party", render: (r) => r.filer_party },
          { label: "Confidence", sortKey: "confidence", cell: (r) => confidencePill(r.confidence) },
          { label: "Amount", sortKey: "amount", num: true, render: (r) => fmtUSD2.format(r.amount) },
          { label: "Purpose", sortKey: "purpose", render: (r) => r.purpose || "—" },
          { label: "Source", sortKey: null, link: (r) => r.source_link, external: true, render: (r) => (r.source_link ? "View ↗" : "—") },
        ],
        () => renderStateVendorDetail(stateId, id)
      );
      const recordsCard = el("div", { className: "card" });
      recordsCard.appendChild(el("h3", { text: "Individual disbursements" }));
      recordsCard.appendChild(
        el("p", {
          className: "note",
          text: "Every matched record's own " + cfg.sourceShort + " filing is one click away via the source link, largest first" + (v.records.length >= MAX_DETAIL_RECORDS_MA ? " (capped at " + fmtInt.format(MAX_DETAIL_RECORDS_MA) + " records)" : "") + ".",
        })
      );
      recordsCard.appendChild(buildTable(recHeaders, recRows, { sort: sortState.stateVendorRecords }));
      view.appendChild(el("div", { className: "card-grid single", children: [recordsCard] }));
    }

    // charts
    const years = v.time_series.map((r) => r.year).sort((a, b) => a - b);
    makeChart("state-detail-chart-ts", {
      type: "line",
      data: {
        labels: years.map(String),
        datasets: [
          {
            label: v.name,
            data: years.map((y) => (v.time_series.find((r) => r.year === y) || {}).amount || 0),
            borderColor: accent,
            backgroundColor: accent,
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

    const otherAmount = Math.max(0, v.total - v.dem_amount - v.rep_amount);
    const partySlices = [
      { label: "Democratic", amount: v.dem_amount, color: c.party.Democratic },
      { label: "Republican", amount: v.rep_amount, color: c.party.Republican },
      { label: "Unknown", amount: otherAmount, color: c.muted },
    ].filter((s) => s.amount > 0);
    makeChart("state-detail-chart-party", {
      type: "pie",
      data: { labels: partySlices.map((s) => s.label), datasets: [{ data: partySlices.map((s) => s.amount), backgroundColor: partySlices.map((s) => s.color) }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: Object.assign({ position: "bottom" }, legendBase()),
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: (ctx) => {
                const total = partySlices.reduce((a, s) => a + s.amount, 0);
                return ctx.label + ": " + fmtUSD0.format(ctx.parsed) + " (" + fmtPct((ctx.parsed / total) * 100, 1) + ")";
              },
            },
          }),
        },
      },
    });

    if (v.time_series_by_party && v.time_series_by_party.length) {
      const partyYears = Array.from(new Set(v.time_series_by_party.map((r) => r.year))).sort((a, b) => a - b);
      const seriesByParty = {};
      ["Democratic", "Republican"].forEach((p) => (seriesByParty[p] = v.time_series_by_party.filter((r) => r.party === p)));
      makeChart("state-detail-chart-party-trend", {
        type: "line",
        data: {
          labels: partyYears.map(String),
          datasets: Object.keys(seriesByParty)
            .filter((p) => seriesByParty[p].length)
            .map((p) => ({
              label: p,
              data: partyYears.map((y) => (seriesByParty[p].find((r) => r.year === y) || {}).amount || 0),
              borderColor: c.party[p],
              backgroundColor: c.party[p],
              borderWidth: 2,
              pointRadius: 4,
              tension: 0.15,
            })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: Object.assign({ position: "top" }, legendBase()),
            tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => ctx.dataset.label + ": " + fmtUSD0.format(ctx.parsed.y) } }),
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
            y: { grid: { color: c.grid }, ticks: { color: c.text, callback: fmtUSD0.format }, border: { display: false } },
          },
        },
      });
    }
  }

  function renderStateCandidateDetail(stateId, id) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const view = document.getElementById("state-detail-view");
    view.innerHTML = "";
    const f = STATE_DATA[stateId].filers_detail[id];
    view.appendChild(stateBackLink(stateId));
    if (!f) {
      view.appendChild(el("p", { text: "Filer not found in the " + cfg.label + " AI-spend dataset." }));
      return;
    }
    const c = colors();
    const accent = cssVar("--" + stateId + "-accent");

    const header = el("div", { className: "detail-header" });
    const h2 = el("h2", { text: f.name });
    h2.appendChild(el("span", { className: "pill", text: f.party }));
    header.appendChild(h2);
    view.appendChild(header);
    view.appendChild(
      el("p", { className: "lede", text: "Every " + cfg.sourceShort + " expenditure record naming an AI vendor from this filer, statewide, for the " + stateYearRangeLabel(STATE_DATA[stateId].meta) + " window." })
    );

    const stats = el("div", { className: "detail-stat-row" });
    stats.appendChild(statTile("Total disclosed AI-vendor spending", fmtUSD0.format(f.total), fmtInt.format(f.records_count) + " disbursement records"));
    stats.appendChild(statTile("Total reported expenditure", f.total_expenditure ? fmtUSD0.format(f.total_expenditure) : "—"));
    stats.appendChild(statTile("AI as % of total spend", fmtPct(f.pct_ai, 3)));
    stats.appendChild(statTile("Distinct AI vendors used", fmtInt.format(f.vendor_ids.length)));
    view.appendChild(stats);

    view.appendChild(el("div", { className: "card-grid single", children: [stateDetailCard("Spending over time", "state-cand-chart-ts")] }));

    if (f.records && f.records.length) {
      const recRowsAll = f.records.map((r) =>
        Object.assign({}, r, { display_vendor: r.vendor_names.join(", "), date_sort: mdySortValue(r.date) })
      );
      const recRows = sortRows(recRowsAll, sortState.stateCandidateRecords);
      const recHeaders = withSort(
        "stateCandidateRecords",
        [
          { label: "Date", sortKey: "date_sort", render: (r) => r.date },
          { label: "Vendor", sortKey: "display_vendor", cell: (r) => stateVendorLinksCell(stateId, r.vendor_ids, r.vendor_names) },
          { label: "Confidence", sortKey: null, cell: (r) => confidencePill(r.confidences.indexOf("medium") !== -1 ? "medium" : "high") },
          { label: "Amount", sortKey: "amount", num: true, render: (r) => fmtUSD2.format(r.amount) },
          { label: "Purpose", sortKey: "purpose", render: (r) => r.purpose || "—" },
          { label: "Source", sortKey: null, link: (r) => r.source_link, external: true, render: (r) => (r.source_link ? "View ↗" : "—") },
        ],
        () => renderStateCandidateDetail(stateId, id)
      );
      const recordsCard = el("div", { className: "card" });
      recordsCard.appendChild(el("h3", { text: "Individual disbursements" }));
      recordsCard.appendChild(
        el("p", {
          className: "note",
          text: "Every matched record's own " + cfg.sourceShort + " filing is one click away via the source link, largest first" + (f.records.length >= MAX_DETAIL_RECORDS_MA ? " (capped at " + fmtInt.format(MAX_DETAIL_RECORDS_MA) + " records)" : "") + ".",
        })
      );
      recordsCard.appendChild(buildTable(recHeaders, recRows, { sort: sortState.stateCandidateRecords }));
      view.appendChild(el("div", { className: "card-grid single", children: [recordsCard] }));
    }

    const years = f.time_series.map((r) => r.year).sort((a, b) => a - b);
    makeChart("state-cand-chart-ts", {
      type: "line",
      data: {
        labels: years.map(String),
        datasets: [
          {
            label: f.name,
            data: years.map((y) => (f.time_series.find((r) => r.year === y) || {}).amount || 0),
            borderColor: accent,
            backgroundColor: accent,
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
  }

  function renderStateMethodologyCard(stateId) {
    const meta = STATE_DATA[stateId].meta;
    const sourcesCard = el("div", { className: "card" });
    sourcesCard.appendChild(stateCardTitle(stateId, "Data sources"));
    const sourcesList = el("ul", { className: "notes" });
    meta.sources.forEach((s) => sourcesList.appendChild(el("li", { text: s })));
    sourcesCard.appendChild(sourcesList);

    const notesCard = el("div", { className: "card" });
    notesCard.appendChild(stateCardTitle(stateId, "Notes & limitations"));
    const notesList = el("ul", { className: "notes" });
    meta.methodology_notes.forEach((s) => notesList.appendChild(el("li", { text: s })));
    notesCard.appendChild(notesList);

    return el("div", { className: "card-grid", children: [sourcesCard, notesCard] });
  }

  function renderStateView(stateId) {
    const cfg = STATE_CONFIG_BY_ID[stateId];
    const view = document.getElementById("state-view");
    view.innerHTML = "";
    const data = STATE_DATA[stateId];
    const meta = data.meta;
    const stats = data.stats;

    view.appendChild(
      el("div", {
        className: "state-banner",
        attrs: { style: "--accent:var(--" + stateId + "-accent);--accent-soft:var(--" + stateId + "-accent-soft)" },
        children: [
          el("span", { text: "You're viewing the " }),
          el("strong", { text: cfg.label }),
          el("span", {
            text:
              " tab — a separate dataset drawn from " +
              cfg.bannerSourceLabel +
              ", covering the " +
              meta.date_range.start +
              " through " +
              (meta.date_range.end || "present") +
              " window" +
              cfg.cycleWindowNote +
              ". Not merged with, and not directly comparable dollar-for-dollar to, the Federal tab.",
          }),
        ],
      })
    );

    const statRow = el("div", { className: "stat-row" });
    const recordsScannedSub =
      typeof meta.records_scanned === "object"
        ? fmtInt.format(meta.records_scanned.expenditures) + " expenditures + " + fmtInt.format(meta.records_scanned.subvendor) + " subvendor payments"
        : null;
    statRow.appendChild(statTile("Records scanned statewide", fmtInt.format(totalRecordsScanned(meta)), recordsScannedSub));
    statRow.appendChild(
      statTile(
        "Disclosed AI-vendor spend",
        fmtUSD0.format(includeLegacy ? stats.total_all_eras : stats.total_generative),
        (includeLegacy ? "all eras" : "generative-era vendors only") + " -- toggle above to include legacy-era vendors"
      )
    );
    statRow.appendChild(
      statTile(
        "Filers with AI-vendor spend",
        fmtInt.format(includeLegacy ? stats.filers_with_ai_spend : stats.filers_with_ai_spend_ex_legacy),
        "out of " + fmtInt.format(stats.total_filers_with_activity) + " filers with any expenditure activity"
      )
    );
    // OCPF-only extra: its $5,000/$500 subcontractor-disclosure layer has
    // no equivalent in the other states' disclosure data (see
    // pipeline/lib/build_state_dataset.py's own module docstring), so
    // `subvendor` only ever exists on the Massachusetts dataset.
    if (data.subvendor) {
      statRow.appendChild(statTile("Subvendor payments tested", fmtInt.format(data.subvendor.records_scanned), "OCPF's $5,000/$500 subcontractor-disclosure layer, no federal equivalent"));
    }
    view.appendChild(statRow);

    view.appendChild(el("div", { className: "card-grid single", children: [renderStateVendorsCard(stateId)] }));
    view.appendChild(el("div", { className: "card-grid single", children: [renderStateTrendCard(stateId)] }));
    if (data.party_split) {
      view.appendChild(el("div", { className: "card-grid", children: [renderStatePartyPieCard(stateId), renderStatePartyTrendCard(stateId)] }));
    }
    if (data.weekly_histogram) {
      view.appendChild(el("div", { className: "card-grid single", children: [renderStateWeeklyCard(stateId)] }));
    }
    view.appendChild(el("div", { className: "card-grid single", children: [renderStateNotableCard(stateId)] }));
    view.appendChild(renderStateMethodologyCard(stateId));

    view.appendChild(
      el("p", {
        className: "lede",
        text:
          "Full pipeline code and the shared vendor/category taxonomy (pipeline/config/vendors.yaml) are in the GitHub repository. Dataset generated " +
          new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) +
          " UTC.",
      })
    );
  }

  // ---- Compare tab: one vendor table spanning both datasets ----

  // Short display text for the compare table's Category column -- same ids
  // as CATEGORY_LABELS (and vendors.yaml's own `tags`), just tighter for a
  // narrow table cell than the full disbursement-purpose label text.
  const TAG_SHORT_LABELS = {
    advertising_creative: "Advertising/creative",
    communications_copy: "Comms copy",
    synthetic_media: "Synthetic media",
    research_strategy: "Research/strategy",
    fundraising: "Fundraising",
    data_targeting: "Voter data/targeting",
    administrative_productivity: "Admin/productivity",
    unspecified: "Unspecified",
  };
  // Persists across re-renders like the legacy toggle and confidence
  // toggle do -- switching tabs and coming back keeps the filter active
  // rather than silently dropping it.
  let compareFilterTag = null;

  function tagChips(tags) {
    const frag = document.createDocumentFragment();
    (tags || []).forEach((t) => {
      const label = TAG_SHORT_LABELS[t] || t;
      const isActive = compareFilterTag === t;
      const chip = el("button", {
        className: "tag-chip" + (isActive ? " is-active" : ""),
        text: label,
        attrs: { type: "button", title: (isActive ? "Clear the \"" + label + "\" filter" : "Filter the table to \"" + label + "\"") },
      });
      chip.addEventListener("click", () => {
        compareFilterTag = isActive ? null : t;
        renderCompareView();
      });
      frag.appendChild(chip);
    });
    return frag;
  }

  // A near-zero (but nonzero) earlier-half baseline blows a plain
  // percent-change up to absurd, meaningless magnitudes (a vendor going
  // from $4 to $5,000 is not "a 124,900% increase" in any useful sense);
  // computeMomentum treats anything under this floor as too small a base
  // to rate, the same as an exact zero.
  const MOMENTUM_BASE_FLOOR = 25;

  // A vendor's own time series (Federal: per-cycle; MA: per-year) split in
  // half by period count, comparing the more recent half's total against
  // the earlier half's as a growth rate. `isNew` flags a vendor with no
  // meaningful spend in the earlier half and some in the recent half -- a
  // ratio isn't usefully computable off that small a base, but "went from
  // nothing to something" is itself the signal worth surfacing, so it's
  // returned separately rather than folded into `value` as a fake number.
  function computeMomentum(series, periodKey) {
    if (!series || series.length < 2) return { value: null, isNew: false };
    const sorted = series.slice().sort((a, b) => a[periodKey] - b[periodKey]);
    const mid = Math.ceil(sorted.length / 2);
    const firstSum = sorted.slice(0, mid).reduce((a, r) => a + r.amount, 0);
    const secondSum = sorted.slice(mid).reduce((a, r) => a + r.amount, 0);
    if (firstSum < MOMENTUM_BASE_FLOOR) return { value: null, isNew: secondSum > 0 };
    return { value: (secondSum - firstSum) / firstSum, isNew: false };
  }

  // Combines each dataset's own momentum into one figure, weighted by how
  // much of the vendor's high-confidence spend sits in that dataset -- a
  // vendor spent almost entirely in Massachusetts has its blended momentum
  // driven mostly by the Massachusetts trend, and vice versa.
  function blendMomentum(fed, fedAmt, ma, maAmt) {
    const parts = [];
    if (fed.value !== null && fedAmt > 0) parts.push([fed.value, fedAmt]);
    if (ma.value !== null && maAmt > 0) parts.push([ma.value, maAmt]);
    const isNew = fed.isNew || ma.isNew;
    if (!parts.length) return { value: null, isNew };
    const totalWeight = parts.reduce((a, p) => a + p[1], 0);
    const value = parts.reduce((a, p) => a + p[0] * p[1], 0) / totalWeight;
    return { value, isNew };
  }

  function momentumBadge(r) {
    if (r.momentum_value === null && !r.momentum_is_new) return el("span", { className: "text-muted", text: "—" });
    if (r.momentum_value === null && r.momentum_is_new) return el("span", { className: "trend-up", text: "▲ New" });
    const pct = r.momentum_value * 100;
    const cls = pct > 3 ? "trend-up" : pct < -3 ? "trend-down" : "trend-flat";
    const arrow = pct > 3 ? "▲" : pct < -3 ? "▼" : "▶";
    const prefix = r.momentum_is_new ? "New, " : "";
    // A vendor whose earlier half was real but tiny (say $30) can still
    // multiply hundreds-fold once volume picks up -- a five- or six-digit
    // percentage is technically correct but unreadable, so above 3x growth
    // this switches to multiplier notation ("14.2x"), which is how that
    // kind of jump normally gets described.
    const label = r.momentum_value >= 3 ? (r.momentum_value + 1).toFixed(1) + "x" : (pct >= 0 ? "+" : "") + pct.toFixed(0) + "%";
    return el("span", { className: cls, text: arrow + " " + prefix + label });
  }

  // One row per vendor id found on either tab -- a vendor matched only on
  // Federal (or only in the states) still gets a row, with "—" for the
  // side it has no data on, so the table also shows which tools are
  // federal-only or state-only, not just the ones that overlap. The
  // "states" side reads STATES_DATA (the four-state union built by
  // pipeline/build_dataset_states.py), whose vendor rows already carry a
  // per-state by_state breakdown and a combined time_series, so this
  // doesn't need to merge four separate state datasets itself.
  function buildCompareRows() {
    const byId = {};
    DATA.vendors_overall.forEach((v) => {
      byId[v.id] = Object.assign({ id: v.id }, byId[v.id], {
        name: v.name,
        group: v.group,
        era: v.era,
        tags: v.tags || [],
        description: v.description,
        fed_amount: v.amount_high,
        fed_amount_medium: v.amount_medium,
      });
    });
    STATES_DATA.vendors.forEach((v) => {
      const existing = byId[v.id];
      byId[v.id] = Object.assign({ id: v.id }, existing, {
        name: (existing && existing.name) || v.name,
        group: (existing && existing.group) || v.group,
        era: (existing && existing.era) || v.era,
        tags: (existing && existing.tags && existing.tags.length ? existing.tags : v.tags) || [],
        description: (existing && existing.description) || v.description,
        states_amount: v.amount_high,
        states_amount_medium: v.amount_medium,
        by_state: v.by_state || {},
        states_series: v.time_series || [],
      });
    });

    return Object.values(byId).map((r) => {
      const fed_amount = r.fed_amount || 0;
      const states_amount = r.states_amount || 0;
      const fedSeries = (DATA.vendors_detail[r.id] || {}).time_series || [];
      const statesSeries = r.states_series || [];
      const fedM = computeMomentum(fedSeries, "cycle");
      const statesM = computeMomentum(statesSeries, "year");
      const momentum = blendMomentum(fedM, fed_amount, statesM, states_amount);
      return Object.assign({}, r, {
        fed_amount,
        states_amount,
        by_state: r.by_state || {},
        volume: fed_amount + states_amount,
        momentum_value: momentum.value,
        momentum_is_new: momentum.isNew,
        // A capped finite stand-in for "new" so it sorts above every real
        // growth rate without the NaN a literal Infinity - Infinity tie
        // would produce in sortRows' plain subtraction comparator.
        momentum_sort: momentum.value !== null ? momentum.value : momentum.isNew ? 10 : null,
      });
    });
  }

  // Population-based national projection: a simple population-weighted
  // scale-up of the four states this site covers (Massachusetts,
  // Washington, Colorado, California) to the full U.S. population, built
  // ahead of time by pipeline/build_projection.py from Census Bureau
  // Vintage 2024 state population estimates. Explicitly NOT a statistical
  // estimate -- see PROJECTION_DATA.meta.methodology_notes, rendered in
  // full below, for why the four covered states aren't a representative
  // sample and why the vendor-count figure in particular should be read
  // as an upper-bound-ish illustration rather than a real forecast.
  function renderProjectionSection() {
    const proj = PROJECTION_DATA;
    const meta = proj.meta;
    const covered = proj.covered;
    const projection = proj.projection;

    const spend = includeLegacy ? projection.spend_all_eras : projection.spend_generative;
    const coveredSpend = includeLegacy ? covered.spend_all_eras : covered.spend_generative;
    const filers = includeLegacy ? projection.filers_all_eras : projection.filers_generative;
    const coveredFilers = includeLegacy ? covered.filers_all_eras : covered.filers_generative;
    const vendorInstances = includeLegacy ? projection.vendor_instances_all_eras : projection.vendor_instances_generative;
    const coveredVendorInstances = includeLegacy ? covered.vendor_instances_all_eras : covered.vendor_instances_generative;
    const distinctVendors = includeLegacy ? covered.distinct_vendors_all_eras : covered.distinct_vendors_generative;

    const mainCard = el("div", { className: "card" });
    mainCard.appendChild(el("h3", { text: "National projection, scaled by population" }));
    mainCard.appendChild(
      el("p", {
        className: "note",
        text:
          "A simple population-weighted scale-up, not a statistical estimate -- see the caveats below the table. Based on the " +
          fmtInt.format(meta.covered_population) +
          " people (" +
          (meta.covered_population_share * 100).toFixed(1) +
          "% of the U.S. population) in the four states this site currently covers -- Massachusetts, Washington, Colorado, and California -- scaled " +
          meta.scale_factor.toFixed(2) +
          "x up to the full " +
          fmtInt.format(meta.us_total_population) +
          "-person U.S. population (50 states + DC, U.S. Census Bureau Vintage 2024 estimates)." +
          (includeLegacy ? " All eras, all matched vendors." : " Generative-era vendors only -- toggle above to include legacy-era vendors."),
      })
    );
    const statRow = el("div", { className: "stat-row" });
    statRow.appendChild(
      statTile(
        "Projected national AI-vendor spend",
        fmtUSD0.format(spend),
        fmtUSD0.format(coveredSpend) + " disclosed across the 4 covered states"
      )
    );
    statRow.appendChild(
      statTile(
        "Projected candidate committees using AI",
        fmtInt.format(filers),
        fmtInt.format(coveredFilers) + " identified across the 4 covered states"
      )
    );
    statRow.appendChild(
      statTile(
        "Projected vendor-adoption instances",
        fmtInt.format(vendorInstances),
        fmtInt.format(coveredVendorInstances) + " state-by-vendor pairs across the 4 covered states -- see note below"
      )
    );
    mainCard.appendChild(statRow);
    mainCard.appendChild(
      el("p", {
        className: "note",
        text:
          "“Vendor-adoption instances” is NOT a projected count of distinct vendors -- it sums each covered state's own distinct-vendor count and scales that sum by population, which overstates how many genuinely new AI tools a full 50-state count would actually turn up (most additional states would rediscover the same handful of major vendors rather than each contributing new ones). " +
          fmtInt.format(distinctVendors) +
          " distinct vendors have actually been identified across the 4 covered states so far -- a floor on the true national count, not this scaled figure.",
      })
    );
    const projCardGrid = el("div", { className: "card-grid single", children: [mainCard] });

    const stateHeaders = [
      { label: "State", render: (r) => r.label },
      { label: "Population", num: true, render: (r) => fmtInt.format(r.population) },
      { label: "Disclosed AI-vendor spend", num: true, render: (r) => fmtUSD0.format(includeLegacy ? r.spend_all_eras : r.spend_generative) },
      { label: "Candidate committees using AI", num: true, render: (r) => fmtInt.format(includeLegacy ? r.filers_all_eras : r.filers_generative) },
      { label: "Distinct vendors identified", num: true, render: (r) => fmtInt.format(includeLegacy ? r.distinct_vendors_all_eras : r.distinct_vendors_generative) },
    ];
    const stateRows = meta.covered_states.map((id) => Object.assign({ id }, proj.states[id]));
    const stateCard = el("div", { className: "card" });
    stateCard.appendChild(el("h3", { text: "The underlying numbers, by covered state" }));
    stateCard.appendChild(
      el("p", {
        className: "note",
        text: "Every figure above is built from these four rows -- summed, then divided by their combined population, then multiplied by the U.S. total. Each state's own tab has its own full methodology and record-level detail.",
      })
    );
    stateCard.appendChild(buildTable(stateHeaders, stateRows));

    const notesCard = el("div", { className: "card" });
    notesCard.appendChild(el("h3", { text: "Why this is a rough projection, not an estimate" }));
    const notesList = el("ul", { className: "notes" });
    meta.methodology_notes.forEach((s) => notesList.appendChild(el("li", { text: s })));
    notesCard.appendChild(notesList);

    return [projCardGrid, el("div", { className: "card-grid", children: [stateCard, notesCard] })];
  }

  // ---- combined States tab: a real union of the four covered states'
  // own disclosed records (see pipeline/build_dataset_states.py), the
  // state-level analog of how the Federal tab already unions House and
  // Senate races into one view. Deliberately separate from Compare
  // (Federal vs. Massachusetts specifically) and from the population
  // projection on Compare (an estimate, not a real sum).
  function statesCardTitle(text) {
    return el("h3", {
      children: [document.createTextNode(text), el("span", { className: "dataset-pill", text: "States, combined", attrs: { style: "--accent:var(--states-accent);--accent-soft:var(--states-accent-soft)" } })],
    });
  }

  function renderStatesVendorsCard() {
    const data = STATES_DATA;
    const c = colors();
    const eraFilter = eraFilterList();
    const shownVendors = data.vendors.filter((v) => eraFilter.includes(v.era));
    const nLegacyHidden = data.vendors.filter((v) => v.era === "legacy" && v.amount_high > 0).length;
    const rows = shownVendors.slice(0, 20);
    const labels = rows.map((r) => r.name + (r.era === "legacy" ? " (legacy)" : ""));
    const chartData = rows.map((r) => r.amount_high);

    const card = el("div", { className: "card" });
    const toolbar = el("div", { className: "card-toolbar" });
    const toggleBtn = el("button", { className: "btn-table-toggle", text: "View as table" });
    toolbar.appendChild(toggleBtn);
    card.appendChild(toolbar);
    card.appendChild(statesCardTitle("AI-related expenditures by vendor, combined across covered states"));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "Every covered state's own matched records, summed by vendor. Click a vendor's name (or a bar) to compare it against Federal and a population-scaled national estimate; click a state's own dollar column to open that vendor's detail page on that state's tab." +
          (includeLegacy ? " Legacy-era vendors are currently included, via the toggle above." : " " + nLegacyHidden + " legacy-era vendor" + (nLegacyHidden === 1 ? "" : "s") + " with disclosed spending are hidden by default (toggle above to include them)."),
      })
    );

    const chartHolder = el("div", { className: "chart-holder tall" });
    chartHolder.style.height = Math.max(320, rows.length * 26) + "px";
    chartHolder.appendChild(el("canvas", { id: "chart-states-vendors" }));
    const tableHolder = el("div", { className: "table-holder", attrs: { hidden: "" } });
    card.appendChild(chartHolder);
    card.appendChild(tableHolder);

    toggleBtn.addEventListener("click", () => {
      const showingTable = !tableHolder.hidden;
      tableHolder.hidden = showingTable;
      chartHolder.hidden = !showingTable;
      toggleBtn.textContent = showingTable ? "View as table" : "View chart";
    });

    const stateColumns = STATES_DATA.meta.covered_states.map((stateId) => ({
      label: STATE_CONFIG_BY_ID[stateId].label + " $",
      num: true,
      title: "High-confidence text matches to this vendor on the " + STATE_CONFIG_BY_ID[stateId].label + " tab. Click to open its detail page there.",
      link: (r) => (r.by_state[stateId] && r.by_state[stateId].amount_high > 0 ? "#/" + stateId + "/vendor/" + r.id : null),
      render: (r) => (r.by_state[stateId] && r.by_state[stateId].amount_high > 0 ? fmtUSD0.format(r.by_state[stateId].amount_high) : "—"),
    }));

    tableHolder.appendChild(
      buildTable(
        [
          { label: "Vendor", link: (r) => "#/states/vendor/" + r.id, render: (r) => r.name },
          { label: "Type", render: (r) => VENDOR_GROUP_LABEL[r.group] || r.group },
          { label: "Era", render: (r) => r.era },
          ...stateColumns,
          { label: "Combined $", num: true, render: (r) => fmtUSD0.format(r.amount_high) },
          { label: "Filers", num: true, render: (r) => fmtInt.format(r.filers) },
        ],
        shownVendors
      )
    );

    setTimeout(() => {
      makeChart("chart-states-vendors", {
        type: "bar",
        data: { labels, datasets: [{ label: "Disclosed spend", data: chartData, backgroundColor: cssVar("--states-accent"), borderRadius: 4, barThickness: 16 }] },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          onClick: (evt, elements, chart) => {
            const pts = chart.getElementsAtEventForMode(evt, "nearest", { intersect: true }, false);
            if (pts.length) location.hash = "#/states/vendor/" + rows[pts[0].index].id;
          },
          onHover: (evt, elements) => {
            evt.native.target.style.cursor = elements.length ? "pointer" : "default";
          },
          plugins: {
            legend: { display: false },
            tooltip: Object.assign(tooltipBase(), {
              callbacks: {
                label: (ctx) => {
                  const r = rows[ctx.dataIndex];
                  return STATES_DATA.meta.covered_states
                    .filter((sid) => r.by_state[sid] && r.by_state[sid].amount_high > 0)
                    .map((sid) => STATE_CONFIG_BY_ID[sid].label + ": " + fmtUSD0.format(r.by_state[sid].amount_high));
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
    }, 0);

    return card;
  }

  function renderStatesTrendCard() {
    const data = STATES_DATA;
    const c = colors();
    const rows = data.time_series.map((r) => (includeLegacy ? r : { year: r.year, total: r.total_ex_legacy, records: r.records_ex_legacy }));
    const card = el("div", { className: "card" });
    card.appendChild(statesCardTitle("Combined AI-vendor spending by year"));
    card.appendChild(
      el("p", {
        className: "note",
        text: "Every covered state's own per-year total, summed." + (includeLegacy ? " All eras, all matched vendors." : " Generative-era vendors only -- toggle above to include legacy-era vendors."),
      })
    );
    const chartHolder = el("div", { className: "chart-holder" });
    chartHolder.appendChild(el("canvas", { id: "chart-states-trend" }));
    card.appendChild(chartHolder);

    setTimeout(() => {
      makeChart("chart-states-trend", {
        type: "line",
        data: {
          labels: rows.map((r) => String(r.year)),
          datasets: [
            {
              label: "Disclosed AI-vendor spend",
              data: rows.map((r) => r.total),
              borderColor: cssVar("--states-accent"),
              backgroundColor: cssVar("--states-accent"),
              tension: 0.25,
              pointRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: Object.assign(tooltipBase(), {
              callbacks: {
                label: (ctx) => {
                  const r = rows[ctx.dataIndex];
                  return fmtUSD0.format(r.total) + " · " + fmtInt.format(r.records) + " records";
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
    }, 0);

    return card;
  }

  function renderStatesLeaderboardCard() {
    const rows = sortRows(
      STATES_DATA.states_leaderboard.map((r) => Object.assign({}, r)),
      includeLegacy ? { key: "spend_all_eras", dir: "desc" } : { key: "spend_generative", dir: "desc" }
    );
    const card = el("div", { className: "card" });
    card.appendChild(statesCardTitle("State-by-state leaderboard"));
    card.appendChild(
      el("p", {
        className: "note",
        text: "\"% of state's AI-filer spend\" divides disclosed AI-vendor spend by the same filers' own total reported expenditure that state tracks -- see each state's own tab for exactly how. Click a state's name to open its own tab.",
      })
    );
    card.appendChild(
      buildTable(
        [
          { label: "State", link: (r) => "#/" + r.id, render: (r) => r.label },
          { label: "Source", render: (r) => r.source_label },
          { label: "Disclosed AI-vendor spend", num: true, render: (r) => fmtUSD0.format(includeLegacy ? r.spend_all_eras : r.spend_generative) },
          { label: "Candidate committees using AI", num: true, render: (r) => fmtInt.format(includeLegacy ? r.filers_all_eras : r.filers_generative) },
          { label: "Distinct vendors identified", num: true, render: (r) => fmtInt.format(includeLegacy ? r.distinct_vendors_all_eras : r.distinct_vendors_generative) },
          { label: "% of state's AI-filer spend", num: true, render: (r) => fmtPct(r.pct_ai_overall, 3) },
        ],
        rows
      )
    );
    return card;
  }

  function renderStatesPartyCard() {
    const c = colors();
    const ps = includeLegacy ? STATES_DATA.party_split : STATES_DATA.party_split_ex_legacy;
    const card = el("div", { className: "card" });
    card.appendChild(statesCardTitle("Party split, combined"));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "Democratic vs. Republican, by each state's own filer-party record -- Colorado and California disclose no party field at all, so every one of their records falls under Unknown here. " +
          fmtInt.format(ps.filers_with_known_party) +
          " filers across all covered states have a known major-party affiliation" +
          (includeLegacy ? "" : " (generative-era vendors only)") +
          ".",
      })
    );
    const chartHolder = el("div", { className: "chart-holder" });
    chartHolder.appendChild(el("canvas", { id: "chart-states-party-pie" }));
    card.appendChild(chartHolder);

    setTimeout(() => {
      const slices = [
        { party: "Democratic", amount: ps.dem_amount },
        { party: "Republican", amount: ps.rep_amount },
      ].filter((s) => s.amount > 0);
      makeChart("chart-states-party-pie", {
        type: "pie",
        data: {
          labels: slices.map((s) => s.party),
          datasets: [{ data: slices.map((s) => s.amount), backgroundColor: slices.map((s) => c.party[s.party] || c.muted) }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: Object.assign({ position: "bottom" }, legendBase()),
            tooltip: Object.assign(tooltipBase(), {
              callbacks: {
                label: (ctx) => {
                  const total = slices.reduce((a, s) => a + s.amount, 0);
                  return ctx.label + ": " + fmtUSD2.format(ctx.parsed) + " (" + fmtPct((ctx.parsed / total) * 100, 1) + ")";
                },
              },
            }),
          },
        },
      });
    }, 0);

    return card;
  }

  function statesBackLink() {
    return el("a", { href: "#/states", className: "back-link", text: "← Back to States dashboard" });
  }

  // Mirrors stateRouter(): "" shows the combined States overview,
  // "vendor/<id>" shows one vendor's cross-comparison page in
  // #states-detail-view instead. No "candidate" sub-route here --
  // candidate/committee drill-down always happens on a specific state's
  // own tab, since a filer only ever exists in one state's own system.
  function statesRouter(sub) {
    const mainView = document.getElementById("states-view");
    const detailView = document.getElementById("states-detail-view");
    if (!sub) {
      detailView.hidden = true;
      mainView.hidden = false;
      renderStatesView();
      window.scrollTo(0, 0);
      return;
    }
    mainView.hidden = true;
    detailView.hidden = false;
    const parts = sub.split("/");
    const type = parts[0];
    const id = decodeURIComponent(parts.slice(1).join("/"));
    if (type === "vendor") renderStatesVendorDetail(id);
    else {
      detailView.innerHTML = "";
      detailView.appendChild(statesBackLink());
      detailView.appendChild(el("p", { text: "Page not found." }));
    }
    window.scrollTo(0, 0);
  }

  // A vendor's cross-comparison page: how much it shows up in disclosed
  // spend on Federal and each covered state, plus a population-scaled
  // national estimate built from the covered states alone (see
  // pipeline/build_projection.py's scale_factor) -- there is no
  // projection for Federal itself, which is already national in scope by
  // construction, only for the four-state sample being scaled up to it.
  function renderStatesVendorDetail(id) {
    const view = document.getElementById("states-detail-view");
    view.innerHTML = "";
    view.appendChild(statesBackLink());
    const v = STATES_DATA.vendors.find((r) => r.id === id);
    if (!v) {
      view.appendChild(el("p", { text: "Vendor not found in the combined states dataset." }));
      return;
    }
    const c = colors();

    const header = el("div", { className: "detail-header" });
    const h2 = el("h2", { text: v.name });
    h2.appendChild(el("span", { className: "pill", text: VENDOR_GROUP_LABEL[v.group] || v.group }));
    if (v.era === "legacy") h2.appendChild(el("span", { className: "pill pill-legacy", text: "Legacy (pre-generative AI)" }));
    header.appendChild(h2);
    if (v.homepage) {
      header.appendChild(el("a", { className: "entity-link", href: v.homepage, text: "Vendor website ↗", attrs: { target: "_blank", rel: "noopener" } }));
    }
    view.appendChild(header);
    view.appendChild(
      el("p", {
        className: "lede",
        text:
          "How much " +
          v.name +
          " shows up in disclosed AI-vendor spend across every dataset this site tracks: federal House/Senate races, each covered state, and a population-scaled national estimate built from the states alone (not from Federal, which is already national in scope).",
      })
    );

    const fedVendor = (DATA.vendors_overall || []).find((r) => r.id === id);
    const fedAmount = fedVendor ? fedVendor.amount_high : 0;
    const statesCombined = v.amount_high;
    const scaleFactor = PROJECTION_DATA.meta.scale_factor;
    const projectedAmount = statesCombined * scaleFactor;
    const nStatesWithSpend = Object.keys(v.by_state).length;

    const stats = el("div", { className: "detail-stat-row" });
    stats.appendChild(statTile("Federal spend", fmtUSD0.format(fedAmount), fedVendor ? "high-confidence House/Senate matches" : "no disclosed federal match"));
    stats.appendChild(statTile("Combined states spend", fmtUSD0.format(statesCombined), nStatesWithSpend + " of " + STATES_DATA.meta.covered_states.length + " covered states"));
    stats.appendChild(statTile("Projected national spend (states, population-scaled)", fmtUSD0.format(projectedAmount), scaleFactor.toFixed(2) + "x scale-up -- an estimate, not a disclosed figure"));
    view.appendChild(stats);

    const sourceRows = [{ label: "Federal", amount: fedAmount, href: fedAmount > 0 ? "#/vendor/" + id : null, isProjection: false }];
    STATES_DATA.meta.covered_states.forEach((stateId) => {
      const amt = (v.by_state[stateId] || {}).amount_high || 0;
      sourceRows.push({ label: STATE_CONFIG_BY_ID[stateId].label, amount: amt, href: amt > 0 ? "#/" + stateId + "/vendor/" + id : null, isProjection: false });
    });
    sourceRows.push({ label: "Combined states (real)", amount: statesCombined, href: null, isProjection: false });
    sourceRows.push({ label: "Projected national (population-scaled)", amount: projectedAmount, href: null, isProjection: true });

    const chartCard = el("div", { className: "card" });
    chartCard.appendChild(el("h3", { text: "Spend by source" }));
    chartCard.appendChild(
      el("p", {
        className: "note",
        text: "The last bar (muted gray) is the population-scaled estimate, not a disclosed dollar figure -- see the notes below for why it's a rough scale-up, not a statistical estimate.",
      })
    );
    chartCard.appendChild(el("div", { className: "chart-holder", children: [el("canvas", { id: "states-vendor-detail-chart" })] }));
    view.appendChild(el("div", { className: "card-grid single", children: [chartCard] }));

    const tableCard = el("div", { className: "card" });
    tableCard.appendChild(el("h3", { text: "Every source, side by side" }));
    tableCard.appendChild(
      el("p", {
        className: "note",
        text: "Click a source's own $ figure to open its own detail page, where every individual matched record for this vendor is listed. \"Combined states\" and \"Projected national\" have no page of their own -- both are totals computed here, not links to a filing.",
      })
    );
    tableCard.appendChild(
      buildTable(
        [
          { label: "Source", render: (r) => r.label },
          { label: "Amount", num: true, link: (r) => r.href, render: (r) => fmtUSD0.format(r.amount) },
        ],
        sourceRows
      )
    );
    view.appendChild(el("div", { className: "card-grid single", children: [tableCard] }));

    const notesCard = el("div", { className: "card" });
    notesCard.appendChild(el("h3", { text: "Why the projection is a rough scale-up, not an estimate" }));
    const notesList = el("ul", { className: "notes" });
    (PROJECTION_DATA.meta.methodology_notes || []).forEach((s) => notesList.appendChild(el("li", { text: s })));
    notesCard.appendChild(notesList);
    view.appendChild(el("div", { className: "card-grid single", children: [notesCard] }));

    const chartLabels = sourceRows.map((r) => r.label);
    const chartAmounts = sourceRows.map((r) => r.amount);
    const chartColors = [
      cssVar("--series-1"),
      ...STATES_DATA.meta.covered_states.map((sid) => cssVar("--" + sid + "-accent")),
      cssVar("--states-accent"),
      cssVar("--text-muted"),
    ];
    makeChart("states-vendor-detail-chart", {
      type: "bar",
      data: { labels: chartLabels, datasets: [{ label: "Disclosed / projected spend", data: chartAmounts, backgroundColor: chartColors, borderRadius: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: Object.assign(tooltipBase(), {
            callbacks: {
              label: (ctx) => {
                const r = sourceRows[ctx.dataIndex];
                return fmtUSD0.format(r.amount) + (r.isProjection ? " (estimate, not disclosed)" : "");
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
  }

  function renderStatesMethodologyCard() {
    const meta = STATES_DATA.meta;
    const sourcesCard = el("div", { className: "card" });
    sourcesCard.appendChild(statesCardTitle("Data sources"));
    const sourcesList = el("ul", { className: "notes" });
    meta.sources.forEach((s) => sourcesList.appendChild(el("li", { text: s })));
    sourcesCard.appendChild(sourcesList);

    const notesCard = el("div", { className: "card" });
    notesCard.appendChild(statesCardTitle("Notes & limitations"));
    const notesList = el("ul", { className: "notes" });
    meta.methodology_notes.forEach((s) => notesList.appendChild(el("li", { text: s })));
    notesCard.appendChild(notesList);

    return el("div", { className: "card-grid", children: [sourcesCard, notesCard] });
  }

  function renderStatesView() {
    const view = document.getElementById("states-view");
    view.innerHTML = "";
    const data = STATES_DATA;
    const meta = data.meta;
    const stats = data.stats;
    const stateLabels = meta.covered_states.map((id) => STATE_CONFIG_BY_ID[id].label);

    view.appendChild(
      el("div", {
        className: "state-banner",
        attrs: { style: "--accent:var(--states-accent);--accent-soft:var(--states-accent-soft)" },
        children: [
          el("span", { text: "You're viewing " }),
          el("strong", { text: "States, combined" }),
          el("span", {
            text:
              " — every state this site currently covers (" +
              stateLabels.join(", ") +
              ") unioned into one view. Every figure below is a real sum of each state's own disclosed records; for a population-scaled national estimate built from these same four states, see the Compare tab.",
          }),
        ],
      })
    );

    const statRow = el("div", { className: "stat-row" });
    statRow.appendChild(statTile("States covered", fmtInt.format(meta.covered_states.length), stateLabels.join(", ")));
    statRow.appendChild(
      statTile(
        "Disclosed AI-vendor spend",
        fmtUSD0.format(includeLegacy ? stats.total_all_eras : stats.total_generative),
        (includeLegacy ? "all eras" : "generative-era vendors only") + " -- toggle above to include legacy-era vendors"
      )
    );
    statRow.appendChild(
      statTile(
        "Candidate committees using AI",
        fmtInt.format(includeLegacy ? stats.filers_with_ai_spend : stats.filers_with_ai_spend_ex_legacy),
        "across all covered states"
      )
    );
    statRow.appendChild(
      statTile(
        "Distinct AI vendors identified",
        fmtInt.format(includeLegacy ? stats.distinct_vendors_all_eras : stats.distinct_vendors_generative),
        "across all covered states"
      )
    );
    view.appendChild(statRow);

    view.appendChild(el("div", { className: "card-grid single", children: [renderStatesVendorsCard()] }));
    view.appendChild(el("div", { className: "card-grid single", children: [renderStatesTrendCard()] }));
    view.appendChild(el("div", { className: "card-grid single", children: [renderStatesLeaderboardCard()] }));
    view.appendChild(el("div", { className: "card-grid single", children: [renderStatesPartyCard()] }));
    view.appendChild(renderStatesMethodologyCard());

    view.appendChild(
      el("p", {
        className: "lede",
        text:
          "Full pipeline code and the shared vendor/category taxonomy (pipeline/config/vendors.yaml) are in the GitHub repository. Dataset generated " +
          new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) +
          " UTC.",
      })
    );
  }

  function renderCompareView() {
    const view = document.getElementById("compare-view");
    view.innerHTML = "";
    const eraFilter = eraFilterList();
    const allRows = buildCompareRows();
    const nLegacyHidden = allRows.filter((r) => r.era === "legacy" && r.volume > 0).length;
    const eraRows = allRows.filter((r) => eraFilter.includes(r.era));
    const rows = compareFilterTag ? eraRows.filter((r) => (r.tags || []).includes(compareFilterTag)) : eraRows;

    view.appendChild(
      el("div", {
        className: "compare-banner",
        children: [
          el("span", { text: "You're viewing the " }),
          el("strong", { text: "Compare" }),
          el("span", {
            text:
              " tab — every AI vendor found on Federal (FEC) or any covered state tab (Massachusetts OCPF, Washington PDC, Colorado TRACER, California CAL-ACCESS), in one table. The federal dataset and the four-state union cover different offices, timeframes, and itemization rules, so their dollar figures are shown side by side rather than added into one number, other than the Combined volume column below.",
          }),
        ],
      })
    );

    const nFederal = rows.filter((r) => r.fed_amount > 0).length;
    const nStates = rows.filter((r) => r.states_amount > 0).length;
    const nBoth = rows.filter((r) => r.fed_amount > 0 && r.states_amount > 0).length;
    const totalVolume = rows.reduce((a, r) => a + r.volume, 0);

    const statRow = el("div", { className: "stat-row" });
    statRow.appendChild(
      statTile(
        "AI vendors compared",
        fmtInt.format(rows.length),
        nFederal + " on Federal · " + nStates + " on a covered state · " + nBoth + " on both" + (includeLegacy ? "" : " · " + nLegacyHidden + " legacy vendor" + (nLegacyHidden === 1 ? "" : "s") + " hidden")
      )
    );
    statRow.appendChild(statTile("Combined high-confidence spend", fmtUSD0.format(totalVolume), "Federal + all covered states' high-confidence vendor totals, summed"));
    view.appendChild(statRow);

    const card = el("div", { className: "card" });
    card.appendChild(el("h3", { text: "AI vendors: Federal vs. States" }));
    card.appendChild(
      el("p", {
        className: "note",
        text:
          "High-confidence text matches only, on each tab's own dataset (see each tab's methodology for what that means there). Combined volume sums Federal and all covered states. Momentum compares each vendor's own more-recent half of its time series (Federal: election cycles; states: calendar years, summed across whichever states carry the vendor) against its earlier half, weighted toward whichever side carries more of its spend, shown as a multiplier (e.g. “14.2x”) once growth passes 3x since a percentage that large stops being readable; “New” means its earlier half had little or no spend (under $25) to compare against, so no rate is computable at all. Click a vendor's name to see it compared against a population-scaled national estimate; click a category tag to filter the table to it; hover any column header for details. " +
          (includeLegacy
            ? "Legacy-era vendors are currently included, via the toggle above."
            : nLegacyHidden + " legacy-era vendor" + (nLegacyHidden === 1 ? "" : "s") + " with disclosed spending " + (nLegacyHidden === 1 ? "is" : "are") + " hidden by default (toggle above to include them)."),
      })
    );

    if (compareFilterTag) {
      const bar = el("div", { className: "active-filter-bar" });
      bar.appendChild(document.createTextNode("Filtered to category: "));
      bar.appendChild(el("span", { className: "tag-chip is-active", text: TAG_SHORT_LABELS[compareFilterTag] || compareFilterTag }));
      const clearBtn = el("button", { className: "filter-clear-btn", text: "Clear filter ✕", attrs: { type: "button" } });
      clearBtn.addEventListener("click", () => {
        compareFilterTag = null;
        renderCompareView();
      });
      bar.appendChild(clearBtn);
      card.appendChild(bar);
    }

    if (!rows.length) {
      card.appendChild(el("p", { className: "note", text: "No vendors match this filter." }));
    } else {
      const tableRows = sortRows(rows, sortState.compare);
      const stateColumns = STATES_DATA.meta.covered_states.map((stateId) => ({
        label: STATE_CONFIG_BY_ID[stateId].label + " $",
        num: true,
        title: "High-confidence text matches to this vendor on the " + STATE_CONFIG_BY_ID[stateId].label + " tab. Click to open its detail page there.",
        link: (r) => (r.by_state[stateId] && r.by_state[stateId].amount_high > 0 ? "#/" + stateId + "/vendor/" + r.id : null),
        render: (r) => (r.by_state[stateId] && r.by_state[stateId].amount_high > 0 ? fmtUSD0.format(r.by_state[stateId].amount_high) : "—"),
      }));
      const headers = withSort(
        "compare",
        [
          {
            label: "Vendor",
            sortKey: "name",
            title: "Click to compare this vendor across Federal, every covered state, and a population-scaled national estimate.",
            link: (r) => "#/states/vendor/" + r.id,
            render: (r) => r.name,
          },
          {
            label: "Category",
            sortKey: null,
            title: "The 1-2 use-case tags that best characterize this product (same vocabulary used to label disbursement purpose text elsewhere on the site). Click a tag to filter the table to it.",
            cell: (r) => tagChips(r.tags),
          },
          {
            label: "How campaigns use it",
            sortKey: null,
            title: "A one-line, hand-written summary of what the product is and how a campaign typically uses it -- not derived from any single disbursement's stated purpose.",
            cell: (r) => el("span", { className: "desc-cell", text: r.description || "—" }),
          },
          {
            label: "Federal $",
            sortKey: "fed_amount",
            num: true,
            title: "High-confidence text matches to this vendor on the Federal (FEC) tab. Click the amount to open its Federal vendor page.",
            link: (r) => (r.fed_amount > 0 ? "#/vendor/" + r.id : null),
            render: (r) => (r.fed_amount > 0 ? fmtUSD0.format(r.fed_amount) : "—"),
          },
          ...stateColumns,
          {
            label: "Combined volume",
            sortKey: "volume",
            num: true,
            title: "Federal $ + every covered state's $ added together -- the only column on this page that combines Federal and the states into one number.",
            render: (r) => fmtUSD0.format(r.volume),
          },
          {
            label: "Momentum",
            sortKey: "momentum_sort",
            title: "The vendor's more-recent half of its own time series vs. its earlier half (Federal: election cycles; states: calendar years, summed across whichever states carry the vendor), weighted toward whichever side carries more of its spend. Shown as +/-% normally, or as a multiplier (\"14.2x\") once growth passes 3x; \"New\" means the earlier half had too little spend (under $25) to compute a rate.",
            cell: (r) => momentumBadge(r),
          },
          {
            label: "Era",
            sortKey: "era",
            title: "Generative: built on modern LLM/diffusion/voice-clone AI. Legacy: an \"AI\"-branded company that predates the generative-AI wave -- hidden by default via the toggle above.",
            render: (r) => (r.era === "legacy" ? "Legacy" : "Generative"),
          },
        ],
        renderCompareView
      );
      card.appendChild(buildTable(headers, tableRows, { sort: sortState.compare }));
    }
    view.appendChild(el("div", { className: "card-grid single", children: [card] }));

    if (PROJECTION_DATA) {
      renderProjectionSection().forEach((node) => view.appendChild(node));
    }

    view.appendChild(
      el("p", {
        className: "lede",
        text: "Full pipeline code and the shared vendor/category taxonomy (pipeline/config/vendors.yaml) are in the GitHub repository. See the Federal tab and each state tab's own methodology notes for what each dataset does and doesn't cover.",
      })
    );
  }

  function parseHash() {
    const h = location.hash.replace(/^#\/?/, "");
    if (!h) return null;
    const parts = h.split("/");
    if (parts.length < 2) return null;
    return { type: parts[0], id: decodeURIComponent(parts.slice(1).join("/")) };
  }

  function federalRouter() {
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

  // Top-level dispatcher: the URL hash decides both which dataset tab is
  // active ("#/wa" for Washington, etc., anything else for Federal) and,
  // on the Federal tab, which drill-down page (if any) to show. Keeping
  // the tab itself in the hash means the browser's back/forward buttons
  // and shared links both restore the right dataset, not just the right
  // page.
  function route() {
    const raw = location.hash.replace(/^#\/?/, "");
    const stateMatch = STATE_IDS.filter((id) => raw === id || raw.indexOf(id + "/") === 0)[0];
    if (stateMatch) {
      pendingStateSubroute = raw === stateMatch ? "" : raw.slice(stateMatch.length + 1);
      activateDataset(stateMatch);
      return;
    }
    if (raw === "compare") {
      activateDataset("compare");
      return;
    }
    if (raw === "states" || raw.indexOf("states/") === 0) {
      pendingStatesSubroute = raw === "states" ? "" : raw.slice("states/".length);
      activateDataset("states");
      return;
    }
    activateDataset("federal");
    federalRouter();
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
    route();
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
      buildSearchIndex();
      wireSearch();
      wireDatasetTabs();
      wireStateDropdown();
      tagFederalCardsWithPill();
      renderAll();
      window.addEventListener("hashchange", route);
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        renderAll();
        if (STATE_IDS.indexOf(currentDataset) !== -1 && STATE_DATA[currentDataset]) renderStateView(currentDataset);
        if (currentDataset === "compare" && STATES_DATA) renderCompareView();
        if (currentDataset === "states" && STATES_DATA) renderStatesView();
      });
    })
    .catch((err) => {
      document.getElementById("meta-line").textContent = "Could not load dataset (" + err.message + ").";
      console.error(err);
    });
})();
