(function () {
  const SUPPORTED_EXTS = new Set([
    '.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
    '.go', '.java', '.json', '.sql', '.md', '.csv', '.pdf', '.zip'
  ]);

  const IGNORED_DIRS = new Set([
    'venv', '.venv', 'env', '__pycache__', 'build', 'dist',
    'node_modules', '.next', 'target', 'vendor', '.git',
    'real_test_repos', 'graphify-out', 'coverage', '.idea', '.vscode', '__MACOSX'
  ]);

  const colorMap = {
    controller: { bg: '#8b5cf6', border: '#a78bfa', text: '#ffffff' },
    service:    { bg: '#0284c7', border: '#38bdf8', text: '#ffffff' },
    module:     { bg: '#059669', border: '#34d399', text: '#ffffff' },
    schema:     { bg: '#d97706', border: '#fbbf24', text: '#ffffff' },
    document:   { bg: '#0d9488', border: '#5eead4', text: '#ffffff' },
    class:      { bg: '#475569', border: '#94a3b8', text: '#ffffff' },
    endpoint:   { bg: '#4f46e5', border: '#818cf8', text: '#ffffff' },
    component:  { bg: '#db2777', border: '#f472b6', text: '#ffffff' },
    query:      { bg: '#ea580c', border: '#fb923c', text: '#ffffff' },
    method:     { bg: '#0f766e', border: '#2dd4bf', text: '#ffffff' },
    function:   { bg: '#1e293b', border: '#64748b', text: '#cbd5e1' }
  };

  // Resolve API base URL: same-origin when running via `grafeando web` or directly on Render, else configured Render URL
  function getApiBase() {
    const saved = localStorage.getItem('grafeando_api_url');
    if (saved) return saved.replace(/\/+$/, '');
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1' || host.endsWith('.onrender.com')) {
      return '';
    }
    const cfg = (window.GRAFEANDO_CONFIG && window.GRAFEANDO_CONFIG.RENDER_API_URL) || '';
    return cfg.replace(/\/+$/, '');
  }

  // State
  let demoGraphPayload = null;
  let currentPayload = { project_name: 'grafeando (demo)', nodes: [], edges: [], stats: {} };
  let rawNodes = [];
  let rawEdges = [];
  let allCategories = new Set();
  let selectedCategories = new Set();
  let groupCounts = {};
  const NODE_PAGE_STEP = 100;
  let currentNodeLimit = NODE_PAGE_STEP;
  const edgeTypes = { CALLS: true, INJECTS: true, RENDERS: true, IMPLEMENTS: true, CONTAINS: true };
  let selectedNodeId = null;
  let physicsEnabled = true;

  // Initialize Vis Network
  const nodesDataSet = new vis.DataSet([]);
  const edgesDataSet = new vis.DataSet([]);
  const container = document.getElementById('network-container');
  const network = new vis.Network(
    container,
    { nodes: nodesDataSet, edges: edgesDataSet },
    {
      nodes: { scaling: { min: 10, max: 30 } },
      edges: { smooth: { enabled: true, type: 'dynamic' } },
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -38,
          centralGravity: 0.006,
          springLength: 75,
          springConstant: 0.12,
          damping: 0.42
        },
        stabilization: { iterations: 90, updateInterval: 25 }
      },
      interaction: { hover: true, tooltipDelay: 100, keyboard: true }
    }
  );

  let statusToastTimer = null;

  function setStatusBanner(kind, message) {
    const el = document.getElementById('upload-status');
    const icon = document.getElementById('upload-status-icon');
    const msg = document.getElementById('upload-status-msg');
    if (statusToastTimer) {
      clearTimeout(statusToastTimer);
      statusToastTimer = null;
    }
    el.className = 'upload-status ' + (kind || '');
    if (!kind) {
      el.style.display = 'none';
      return;
    }
    const icons = { info: '⏳', success: '✅', error: '⚠️' };
    if (icon) icon.textContent = icons[kind] || 'ℹ️';
    msg.textContent = message;
    el.style.display = 'flex';
    if (kind === 'success') {
      statusToastTimer = setTimeout(() => {
        el.style.display = 'none';
        el.className = 'upload-status';
      }, 6500);
    }
  }

  const closeStatusBtn = document.getElementById('upload-status-close');
  if (closeStatusBtn) {
    closeStatusBtn.addEventListener('click', () => setStatusBanner('', ''));
  }

  function loadGraphPayload(payload, isCustomUpload = false) {
    currentPayload = payload;
    rawNodes = Array.isArray(payload.nodes) ? payload.nodes.slice() : [];
    rawEdges = Array.isArray(payload.edges) ? payload.edges.slice() : [];

    allCategories = new Set();
    groupCounts = {};
    rawNodes.forEach((n) => {
      allCategories.add(n.group);
      groupCounts[n.group] = (groupCounts[n.group] || 0) + 1;
    });
    selectedCategories = new Set(allCategories);
    currentNodeLimit = NODE_PAGE_STEP;
    document.getElementById('limit-select').value = String(NODE_PAGE_STEP);

    document.getElementById('project-label').textContent = payload.project_name || 'Codebase Graph';
    document.getElementById('btn-reset-demo').style.display = isCustomUpload ? 'inline-flex' : 'none';
    document.getElementById('inspector-drawer').classList.remove('open');
    selectedNodeId = null;

    renderCategoryPills();
    applyFiltersAndRender(true);
  }

  function applyFiltersAndRender(fit) {
    const filteredByCategory = rawNodes.filter((n) => selectedCategories.has(n.group));
    const limitedNodes = filteredByCategory.slice(0, currentNodeLimit);
    const visibleNodeIds = new Set(limitedNodes.map((n) => n.id));

    const formattedNodes = limitedNodes.map((n) => {
      const c = colorMap[n.group] || colorMap.class;
      return {
        id: n.id,
        label: n.label,
        shape: n.shape || 'box',
        color: {
          background: c.bg,
          border: c.border,
          highlight: { background: c.border, border: '#ffffff' },
          hover: { background: c.border, border: '#ffffff' }
        },
        font: { color: c.text, size: 12, face: 'Plus Jakarta Sans', strokeWidth: 0 },
        margin: { top: 6, bottom: 6, left: 10, right: 10 },
        borderWidth: 1.5,
        shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 4 },
        meta: n
      };
    });

    const formattedEdges = [];
    rawEdges.forEach((e, idx) => {
      if (edgeTypes[e.type] && visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)) {
        let col = '#475569';
        let dashes = false;
        if (e.type === 'CALLS') col = '#38bdf8';
        if (e.type === 'INJECTS') { col = '#a855f7'; dashes = true; }
        if (e.type === 'RENDERS') col = '#f472b6';
        if (e.type === 'IMPLEMENTS') { col = '#34d399'; dashes = true; }
        if (e.type === 'CONTAINS') col = '#334155';

        formattedEdges.push({
          id: 'e_' + idx,
          from: e.from,
          to: e.to,
          arrows: 'to',
          dashes: dashes,
          color: { color: col, highlight: '#ffffff', opacity: 0.55 },
          width: e.type === 'INJECTS' || e.type === 'RENDERS' ? 2 : 1.2,
          smooth: { type: 'continuous' },
          meta: e
        });
      }
    });

    nodesDataSet.clear();
    nodesDataSet.add(formattedNodes);
    edgesDataSet.clear();
    edgesDataSet.add(formattedEdges);

    document.getElementById('stat-visible-nodes').textContent = formattedNodes.length.toLocaleString();
    document.getElementById('stat-total-nodes').textContent = rawNodes.length.toLocaleString();
    document.getElementById('stat-total-edges').textContent = formattedEdges.length.toLocaleString();

    const btnShowMore = document.getElementById('btn-show-more');
    const remaining = Math.max(0, filteredByCategory.length - limitedNodes.length);
    if (remaining > 0) {
      btnShowMore.disabled = false;
      btnShowMore.style.opacity = '1';
      btnShowMore.textContent = `➕ +${Math.min(NODE_PAGE_STEP, remaining)}`;
    } else {
      btnShowMore.disabled = true;
      btnShowMore.style.opacity = '0.45';
      btnShowMore.textContent = 'All Shown';
    }

    if (fit) {
      setTimeout(() => {
        network.fit({ animation: { duration: 450, easingFunction: 'easeInOutQuad' } });
      }, 80);
    }
  }

  function renderCategoryPills() {
    const pillsContainer = document.getElementById('filter-pills');
    pillsContainer.innerHTML = '';
    const sorted = Array.from(allCategories).sort((a, b) => (groupCounts[b] || 0) - (groupCounts[a] || 0));

    sorted.forEach((cat) => {
      const isSelected = selectedCategories.has(cat);
      const c = colorMap[cat] || colorMap.class;
      const pill = document.createElement('div');
      pill.className = 'pill ' + (isSelected ? 'active' : '');
      if (isSelected) {
        pill.style.background = 'rgba(255,255,255,0.08)';
        pill.style.borderColor = c.border;
      }
      pill.innerHTML = `
        <span class="dot" style="background:${c.bg}"></span>
        <span>${cat}</span>
        <span style="opacity:0.6;font-size:10px;">${groupCounts[cat] || 0}</span>
      `;
      pill.onclick = () => {
        if (selectedCategories.has(cat)) {
          if (selectedCategories.size > 1) selectedCategories.delete(cat);
        } else {
          selectedCategories.add(cat);
        }
        renderCategoryPills();
        applyFiltersAndRender(false);
      };
      pillsContainer.appendChild(pill);
    });
  }

  // Node Selection & Inspector
  window.selectAndFocusNode = function (nodeId, ensureVisible) {
    selectedNodeId = nodeId;
    const nodeMeta = rawNodes.find((n) => n.id === nodeId);
    if (!nodeMeta) return;

    if (ensureVisible && !nodesDataSet.get(nodeId)) {
      selectedCategories.add(nodeMeta.group);
      renderCategoryPills();
      const idx = rawNodes.indexOf(nodeMeta);
      if (idx >= currentNodeLimit) {
        rawNodes.splice(idx, 1);
        rawNodes.unshift(nodeMeta);
      }
      applyFiltersAndRender(false);
    }

    network.selectNodes([nodeId]);
    network.focus(nodeId, { scale: 1.2, animation: { duration: 450, easingFunction: 'easeInOutQuad' } });

    document.getElementById('inspect-name').textContent = nodeMeta.label;
    const c = colorMap[nodeMeta.group] || colorMap.class;
    const badge = document.getElementById('inspect-badge');
    badge.textContent = (nodeMeta.category || nodeMeta.group).toUpperCase();
    badge.style.background = c.bg;
    document.getElementById('inspect-file').textContent = `${nodeMeta.file_path}:${nodeMeta.start_line || 1}`;

    const incoming = rawEdges.filter((e) => e.to === nodeId);
    const outgoing = rawEdges.filter((e) => e.from === nodeId);
    document.getElementById('count-incoming').textContent = incoming.length;
    document.getElementById('count-outgoing').textContent = outgoing.length;

    const escapeHtml = (str) => String(str).replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));

    const inEl = document.getElementById('list-incoming');
    inEl.innerHTML = incoming.map((e) => {
      const src = rawNodes.find((n) => n.id === e.from);
      return `<div class="rel-item" data-target="${escapeHtml(e.from)}">
        <span>${escapeHtml(src ? src.label : e.from)}</span>
        <span class="rel-tag">${escapeHtml(e.type)}</span>
      </div>`;
    }).join('') || '<div style="font-size:11px;color:#64748b;">No incoming dependents</div>';

    const outEl = document.getElementById('list-outgoing');
    outEl.innerHTML = outgoing.map((e) => {
      const dst = rawNodes.find((n) => n.id === e.to);
      return `<div class="rel-item" data-target="${escapeHtml(e.to)}">
        <span>${escapeHtml(dst ? dst.label : e.to)}</span>
        <span class="rel-tag">${escapeHtml(e.type)}</span>
      </div>`;
    }).join('') || '<div style="font-size:11px;color:#64748b;">No outgoing dependencies</div>';

    [inEl, outEl].forEach((listEl) => {
      listEl.querySelectorAll('.rel-item').forEach((item) => {
        item.onclick = () => window.selectAndFocusNode(item.getAttribute('data-target'), true);
      });
    });

    document.getElementById('inspector-drawer').classList.add('open');
  };

  function isolateNeighborhood(centerId, depth) {
    const visited = new Set([centerId]);
    let layer = new Set([centerId]);
    for (let i = 0; i < depth; i++) {
      const next = new Set();
      rawEdges.forEach((e) => {
        if (layer.has(e.from) && !visited.has(e.to)) { visited.add(e.to); next.add(e.to); }
        if (layer.has(e.to) && !visited.has(e.from)) { visited.add(e.from); next.add(e.from); }
      });
      layer = next;
    }

    const subNodes = rawNodes.filter((n) => visited.has(n.id)).map((n) => {
      const c = colorMap[n.group] || colorMap.class;
      return {
        id: n.id,
        label: n.label,
        shape: n.shape || 'box',
        color: { background: c.bg, border: c.border },
        font: { color: c.text, size: 12, face: 'Plus Jakarta Sans' },
        meta: n
      };
    });

    const subEdges = [];
    rawEdges.forEach((e, idx) => {
      if (visited.has(e.from) && visited.has(e.to)) {
        let col = '#475569';
        let dashes = false;
        if (e.type === 'CALLS') col = '#38bdf8';
        if (e.type === 'INJECTS') { col = '#a855f7'; dashes = true; }
        if (e.type === 'RENDERS') col = '#f472b6';
        if (e.type === 'IMPLEMENTS') { col = '#34d399'; dashes = true; }
        if (e.type === 'CONTAINS') col = '#334155';
        subEdges.push({
          id: 'sub_' + idx,
          from: e.from,
          to: e.to,
          arrows: 'to',
          dashes: dashes,
          color: { color: col, opacity: 0.75 },
          width: 1.5
        });
      }
    });

    nodesDataSet.clear();
    nodesDataSet.add(subNodes);
    edgesDataSet.clear();
    edgesDataSet.add(subEdges);
    document.getElementById('stat-visible-nodes').textContent = subNodes.length.toLocaleString();
    document.getElementById('stat-total-edges').textContent = subEdges.length.toLocaleString();
    network.fit({ animation: true });
  }

  // Client-side file filtering & upload
  function getExt(name) {
    const idx = name.lastIndexOf('.');
    return idx >= 0 ? name.slice(idx).toLowerCase() : '';
  }

  function shouldIgnorePath(relPath) {
    const parts = relPath.replace(/\\/g, '/').split('/').filter(Boolean);
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts[i];
      if (IGNORED_DIRS.has(seg) || (seg.startsWith('.') && seg !== '.agents')) {
        return true;
      }
    }
    const base = parts[parts.length - 1] || '';
    return base === '.DS_Store' || base === 'Thumbs.db' || base.startsWith('._');
  }

  async function uploadEntriesToApi(entries) {
    const valid = [];
    let skippedIgnored = 0;
    let skippedUnsupported = 0;

    for (const item of entries) {
      const relPath = (item.path || item.file.webkitRelativePath || item.file.name || '').replace(/^\/+/, '');
      if (!relPath) continue;
      if (shouldIgnorePath(relPath)) {
        skippedIgnored++;
        continue;
      }
      if (!SUPPORTED_EXTS.has(getExt(relPath))) {
        skippedUnsupported++;
        continue;
      }
      valid.push({ file: item.file, path: relPath });
    }

    if (valid.length === 0) {
      setStatusBanner(
        'error',
        `No supported files found (skipped ${skippedUnsupported} unsupported and ${skippedIgnored} ignored files). Supported: .py, .ts, .tsx, .js, .jsx, .mjs, .cjs, .go, .java, .sql, .json, .md, .csv, .pdf, or .zip.`
      );
      return;
    }

    const capped = valid.slice(0, 600);
    setStatusBanner('info', `Parsing ${capped.length} supported file(s) with Grafeando Python AST engine...`);

    const coldStartTimer = setTimeout(() => {
      setStatusBanner(
        'info',
        `Waking up Python AST engine on Render (~20s on free-tier cold start) — parsing ${capped.length} file(s)...`
      );
    }, 2800);

    const formData = new FormData();
    capped.forEach(({ file, path }) => {
      formData.append('files', file, path);
      formData.append('paths', path);
    });

    try {
      const apiBase = getApiBase();
      const res = await fetch(`${apiBase}/api/graph`, {
        method: 'POST',
        body: formData
      });
      clearTimeout(coldStartTimer);

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || `Server responded with status ${res.status}`);
      }

      loadGraphPayload(data, true);
      setApiIndicator('online', 'Engine Online');

      const totalSkipped = skippedIgnored + skippedUnsupported + (data.stats?.skipped_unsupported || 0) + (data.stats?.skipped_ignored || 0);
      const skipNote = totalSkipped > 0 ? ` · Skipped ${totalSkipped} ignored/unsupported files` : '';
      setStatusBanner(
        'success',
        `Loaded "${data.project_name}": ${data.stats.files} supported file(s), ${data.nodes.length} symbols, ${data.edges.length} relationships in ${data.stats.elapsed_ms} ms${skipNote}.`
      );
      document.getElementById('explorer').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
      clearTimeout(coldStartTimer);
      setApiIndicator('offline', 'API Unreachable');
      setStatusBanner(
        'error',
        `Could not reach Python parser API (${getApiBase() || 'local'}): ${err.message}. Click the status pill in the top bar to set your Render URL or run "grafeando web" locally.`
      );
    }
  }

  // Recursive drag-and-drop folder reader
  async function readDroppedDataTransfer(dataTransfer) {
    const out = [];
    const items = Array.from(dataTransfer.items || []);

    async function traverseEntry(entry, prefix) {
      if (!entry) return;
      if (entry.isFile) {
        await new Promise((resolve) => {
          entry.file((file) => {
            out.push({ file, path: prefix + file.name });
            resolve();
          }, () => resolve());
        });
      } else if (entry.isDirectory) {
        if (IGNORED_DIRS.has(entry.name) || (entry.name.startsWith('.') && entry.name !== '.agents')) {
          return;
        }
        const reader = entry.createReader();
        const readBatch = () =>
          new Promise((resolve) => {
            reader.readEntries(async (entries) => {
              if (!entries || entries.length === 0) {
                resolve();
                return;
              }
              for (const child of entries) {
                await traverseEntry(child, `${prefix}${entry.name}/`);
              }
              await readBatch();
              resolve();
            }, () => resolve());
          });
        await readBatch();
      }
    }

    if (items.length > 0 && typeof items[0].webkitGetAsEntry === 'function') {
      const entries = items.map((it) => it.webkitGetAsEntry()).filter(Boolean);
      for (const entry of entries) {
        await traverseEntry(entry, '');
      }
      if (out.length > 0) return out;
    }

    return Array.from(dataTransfer.files || []).map((file) => ({
      file,
      path: file.webkitRelativePath || file.name
    }));
  }

  // API Warm-up Ping (wakes Render free tier on page open)
  function setApiIndicator(state, label) {
    const dot = document.getElementById('api-status-dot');
    const txt = document.getElementById('api-status-text');
    dot.className = 'status-dot ' + state;
    txt.textContent = label;
  }

  async function warmUpApi() {
    const apiBase = getApiBase();
    setApiIndicator('', 'Waking engine...');
    try {
      const res = await fetch(`${apiBase}/api/health`, { method: 'GET' });
      if (res.ok) {
        setApiIndicator('online', 'Engine Online');
      } else {
        setApiIndicator('offline', 'Demo Mode');
      }
    } catch (_) {
      setApiIndicator('offline', 'Demo Mode');
    }
  }

  // Wire up UI controls
  document.getElementById('btn-pick-folder').onclick = () => document.getElementById('input-folder').click();
  document.getElementById('btn-pick-files').onclick = () => document.getElementById('input-files').click();

  document.getElementById('input-folder').onchange = (e) => {
    const files = Array.from(e.target.files || []).map((f) => ({ file: f, path: f.webkitRelativePath || f.name }));
    if (files.length) uploadEntriesToApi(files);
    e.target.value = '';
  };

  document.getElementById('input-files').onchange = (e) => {
    const files = Array.from(e.target.files || []).map((f) => ({ file: f, path: f.name }));
    if (files.length) uploadEntriesToApi(files);
    e.target.value = '';
  };

  document.getElementById('btn-reset-demo').onclick = () => {
    if (demoGraphPayload) {
      loadGraphPayload(demoGraphPayload, false);
      setStatusBanner('', '');
    }
  };

  const dropzone = document.getElementById('dropzone');
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    const entries = await readDroppedDataTransfer(e.dataTransfer);
    if (entries.length) uploadEntriesToApi(entries);
  });

  document.getElementById('api-status-pill').onclick = () => {
    const current = getApiBase();
    const next = window.prompt(
      'Enter your Render Python API URL (leave empty to reset to default config.js):',
      current
    );
    if (next === null) return;
    if (next.trim()) {
      localStorage.setItem('grafeando_api_url', next.trim().replace(/\/+$/, ''));
    } else {
      localStorage.removeItem('grafeando_api_url');
    }
    warmUpApi();
  };

  document.getElementById('select-all-cats').onclick = () => {
    selectedCategories = new Set(allCategories);
    renderCategoryPills();
    applyFiltersAndRender(true);
  };

  document.getElementById('clear-all-cats').onclick = () => {
    const core = ['controller', 'service', 'endpoint', 'component', 'schema'].filter((c) => allCategories.has(c));
    selectedCategories = new Set(core.length ? core : allCategories);
    renderCategoryPills();
    applyFiltersAndRender(true);
  };

  document.getElementById('limit-select').onchange = (e) => {
    currentNodeLimit = parseInt(e.target.value, 10) || NODE_PAGE_STEP;
    applyFiltersAndRender(true);
  };

  document.getElementById('btn-show-more').onclick = () => {
    currentNodeLimit += NODE_PAGE_STEP;
    applyFiltersAndRender(false);
  };

  ['CALLS', 'INJECTS', 'RENDERS', 'CONTAINS'].forEach((type) => {
    const btn = document.getElementById(`toggle-${type.toLowerCase()}`);
    if (!btn) return;
    btn.onclick = () => {
      edgeTypes[type] = !edgeTypes[type];
      btn.classList.toggle('btn-active', edgeTypes[type]);
      applyFiltersAndRender(false);
    };
  });

  document.getElementById('btn-physics').onclick = () => {
    physicsEnabled = !physicsEnabled;
    network.setOptions({ physics: { enabled: physicsEnabled } });
    document.getElementById('btn-physics').classList.toggle('btn-active', physicsEnabled);
  };

  document.getElementById('btn-fit').onclick = () => {
    network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
  };

  document.getElementById('btn-focus-mode').onclick = () => {
    if (selectedNodeId) isolateNeighborhood(selectedNodeId, 2);
    else setStatusBanner('info', 'Click any node in the graph first to isolate its 2-hop neighborhood.');
  };

  document.getElementById('btn-calc-blast').onclick = () => {
    if (selectedNodeId) isolateNeighborhood(selectedNodeId, 3);
  };

  document.getElementById('inspect-close').onclick = () => {
    document.getElementById('inspector-drawer').classList.remove('open');
  };

  document.getElementById('btn-download-json').onclick = () => {
    const blob = new Blob([JSON.stringify(currentPayload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(currentPayload.project_name || 'grafeando').replace(/[^a-z0-9_-]/gi, '_')}-graph.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  document.getElementById('btn-fullscreen').onclick = () => {
    const wrap = document.getElementById('explorer');
    wrap.classList.toggle('fullscreen');
    document.getElementById('btn-fullscreen').textContent = wrap.classList.contains('fullscreen') ? '✕ Exit' : '⛶ Fullscreen';
    setTimeout(() => network.fit({ animation: true }), 120);
  };

  document.getElementById('btn-copy-cmd').onclick = () => {
    const cmd = document.getElementById('install-cmd').textContent;
    navigator.clipboard.writeText(cmd);
    const btn = document.getElementById('btn-copy-cmd');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
  };

  // Search autocomplete
  const searchInput = document.getElementById('search-input');
  const autoList = document.getElementById('autocomplete-list');
  searchInput.addEventListener('input', (e) => {
    const val = e.target.value.toLowerCase().trim();
    if (!val) {
      autoList.style.display = 'none';
      return;
    }
    const matches = rawNodes
      .filter((n) => n.label.toLowerCase().includes(val) || n.file_path.toLowerCase().includes(val))
      .slice(0, 15);
    if (!matches.length) {
      autoList.style.display = 'none';
      return;
    }
    autoList.innerHTML = matches.map((m) => `
      <div class="autocomplete-item" data-id="${m.id.replace(/"/g, '&quot;')}">
        <div>
          <strong>${m.label}</strong>
          <div style="font-size:10px;color:#64748b;">${m.file_path}</div>
        </div>
        <span class="badge" style="background:${colorMap[m.group]?.bg || '#475569'}">${m.group}</span>
      </div>
    `).join('');
    autoList.style.display = 'block';
    autoList.querySelectorAll('.autocomplete-item').forEach((item) => {
      item.onclick = () => {
        window.selectAndFocusNode(item.getAttribute('data-id'), true);
        autoList.style.display = 'none';
        searchInput.value = '';
      };
    });
  });

  document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !autoList.contains(e.target)) {
      autoList.style.display = 'none';
    }
  });

  network.on('click', (params) => {
    if (params.nodes.length > 0) {
      window.selectAndFocusNode(params.nodes[0], false);
    }
  });

  // Boot: load pre-built demo graph + warm up Render API in parallel
  fetch('./demo-graph.json')
    .then((r) => r.json())
    .then((data) => {
      demoGraphPayload = data;
      loadGraphPayload(data, false);
    })
    .catch(() => {
      setStatusBanner('info', 'Upload a folder or file above to generate your interactive graph.');
    });

  warmUpApi();
})();
