/* USVI Beach Water Quality Tracker - reads the JSON files written by pipeline/step6_export.py */
(async function () {
  const C = { ink: '#0E2A3B', coral: '#C8553D', coralL: '#E8836B', sea: '#2F7F86', seaL: '#8CC2C4', grey: '#B9C2C8', line: '#E6DFD2', muted: '#6B7C89' };
  const ISLAND_COLORS = { 'St. Croix': '#C8553D', 'St. Thomas': '#0E2A3B', 'St. John': '#2F7F86', 'Water Island': '#D9A441' };
  const load = (f) => fetch(`data/${f}.json`).then((r) => r.json());
  const [beaches, samples, weekly, streaks, weeks, meta] = await Promise.all(
    ['beaches', 'samples', 'island_weekly', 'streaks', 'weeks', 'meta'].map(load));

  const fmtDate = (s, opts = { month: 'short', day: 'numeric', year: 'numeric' }) =>
    new Date(s + 'T12:00:00').toLocaleDateString('en-US', opts);
  const fmtVal = (v, q) => v == null ? '–' : (q === 'below_reporting_limit' ? '<' : '') + Math.round(v).toLocaleString('en-US');
  const byId = Object.fromEntries(beaches.map((b) => [b.beach_id, b]));
  const pdfFor = Object.fromEntries(weeks.map((w) => [w.sample_date, w.source_url]));
  const latest = meta.latest_sample_date;

  document.getElementById('range').textContent = `· ${fmtDate(meta.first_sample_date, { month: 'short', year: 'numeric' })} to ${fmtDate(latest)}`;
  document.getElementById('built').textContent = `Data through ${fmtDate(latest)}.`;

  let island = 'All';
  let selected = null;
  const inIsland = (b) => island === 'All' || b.island === island;

  /* ---------- KPIs ---------- */
  function renderKpis() {
    const bs = beaches.filter(inIsland);
    const ids = new Set(bs.map((b) => b.beach_id));
    const wk = samples.filter((s) => s.sample_date === latest && ids.has(s.beach_id));
    const unsafe = wk.filter((s) => s.unsafe).length;
    const all = samples.filter((s) => ids.has(s.beach_id));
    const allUnsafe = all.filter((s) => s.unsafe).length;
    const weeksSet = new Set(all.map((s) => s.sample_date));
    const k = [
      ['Latest sheet', fmtDate(latest, { month: 'short', day: 'numeric' }), `<span>${new Date(latest).getUTCFullYear()}</span>`],
      ['Beaches tested', wk.length, `<span>of ${bs.length} monitored</span>`],
      ['Unsafe this week', unsafe, unsafe ? `<b class="warn">${Math.round(100 * unsafe / Math.max(wk.length, 1))}%</b><span>of tested</span>` : '<span>none above 70</span>'],
      ['Unsafe rate, all weeks', (100 * allUnsafe / Math.max(all.length, 1)).toFixed(1) + '%', `<span>${allUnsafe.toLocaleString()} of ${all.length.toLocaleString()} samples</span>`],
      ['Weeks of data', weeksSet.size, '<span>since Oct 2022</span>'],
    ];
    document.getElementById('kpis').innerHTML = k.map(([l, v, d]) =>
      `<div class="kpi"><p class="l">${l}</p><p class="v">${v}</p><p class="d ${l === 'Unsafe this week' && unsafe ? 'warn' : ''}">${d}</p></div>`).join('');
    document.getElementById('applied').textContent = island === 'All'
      ? `Showing all ${beaches.length} monitored beaches` : `Showing ${bs.length} beaches on ${island}`;
  }

  /* ---------- Map ---------- */
  const map = L.map('map', { scrollWheelZoom: false, attributionControl: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 17,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const markers = {};
  function statusOf(b) {
    if (b.latest_date !== latest || b.latest_status !== 'sampled') return 'none';
    return b.latest_is_exceedance ? 'unsafe' : 'safe';
  }
  beaches.forEach((b) => {
    const st = statusOf(b);
    const m = L.circleMarker([b.latitude, b.longitude], {
      radius: st === 'unsafe' ? 9 : 7, weight: 2, color: '#fff',
      fillColor: st === 'unsafe' ? C.coral : st === 'safe' ? C.sea : C.grey, fillOpacity: 0.95,
    }).addTo(map);
    const val = st === 'none' ? 'Not sampled this week' : `${fmtVal(b.latest_enterococci, b.latest_qualifier)} per 100 mL`;
    m.bindPopup(`<b>${b.beach_name}</b><br>${b.island}<br>${val}<br><button class="pop-btn" data-b="${b.beach_id}">View history</button>`);
    m.bindTooltip(b.beach_name, { direction: 'top', offset: [0, -6] });
    markers[b.beach_id] = m;
  });
  map.on('popupopen', (e) => {
    const btn = e.popup.getElement().querySelector('.pop-btn');
    if (btn) btn.addEventListener('click', () => selectBeach(btn.dataset.b, true));
  });
  function fitMap() {
    const pts = beaches.filter(inIsland).map((b) => [b.latitude, b.longitude]);
    Object.entries(markers).forEach(([id, m]) => {
      const show = inIsland(byId[id]);
      m.setStyle({ opacity: show ? 1 : 0.15, fillOpacity: show ? 0.95 : 0.15 });
    });
    map.fitBounds(pts, { padding: [28, 28], maxZoom: island === 'Water Island' ? 14 : 12 });
  }

  /* ---------- This week ---------- */
  function renderWeek() {
    const wk = samples.filter((s) => s.sample_date === latest && inIsland(byId[s.beach_id]));
    const bad = wk.filter((s) => s.unsafe).sort((a, b) => b.entero - a.entero);
    document.getElementById('weekSub').textContent = `Sheet dated ${fmtDate(latest)} · ${wk.length} beaches tested`;
    document.getElementById('mapSub').textContent = `DPNR sheet dated ${fmtDate(latest)}`;
    const ul = document.getElementById('unsafeList');
    ul.innerHTML = bad.length ? bad.map((s) => {
      const b = byId[s.beach_id];
      return `<li data-b="${b.beach_id}" tabindex="0"><div><b>${b.beach_name}</b><small>${b.island}</small></div><p class="v">${fmtVal(s.entero, s.qualifier)}<span>/100 mL</span></p></li>`;
    }).join('') : '<li class="empty"><div><b>No unsafe results</b><small>All tested beaches at or below 70</small></div></li>';
    ul.querySelectorAll('li[data-b]').forEach((li) => {
      li.addEventListener('click', () => selectBeach(li.dataset.b, true));
      li.addEventListener('keydown', (e) => { if (e.key === 'Enter') selectBeach(li.dataset.b, true); });
    });
    const a = document.getElementById('weekPdf');
    a.href = pdfFor[latest];
    a.textContent = `Open DPNR source sheet (${fmtDate(latest, { month: 'short', day: 'numeric' })})`;
  }

  /* ---------- Weekly chart ---------- */
  Chart.defaults.font.family = "'Satoshi', system-ui, sans-serif";
  Chart.defaults.color = C.muted;
  const dates = [...new Set(weekly.map((w) => w.sample_date))].sort();
  const weeklyChart = new Chart(document.getElementById('cWeekly'), {
    type: 'bar',
    data: { labels: dates, datasets: [] },
    options: {
      maintainAspectRatio: false, animation: { duration: 400 },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
        tooltip: { callbacks: { title: (it) => fmtDate(it[0].label) } },
      },
      scales: {
        x: { stacked: true, grid: { display: false },
             ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, callback: function (v) { return fmtDate(this.getLabelForValue(v), { month: 'short', year: '2-digit' }); } } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#EFE9DE' }, title: { display: true, text: 'Unsafe results' } },
      },
    },
  });
  function renderWeekly() {
    const isl = island === 'All' ? Object.keys(ISLAND_COLORS) : [island];
    weeklyChart.data.datasets = isl.map((i) => ({
      label: i, backgroundColor: ISLAND_COLORS[i], borderRadius: 2, maxBarThickness: 10,
      data: dates.map((d) => (weekly.find((w) => w.sample_date === d && w.island === i) || {}).beaches_unsafe || 0),
    }));
    weeklyChart.update();
  }

  /* ---------- Beach history chart ---------- */
  const pick = document.getElementById('beachPick');
  const beachChart = new Chart(document.getElementById('cBeach'), {
    type: 'scatter',
    data: { datasets: [] },
    options: {
      maintainAspectRatio: false, animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (it) => `${fmtDate(it.raw.d)}: ${fmtVal(it.raw.y, it.raw.q)} per 100 mL` } },
      },
      scales: {
        x: { type: 'linear', grid: { display: false },
             ticks: { maxTicksLimit: 6, callback: (v) => new Date(v).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) } },
        y: { type: 'logarithmic', min: 5, grid: { color: '#EFE9DE' },
             ticks: { callback: (v) => [10, 70, 1000, 10000].includes(v) ? v.toLocaleString() : '' },
             afterBuildTicks: (ax) => { ax.ticks = [10, 70, 1000, 10000].filter((t) => t <= ax.max).map((v) => ({ value: v })); } },
      },
    },
  });
  function selectBeach(id, scroll) {
    selected = id;
    const b = byId[id];
    pick.value = id;
    const s = samples.filter((x) => x.beach_id === id && x.entero != null);
    const pts = (fn) => s.filter(fn).map((x) => ({ x: new Date(x.sample_date + 'T12:00:00').getTime(), y: Math.max(x.entero, 5), d: x.sample_date, q: x.qualifier }));
    const xs = s.map((x) => new Date(x.sample_date + 'T12:00:00').getTime());
    const xmin = Math.min(...xs, new Date('2023-01-01').getTime()), xmax = Math.max(...xs, new Date(latest).getTime());
    beachChart.data.datasets = [
      { label: 'Threshold', type: 'line', data: [{ x: xmin, y: 70 }, { x: xmax, y: 70 }], borderColor: C.coral, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 },
      { label: 'Below reporting limit', data: pts((x) => x.qualifier === 'below_reporting_limit'), pointRadius: 3, pointStyle: 'circle', backgroundColor: 'rgba(0,0,0,0)', borderColor: C.seaL, borderWidth: 1.5 },
      { label: 'Safe', data: pts((x) => x.qualifier !== 'below_reporting_limit' && !x.unsafe), pointRadius: 3.5, backgroundColor: C.sea, borderColor: C.sea },
      { label: 'Unsafe', data: pts((x) => x.unsafe), pointRadius: 5, backgroundColor: C.coral, borderColor: '#fff', borderWidth: 1 },
    ];
    beachChart.update();
    document.getElementById('beachTitle').textContent = b.beach_name;
    document.getElementById('beachSub').textContent = `${b.island} · enterococci per 100 mL, log scale · dashed line = 70`;
    const rate = b.exceedance_rate_pct == null ? '–' : b.exceedance_rate_pct + '%';
    document.getElementById('beachNote').innerHTML = b.samples
      ? `<b>${b.exceedances} of ${b.samples}</b> samples unsafe (${rate}). Highest: ${fmtVal(b.max_enterococci)}${b.last_exceedance_date ? `. Last unsafe ${fmtDate(b.last_exceedance_date)}` : '. Never above 70'}.${b.samples < 20 ? ' Few samples, so read the rate with care.' : ''}`
      : 'No sampled results yet.';
    document.querySelectorAll('#tBeach tbody tr').forEach((tr) => tr.classList.toggle('sel', tr.dataset.b === id));
    if (markers[id] && scroll !== 'quiet') markers[id].openTooltip();
    if (scroll === true) document.getElementById('cBeach').closest('.card').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  pick.addEventListener('change', () => selectBeach(pick.value));

  /* ---------- Table ---------- */
  let sortKey = 'exceedance_rate_pct', sortDir = -1;
  function renderTable() {
    const rows = beaches.filter(inIsland).slice().sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null) return 1; if (y == null) return -1;
      return (typeof x === 'string' ? x.localeCompare(y) : x - y) * sortDir;
    });
    document.querySelector('#tBeach tbody').innerHTML = rows.map((b) => {
      const st = statusOf(b);
      const latestTag = st === 'none' ? '<span class="tag plain">Not sampled</span>'
        : `<span class="tag ${st === 'unsafe' ? 'warn' : 'good'}">${fmtVal(b.latest_enterococci, b.latest_qualifier)}</span>`;
      return `<tr data-b="${b.beach_id}" class="${b.beach_id === selected ? 'sel' : ''}">
        <td><b>${b.beach_name}</b><small class="isl">${b.island}</small></td>
        <td class="n">${b.samples}</td><td class="n">${b.exceedances}</td>
        <td class="n">${b.exceedance_rate_pct == null ? '–' : b.exceedance_rate_pct.toFixed(1) + '%'}${b.samples < 20 ? '<span class="few">few samples</span>' : ''}</td>
        <td class="n">${fmtVal(b.max_enterococci)}</td><td>${latestTag}</td></tr>`;
    }).join('');
    document.querySelectorAll('#tBeach tbody tr').forEach((tr) => tr.addEventListener('click', () => selectBeach(tr.dataset.b, true)));
    document.querySelectorAll('#tBeach th[data-k]').forEach((th) => {
      th.setAttribute('aria-sort', th.dataset.k === sortKey ? (sortDir < 0 ? 'descending' : 'ascending') : 'none');
    });
  }
  document.querySelectorAll('#tBeach th[data-k]').forEach((th) => th.addEventListener('click', () => {
    const k = th.dataset.k;
    if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = ['beach_name', 'island'].includes(k) ? 1 : -1; }
    renderTable();
  }));
  document.querySelector('#tBeach').closest('.table-wrap').classList.add('tall');

  /* ---------- Streaks ---------- */
  function renderStreaks() {
    const list = streaks.filter((s) => island === 'All' || s.island === island).slice(0, 7);
    document.getElementById('streaks').innerHTML = list.length ? list.map((s) =>
      `<li><span class="n">${s.consecutive_unsafe_samples}</span><div><b>${s.beach_name}</b><small>${s.island} · ${fmtDate(s.streak_start, { month: 'short', day: 'numeric', year: 'numeric' })} to ${fmtDate(s.streak_end, { month: 'short', day: 'numeric', year: 'numeric' })}</small></div></li>`).join('')
      : '<li><span class="n">0</span><div><b>No streaks of 3 or more</b><small>on this island</small></div></li>';
  }

  /* ---------- Island filter ---------- */
  function populatePick() {
    const opts = beaches.filter(inIsland).slice().sort((a, b) => a.beach_name.localeCompare(b.beach_name));
    pick.innerHTML = opts.map((b) => `<option value="${b.beach_id}">${b.beach_name}</option>`).join('');
    if (!selected || !inIsland(byId[selected])) {
      const top = beaches.filter(inIsland).filter((b) => b.samples >= 20).sort((a, b) => b.exceedance_rate_pct - a.exceedance_rate_pct)[0] || opts[0];
      selected = top.beach_id;
    }
  }
  function renderAll() {
    renderKpis(); renderWeek(); renderWeekly(); renderTable(); renderStreaks(); populatePick(); selectBeach(selected, 'quiet'); fitMap();
  }
  document.querySelectorAll('#islandSeg button').forEach((btn) => btn.addEventListener('click', () => {
    island = btn.dataset.i;
    document.querySelectorAll('#islandSeg button').forEach((b) => b.setAttribute('aria-checked', b === btn ? 'true' : 'false'));
    renderAll();
  }));
  renderAll();
})();
