(() => {
  const root = document.querySelector("[data-global-search]");
  if (!root) return;

  const form = root.querySelector("[data-global-search-form]");
  const input = root.querySelector("[data-global-search-input]");
  const panel = root.querySelector("[data-search-panel]");
  const heading = root.querySelector("[data-search-heading]");
  const state = root.querySelector("[data-search-state]");
  const results = root.querySelector("[data-search-results]");
  const pagination = root.querySelector("[data-search-pagination]");
  const endpoint = root.dataset.searchEndpoint;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let debounceTimer = 0;
  let requestController = null;
  let panelTimer = 0;

  const selectedMode = () =>
    form.querySelector("[data-search-mode]:checked")?.value || "strict";

  const resultCard = (item, index) => {
    const link = document.createElement("a");
    link.className = `search-result-card search-result-card--${item.source}`;
    link.href = item.url;
    link.style.setProperty("--search-order", index);
    const source = document.createElement("span");
    source.className = "search-result-card__source";
    source.textContent = item.source_label;
    const copy = document.createElement("span");
    copy.className = "search-result-card__copy";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const excerpt = document.createElement("small");
    excerpt.textContent = item.excerpt;
    copy.append(title, excerpt);
    link.append(source, copy);
    if (item.date) {
      const time = document.createElement("time");
      time.textContent = item.date;
      link.append(time);
    }
    const arrow = document.createElement("span");
    arrow.className = "search-result-card__arrow";
    arrow.ariaHidden = "true";
    arrow.textContent = "→";
    link.append(arrow);
    return link;
  };

  const emptyState = () => {
    const empty = document.createElement("div");
    empty.className = "search-empty-state";
    const sparkle = document.createElement("span");
    sparkle.ariaHidden = "true";
    sparkle.textContent = "✦";
    const label = document.createElement("strong");
    label.textContent = "暂时没有找到相同的星光";
    empty.append(sparkle, label);
    return empty;
  };

  const animatePanel = (update) => {
    window.clearTimeout(panelTimer);
    const oldHeight = panel.hidden ? 0 : panel.getBoundingClientRect().height;
    panel.hidden = false;
    panel.classList.add("is-visible", "is-resizing");
    panel.style.height = `${oldHeight}px`;
    update();
    const targetHeight = panel.scrollHeight;
    if (reduceMotion.matches) {
      panel.style.height = "auto";
      panel.classList.remove("is-resizing");
      return;
    }
    requestAnimationFrame(() => {
      panel.style.height = `${targetHeight}px`;
    });
    panelTimer = window.setTimeout(() => {
      panel.style.height = "auto";
      panel.classList.remove("is-resizing");
    }, 520);
  };

  const collapsePanel = () => {
    if (panel.hidden) return;
    window.clearTimeout(panelTimer);
    if (reduceMotion.matches) {
      panel.hidden = true;
      panel.classList.remove("is-visible", "is-resizing");
      panel.style.height = "";
      return;
    }
    panel.style.height = `${panel.getBoundingClientRect().height}px`;
    panel.classList.add("is-resizing");
    requestAnimationFrame(() => {
      panel.classList.remove("is-visible");
      panel.style.height = "0px";
    });
    panelTimer = window.setTimeout(() => {
      panel.hidden = true;
      panel.classList.remove("is-resizing");
      panel.style.height = "";
    }, 440);
  };

  const renderPagination = (payload) => {
    pagination.replaceChildren();
    if (payload.pages <= 1) {
      pagination.hidden = true;
      return;
    }
    const fragment = document.createDocumentFragment();
    for (let number = 1; number <= payload.pages; number += 1) {
      const link = document.createElement("a");
      link.href = `?q=${encodeURIComponent(payload.query)}&mode=${payload.mode}&page=${number}`;
      link.dataset.searchPage = number;
      link.ariaLabel = `第 ${number} 页`;
      link.textContent = number;
      if (number === payload.page) {
        link.className = "is-current";
        link.ariaCurrent = "page";
      }
      fragment.append(link);
    }
    pagination.append(fragment);
    pagination.hidden = false;
  };

  const renderPayload = (payload) => {
    animatePanel(() => {
      heading.textContent = payload.total ? `找到 ${payload.total} 条结果` : "没有找到结果";
      state.textContent = "已检索五类公开内容";
      results.replaceChildren();
      const fragment = document.createDocumentFragment();
      if (payload.items.length) {
        payload.items.forEach((item, index) => fragment.append(resultCard(item, index)));
      } else {
        fragment.append(emptyState());
      }
      results.append(fragment);
      renderPagination(payload);
    });
  };

  const updateLocation = (query, mode, page) => {
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("q", query);
    url.searchParams.set("mode", mode);
    if (page > 1) url.searchParams.set("page", page);
    window.history.replaceState({ search: true }, "", url);
  };

  const runSearch = async (page = 1) => {
    const query = input.value.trim();
    const mode = selectedMode();
    if (!query) {
      requestController?.abort();
      state.textContent = "";
      collapsePanel();
      const url = new URL(window.location.href);
      url.search = "";
      window.history.replaceState({ search: true }, "", url);
      return;
    }
    requestController?.abort();
    const activeController = new AbortController();
    requestController = activeController;
    panel.hidden = false;
    panel.classList.add("is-visible", "is-loading");
    panel.ariaBusy = "true";
    state.textContent = "正在检索…";
    const params = new URLSearchParams({ q: query, mode, page: String(page) });
    try {
      const response = await fetch(`${endpoint}?${params}`, {
        headers: { Accept: "application/json" },
        signal: activeController.signal,
      });
      if (!response.ok) throw new Error(`search request failed: ${response.status}`);
      const payload = await response.json();
      renderPayload(payload);
      updateLocation(payload.query, payload.mode, payload.page);
    } catch (error) {
      if (error.name === "AbortError") return;
      animatePanel(() => {
        heading.textContent = "暂时无法完成检索";
        state.textContent = "请稍后重试";
        results.replaceChildren(emptyState());
        pagination.hidden = true;
      });
    } finally {
      if (requestController === activeController) {
        requestController = null;
        panel.classList.remove("is-loading");
        panel.ariaBusy = "false";
      }
    }
  };

  const scheduleSearch = (delay = 950) => {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => runSearch(1), delay);
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.clearTimeout(debounceTimer);
    runSearch(1);
  });
  input.addEventListener("input", () => scheduleSearch());
  form.querySelectorAll("[data-search-mode]").forEach((control) => {
    control.addEventListener("change", () => scheduleSearch(260));
  });
  pagination.addEventListener("click", (event) => {
    const link = event.target.closest("[data-search-page]");
    if (!link) return;
    event.preventDefault();
    runSearch(Number(link.dataset.searchPage));
  });
})();
