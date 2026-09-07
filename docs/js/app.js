(function () {
  "use strict";

  const fmtUSD0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const fmtInt = new Intl.NumberFormat("en-US");

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
  const PARTY_ORDER = ["Democratic", "Republican", "Other", "Unknown"];
  const CHAMBER_ORDER = ["House", "Senate"];

  let DATA = null;
  const chartInstances = {};

  function destroyCharts() {
    Object.values(chartInstances).forEach((c) => c && c.destroy());
  }

  function baseGridOptions(c) {
    return {
      x: { grid: { display: false }, ticks: { color: c.text } },
      y: { grid: { color: c.grid, drawTicks: false }, ticks: { color: c.text }, border: { display: false } },
    };
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

  function makeChart(canvasId, config) {
    const el = document.getElementById(canvasId);
    if (!el) return null;
    chartInstances[canvasId] = new Chart(el.getContext("2d"), config);
    return chartInstances[canvasId];
  }

  function setPanelTable(panel, headers, rows) {
    const holder = document.querySelector('.table-holder[data-panel="' + panel + '"]');
    if (!holder) return;
    holder.innerHTML = "";
    const table = document.createElement("table");
    table.className = "data-table";
    const thead = document.createElement("thead");
    const trh = document.createElement("tr");
    headers.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h.label;
      if (h.num) th.className = "num";
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      headers.forEach((h) => {
        const td = document.createElement("td");
        td.textContent = r[h.key];
        if (h.num) td.className = "num";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    holder.appendChild(table);
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

  function renderStats() {
    const c = colors();
    const meta = DATA.meta;
    const totalMatchedRows = Object.values(meta.matched_row_counts_by_cycle || {}).reduce((a, b) => a + b, 0);
    const totalHighAmount = DATA.vendors_overall.reduce((a, v) => a + v.amount_high, 0);
    const nGeneral = DATA.vendors_overall.filter((v) => v.group === "general_purpose").length;
    const nPolitical = DATA.vendors_overall.filter((v) => v.group === "political_specific").length;

    const tiles = [
      {
        label: "AI vendors identified in disclosures",
        value: fmtInt.format(DATA.vendors_overall.length),
        sub: nGeneral + " general-purpose · " + nPolitical + " campaign-specific",
      },
      {
        label: "AI-related disbursement records found",
        value: fmtInt.format(totalMatchedRows),
        sub: "across " + meta.cycles.join(", ") + " cycles, all confidence tiers",
      },
      {
        label: "Total high-confidence AI spending",
        value: fmtUSD0.format(totalHighAmount),
        sub: "all committees, all cycles",
      },
      {
        label: "2026 House/Senate candidates paying OpenAI",
        value: fmtInt.format(meta.openai_high_confidence_house_senate_candidates_2026),
        sub: "WaPo (Sept 2026) found 39 candidates paying for an OpenAI subscription; methodology differs, see notes",
      },
    ];

    const row = document.getElementById("stat-row");
    row.innerHTML = "";
    tiles.forEach((t) => {
      const div = document.createElement("div");
      div.className = "stat-tile";
      const l = document.createElement("div");
      l.className = "label";
      l.textContent = t.label;
      const v = document.createElement("div");
      v.className = "value";
      v.textContent = t.value;
      const s = document.createElement("div");
      s.className = "sub";
      s.textContent = t.sub;
      div.appendChild(l);
      div.appendChild(v);
      div.appendChild(s);
      row.appendChild(div);
    });

    document.getElementById("coverage-callout").innerHTML =
      "<strong>Coverage:</strong> this pipeline scans itemized operating-expenditure (Schedule B) records from FEC bulk data for the " +
      meta.cycles.join(", ") +
      " two-year cycles, matches payee/purpose/memo text against a curated AI-vendor taxonomy, and joins matches to candidate party, chamber, incumbency status, and (where available) age. As with the Post's original analysis, disclosed spending understates actual AI use, since campaigns can pay through corporate cards, staff, or consultants without the vendor name ever appearing in a filing.";

    document.getElementById("meta-line").textContent =
      "Data generated " + new Date(meta.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) + " UTC · cycles: " + meta.cycles.join(", ");
    document.getElementById("footer-generated").textContent = "Dataset last built " + meta.generated_at + ".";
  }

  function renderVendors() {
    const c = colors();
    const rows = DATA.vendors_overall.slice(0, 20);
    const labels = rows.map((r) => r.name);
    const data = rows.map((r) => r.amount_high);
    const bg = rows.map((r) => (r.group === "general_purpose" ? c.general_purpose : c.political_specific));

    makeChart("chart-vendors", {
      type: "bar",
      data: { labels, datasets: [{ label: "High-confidence spending", data, backgroundColor: bg, borderRadius: 4, barThickness: 16 }] },
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
                return [
                  fmtUSD0.format(r.amount_high) + " · " + fmtInt.format(r.count_high) + " records · " + fmtInt.format(r.distinct_committees_high) + " committees",
                  r.amount_medium > 0 ? "+" + fmtUSD0.format(r.amount_medium) + " lower-confidence signal" : "",
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
          y: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
        },
      },
    });

    document.querySelector('.card-toolbar').parentElement; // no-op, keep legend markup simple
    setPanelTable(
      "vendors",
      [
        { key: "name", label: "Vendor" },
        { key: "group", label: "Type" },
        { key: "amount_high", label: "High-confidence $", num: true },
        { key: "count_high", label: "Records", num: true },
        { key: "amount_medium", label: "Lower-confidence $", num: true },
      ],
      DATA.vendors_overall.map((r) => ({
        name: r.name,
        group: VENDOR_GROUP_LABEL[r.group] || r.group,
        amount_high: fmtUSD0.format(r.amount_high),
        count_high: fmtInt.format(r.count_high),
        amount_medium: fmtUSD0.format(r.amount_medium),
      }))
    );

    // Inline legend under the vendors chart heading.
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

  function renderUseCases() {
    const c = colors();
    const rows = DATA.use_categories.slice().sort((a, b) => b.amount - a.amount);
    const labelFor = (id) => (DATA._categoryLabels && DATA._categoryLabels[id]) || id;
    const labels = rows.map((r) => labelFor(r.id));
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
          y: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
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
      rows.map((r) => ({ label: labelFor(r.id), amount: fmtUSD0.format(r.amount), count: fmtInt.format(r.count), candidates: fmtInt.format(r.distinct_candidates) }))
    );

    // stacked by vendor group
    const cross = DATA.use_category_by_vendor_group;
    const catIds = rows.map((r) => r.id);
    const gp = catIds.map((id) => (cross.find((x) => x.category === id && x.group === "general_purpose") || {}).amount || 0);
    const ps = catIds.map((id) => (cross.find((x) => x.category === id && x.group === "political_specific") || {}).amount || 0);

    makeChart("chart-usecases-group", {
      type: "bar",
      data: {
        labels: catIds.map(labelFor),
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
      catIds.map((id, i) => ({ label: labelFor(id), gp: fmtUSD0.format(gp[i]), ps: fmtUSD0.format(ps[i]) }))
    );
  }

  function stackedByGroupChart(canvasId, panel, rows, orderKey, order) {
    const c = colors();
    const cats = order.filter((k) => rows.some((r) => String(r[orderKey]) === k));
    const gp = cats.map((k) => rows.filter((r) => String(r[orderKey]) === k && r.vendor_group === "general_purpose").reduce((a, r) => a + r.amount, 0));
    const ps = cats.map((k) => rows.filter((r) => String(r[orderKey]) === k && r.vendor_group === "political_specific").reduce((a, r) => a + r.amount, 0));
    const counts = cats.map((k) => rows.filter((r) => String(r[orderKey]) === k).reduce((a, r) => a + r.distinct_candidates, 0));
    const displayLabels = cats.slice();

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
              footer: function (items) {
                const i = items[0].dataIndex;
                return fmtInt.format(counts[i]) + " distinct candidates";
              },
            },
          }),
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { stacked: true, grid: { color: c.grid }, ticks: { color: c.text, callback: (v) => fmtUSD0.format(v) }, border: { display: false } },
        },
      },
    });

    setPanelTable(
      panel,
      [
        { key: "label", label: "Category" },
        { key: "gp", label: "General-purpose $", num: true },
        { key: "ps", label: "Campaign-specific $", num: true },
        { key: "candidates", label: "Distinct candidates", num: true },
      ],
      displayLabels.map((label, i) => ({ label, gp: fmtUSD0.format(gp[i]), ps: fmtUSD0.format(ps[i]), candidates: fmtInt.format(counts[i]) }))
    );
  }

  function renderBreakdowns() {
    stackedByGroupChart("chart-party", "party", DATA.by_party, "cand_party", PARTY_ORDER);
    stackedByGroupChart("chart-incumbency", "incumbency", DATA.by_incumbency, "ici", INCUMBENCY_ORDER);
    stackedByGroupChart("chart-chamber", "chamber", DATA.by_chamber, "office", CHAMBER_ORDER);
    stackedByGroupChart("chart-age", "age", DATA.by_age_bucket, "age_bucket", AGE_ORDER);
  }

  function lineChart(canvasId, panel, cycles, series, colorMap, valueKey) {
    const c = colors();
    const datasets = Object.keys(series).map((name) => ({
      label: name,
      data: cycles.map((cy) => {
        const row = series[name].find((r) => Number(r.cycle) === cy);
        return row ? row[valueKey] : 0;
      }),
      borderColor: colorMap[name] || c.muted,
      backgroundColor: colorMap[name] || c.muted,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      pointBackgroundColor: colorMap[name] || c.muted,
      tension: 0.15,
      fill: false,
    }));

    makeChart(canvasId, {
      type: "line",
      data: { labels: cycles.map(String), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: Object.assign({ position: "top" }, legendBase()), tooltip: Object.assign(tooltipBase(), { callbacks: { label: (ctx) => ctx.dataset.label + ": " + fmtUSD0.format(ctx.parsed.y) } }) },
        scales: {
          x: { grid: { display: false }, ticks: { color: c.text }, border: { display: false } },
          y: { grid: { color: c.grid }, ticks: { color: c.text, callback: (v) => fmtUSD0.format(v) }, border: { display: false } },
        },
      },
    });

    const headers = [{ key: "cycle", label: "Cycle" }].concat(Object.keys(series).map((name) => ({ key: name, label: name, num: true })));
    const rows = cycles.map((cy) => {
      const row = { cycle: cy };
      Object.keys(series).forEach((name) => {
        const r = series[name].find((rr) => Number(rr.cycle) === cy);
        row[name] = fmtUSD0.format(r ? r[valueKey] : 0);
      });
      return row;
    });
    setPanelTable(panel, headers, rows);
  }

  function renderTrends() {
    const c = colors();
    const cycles = DATA.meta.cycles.slice().sort((a, b) => a - b);

    lineChart(
      "chart-trend-overall",
      "trend-overall",
      cycles,
      {
        [VENDOR_GROUP_LABEL.general_purpose]: DATA.time_series.filter((r) => r.vendor_group === "general_purpose"),
        [VENDOR_GROUP_LABEL.political_specific]: DATA.time_series.filter((r) => r.vendor_group === "political_specific"),
      },
      { [VENDOR_GROUP_LABEL.general_purpose]: c.general_purpose, [VENDOR_GROUP_LABEL.political_specific]: c.political_specific },
      "amount"
    );

    const byParty = {};
    PARTY_ORDER.filter((p) => p !== "").forEach((p) => (byParty[p] = DATA.time_series_by_party.filter((r) => r.cand_party === p)));
    lineChart("chart-trend-party", "trend-party", cycles, byParty, c.party, "amount");

    const byInc = {};
    ["Incumbent", "Challenger", "Open seat"].forEach((k) => (byInc[k] = DATA.time_series_by_incumbency.filter((r) => r.ici === k)));
    lineChart("chart-trend-incumbency", "trend-incumbency", cycles, byInc, c.incumbency, "amount");

    const byChamber = {};
    CHAMBER_ORDER.forEach((k) => (byChamber[k] = DATA.time_series_by_chamber.filter((r) => r.office === k)));
    lineChart("chart-trend-chamber", "trend-chamber", cycles, byChamber, c.chamber, "amount");
  }

  function renderTopCommittees() {
    const rows = DATA.top_committees.slice(0, 25);
    const container = document.getElementById("table-top-committees");
    container.innerHTML = "";
    const table = document.createElement("table");
    table.className = "data-table";
    const thead = document.createElement("thead");
    thead.innerHTML = "";
    const trh = document.createElement("tr");
    ["Committee", "AI-related spending", "Records"].forEach((h, i) => {
      const th = document.createElement("th");
      th.textContent = h;
      if (i > 0) th.className = "num";
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = r.cmte_name || r.cmte_id;
      const tdAmt = document.createElement("td");
      tdAmt.className = "num";
      tdAmt.textContent = fmtUSD0.format(r.amount);
      const tdCount = document.createElement("td");
      tdCount.className = "num";
      tdCount.textContent = fmtInt.format(r.count);
      tr.appendChild(tdName);
      tr.appendChild(tdAmt);
      tr.appendChild(tdCount);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  function renderMethodology() {
    const sources = document.getElementById("sources-list");
    sources.innerHTML = "";
    DATA.meta.sources.forEach((s) => {
      const li = document.createElement("li");
      li.textContent = s;
      sources.appendChild(li);
    });
    const notes = document.getElementById("notes-list");
    notes.innerHTML = "";
    DATA.meta.methodology_notes.forEach((s) => {
      const li = document.createElement("li");
      li.textContent = s;
      notes.appendChild(li);
    });
  }

  function renderAll() {
    destroyCharts();
    renderStats();
    renderVendors();
    renderUseCases();
    renderBreakdowns();
    renderTrends();
    renderTopCommittees();
    renderMethodology();
  }

  fetch("data/dashboard.json")
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((json) => {
      DATA = json;
      DATA._categoryLabels = {
        advertising_creative: "Advertising / creative content",
        communications_copy: "Communications copy (email/text/scripts)",
        synthetic_media: "Synthetic media / deepfake-adjacent",
        research_strategy: "Research, polling & strategy",
        fundraising: "Fundraising",
        data_targeting: "Voter data & targeting",
        administrative_productivity: "Administrative / general productivity",
        unspecified: "Unspecified / generic",
      };
      wireToggles();
      renderAll();
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
    })
    .catch((err) => {
      document.getElementById("meta-line").textContent = "Could not load dataset (" + err.message + ").";
      console.error(err);
    });
})();
