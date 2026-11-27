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

  // High-contrast semantic palette tailored for the warm parchment canvas
  const colorMap = {
    controller: { bg: '#F5F3FF', border: '#7C3AED', accent: '#7C3AED', text: '#1C1C1C' },
    service:    { bg: '#EFF6FF', border: '#2563EB', accent: '#2563EB', text: '#1C1C1C' },
    module:     { bg: '#ECFDF5', border: '#059669', accent: '#059669', text: '#1C1C1C' },
    schema:     { bg: '#FFFBEB', border: '#D97706', accent: '#D97706', text: '#1C1C1C' },
    document:   { bg: '#F0FDFA', border: '#0D9488', accent: '#0D9488', text: '#1C1C1C' },
    class:      { bg: '#F8FAFC', border: '#475569', accent: '#475569', text: '#1C1C1C' },
    endpoint:   { bg: '#EEF2FF', border: '#4F46E5', accent: '#4F46E5', text: '#1C1C1C' },
    component:  { bg: '#FDF2F8', border: '#DB2777', accent: '#DB2777', text: '#1C1C1C' },
    query:      { bg: '#FFF7ED', border: '#EA580C', accent: '#EA580C', text: '#1C1C1C' },
    method:     { bg: '#F0FDFA', border: '#0F766E', accent: '#0F766E', text: '#1C1C1C' },
    function:   { bg: '#FFFFFF', border: '#64748B', accent: '#334155', text: '#1C1C1C' }
  };

  function getEdgeStyle(type) {
    if (type === 'CALLS') return { color: '#2563EB', dashes: false, width: 1.4 };
    if (type === 'INJECTS') return { color: '#7C3AED', dashes: true, width: 1.8 };
    if (type === 'RENDERS') return { color: '#DB2777', dashes: false, width: 1.8 };
    if (type === 'IMPLEMENTS') return { color: '#059669', dashes: true, width: 1.5 };
    return { color: '#94A3B8', dashes: false, width: 1.1 };
  }

  // Resolve API base URL: same-origin when running locally or on Render, otherwise configured URL
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
  let isIsolated = false;

  // Initialize Vis Network
  const nodesDataSet = new vis.DataSet([]);
  const edgesDataSet = new vis.DataSet([]);
  const container = document.getElementById('network-container');
  const network = new vis.Network(
    container,
    { nodes: nodesDataSet, edges: edgesDataSet },
    {
      nodes: {
        scaling: { min: 10, max: 30 },
        shapeProperties: { borderRadius: 6 }
      },
      edges: { smooth: { enabled: true, type: 'dynamic' } },
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -42,
          centralGravity: 0.006,
          springLength: 82,
          springConstant: 0.12,
          damping: 0.44
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
    const icons = { info: '●', success: '✓', error: '!' };
    if (icon) icon.textContent = icons[kind] || '•';
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

  function setIsolationUi(active, label) {
    isIsolated = active;
    const btnExit = document.getElementById('btn-exit-isolation');
    if (!btnExit) return;
    btnExit.style.display = active ? 'inline-flex' : 'none';
    if (label) btnExit.textContent = label;
  }

  function formatVisNode(n, isCenter = false) {
    const c = colorMap[n.group] || colorMap.class;
    return {
      id: n.id,
      label: n.label,
      shape: n.shape || 'box',
      color: {
        background: isCenter ? c.accent : c.bg,
        border: c.border,
        highlight: { background: c.bg, border: '#1C1C1C' },
        hover: { background: c.bg, border: '#1C1C1C' }
      },
      font: {
        color: isCenter ? '#FFFFFF' : c.text,
        size: 12,
        face: 'Inter, -apple-system, sans-serif',
        strokeWidth: 0
      },
      margin: { top: 6, bottom: 6, left: 10, right: 10 },
      borderWidth: isCenter ? 2.2 : 1.4,
      borderWidthSelected: 2.4,
      shadow: { enabled: true, color: 'rgba(28, 28, 28, 0.07)', size: 6, x: 0, y: 2 },
      meta: n
    };
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
    setIsolationUi(false);

    renderCategoryPills();
    applyFiltersAndRender(true);
  }

  function applyFiltersAndRender(fit) {
    setIsolationUi(false);
    const filteredByCategory = rawNodes.filter((n) => selectedCategories.has(n.group));
    const limitedNodes = filteredByCategory.slice(0, currentNodeLimit);
    const visibleNodeIds = new Set(limitedNodes.map((n) => n.id));

    const formattedNodes = limitedNodes.map((n) => formatVisNode(n, false));

    const formattedEdges = [];
    rawEdges.forEach((e, idx) => {
      if (edgeTypes[e.type] && visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)) {
        const style = getEdgeStyle(e.type);
        formattedEdges.push({
          id: 'e_' + idx,
          from: e.from,
          to: e.to,
          arrows: { to: { enabled: true, scaleFactor: 0.65 } },
          dashes: style.dashes,
          color: { color: style.color, highlight: '#1C1C1C', hover: '#1C1C1C', opacity: 0.62 },
          width: style.width,
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
      btnShowMore.textContent = `+${Math.min(NODE_PAGE_STEP, remaining)}`;
    } else {
      btnShowMore.disabled = true;
      btnShowMore.style.opacity = '0.45';
      btnShowMore.textContent = 'All Shown';
    }

    if (fit) {
      setTimeout(() => {
        network.fit({ animation: { duration: 420, easingFunction: 'easeInOutQuad' } });
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
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'pill ' + (isSelected ? 'active' : '');
      if (isSelected) {
        pill.style.borderColor = c.border;
      }
      pill.innerHTML = `
        <span class="dot" style="background:${c.accent}"></span>
        <span>${cat}</span>
        <span class="pill-count">${groupCounts[cat] || 0}</span>
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

    const hint = document.getElementById('canvas-hint');
    if (hint) hint.style.display = 'none';

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
    network.focus(nodeId, { scale: 1.2, animation: { duration: 420, easingFunction: 'easeInOutQuad' } });

    document.getElementById('inspect-name').textContent = nodeMeta.label;
    const c = colorMap[nodeMeta.group] || colorMap.class;
    const badge = document.getElementById('inspect-badge');
    badge.textContent = (nodeMeta.category || nodeMeta.group).toUpperCase();
    badge.style.background = c.accent;
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
    }).join('') || '<div class="rel-empty">No incoming callers or dependents found.</div>';

    const outEl = document.getElementById('list-outgoing');
    outEl.innerHTML = outgoing.map((e) => {
      const dst = rawNodes.find((n) => n.id === e.to);
      return `<div class="rel-item" data-target="${escapeHtml(e.to)}">
        <span>${escapeHtml(dst ? dst.label : e.to)}</span>
        <span class="rel-tag">${escapeHtml(e.type)}</span>
      </div>`;
    }).join('') || '<div class="rel-empty">No outgoing dependencies found.</div>';

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

    const subNodes = rawNodes
      .filter((n) => visited.has(n.id))
      .map((n) => formatVisNode(n, n.id === centerId));

    const subEdges = [];
    rawEdges.forEach((e, idx) => {
      if (visited.has(e.from) && visited.has(e.to)) {
        const style = getEdgeStyle(e.type);
        subEdges.push({
          id: 'sub_' + idx,
          from: e.from,
          to: e.to,
          arrows: { to: { enabled: true, scaleFactor: 0.65 } },
          dashes: style.dashes,
          color: { color: style.color, highlight: '#1C1C1C', opacity: 0.8 },
          width: style.width
        });
      }
    });

    nodesDataSet.clear();
    nodesDataSet.add(subNodes);
    edgesDataSet.clear();
    edgesDataSet.add(subEdges);
    document.getElementById('stat-visible-nodes').textContent = subNodes.length.toLocaleString();
    document.getElementById('stat-total-edges').textContent = subEdges.length.toLocaleString();
    setIsolationUi(true, `✕ Exit ${depth}-Hop View`);
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
        `No supported source files found (skipped ${skippedUnsupported} unsupported and ${skippedIgnored} ignored files). Upload .py, .ts, .tsx, .js, .jsx, .go, .java, .sql, .json, .md, .csv, .pdf, or .zip.`
      );
      return;
    }

    const capped = valid.slice(0, 600);
    const fileLabel = capped.length === 1 ? '1 file' : `${capped.length} files`;
    setStatusBanner('info', `Parsing ${fileLabel} with the static AST engine…`);

    const coldStartTimer = setTimeout(() => {
      setStatusBanner(
        'info',
        `Starting parser service (~20s on free-tier cold start) — analyzing ${fileLabel}…`
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
        throw new Error(data.error || `Server returned HTTP ${res.status}`);
      }

      loadGraphPayload(data, true);
      setApiIndicator('online', 'Engine Ready');

      const totalSkipped = skippedIgnored + skippedUnsupported + (data.stats?.skipped_unsupported || 0) + (data.stats?.skipped_ignored || 0);
      const skipNote = totalSkipped > 0 ? ` (${totalSkipped} ignored/unsupported skipped)` : '';
      setStatusBanner(
        'success',
        `Mapped "${data.project_name}": ${data.stats.files} files, ${data.nodes.length} symbols, and ${data.edges.length} edges in ${data.stats.elapsed_ms} ms${skipNote}.`
      );
      document.getElementById('explorer').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
      clearTimeout(coldStartTimer);
      setApiIndicator('offline', 'API Offline');
      setStatusBanner(
        'error',
        `Unable to reach the parser API (${getApiBase() || 'local'}): ${err.message}. Click the engine status badge in the header to configure a custom URL, or run "grafeando web" locally.`
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

  // API Warm-up Ping
  function setApiIndicator(state, label) {
    const dot = document.getElementById('api-status-dot');
    const txt = document.getElementById('api-status-text');
    dot.className = 'status-dot ' + state;
    txt.textContent = label;
  }

  async function warmUpApi() {
    const apiBase = getApiBase();
    setApiIndicator('', 'Starting engine…');
    try {
      const res = await fetch(`${apiBase}/api/health`, { method: 'GET' });
      if (res.ok) {
        setApiIndicator('online', 'Engine Ready');
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

  const btnExitIsolation = document.getElementById('btn-exit-isolation');
  if (btnExitIsolation) {
    btnExitIsolation.onclick = () => applyFiltersAndRender(true);
  }

  // Support drag-and-drop on both the upload bar and the graph workspace
  [document.getElementById('dropzone'), document.getElementById('explorer')].forEach((zone) => {
    if (!zone) return;
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', (e) => {
      if (!zone.contains(e.relatedTarget)) {
        zone.classList.remove('drag-over');
      }
    });
    zone.addEventListener('drop', async (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const entries = await readDroppedDataTransfer(e.dataTransfer);
      if (entries.length) uploadEntriesToApi(entries);
    });
  });

  document.getElementById('api-status-pill').onclick = () => {
    const current = getApiBase();
    const next = window.prompt(
      'Enter a custom parser API URL (leave blank to use default configuration):',
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
    network.fit({ animation: { duration: 450, easingFunction: 'easeInOutQuad' } });
  };

  document.getElementById('btn-focus-mode').onclick = () => {
    if (selectedNodeId) {
      isolateNeighborhood(selectedNodeId, 2);
    } else {
      setStatusBanner('info', 'Select any node on the graph first to isolate its 2-hop neighborhood.');
    }
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
    document.getElementById('btn-fullscreen').textContent = wrap.classList.contains('fullscreen') ? 'Exit Fullscreen' : 'Fullscreen';
    setTimeout(() => network.fit({ animation: true }), 120);
  };

  document.getElementById('btn-copy-cmd').onclick = () => {
    const cmd = document.getElementById('install-cmd').textContent;
    navigator.clipboard.writeText(cmd);
    const btn = document.getElementById('btn-copy-cmd');
    btn.textContent = 'Copied';
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
  };

  // Search autocomplete + keyboard shortcuts ('/' to search, 'Escape' to dismiss)
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
    const escapeAttr = (s) => String(s).replace(/"/g, '&quot;').replace(/</g, '&lt;');
    autoList.innerHTML = matches.map((m) => {
      const c = colorMap[m.group] || colorMap.class;
      return `
        <div class="autocomplete-item" data-id="${escapeAttr(m.id)}">
          <div>
            <strong>${escapeAttr(m.label)}</strong>
            <div class="autocomplete-path">${escapeAttr(m.file_path)}</div>
          </div>
          <span class="badge" style="background:${c.accent};margin:0;">${escapeAttr(m.group)}</span>
        </div>
      `;
    }).join('');
    autoList.style.display = 'block';
    autoList.querySelectorAll('.autocomplete-item').forEach((item) => {
      item.onclick = () => {
        window.selectAndFocusNode(item.getAttribute('data-id'), true);
        autoList.style.display = 'none';
        searchInput.value = '';
      };
    });
  });

  document.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName) || '';
    const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
    if (e.key === '/' && !isInput) {
      e.preventDefault();
      searchInput.focus();
    } else if (e.key === 'Escape') {
      autoList.style.display = 'none';
      if (isInput) e.target.blur();
      const wrap = document.getElementById('explorer');
      if (wrap.classList.contains('fullscreen')) {
        wrap.classList.remove('fullscreen');
        document.getElementById('btn-fullscreen').textContent = 'Fullscreen';
        setTimeout(() => network.fit({ animation: true }), 120);
      } else if (document.getElementById('inspector-drawer').classList.contains('open')) {
        document.getElementById('inspector-drawer').classList.remove('open');
      } else if (isIsolated) {
        applyFiltersAndRender(true);
      }
    }
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

  // Boot: load pre-built demo graph + warm up API in parallel
  fetch('./demo-graph.json')
    .then((r) => r.json())
    .then((data) => {
      demoGraphPayload = data;
      loadGraphPayload(data, false);
    })
    .catch(() => {
      setStatusBanner('info', 'Upload a folder or source file above to generate an interactive dependency graph.');
    });

  warmUpApi();
})();
