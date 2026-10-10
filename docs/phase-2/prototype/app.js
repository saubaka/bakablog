(() => {
  const views = [...document.querySelectorAll('[data-view]')];
  const switchButtons = [...document.querySelectorAll('[data-view-target]')];
  const toast = document.querySelector('.toast');
  const motionToggle = document.querySelector('.motion-toggle');
  let toastTimer;

  function setView(name, pushHash = true) {
    const next = views.find((view) => view.dataset.view === name);
    if (!next) return;

    views.forEach((view) => {
      const active = view === next;
      view.classList.toggle('is-active', active);
      view.hidden = !active;
    });

    switchButtons.forEach((button) => {
      const active = button.dataset.viewTarget === name;
      button.classList.toggle('is-active', active);
      button.classList.toggle('is-current', active);
      if (button.closest('.prototype-switcher')) button.setAttribute('aria-pressed', String(active));
    });

    document.body.classList.toggle('showing-admin', name === 'admin');
    if (pushHash) history.replaceState(null, '', `#${name}`);
    window.scrollTo({ top: 0, behavior: document.body.classList.contains('reduce-motion') ? 'auto' : 'smooth' });
  }

  function showToast(message) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add('is-visible'));
    toastTimer = window.setTimeout(() => {
      toast.classList.remove('is-visible');
      window.setTimeout(() => { toast.hidden = true; }, 180);
    }, 2800);
  }

  switchButtons.forEach((button) => button.addEventListener('click', () => setView(button.dataset.viewTarget)));
  document.querySelectorAll('[data-jump-view]').forEach((element) => element.addEventListener('click', (event) => {
    event.preventDefault();
    setView(element.dataset.jumpView);
  }));

  document.querySelectorAll('[data-demo-link], [data-demo-button]').forEach((element) => element.addEventListener('click', (event) => {
    event.preventDefault();
    showToast('这是视觉原型，业务功能将在后续阶段实现。');
  }));

  document.querySelectorAll('[data-demo-form]').forEach((form) => form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    showToast('申请表状态已验证；真实提交功能将在阶段七实现。');
  }));

  document.querySelector('[data-scroll-application]')?.addEventListener('click', () => {
    document.querySelector('#friend-application')?.scrollIntoView({ behavior: document.body.classList.contains('reduce-motion') ? 'auto' : 'smooth' });
  });

  motionToggle.addEventListener('click', () => {
    const active = document.body.classList.toggle('reduce-motion');
    motionToggle.setAttribute('aria-pressed', String(active));
    showToast(active ? '已在原型中减少动态效果。' : '已恢复完整原型动效。');
  });

  const initialView = location.hash.slice(1);
  setView(views.some((view) => view.dataset.view === initialView) ? initialView : 'home', false);
})();
