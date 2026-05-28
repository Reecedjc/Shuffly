const state = {
  shows: [],
  playlists: [],
  currentId: null,
  selectedShowPaths: new Set(),
  selectedEpisodeIds: [],
  settings: null,
  browsePurpose: null,
  browsePath: "/",
  loadingCount: 0,
};

const el = {
  scanButton:     document.querySelector("#scanButton"),
  exportButton:   document.querySelector("#exportButton"),
  importInput:    document.querySelector("#importInput"),
  showCount:      document.querySelector("#showCount"),
  showGrid:       document.querySelector("#showGrid"),
  playlistSelect: document.querySelector("#playlistSelect"),
  playlistForm:   document.querySelector("#playlistForm"),
  title:          document.querySelector("#title"),
  mode:           document.querySelector("#mode"),
  seed:           document.querySelector("#seed"),
  outputFolder:   document.querySelector("#outputFolder"),
  clearButton:    document.querySelector("#clearButton"),
  generateButton: document.querySelector("#generateButton"),
  selectedCount:  document.querySelector("#selectedCount"),
  selectedEpisodes: document.querySelector("#selectedEpisodes"),
  log:            document.querySelector("#log"),
  progressBar:    document.querySelector("#progressBar"),
  modal:          document.querySelector("#modal"),
  modalBackdrop:  document.querySelector("#modalBackdrop"),
  modalTitle:     document.querySelector("#modalTitle"),
  modalBody:      document.querySelector("#modalBody"),
  modalClose:     document.querySelector("#modalClose"),
  addMediaFolder: document.querySelector("#addMediaFolder"),
  addOutputFolder: document.querySelector("#addOutputFolder"),
  mediaFolderList: document.querySelector("#mediaFolderList"),
  outputFolderList: document.querySelector("#outputFolderList"),
  configFolder:   document.querySelector("#configFolder"),
  browserBackdrop: document.querySelector("#browserBackdrop"),
  browserTitle:   document.querySelector("#browserTitle"),
  browserPath:    document.querySelector("#browserPath"),
  browserError:   document.querySelector("#browserError"),
  browserList:    document.querySelector("#browserList"),
  browserUse:     document.querySelector("#browserUse"),
  browserClose:   document.querySelector("#browserClose"),
};

// ── Loading bar ───────────────────────────────────────────────────

function setLoading(on) {
  state.loadingCount = Math.max(0, state.loadingCount + (on ? 1 : -1));
  el.progressBar.classList.toggle("loading", state.loadingCount > 0);
}

// ── Logging ───────────────────────────────────────────────────────

function log(message, payload = null) {
  const text = payload
    ? `${message}\n${JSON.stringify(payload, null, 2)}`
    : message;
  el.log.textContent = `${new Date().toLocaleTimeString()} ${text}\n\n${el.log.textContent}`;
}

// ── API wrapper ───────────────────────────────────────────────────

async function api(path, options = {}) {
  setLoading(true);
  try {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : { detail: await response.text() };
    if (!response.ok) throw new Error(data.detail || response.statusText);
    return data;
  } finally {
    setLoading(false);
  }
}

// ── Helpers ───────────────────────────────────────────────────────

function allEpisodes() {
  return state.shows.flatMap((show) => show.episodes);
}

function selectedEpisodeObjects() {
  const byId = new Map(allEpisodes().map((ep) => [ep.id, ep]));
  return state.selectedEpisodeIds.map((id) => byId.get(id)).filter(Boolean);
}

function selectionCountForShow(show) {
  return show.episodes.filter((ep) => state.selectedEpisodeIds.includes(ep.id)).length;
}

function formatEpisodeNumber(ep) {
  const s = ep.season == null ? "?" : String(ep.season).padStart(2, "0");
  const e = ep.episode == null ? "?" : String(ep.episode).padStart(2, "0");
  return `S${s}E${e}`;
}

function groupBySeason(episodes) {
  const map = new Map();
  for (const ep of episodes) {
    const key = ep.season ?? null;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(ep);
  }
  // Sort: numbered seasons first (ascending), then null last
  const sorted = new Map(
    [...map.entries()].sort(([a], [b]) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return a - b;
    })
  );
  return sorted;
}

function addEpisode(id) {
  if (!state.selectedEpisodeIds.includes(id)) state.selectedEpisodeIds.push(id);
}

function removeEpisode(id) {
  state.selectedEpisodeIds = state.selectedEpisodeIds.filter((i) => i !== id);
}

function moveEpisode(fromIdx, toIdx) {
  const ids = state.selectedEpisodeIds;
  if (fromIdx < 0 || fromIdx >= ids.length) return;
  if (toIdx < 0 || toIdx >= ids.length) return;
  if (fromIdx === toIdx) return;
  const [moved] = ids.splice(fromIdx, 1);
  ids.splice(toIdx, 0, moved);
  renderSelectedEpisodes();
}

// Remove show from selectedShowPaths if it has no remaining selected episodes
function syncShowPath(showName) {
  const showObj = state.shows.find((s) => s.name === showName);
  if (showObj && selectionCountForShow(showObj) === 0) {
    state.selectedShowPaths.delete(showObj.path);
  }
}

// Make a checked checkbox that stops click from toggling a parent <details>
function makeSelCb(onChange) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "sel-remove-btn";
  btn.textContent = "×";
  btn.setAttribute("aria-label", "Remove");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    onChange();
  });
  return btn;
}


// ── Renders ───────────────────────────────────────────────────────

function renderCardGrid() {
  el.showGrid.innerHTML = "";
  el.showCount.textContent = state.shows.length
    ? `${state.shows.length} shows`
    : "";

  const fragment = document.createDocumentFragment();

  for (const show of state.shows) {
    const count = selectionCountForShow(show);
    const card = document.createElement("div");
    card.className = "show-card" + (count > 0 ? " has-selection" : "");
    card.title = show.name;

    // Poster
    const wrap = document.createElement("div");
    wrap.className = "poster-wrap";

    // Selection badge (inside wrap so clicks on it open the modal)
    const badge = document.createElement("span");
    badge.className = "selection-badge";
    badge.textContent = count;
    wrap.append(badge);
    if (show.poster_url) {
      const img = document.createElement("img");
      img.src = show.poster_url;
      img.alt = show.name;
      img.addEventListener("error", () => {
        img.remove();
        wrap.append(makePosterInitial(show.name));
      });
      wrap.append(img);
    } else {
      wrap.append(makePosterInitial(show.name));
    }
    card.append(wrap);

    // Info bar
    const info = document.createElement("div");
    info.className = "card-info";

    const textWrap = document.createElement("div");
    textWrap.className = "card-text";
    const titleEl = document.createElement("div");
    titleEl.className = "card-title";
    titleEl.textContent = show.name;
    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = `${show.episodes.length} episodes`;
    textWrap.append(titleEl, meta);

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "card-select-cb";
    cb.title = "Select all episodes";
    cb.checked = count === show.episodes.length && show.episodes.length > 0;
    cb.indeterminate = count > 0 && count < show.episodes.length;
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      if (cb.checked) {
        show.episodes.forEach((ep) => addEpisode(ep.id));
        state.selectedShowPaths.add(show.path);
      } else {
        show.episodes.forEach((ep) => removeEpisode(ep.id));
        state.selectedShowPaths.delete(show.path);
      }
      renderCardGrid();
      renderSelectedEpisodes();
    });

    info.append(textWrap, cb);
    card.append(info);

    wrap.addEventListener("click", () => openShowModal(show));
    info.addEventListener("click", (e) => {
      if (e.target === cb) return;
      cb.checked = !cb.checked;
      cb.dispatchEvent(new Event("change"));
    });
    fragment.append(card);
  }

  el.showGrid.append(fragment);
}

function makePosterInitial(name) {
  const span = document.createElement("span");
  span.className = "poster-initial";
  span.textContent = name.trim()[0] || "?";
  return span;
}

function renderPlaylists() {
  el.playlistSelect.innerHTML = "";
  const newOpt = document.createElement("option");
  newOpt.value = "";
  newOpt.textContent = "New playlist";
  el.playlistSelect.append(newOpt);
  for (const pl of state.playlists) {
    const opt = document.createElement("option");
    opt.value = pl.id;
    opt.textContent = pl.title;
    el.playlistSelect.append(opt);
  }
  el.playlistSelect.value = state.currentId || "";
}

function defaultOutputFolder() {
  return state.settings?.default_output_folder || "";
}

function validOutputFolder(path) {
  return state.settings?.output_folders?.some((item) => item.path === path);
}

function renderOutputFolderSelect(selected = null) {
  el.outputFolder.innerHTML = "";
  const folders = state.settings?.output_folders || [];
  if (folders.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No output folders configured";
    el.outputFolder.append(option);
    el.outputFolder.disabled = true;
    return;
  }
  el.outputFolder.disabled = false;
  const selectedPath = validOutputFolder(selected)
    ? selected
    : defaultOutputFolder();
  for (const folder of folders) {
    const option = document.createElement("option");
    option.value = folder.path;
    option.textContent = folder.is_default
      ? `${folder.path} (default)`
      : folder.path;
    el.outputFolder.append(option);
  }
  el.outputFolder.value = selectedPath || folders[0].path;
}

function renderOrderedList(episodes, flipPositions = new Map()) {
  const hint = document.createElement("p");
  hint.className = "ordered-hint";
  hint.textContent = "Drag to reorder";
  el.selectedEpisodes.append(hint);

  for (let i = 0; i < episodes.length; i++) {
    const ep = episodes[i];
    const row = document.createElement("div");
    row.className = "ord-ep-row";
    row.draggable = true;
    row.dataset.idx = i;
    row.dataset.epId = ep.id;

    const handle = document.createElement("span");
    handle.className = "ord-handle";
    handle.textContent = "⠿";
    handle.setAttribute("aria-hidden", "true");

    const pos = document.createElement("span");
    pos.className = "ord-pos";
    pos.textContent = `#${i + 1}`;

    const cb = makeSelCb(() => {
      removeEpisode(ep.id);
      syncShowPath(ep.show);
      renderSelectedEpisodes();
      requestAnimationFrame(() => renderCardGrid());
    });

    const label = document.createElement("span");
    label.className = "ord-label";
    const fullText = [ep.show, formatEpisodeNumber(ep), ep.title].filter(Boolean).join(" · ");
    label.textContent = fullText;
    label.title = fullText;

    const upBtn = document.createElement("button");
    upBtn.className = "ord-move-btn";
    upBtn.textContent = "↑";
    upBtn.title = "Move up";
    upBtn.disabled = i === 0;
    upBtn.addEventListener("click", () => moveEpisode(i, i - 1));

    const downBtn = document.createElement("button");
    downBtn.className = "ord-move-btn";
    downBtn.textContent = "↓";
    downBtn.title = "Move down";
    downBtn.disabled = i === episodes.length - 1;
    downBtn.addEventListener("click", () => moveEpisode(i, i + 1));

    row.append(handle, pos, cb, label, upBtn, downBtn);

    row.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", String(i));
      e.dataTransfer.effectAllowed = "move";
      // defer so drag ghost captures the un-dimmed row
      requestAnimationFrame(() => row.classList.add("ord-dragging"));
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("ord-dragging");
      el.selectedEpisodes
        .querySelectorAll(".ord-drop-target")
        .forEach((r) => r.classList.remove("ord-drop-target"));
    });
    row.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      el.selectedEpisodes
        .querySelectorAll(".ord-drop-target")
        .forEach((r) => r.classList.remove("ord-drop-target"));
      row.classList.add("ord-drop-target");
    });
    row.addEventListener("dragleave", () => row.classList.remove("ord-drop-target"));
    row.addEventListener("drop", (e) => {
      e.preventDefault();
      const fromIdx = Number(e.dataTransfer.getData("text/plain"));
      const toIdx = Number(row.dataset.idx);
      if (fromIdx !== toIdx) moveEpisode(fromIdx, toIdx);
    });

    el.selectedEpisodes.append(row);
  }

  // FLIP steps 2-4 — read new positions, invert, then play to natural position
  el.selectedEpisodes.querySelectorAll(".ord-ep-row[data-ep-id]").forEach((row) => {
    const delta = (flipPositions.get(row.dataset.epId) ?? null);
    if (delta === null) return;
    const dy = delta - row.getBoundingClientRect().top;
    if (Math.abs(dy) < 1) return;

    // Invert: jump to old position instantly
    row.style.transition = "none";
    row.style.transform = `translateY(${dy}px)`;

    // Play: animate to final position
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        row.style.transition = "transform 0.25s ease";
        row.style.transform = "translateY(0)";
        row.addEventListener("transitionend", (e) => {
          if (e.propertyName === "transform") {
            row.style.transition = "";
            row.style.transform = "";
          }
        }, { once: true });
      });
    });
  });
}

function renderSelectedEpisodes() {
  // Snapshot which dropdowns are open before wiping the DOM
  const openShows = new Set(
    [...el.selectedEpisodes.querySelectorAll("details.sel-show[open]")]
      .map((d) => d.dataset.show)
  );
  const openSeasons = new Set(
    [...el.selectedEpisodes.querySelectorAll("details.sel-season[open]")]
      .map((d) => d.dataset.season)
  );

  // FLIP step 1 — snapshot Y positions before the DOM is wiped
  const flipPositions = new Map();
  el.selectedEpisodes.querySelectorAll(".ord-ep-row[data-ep-id]").forEach((row) => {
    flipPositions.set(row.dataset.epId, row.getBoundingClientRect().top);
  });
  const treeFlipPositions = new Map();
  el.selectedEpisodes.querySelectorAll(".sel-show[data-show]").forEach((row) => {
    treeFlipPositions.set(row.dataset.show, row.getBoundingClientRect().top);
  });

  const episodes = selectedEpisodeObjects();
  el.selectedCount.textContent = episodes.length;
  el.selectedEpisodes.innerHTML = "";

  if (episodes.length === 0) return;

  if (el.mode.value === "selected_order") {
    renderOrderedList(episodes, flipPositions);
    return;
  }

  // Group: show -> season -> episodes (preserving selection order within each bucket)
  const byShow = new Map();
  for (const ep of episodes) {
    if (!byShow.has(ep.show)) byShow.set(ep.show, new Map());
    const seasons = byShow.get(ep.show);
    const key = ep.season ?? null;
    if (!seasons.has(key)) seasons.set(key, []);
    seasons.get(key).push(ep);
  }

  const fragment = document.createDocumentFragment();

  for (const [showName, seasons] of [...byShow.entries()].sort(([a], [b]) => a.localeCompare(b, undefined, { sensitivity: "base" }))) {
    const totalForShow = [...seasons.values()].reduce((n, eps) => n + eps.length, 0);
    const allShowEps = [...seasons.values()].flat();

    const showDetails = document.createElement("details");
    showDetails.className = "sel-show";
    showDetails.dataset.show = showName;
    showDetails.open = openShows.has(showName);

    const showSummary = document.createElement("summary");
    showSummary.className = "sel-summary";

    const showCb = makeSelCb(() => {
      allShowEps.forEach((ep) => removeEpisode(ep.id));
      const showObj = state.shows.find((s) => s.name === showName);
      if (showObj) state.selectedShowPaths.delete(showObj.path);
      renderCardGrid();
      renderSelectedEpisodes();
    });
    const showChevron = document.createElement("span");
    showChevron.className = "sel-chevron";
    showChevron.textContent = "▼";
    const showLabel = document.createElement("span");
    showLabel.className = "sel-label";
    showLabel.textContent = showName;
    const showPill = document.createElement("span");
    showPill.className = "sel-pill";
    showPill.textContent = totalForShow;
    showSummary.append(showCb, showChevron, showLabel, showPill);
    showDetails.append(showSummary);

    const sortedSeasons = [...seasons.entries()].sort(([a], [b]) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return a - b;
    });

    for (const [seasonKey, eps] of sortedSeasons) {
      const seasonLabel = seasonKey === null
        ? "Unknown Season"
        : `Season ${String(seasonKey).padStart(2, "0")}`;

      const seasonKey2 = `${showName}::${seasonKey}`;
      const seasonDetails = document.createElement("details");
      seasonDetails.className = "sel-season";
      seasonDetails.dataset.season = seasonKey2;
      seasonDetails.open = openSeasons.has(seasonKey2);

      const seasonSummary = document.createElement("summary");
      seasonSummary.className = "sel-summary sel-season-summary";

      const seasonCb = makeSelCb(() => {
        eps.forEach((ep) => removeEpisode(ep.id));
        syncShowPath(showName);
        renderCardGrid();
        renderSelectedEpisodes();
      });
      const seasonChevron = document.createElement("span");
      seasonChevron.className = "sel-chevron";
      seasonChevron.textContent = "▼";
      const seasonLabelEl = document.createElement("span");
      seasonLabelEl.className = "sel-label";
      seasonLabelEl.textContent = seasonLabel;
      const seasonPill = document.createElement("span");
      seasonPill.className = "sel-pill";
      seasonPill.textContent = eps.length;
      seasonSummary.append(seasonCb, seasonChevron, seasonLabelEl, seasonPill);
      seasonDetails.append(seasonSummary);

      const episodeList = document.createElement("div");
      episodeList.className = "sel-episode-list";
      for (const ep of [...eps].sort((a, b) => (a.episode ?? 9999) - (b.episode ?? 9999))) {
        const row = document.createElement("div");
        row.className = "sel-ep-row";
        const epCb = makeSelCb(() => {
          removeEpisode(ep.id);
          syncShowPath(showName);
          renderCardGrid();
          renderSelectedEpisodes();
        });
        const num = document.createElement("span");
        num.className = "ep-num";
        num.textContent = formatEpisodeNumber(ep);
        const title = document.createElement("span");
        title.className = "ep-title";
        title.textContent = ep.title;
        row.append(epCb, num, title);
        episodeList.append(row);
      }

      seasonDetails.append(episodeList);
      showDetails.append(seasonDetails);
    }

    fragment.append(showDetails);
  }

  el.selectedEpisodes.append(fragment);

  // FLIP steps 2-4 (tree) — slide shows up into their new positions
  el.selectedEpisodes.querySelectorAll(".sel-show[data-show]").forEach((showEl) => {
    const oldTop = treeFlipPositions.get(showEl.dataset.show);
    if (oldTop === undefined) return;
    const dy = oldTop - showEl.getBoundingClientRect().top;
    if (Math.abs(dy) < 1) return;
    showEl.style.transition = "none";
    showEl.style.transform = `translateY(${dy}px)`;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        showEl.style.transition = "transform 0.22s ease";
        showEl.style.transform = "translateY(0)";
        showEl.addEventListener("transitionend", (e) => {
          if (e.propertyName === "transform") {
            showEl.style.transition = "";
            showEl.style.transform = "";
          }
        }, { once: true });
      });
    });
  });
}

// ── Modal ─────────────────────────────────────────────────────────

function openShowModal(show) {
  el.modal.classList.remove("confirm-modal");
  el.modalTitle.textContent = show.name;
  el.modalBody.innerHTML = "";

  const seasons = groupBySeason(show.episodes);

  for (const [seasonKey, episodes] of seasons) {
    const seasonLabel = seasonKey === null
      ? "Unknown Season"
      : `Season ${String(seasonKey).padStart(2, "0")}`;

    const details = document.createElement("details");
    details.className = "season";
    // Open the first season by default
    if (seasons.keys().next().value === seasonKey) details.open = true;

    // Summary row
    const summary = document.createElement("summary");

    const chevron = document.createElement("span");
    chevron.className = "season-chevron";
    chevron.textContent = "▼";

    const nameSpan = document.createElement("span");
    nameSpan.textContent = seasonLabel;

    const metaSpan = document.createElement("span");
    metaSpan.className = "season-meta";
    metaSpan.textContent = `${episodes.length} episodes`;

    const selectAllLabel = document.createElement("label");
    selectAllLabel.className = "season-select-all";
    selectAllLabel.addEventListener("click", (e) => e.stopPropagation());

    const selectAllCb = document.createElement("input");
    selectAllCb.type = "checkbox";
    const allSelected = episodes.every((ep) => state.selectedEpisodeIds.includes(ep.id));
    const someSelected = episodes.some((ep) => state.selectedEpisodeIds.includes(ep.id));
    selectAllCb.checked = allSelected;
    selectAllCb.indeterminate = someSelected && !allSelected;

    selectAllCb.addEventListener("change", () => {
      if (selectAllCb.checked) {
        episodes.forEach((ep) => addEpisode(ep.id));
      } else {
        episodes.forEach((ep) => removeEpisode(ep.id));
      }
      rerenderModal(show);
      renderCardGrid();
      renderSelectedEpisodes();
    });

    selectAllLabel.append(selectAllCb, document.createTextNode("All"));
    summary.append(chevron, nameSpan, metaSpan, selectAllLabel);
    details.append(summary);

    // Episode rows
    const epList = document.createElement("div");
    epList.className = "episodes-list";

    for (const ep of episodes) {
      const row = document.createElement("div");
      row.className = "episode-row";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.selectedEpisodeIds.includes(ep.id);
      cb.addEventListener("change", () => {
        if (cb.checked) {
          addEpisode(ep.id);
        } else {
          removeEpisode(ep.id);
        }
        updateSeasonCheckbox(details, episodes);
        renderCardGrid();
        renderSelectedEpisodes();
      });

      const num = document.createElement("span");
      num.className = "ep-num";
      num.textContent = formatEpisodeNumber(ep);

      const title = document.createElement("span");
      title.className = "ep-title";
      title.textContent = ep.title;

      row.append(cb, num, title);

      if (ep.premiere_date) {
        const date = document.createElement("span");
        date.className = "ep-date";
        date.textContent = ep.premiere_date;
        row.append(date);
      }

      row.addEventListener("click", (e) => {
        if (e.target === cb) return;
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event("change"));
      });

      epList.append(row);
    }

    details.append(epList);
    el.modalBody.append(details);
  }

  el.modalBackdrop.classList.remove("hidden");
}

function updateSeasonCheckbox(details, episodes) {
  const cb = details.querySelector(".season-select-all input");
  if (!cb) return;
  const allSel = episodes.every((ep) => state.selectedEpisodeIds.includes(ep.id));
  const someSel = episodes.some((ep) => state.selectedEpisodeIds.includes(ep.id));
  cb.checked = allSel;
  cb.indeterminate = someSel && !allSel;
}

function rerenderModal(show) {
  // Re-open the modal with updated state, preserving open seasons
  const openSeasons = new Set(
    [...el.modalBody.querySelectorAll("details.season[open]")]
      .map((d) => d.querySelector("summary span:nth-child(2)").textContent)
  );
  el.modalBody.innerHTML = "";
  const seasons = groupBySeason(show.episodes);

  for (const [seasonKey, episodes] of seasons) {
    const seasonLabel = seasonKey === null
      ? "Unknown Season"
      : `Season ${String(seasonKey).padStart(2, "0")}`;

    const details = document.createElement("details");
    details.className = "season";
    if (openSeasons.has(seasonLabel) || openSeasons.size === 0) details.open = true;

    const summary = document.createElement("summary");
    const chevron = document.createElement("span");
    chevron.className = "season-chevron";
    chevron.textContent = "▼";

    const nameSpan = document.createElement("span");
    nameSpan.textContent = seasonLabel;

    const metaSpan = document.createElement("span");
    metaSpan.className = "season-meta";
    metaSpan.textContent = `${episodes.length} episodes`;

    const selectAllLabel = document.createElement("label");
    selectAllLabel.className = "season-select-all";
    selectAllLabel.addEventListener("click", (e) => e.stopPropagation());

    const selectAllCb = document.createElement("input");
    selectAllCb.type = "checkbox";
    const allSelected = episodes.every((ep) => state.selectedEpisodeIds.includes(ep.id));
    const someSelected = episodes.some((ep) => state.selectedEpisodeIds.includes(ep.id));
    selectAllCb.checked = allSelected;
    selectAllCb.indeterminate = someSelected && !allSelected;

    selectAllCb.addEventListener("change", () => {
      if (selectAllCb.checked) {
        episodes.forEach((ep) => addEpisode(ep.id));
      } else {
        episodes.forEach((ep) => removeEpisode(ep.id));
      }
      rerenderModal(show);
      renderCardGrid();
      renderSelectedEpisodes();
    });

    selectAllLabel.append(selectAllCb, document.createTextNode("All"));
    summary.append(chevron, nameSpan, metaSpan, selectAllLabel);
    details.append(summary);

    const epList = document.createElement("div");
    epList.className = "episodes-list";

    for (const ep of episodes) {
      const row = document.createElement("div");
      row.className = "episode-row";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.selectedEpisodeIds.includes(ep.id);
      cb.addEventListener("change", () => {
        if (cb.checked) addEpisode(ep.id);
        else removeEpisode(ep.id);
        updateSeasonCheckbox(details, episodes);
        renderCardGrid();
        renderSelectedEpisodes();
      });

      const num = document.createElement("span");
      num.className = "ep-num";
      num.textContent = formatEpisodeNumber(ep);

      const title = document.createElement("span");
      title.className = "ep-title";
      title.textContent = ep.title;

      row.append(cb, num, title);

      if (ep.premiere_date) {
        const date = document.createElement("span");
        date.className = "ep-date";
        date.textContent = ep.premiere_date;
        row.append(date);
      }

      row.addEventListener("click", (e) => {
        if (e.target === cb) return;
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event("change"));
      });

      epList.append(row);
    }

    details.append(epList);
    el.modalBody.append(details);
  }
}

function closeModal() {
  el.modalBackdrop.classList.add("hidden");
  el.modal.classList.remove("confirm-modal");
  el.modalBody.innerHTML = "";
}

el.modalClose.addEventListener("click", closeModal);
el.modalBackdrop.addEventListener("click", (e) => {
  if (e.target === el.modalBackdrop) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// ── Playlist form ─────────────────────────────────────────────────

function applyPlaylist(playlist) {
  state.currentId = playlist?.id || null;
  state.selectedShowPaths = new Set(playlist?.selected_show_paths || []);
  state.selectedEpisodeIds = [...(playlist?.selected_episode_ids || [])];
  el.title.value = playlist?.title || "";
  el.mode.value = playlist?.mode || "show_shuffle";
  el.seed.value = playlist?.seed ?? "";
  renderOutputFolderSelect(playlist?.output_folder || null);
  clearGenerateStatus();
  updateGenerateButton();
  renderPlaylists();
  renderCardGrid();
  renderSelectedEpisodes();
}

function updateGenerateButton() {
  el.generateButton.textContent = state.currentId ? "Regenerate" : "Generate";
}

function showGenerateStatus(success, message) {
  const status = document.getElementById("generateStatus");
  status.className = `generate-status ${success ? "success" : "error"}`;
  status.textContent = (success ? "✓  " : "✗  ") + message;
}

function clearGenerateStatus() {
  const status = document.getElementById("generateStatus");
  status.className = "generate-status hidden";
  status.textContent = "";
}

function formPayload() {
  const selectedShows = new Set(state.selectedShowPaths);
  const selectedIds = new Set(state.selectedEpisodeIds);
  for (const show of state.shows) {
    if (show.episodes.some((ep) => selectedIds.has(ep.id))) {
      selectedShows.add(show.path);
    }
  }

  return {
    id: state.currentId,
    title: el.title.value.trim(),
    mode: el.mode.value,
    selected_show_paths: [...selectedShows],
    selected_episode_ids: [...state.selectedEpisodeIds],
    seed: el.seed.value === "" ? null : Number(el.seed.value),
    output_folder: el.outputFolder.value || null,
  };
}

// ── API calls ─────────────────────────────────────────────────────

async function scanMedia() {
  const data = await api("/api/scan");
  state.shows = data.shows;
  renderCardGrid();
  renderSelectedEpisodes();
  log("Scan complete.", { shows: state.shows.length });
}

async function loadPlaylists() {
  const data = await api("/api/playlists");
  state.playlists = data.playlists;
  renderPlaylists();
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  renderOutputFolderSelect(el.outputFolder.value || null);
  renderSettingsPage();
}

// ── Event wiring ──────────────────────────────────────────────────

el.scanButton.addEventListener("click", () =>
  scanMedia().catch((e) => log(e.message))
);

el.playlistSelect.addEventListener("change", () => {
  const id = Number(el.playlistSelect.value);
  const playlist = state.playlists.find((p) => p.id === id);
  applyPlaylist(playlist);
});

el.clearButton.addEventListener("click", () => applyPlaylist(null));

el.mode.addEventListener("change", () => renderSelectedEpisodes());

el.generateButton.addEventListener("click", async () => {
  if (!el.title.value.trim()) {
    showGenerateStatus(false, "Please enter a playlist title.");
    el.title.focus();
    return;
  }
  try {
    const saved = await api("/api/playlists", {
      method: "POST",
      body: JSON.stringify(formPayload()),
    });
    state.currentId = saved.playlist.id;
    const data = await api(`/api/playlists/${state.currentId}/generate`, {
      method: "POST",
    });
    await loadPlaylists();
    updateGenerateButton();
    log("Playlist generated.", data);
    showGenerateStatus(true, "Playlist Generated");
  } catch (e) {
    log(e.message);
    showGenerateStatus(false, "Failed to generate — check the Activity tab");
  }
});

el.exportButton.addEventListener("click", async () => {
  try {
    const data = await api("/api/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "shuffly-playlists.json";
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (e) {
    log(e.message);
  }
});

el.importInput.addEventListener("change", async () => {
  const file = el.importInput.files[0];
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    await api("/api/import", { method: "POST", body: JSON.stringify(payload) });
    await loadPlaylists();
    applyPlaylist(null);
    log("Playlists imported.");
  } catch (e) {
    log(e.message);
  } finally {
    el.importInput.value = "";
  }
});

// ── Tab switching ─────────────────────────────────────────────────

const MODE_LABELS = {
  show_shuffle: "Shuffle in Order",
  selected_order: "Manually Order",
  mixed_timeline: "Sort by Release Date",
};

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  document.getElementById("createPage").classList.toggle("hidden", name !== "create");
  document.getElementById("managePage").classList.toggle("hidden", name !== "manage");
  document.getElementById("settingsPage").classList.toggle("hidden", name !== "settings");
  document.getElementById("activityPage").classList.toggle("hidden", name !== "activity");
  if (name === "manage") renderManagePage();
  if (name === "settings") renderSettingsPage();
}

document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => switchTab(t.dataset.tab))
);

// ── Playlists page ────────────────────────────────────────────────

function renderManagePage() {
  const container = document.getElementById("playlistCards");
  container.innerHTML = "";
  if (state.playlists.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No playlists yet. Create one on the Create tab.";
    container.append(empty);
    return;
  }
  state.playlists.forEach((pl) => container.append(makePlaylistCard(pl)));
}

function makePlaylistCard(pl) {
  const card = document.createElement("div");
  card.className = "pl-card";
  card.dataset.mode = pl.mode;

  // ── Poster thumbnail ──────────────────────────────────────────
  const thumb = document.createElement("div");
  thumb.className = "pl-card-thumb";
  if (pl.poster_url) {
    const img = document.createElement("img");
    img.src = pl.poster_url;
    img.alt = pl.title;
    img.addEventListener("error", () => {
      img.remove();
      thumb.append(_makeThumbPlaceholder(pl.title));
    });
    thumb.append(img);
  } else {
    thumb.append(_makeThumbPlaceholder(pl.title));
  }
  card.append(thumb);

  // ── Content wrapper (body + footer) ──────────────────────────
  const content = document.createElement("div");
  content.className = "pl-card-content";

  // ── Body ──────────────────────────────────────────────────────
  const body = document.createElement("div");
  body.className = "pl-card-body";

  const titleRow = document.createElement("div");
  titleRow.className = "pl-card-title-row";

  const titleEl = document.createElement("h3");
  titleEl.className = "pl-card-title";
  titleEl.textContent = pl.title;

  const modeBadge = document.createElement("span");
  modeBadge.className = "mode-badge";
  modeBadge.textContent = MODE_LABELS[pl.mode] || pl.mode;

  titleRow.append(titleEl, modeBadge);

  const stats = document.createElement("div");
  stats.className = "pl-card-stats";

  const epCount = document.createElement("span");
  epCount.textContent = `${pl.selected_episode_ids.length} episodes`;

  const sep = document.createElement("span");
  sep.className = "stat-sep";
  sep.textContent = "·";

  const genDate = document.createElement("span");
  genDate.textContent = pl.last_generated_at
    ? `Generated ${new Date(pl.last_generated_at + " UTC").toLocaleDateString()}`
    : "Never generated";

  stats.append(epCount, sep, genDate);
  body.append(titleRow, stats);

  // ── Footer ────────────────────────────────────────────────────
  const footer = document.createElement("div");
  footer.className = "pl-card-footer";

  const loadBtn = document.createElement("button");
  loadBtn.className = "btn-primary pl-load-btn";
  loadBtn.textContent = "Load";
  loadBtn.addEventListener("click", () => {
    applyPlaylist(pl);
    switchTab("create");
  });

  const secActions = document.createElement("div");
  secActions.className = "pl-card-actions";

  const renameBtn = document.createElement("button");
  renameBtn.className = "btn-ghost pl-action-btn";
  renameBtn.textContent = "Rename";
  renameBtn.addEventListener("click", () => startRename(card, titleEl, pl));

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "pl-delete-btn";
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", () => confirmDelete(card, footer, pl));

  secActions.append(renameBtn, deleteBtn);
  footer.append(loadBtn, secActions);
  content.append(body, footer);
  card.append(content);
  return card;
}

function _makeThumbPlaceholder(title) {
  const span = document.createElement("span");
  span.className = "pl-card-thumb-placeholder";
  span.textContent = title.trim()[0]?.toUpperCase() || "P";
  return span;
}

function startRename(card, titleEl, pl) {
  const input = document.createElement("input");
  input.className = "rename-input";
  input.value = pl.title;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  async function save() {
    const newTitle = input.value.trim();
    if (!newTitle || newTitle === pl.title) {
      input.replaceWith(titleEl);
      return;
    }
    try {
      await api("/api/playlists", {
        method: "POST",
        body: JSON.stringify({ ...pl, title: newTitle }),
      });
      await loadPlaylists();
      renderManagePage();
    } catch (e) {
      log(e.message);
      input.replaceWith(titleEl);
    }
  }

  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    if (e.key === "Escape") { e.preventDefault(); input.removeEventListener("blur", save); input.replaceWith(titleEl); }
  });
}

function confirmDelete(card, footer, pl) {
  footer.innerHTML = "";
  footer.classList.add("pl-card-footer--danger");

  const msg = document.createElement("span");
  msg.className = "delete-confirm-msg";
  msg.textContent = "Delete playlist and output folder?";

  const btnGroup = document.createElement("div");
  btnGroup.className = "pl-card-actions";

  const yesBtn = document.createElement("button");
  yesBtn.className = "btn-danger pl-action-btn";
  yesBtn.textContent = "Yes, delete";
  yesBtn.addEventListener("click", async () => {
    try {
      await api(`/api/playlists/${pl.id}`, { method: "DELETE" });
      await loadPlaylists();
      renderManagePage();
    } catch (e) {
      log(e.message);
    }
  });

  const noBtn = document.createElement("button");
  noBtn.className = "btn-ghost pl-action-btn";
  noBtn.textContent = "Cancel";
  noBtn.addEventListener("click", () => {
    const fresh = makePlaylistCard(pl);
    card.replaceWith(fresh);
  });

  btnGroup.append(yesBtn, noBtn);
  footer.append(msg, btnGroup);
}

// ── Settings page ─────────────────────────────────────────────────

function renderSettingsPage() {
  if (!state.settings) return;
  el.configFolder.textContent = state.settings.config_folder || "/config";
  renderFolderList(
    el.mediaFolderList,
    state.settings.media_folders.map((path) => ({ path })),
    "media",
  );
  renderFolderList(
    el.outputFolderList,
    state.settings.output_folders,
    "output",
  );
}

function renderFolderList(container, folders, kind) {
  container.innerHTML = "";
  if (folders.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state compact";
    empty.textContent = "No folders configured.";
    container.append(empty);
    return;
  }
  for (const folder of folders) {
    const row = document.createElement("div");
    row.className = "folder-row";

    const path = document.createElement("span");
    path.className = "folder-path";
    path.textContent = folder.path;
    row.append(path);

    if (folder.is_default) {
      const badge = document.createElement("span");
      badge.className = "default-badge";
      badge.textContent = "default";
      row.append(badge);
    }

    if (kind === "output" && !folder.is_default) {
      const makeDefaultBtn = document.createElement("button");
      makeDefaultBtn.type = "button";
      makeDefaultBtn.className = "folder-default-btn";
      makeDefaultBtn.textContent = "Set as default";
      makeDefaultBtn.addEventListener("click", () =>
        makeDefaultOutput(folder.path)
      );
      row.append(makeDefaultBtn);
    }

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "folder-remove-btn";
    remove.textContent = "✕";
    remove.setAttribute("aria-label", `Remove ${folder.path}`);
    remove.title = "Remove folder";
    remove.addEventListener("click", () =>
      confirmRemoveFolder(kind, folder.path, Boolean(folder.is_default))
    );
    row.append(remove);

    container.append(row);
  }
}

function confirmRemoveFolder(kind, path, isDefault) {
  const isBlocked = kind === "output" && isDefault;
  el.modal.classList.add("confirm-modal");
  el.modalTitle.textContent = `Remove ${kind} folder`;
  el.modalBody.innerHTML = "";

  const message = document.createElement("p");
  message.className = "confirm-message";
  message.textContent = isBlocked
    ? "You cannot delete the default output folder."
    : "Remove this folder from Shuffly settings?";

  const pathEl = document.createElement("div");
  pathEl.className = "readonly-path";
  pathEl.textContent = path;

  const actions = document.createElement("div");
  actions.className = "confirm-actions";

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn-secondary";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", closeModal);

  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.className = "btn-danger";
  confirm.textContent = "Remove";
  confirm.disabled = isBlocked;
  confirm.addEventListener("click", async () => {
    await removeFolder(kind, path);
    closeModal();
  });

  actions.append(cancel, confirm);
  el.modalBody.append(message, pathEl, actions);
  el.modalBackdrop.classList.remove("hidden");
}

async function addFolder(kind, path) {
  const endpoint = kind === "media"
    ? "/api/settings/media-folders"
    : "/api/settings/output-folders";
  try {
    state.settings = await api(endpoint, {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    renderSettingsPage();
    renderOutputFolderSelect(el.outputFolder.value || null);
    if (kind === "media") await scanMedia();
    clearBrowserError();
    closeBrowser();
  } catch (e) {
    showBrowserError(e.message);
    log(e.message);
  }
}

async function removeFolder(kind, path) {
  const endpoint = kind === "media"
    ? "/api/settings/media-folders"
    : "/api/settings/output-folders";
  try {
    state.settings = await api(endpoint, {
      method: "DELETE",
      body: JSON.stringify({ path }),
    });
    renderSettingsPage();
    renderOutputFolderSelect(el.outputFolder.value || null);
    if (kind === "media") await scanMedia();
  } catch (e) {
    log(e.message);
  }
}

async function makeDefaultOutput(path) {
  try {
    state.settings = await api("/api/settings/output-folders/default", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    renderSettingsPage();
    renderOutputFolderSelect(path);
  } catch (e) {
    log(e.message);
  }
}

async function openBrowser(kind) {
  state.browsePurpose = kind;
  state.browsePath = "/";
  el.browserTitle.textContent = kind === "media"
    ? "Choose media folder"
    : "Choose output folder";
  el.browserBackdrop.classList.remove("hidden");
  clearBrowserError();
  await renderBrowser("/");
}

async function renderBrowser(path) {
  try {
    const data = await api(`/api/browse?path=${encodeURIComponent(path)}`);
    state.browsePath = data.path;
    el.browserPath.textContent = data.path;
    el.browserList.innerHTML = "";
    if (data.parent) {
      el.browserList.append(browserRow("..", data.parent));
    }
    for (const directory of data.directories) {
      el.browserList.append(browserRow(directory.name, directory.path));
    }
    clearBrowserError();
  } catch (e) {
    showBrowserError(e.message);
    log(e.message);
  }
}

function browserRow(name, path) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "browser-row";
  row.textContent = name;
  row.addEventListener("click", () => renderBrowser(path));
  return row;
}

function closeBrowser() {
  el.browserBackdrop.classList.add("hidden");
  el.browserList.innerHTML = "";
  clearBrowserError();
}

function showBrowserError(message) {
  el.browserError.textContent = message;
  el.browserError.classList.remove("hidden");
}

function clearBrowserError() {
  el.browserError.textContent = "";
  el.browserError.classList.add("hidden");
}

el.addMediaFolder.addEventListener("click", () => openBrowser("media"));
el.addOutputFolder.addEventListener("click", () => openBrowser("output"));
el.browserClose.addEventListener("click", closeBrowser);
el.browserBackdrop.addEventListener("click", (e) => {
  if (e.target === el.browserBackdrop) closeBrowser();
});
el.browserUse.addEventListener("click", async () => {
  if (!state.browsePurpose) return;
  await addFolder(state.browsePurpose, state.browsePath);
});

// ── Init ──────────────────────────────────────────────────────────

Promise.all([loadSettings(), scanMedia(), loadPlaylists()]).catch((e) =>
  log(e.message)
);
