(() => {
  "use strict";

  const makeId = () => (crypto.randomUUID ? crypto.randomUUID() : `item-${Date.now()}-${Math.random().toString(16).slice(2)}`);

  function sortable(container, selector, onChange) {
    if (!container) return;
    let dragged = null;
    container.addEventListener("dragstart", (event) => {
      dragged = event.target.closest(selector);
      if (!dragged) return;
      dragged.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
    });
    container.addEventListener("dragover", (event) => {
      if (!dragged) return;
      event.preventDefault();
      const target = event.target.closest(selector);
      if (!target || target === dragged || target.parentElement !== dragged.parentElement) return;
      const rect = target.getBoundingClientRect();
      target.parentElement.insertBefore(dragged, event.clientY < rect.top + rect.height / 2 ? target : target.nextSibling);
    });
    container.addEventListener("dragend", () => {
      if (!dragged) return;
      dragged.classList.remove("is-dragging");
      dragged = null;
      onChange?.();
    });
  }

  const blockList = document.querySelector("[data-page-block-list]");
  if (blockList) {
    const renumber = () => blockList.querySelectorAll("[data-page-block] strong").forEach((node, index) => { node.textContent = `板块 ${index + 1}`; });
    sortable(blockList, "[data-page-block]", renumber);
    document.addEventListener("click", (event) => {
      if (event.target.closest("[data-add-page-block]")) {
        const template = document.querySelector("template[data-page-block-template]");
        const item = template.content.firstElementChild.cloneNode(true);
        const id = makeId();
        item.querySelector("[name=block_id]").value = id;
        item.querySelector("[name=block_enabled]").value = id;
        blockList.append(item);
        renumber();
        item.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      const remove = event.target.closest("[data-remove-page-block]");
      if (remove) {
        const item = remove.closest("[data-page-block]");
        item.classList.add("is-removing");
        setTimeout(() => { item.remove(); renumber(); }, 220);
      }
    });
  }

  const menuList = document.querySelector("[data-sortable-menu]");
  if (menuList) {
    sortable(menuList, "[data-menu-item-id]");
    document.querySelector("[data-menu-order-form]")?.addEventListener("submit", () => {
      document.querySelector("[data-menu-order-value]").value = JSON.stringify(
        [...menuList.querySelectorAll("[data-menu-item-id]")].map((item) => item.dataset.menuItemId),
      );
    });
  }

  const footerEditor = document.querySelector("[data-footer-editor]");
  if (footerEditor) {
    const list = footerEditor.querySelector("[data-footer-column-list]");
    document.addEventListener("click", (event) => {
      const addColumn = event.target.closest("[data-add-footer-column]");
      if (addColumn) list.append(document.querySelector("template[data-footer-column-template]").content.cloneNode(true));
      const addLink = event.target.closest("[data-add-footer-link]");
      if (addLink) addLink.closest("[data-footer-column]").querySelector("[data-footer-link-list]").append(document.querySelector("template[data-footer-link-template]").content.cloneNode(true));
      const removeColumn = event.target.closest("[data-remove-footer-column]");
      if (removeColumn) removeColumn.closest("[data-footer-column]").remove();
      const removeLink = event.target.closest("[data-remove-footer-link]");
      if (removeLink) removeLink.closest("[data-footer-link]").remove();
    });
    footerEditor.addEventListener("submit", () => {
      const columns = [...list.querySelectorAll("[data-footer-column]")].map((column) => ({
        id: makeId(),
        title: column.querySelector("[data-footer-column-title]").value.trim(),
        links: [...column.querySelectorAll("[data-footer-link]")].map((link) => ({
          label: link.querySelector("[data-footer-link-label]").value.trim(),
          url: link.querySelector("[data-footer-link-url]").value.trim(),
        })).filter((link) => link.label && link.url),
      })).filter((column) => column.title);
      footerEditor.querySelector("[data-footer-columns-value]").value = JSON.stringify(columns);
    });
  }

  const layoutEditor = document.querySelector("[data-admin-layout-editor]");
  if (layoutEditor) {
    const parents = layoutEditor.querySelector("[data-admin-layout-parents]");
    sortable(parents, "[data-layout-parent]");
    parents.querySelectorAll("[data-layout-children]").forEach((list) => sortable(list, "[data-layout-child]"));
    layoutEditor.addEventListener("submit", () => {
      const payload = { parents: [], children: {} };
      parents.querySelectorAll(":scope > [data-layout-parent]").forEach((parent) => {
        const key = parent.dataset.layoutParent;
        payload.parents.push(key);
        payload.children[key] = [...parent.querySelectorAll(":scope [data-layout-child]")].map((child) => child.dataset.layoutChild);
      });
      layoutEditor.querySelector("[data-admin-layout-value]").value = JSON.stringify(payload);
    });
  }

  const navigation = document.querySelector("[data-admin-navigation]");
  const navigationLayout = document.querySelector("[data-admin-navigation-layout]");
  if (navigation && navigationLayout) {
    try {
      const layout = JSON.parse(navigationLayout.textContent);
      (layout.parents || []).forEach((key) => {
        const parent = navigation.querySelector(`[data-menu-key="${CSS.escape(key)}"]`);
        if (parent) navigation.append(parent);
      });
      Object.entries(layout.children || {}).forEach(([parentKey, children]) => {
        const parent = navigation.querySelector(`[data-menu-key="${CSS.escape(parentKey)}"]`);
        const container = parent?.querySelector(".admin-nav-group__items > div");
        if (!container) return;
        children.forEach((key) => {
          const child = container.querySelector(`[data-submenu-key="${CSS.escape(key)}"], [data-admin-child-key="${CSS.escape(key)}"]`);
          if (child) container.append(child);
        });
      });
    } catch (_error) {
      // Invalid persisted layout falls back to the deterministic template order.
    }
  }
})();
