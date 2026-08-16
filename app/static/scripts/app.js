(() => {
  const doc = document;
  const root = doc.documentElement;
  const mobileDrawer = doc.querySelector('#mobile-drawer');
  const mobileBackdrop = doc.querySelector('[data-mobile-backdrop]');
  const adminSidebar = doc.querySelector('#admin-sidebar');
  const adminBackdrop = doc.querySelector('[data-admin-backdrop]');
  let lastTrigger = null;
  let toastSequence = 0;
  let mobileDrawerState = 'closed';
  let mobileDrawerCloseTimer = 0;
  const systemReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function motionIsReduced() {
    return root.dataset.motion === 'reduce' || (root.dataset.motion === 'system' && systemReducedMotion.matches);
  }

  if ((navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) || (navigator.deviceMemory && navigator.deviceMemory <= 4)) {
    root.dataset.performance = 'low';
  }

  function setMotionPreference(value) {
    root.dataset.motion = value;
    try { localStorage.setItem('cloud-diary-motion', value); } catch (_) { /* storage is optional */ }
    updateMotionControls();
  }

  function updateMotionControls() {
    doc.querySelectorAll('[data-motion-toggle]').forEach((button) => {
      const reduced = motionIsReduced();
      button.setAttribute('aria-pressed', String(root.dataset.motion === 'reduce'));
      button.textContent = reduced ? '动效：精简' : '动效：跟随系统';
    });
  }

  try {
    const storedMotion = localStorage.getItem('cloud-diary-motion');
    if (storedMotion === 'reduce') setMotionPreference('reduce');
    else if (storedMotion === 'full') setMotionPreference('system');
  } catch (_) { /* storage is optional */ }

  function focusableWithin(container) {
    return [...container.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])')];
  }

  function trapFocus(event, container) {
    if (event.key !== 'Tab') return;
    const items = focusableWithin(container).filter((item) => item.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && doc.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }

  function setSiteInert(value) {
    doc.querySelectorAll('.site-header, .site-main, .site-footer, .mobile-bottom-nav').forEach((item) => {
      item.inert = value;
    });
  }

  function openMobileDrawer(trigger) {
    if (!mobileDrawer || !mobileBackdrop || mobileDrawerState === 'open') return;
    window.clearTimeout(mobileDrawerCloseTimer);
    mobileDrawerState = 'opening';
    lastTrigger = trigger;
    mobileDrawer.setAttribute('aria-hidden', 'false');
    mobileBackdrop.hidden = false;
    doc.body.classList.add('drawer-open');
    doc.querySelectorAll('[data-mobile-drawer]').forEach((item) => item.setAttribute('aria-expanded', 'true'));
    setSiteInert(true);
    requestAnimationFrame(() => {
      mobileDrawer.classList.add('is-open');
      mobileBackdrop.classList.add('is-visible');
      mobileDrawerState = 'open';
      focusableWithin(mobileDrawer)[0]?.focus();
    });
  }

  function closeMobileDrawer() {
    if (!mobileDrawer || mobileDrawerState === 'closed') return;
    mobileDrawerState = 'closing';
    mobileDrawer.setAttribute('aria-hidden', 'true');
    mobileDrawer.classList.remove('is-open');
    mobileBackdrop?.classList.remove('is-visible');
    doc.body.classList.remove('drawer-open');
    doc.querySelectorAll('[data-mobile-drawer]').forEach((item) => item.setAttribute('aria-expanded', 'false'));
    setSiteInert(false);
    mobileDrawerCloseTimer = window.setTimeout(() => {
      if (mobileBackdrop) mobileBackdrop.hidden = true;
      mobileDrawerState = 'closed';
      lastTrigger?.focus();
    }, motionIsReduced() ? 0 : 360);
  }

  function openAdminDrawer(trigger) {
    if (!adminSidebar) return;
    lastTrigger = trigger;
    adminSidebar.classList.add('is-open');
    adminBackdrop.hidden = false;
    requestAnimationFrame(() => adminBackdrop.classList.add('is-visible'));
    trigger.setAttribute('aria-expanded', 'true');
    doc.body.classList.add('drawer-open');
    adminSidebar.querySelector('a')?.focus();
  }

  function closeAdminDrawer() {
    if (!adminSidebar) return;
    adminSidebar.classList.remove('is-open');
    adminBackdrop?.classList.remove('is-visible');
    doc.body.classList.remove('drawer-open');
    doc.querySelector('[data-admin-drawer]')?.setAttribute('aria-expanded', 'false');
    window.setTimeout(() => { if (adminBackdrop) adminBackdrop.hidden = true; }, 180);
    lastTrigger?.focus();
  }

  function showToast(message, tone = 'info') {
    const region = doc.querySelector('.toast-region');
    if (!region) return;
    toastSequence += 1;
    const toast = doc.createElement('div');
    toast.className = `toast toast--${tone}`;
    toast.dataset.toast = String(toastSequence);
    toast.innerHTML = '<span class="toast__dot" aria-hidden="true"></span><span></span><button class="icon-button icon-button--small" type="button" aria-label="关闭通知">×</button>';
    toast.querySelector('span:nth-child(2)').textContent = message;
    toast.querySelector('button').addEventListener('click', () => dismissToast(toast));
    region.append(toast);
    toast.getBoundingClientRect();
    toast.classList.add('is-visible');
    window.setTimeout(() => dismissToast(toast), 4500);
  }

  function dismissToast(toast) {
    if (!toast?.isConnected) return;
    toast.classList.remove('is-visible');
    window.setTimeout(() => toast.remove(), 180);
  }

  const appSystemDialog = doc.querySelector('[data-app-system-dialog]');
  let pendingSystemDialog = null;
  const settleSystemDialog = (value) => {
    if (!pendingSystemDialog) return;
    const resolve = pendingSystemDialog.resolve;
    const trigger = pendingSystemDialog.trigger;
    pendingSystemDialog = null;
    closeDialog(appSystemDialog);
    resolve(value);
    if (value === false || value === null) window.setTimeout(() => trigger?.focus(), 0);
  };
  const requestSystemDialog = ({ mode = 'confirm', title, message, value = '', inputLabel = '请输入内容' }) => {
    if (!appSystemDialog) return Promise.resolve(mode === 'prompt' ? null : false);
    if (pendingSystemDialog) settleSystemDialog(pendingSystemDialog.cancelValue);
    const trigger = doc.activeElement;
    const inputField = appSystemDialog.querySelector('[data-app-dialog-field]');
    const input = appSystemDialog.querySelector('[data-app-dialog-input]');
    const cancelButtons = appSystemDialog.querySelectorAll('[data-app-dialog-cancel]');
    const confirmButton = appSystemDialog.querySelector('[data-app-dialog-confirm]');
    const isPrompt = mode === 'prompt';
    const isAlert = mode === 'alert';
    appSystemDialog.dataset.dialogMode = mode;
    appSystemDialog.querySelector('[data-app-dialog-title]').textContent = title || (isPrompt ? '输入内容' : isAlert ? '提示' : '确认操作');
    appSystemDialog.querySelector('[data-app-dialog-message]').textContent = message || '';
    appSystemDialog.querySelector('[data-app-dialog-input-label]').textContent = inputLabel;
    inputField.hidden = !isPrompt;
    input.value = isPrompt ? value : '';
    cancelButtons.forEach((button) => { button.hidden = isAlert && !button.classList.contains('icon-button'); });
    confirmButton.textContent = isAlert ? '知道了' : '确认';
    openDialog(appSystemDialog);
    window.setTimeout(() => (isPrompt ? input : confirmButton).focus(), 0);
    return new Promise((resolve) => {
      pendingSystemDialog = {
        resolve,
        mode,
        cancelValue: isPrompt ? null : false,
        trigger
      };
    });
  };
  const themedConfirm = (message, title = '确认操作') => requestSystemDialog({ mode: 'confirm', title, message });
  const themedPrompt = (message, value = '', title = '输入内容') => requestSystemDialog({ mode: 'prompt', title, message, value });
  const themedAlert = (message, title = '提示') => requestSystemDialog({ mode: 'alert', title, message });
  appSystemDialog?.querySelectorAll('[data-app-dialog-cancel]').forEach((button) => button.addEventListener('click', () => {
    settleSystemDialog(pendingSystemDialog?.cancelValue ?? false);
  }));
  appSystemDialog?.querySelector('[data-app-dialog-confirm]')?.addEventListener('click', () => {
    const value = pendingSystemDialog?.mode === 'prompt'
      ? appSystemDialog.querySelector('[data-app-dialog-input]').value.trim()
      : true;
    settleSystemDialog(value);
  });
  appSystemDialog?.querySelector('[data-app-dialog-input]')?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    settleSystemDialog(event.currentTarget.value.trim());
  });
  appSystemDialog?.addEventListener('cancel', (event) => {
    event.preventDefault();
    settleSystemDialog(pendingSystemDialog?.cancelValue ?? false);
  });
  appSystemDialog?.addEventListener('close', () => {
    if (pendingSystemDialog) settleSystemDialog(pendingSystemDialog.cancelValue);
  });

  doc.querySelectorAll('[data-toast]').forEach((toast) => {
    toast.getBoundingClientRect();
    toast.classList.add('is-visible');
    window.setTimeout(() => dismissToast(toast), 5000);
  });

  doc.addEventListener('click', (event) => {
    const target = event.target.closest('button, a');
    if (!target) return;
    if (target.matches('[data-mobile-drawer]')) openMobileDrawer(target);
    if (target.matches('[data-close-mobile-drawer]')) closeMobileDrawer();
    if (target.matches('[data-admin-drawer]')) openAdminDrawer(target);
    if (target.matches('[data-motion-toggle]')) {
      setMotionPreference(motionIsReduced() ? 'system' : 'reduce');
    }
    if (target.matches('[data-dismiss-toast]')) dismissToast(target.closest('.toast'));
    if (target.matches('[data-open-dialog]')) {
      const dialog = doc.getElementById(target.dataset.openDialog);
      if (dialog) { lastTrigger = target; openDialog(dialog); }
    }
    if (target.matches('[data-close-dialog]')) {
      closeDialog(target.closest('dialog'));
      lastTrigger?.focus();
    }
  });

  mobileBackdrop?.addEventListener('click', closeMobileDrawer);
  adminBackdrop?.addEventListener('click', closeAdminDrawer);

  doc.querySelectorAll('[data-demo-toast]').forEach((button) => button.addEventListener('click', () => {
    showToast(button.dataset.demoToast, button.dataset.demoTone || 'info');
  }));

  doc.querySelectorAll('[data-demo-form]').forEach((form) => form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    showToast('表单验证通过', 'success');
  }));

  doc.querySelectorAll('[data-component-motion]').forEach((button) => button.addEventListener('click', () => {
    const stage = doc.querySelector('[data-component-motion-stage]');
    if (!stage) return;
    stage.dataset.previewMotion = button.dataset.componentMotion || 'none';
    stage.classList.remove('is-playing');
    void stage.offsetWidth;
    stage.classList.add('is-playing');
    button.closest('[data-component-motion-options]')?.querySelectorAll('[data-component-motion]').forEach((item) => {
      item.classList.toggle('is-active', item === button);
      item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
    });
  }));

  doc.querySelectorAll('[data-component-segment]').forEach((button) => button.addEventListener('click', () => {
    button.parentElement?.querySelectorAll('[data-component-segment]').forEach((item) => {
      item.classList.toggle('is-active', item === button);
      item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
    });
    const labels = { all: '全部', published: '已发布', draft: '草稿' };
    const copy = button.closest('.component-preview-panel')?.querySelector('[data-component-segment-copy]');
    if (copy) copy.textContent = `当前显示：${labels[button.dataset.componentSegment] || '全部'}`;
  }));

  doc.querySelectorAll('[data-component-font]').forEach((card) => {
    const activate = () => {
      root.dataset.fontStyle = card.dataset.componentFont;
      doc.querySelectorAll('[data-component-font]').forEach((item) => {
        const active = item === card;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      showToast(`已在当前预览切换为${card.querySelector('.font-choice__name')?.textContent || '所选字体'}`, 'info');
    };
    card.addEventListener('click', activate);
    card.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      activate();
    });
  });

  doc.querySelectorAll('[data-component-action]').forEach((button) => button.addEventListener('click', () => {
    showToast(`${button.dataset.componentAction}已触发`, button.classList.contains('button--danger') ? 'warning' : 'success');
  }));
  doc.querySelectorAll('[data-component-icon]').forEach((button) => button.addEventListener('click', () => {
    showToast(`${button.dataset.componentIcon}图标按钮已触发`, 'info');
  }));
  doc.querySelectorAll('[data-component-loading]').forEach((button) => button.addEventListener('click', () => {
    if (button.getAttribute('aria-busy') === 'true') return;
    button.setAttribute('aria-busy', 'true');
    button.querySelector('span').textContent = '处理中';
    window.setTimeout(() => {
      button.setAttribute('aria-busy', 'false');
      button.querySelector('span').textContent = '体验加载';
      showToast('加载状态演示完成', 'success');
    }, motionIsReduced() ? 300 : 1200);
  }));

  doc.querySelectorAll('[data-component-capsule]').forEach((nav) => nav.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    nav.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
  }));
  doc.querySelectorAll('[data-component-admin-parent]').forEach((button) => button.addEventListener('click', () => {
    const parent = button.parentElement;
    parent?.querySelectorAll('[data-component-admin-parent]').forEach((item) => {
      const active = item === button && !item.classList.contains('is-open');
      item.classList.toggle('is-open', active);
      const indicator = item.querySelector(':scope > span:first-child > i');
      if (indicator) indicator.textContent = active ? '⌃' : '⌄';
    });
  }));

  doc.querySelectorAll('[data-component-accent]').forEach((input) => input.addEventListener('input', () => {
    input.closest('.component-showcase')?.style.setProperty('--component-accent', input.value);
    showToast(`预览强调色：${input.value.toUpperCase()}`, 'info');
  }));

  doc.querySelectorAll('[data-component-media-select]').forEach((button) => {
    const card = button.closest('.component-image-preview');
    const input = card?.querySelector('[data-component-media-input]');
    button.addEventListener('click', () => input?.click());
    input?.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file) return;
      const stage = card.querySelector('[data-component-media-stage]');
      const previousUrl = stage.dataset.previewUrl;
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      const previewUrl = URL.createObjectURL(file);
      stage.dataset.previewUrl = previewUrl;
      stage.style.backgroundImage = `url("${previewUrl}")`;
      stage.classList.add('has-image');
      card.querySelector('[data-component-media-name]').textContent = file.name;
    });
  });
  doc.querySelectorAll('[data-component-size-options]').forEach((group) => group.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    group.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
  }));
  doc.querySelectorAll('[data-component-crop-scale]').forEach((input) => input.addEventListener('input', () => {
    const canvas = input.closest('.component-crop-preview')?.querySelector('[data-component-crop-canvas]');
    canvas?.style.setProperty('--crop-scale', String(1 + Number(input.value) / 180));
  }));
  doc.querySelectorAll('[data-component-ratios]').forEach((group) => group.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    group.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
    const canvas = group.closest('.component-crop-preview')?.querySelector('[data-component-crop-canvas]');
    if (canvas) canvas.style.aspectRatio = button.dataset.ratio;
  }));

  const componentEditor = doc.querySelector('[data-component-editor-content]');
  const updateComponentEditorCount = () => {
    const count = componentEditor?.innerText.replace(/\s/g, '').length || 0;
    const counter = doc.querySelector('[data-component-editor-count]');
    if (counter) counter.textContent = `${count} 字 · 预计阅读 ${Math.max(1, Math.ceil(count / 400))} 分钟`;
  };
  componentEditor?.addEventListener('input', updateComponentEditorCount);
  updateComponentEditorCount();
  doc.querySelectorAll('[data-component-command]').forEach((button) => button.addEventListener('click', () => {
    componentEditor?.focus();
    document.execCommand(button.dataset.componentCommand, false, button.dataset.commandValue || null);
    updateComponentEditorCount();
  }));
  doc.querySelectorAll('[data-component-editor-modes]').forEach((group) => group.addEventListener('click', (event) => {
    const button = event.target.closest('[data-editor-mode]');
    if (!button || !componentEditor) return;
    group.querySelectorAll('[data-editor-mode]').forEach((item) => item.classList.toggle('is-active', item === button));
    const sourceMode = button.dataset.editorMode === 'source';
    componentEditor.classList.toggle('is-source-mode', sourceMode);
    componentEditor.contentEditable = String(!sourceMode);
    const status = doc.querySelector('[data-component-editor-status]');
    if (status) status.textContent = sourceMode ? '源码模式仅用于结构预览' : '可直接编辑预览内容';
  }));

  doc.querySelectorAll('[data-identity-menu]').forEach((menu) => {
    const trigger = menu.querySelector('[data-identity-menu-trigger]');
    const panel = menu.querySelector('[data-identity-menu-panel]');
    const setOpen = (open) => {
      menu.classList.toggle('is-open', open);
      trigger?.setAttribute('aria-expanded', String(open));
    };
    trigger?.addEventListener('click', (event) => {
      event.stopPropagation();
      setOpen(!menu.classList.contains('is-open'));
    });
    menu.addEventListener('mouseenter', () => setOpen(true));
    doc.addEventListener('pointermove', (event) => {
      if (!menu.classList.contains('is-open') || menu.matches(':focus-within')) return;
      const triggerRect = trigger?.getBoundingClientRect();
      const panelRect = panel?.getBoundingClientRect();
      if (!triggerRect || !panelRect) return;
      const insideTrigger = event.clientX >= triggerRect.left
        && event.clientX <= triggerRect.right
        && event.clientY >= triggerRect.top
        && event.clientY <= triggerRect.bottom;
      const insidePanel = event.clientX >= panelRect.left
        && event.clientX <= panelRect.right
        && event.clientY >= panelRect.top
        && event.clientY <= panelRect.bottom;
      const insideDownwardBridge = event.clientX >= triggerRect.left - 5
        && event.clientX <= triggerRect.right + 5
        && event.clientY > triggerRect.bottom
        && event.clientY < panelRect.top;
      if (!insideTrigger && !insidePanel && !insideDownwardBridge) setOpen(false);
    });
    menu.addEventListener('focusout', () => window.setTimeout(() => {
      if (!menu.matches(':focus-within')) setOpen(false);
    }, 0));
    doc.addEventListener('click', (event) => {
      if (!menu.contains(event.target)) setOpen(false);
    });
  });

  doc.querySelectorAll('form[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
    if (form.dataset.confirmApproved === 'true') return;
    event.preventDefault();
    const submitter = event.submitter;
    themedConfirm(form.dataset.confirm).then((confirmed) => {
      if (!confirmed) return;
      form.dataset.confirmApproved = 'true';
      if (submitter?.isConnected) form.requestSubmit(submitter);
      else form.requestSubmit();
    });
  }));

  doc.querySelectorAll('[data-moderation-edit-toggle]').forEach((button) => {
    const panel = doc.getElementById(button.getAttribute('aria-controls'));
    if (!panel) return;
    button.addEventListener('click', () => {
      const open = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', String(open));
      button.textContent = open ? '收起' : '编辑';
      panel.classList.toggle('is-open', open);
      panel.setAttribute('aria-hidden', String(!open));
      if (open) window.setTimeout(() => panel.querySelector('textarea')?.focus(), 180);
    });
  });

  doc.querySelectorAll('form[data-card-delete]').forEach((form) => form.addEventListener('submit', (event) => {
    if (event.defaultPrevented || form.dataset.cardDeleteReady === 'true') return;
    event.preventDefault();
    const submitter = event.submitter;
    const card = form.closest('[data-moderation-card]');
    if (!card) {
      form.dataset.cardDeleteReady = 'true';
      form.requestSubmit(submitter);
      return;
    }
    card.style.maxHeight = `${card.scrollHeight}px`;
    card.getBoundingClientRect();
    card.classList.add('is-removing');
    window.setTimeout(() => {
      form.dataset.cardDeleteReady = 'true';
      if (submitter?.isConnected) form.requestSubmit(submitter);
      else form.requestSubmit();
    }, motionIsReduced() ? 0 : 260);
  }));

  doc.addEventListener('keydown', (event) => {
    if (mobileDrawer?.classList.contains('is-open')) trapFocus(event, mobileDrawer);
    if (adminSidebar?.classList.contains('is-open')) trapFocus(event, adminSidebar);
    if (event.key !== 'Escape') return;
    if (mobileDrawer?.classList.contains('is-open')) closeMobileDrawer();
    if (adminSidebar?.classList.contains('is-open')) closeAdminDrawer();
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 860 && mobileDrawerState !== 'closed') closeMobileDrawer();
  }, { passive: true });

  doc.addEventListener('visibilitychange', () => root.classList.toggle('page-hidden', doc.hidden));
  systemReducedMotion.addEventListener?.('change', updateMotionControls);
  updateMotionControls();

  doc.querySelectorAll('dialog[data-open-on-load]').forEach((dialog) => {
    window.requestAnimationFrame(() => openDialog(dialog));
  });

  const adminNavigation = doc.querySelector('.admin-nav');
  const adminAccordionTransitions = new WeakMap();
  const animateAdminAccordion = (items, nextItem, {
    panelSelector,
    toggleSelector,
    duration,
    ready,
  }) => {
    const records = items.map((item) => {
      const panel = item.querySelector(panelSelector);
      const open = item === nextItem;
      const changed = item.classList.contains('is-open') !== open;
      return {
        item,
        panel,
        open,
        changed,
        startHeight: changed ? (panel?.getBoundingClientRect().height || 0) : 0,
      };
    });
    const shouldAnimate = ready && !motionIsReduced();

    records.forEach(({ item, open }) => {
      item.classList.toggle('is-open', open);
      item.querySelector(toggleSelector)?.setAttribute('aria-expanded', String(open));
    });

    records.forEach(({ panel, open, changed, startHeight }) => {
      if (!panel) return;
      if (shouldAnimate && !changed) return;
      const previous = adminAccordionTransitions.get(panel);
      if (previous) {
        window.clearTimeout(previous.timer);
        panel.removeEventListener('transitionend', previous.finish);
      }
      if (!shouldAnimate) {
        panel.classList.remove('is-height-animating');
        panel.style.removeProperty('height');
        adminAccordionTransitions.delete(panel);
        return;
      }

      panel.classList.add('is-height-animating');
      panel.style.height = `${startHeight}px`;
      const endHeight = open ? panel.scrollHeight : 0;
      const token = {};
      const finish = (event) => {
        if (event && (event.target !== panel || event.propertyName !== 'height')) return;
        if (adminAccordionTransitions.get(panel)?.token !== token) return;
        panel.classList.remove('is-height-animating');
        panel.style.removeProperty('height');
        panel.removeEventListener('transitionend', finish);
        window.clearTimeout(adminAccordionTransitions.get(panel)?.timer);
        adminAccordionTransitions.delete(panel);
      };
      panel.addEventListener('transitionend', finish);
      const timer = window.setTimeout(() => finish(), duration + 90);
      adminAccordionTransitions.set(panel, { token, timer, finish });
      window.requestAnimationFrame(() => {
        if (adminAccordionTransitions.get(panel)?.token === token) {
          panel.style.height = `${endHeight}px`;
        }
      });
    });
  };

  const gatewayEditorTransitions = new WeakMap();
  doc.querySelectorAll('[data-gateway-connection-editor]').forEach((editor) => {
    const panel = editor.querySelector('[data-gateway-editor-panel]');
    const inner = panel?.querySelector('.gateway-connection-editor__inner');
    const toggles = [...editor.querySelectorAll('[data-gateway-editor-toggle]')];
    const closeButtons = [...editor.querySelectorAll('[data-gateway-editor-close]')];
    if (!panel || !inner || !toggles.length) return;

    let gatewayEditorOpen = false;
    const finishGatewayEditorTransition = (open, token) => {
      const active = gatewayEditorTransitions.get(panel);
      if (active?.token !== token) return;
      panel.style.height = open ? 'auto' : '0px';
      panel.classList.toggle('is-open', open);
      panel.inert = !open;
      panel.removeEventListener('transitionend', active.finish);
      window.clearTimeout(active.timer);
      gatewayEditorTransitions.delete(panel);
    };

    const setGatewayEditorOpen = (open, { focusInside = false, returnFocus = false } = {}) => {
      const previous = gatewayEditorTransitions.get(panel);
      if (previous) {
        panel.removeEventListener('transitionend', previous.finish);
        window.clearTimeout(previous.timer);
        gatewayEditorTransitions.delete(panel);
      }

      gatewayEditorOpen = open;
      panel.inert = !open;
      const startHeight = panel.getBoundingClientRect().height;
      panel.style.height = `${startHeight}px`;
      panel.classList.toggle('is-open', open);
      panel.setAttribute('aria-hidden', String(!open));
      editor.classList.toggle('is-editor-open', open);
      toggles.forEach((toggle) => toggle.setAttribute('aria-expanded', String(open)));

      if (motionIsReduced()) {
        panel.style.height = open ? 'auto' : '0px';
        panel.inert = !open;
        if (focusInside && open) inner.querySelector('input:not([type="hidden"])')?.focus();
        if (returnFocus && !open) toggles[0]?.focus();
        return;
      }

      panel.getBoundingClientRect();
      const endHeight = open ? inner.scrollHeight : 0;
      const token = {};
      const finish = (event) => {
        if (event && (event.target !== panel || event.propertyName !== 'height')) return;
        finishGatewayEditorTransition(open, token);
        if (focusInside && open) inner.querySelector('input:not([type="hidden"])')?.focus();
        if (returnFocus && !open) toggles[0]?.focus();
      };
      panel.addEventListener('transitionend', finish);
      const timer = window.setTimeout(() => finish(), 540);
      gatewayEditorTransitions.set(panel, { token, timer, finish });
      window.requestAnimationFrame(() => {
        if (gatewayEditorTransitions.get(panel)?.token === token) {
          panel.style.height = `${endHeight}px`;
        }
      });
    };

    panel.style.height = '0px';
    panel.setAttribute('aria-hidden', 'true');
    panel.inert = true;
    toggles.forEach((toggle) => toggle.setAttribute('aria-expanded', 'false'));
    editor.dataset.editorReady = 'true';
    if (editor.dataset.editorStartOpen === 'true') {
      setGatewayEditorOpen(true);
    }

    toggles.forEach((toggle) => toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      setGatewayEditorOpen(open, { focusInside: open });
    }));
    closeButtons.forEach((button) => button.addEventListener('click', () => {
      setGatewayEditorOpen(false, { returnFocus: true });
    }));
    editor.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape' || panel.getAttribute('aria-hidden') === 'true') return;
      event.preventDefault();
      setGatewayEditorOpen(false, { returnFocus: true });
    });
    if (typeof ResizeObserver === 'function') {
      new ResizeObserver(() => {
        const active = gatewayEditorTransitions.get(panel);
        if (!gatewayEditorOpen || !active) return;
        panel.style.height = `${inner.scrollHeight}px`;
      }).observe(inner);
    }
  });

  const adminMenuGroups = [...doc.querySelectorAll('[data-admin-menu-group]')];
  if (adminNavigation && adminMenuGroups.length) {
    adminNavigation.dataset.heightAccordion = 'true';
    let storedMenuKey = '';
    try { storedMenuKey = localStorage.getItem('cloud-diary-admin-menu-open') || ''; } catch (_) { /* storage is optional */ }
    const currentGroup = adminMenuGroups.find((group) => group.querySelector('.is-current'));
    const storedGroup = adminMenuGroups.find((group) => group.dataset.menuKey === storedMenuKey);
    const initialGroup = currentGroup || storedGroup || adminMenuGroups.find((group) => group.dataset.menuKey === 'workspace');
    const setAdminMenuGroup = (nextGroup, persist = true) => {
      animateAdminAccordion(adminMenuGroups, nextGroup, {
        panelSelector: ':scope > .admin-nav-group__items',
        toggleSelector: ':scope > [data-admin-menu-toggle]',
        duration: 280,
        ready: adminNavigation.dataset.accordionReady === 'true',
      });
      if (persist) {
        try { localStorage.setItem('cloud-diary-admin-menu-open', nextGroup?.dataset.menuKey || ''); } catch (_) { /* storage is optional */ }
      }
    };
    setAdminMenuGroup(initialGroup, false);
    requestAnimationFrame(() => requestAnimationFrame(() => { adminNavigation.dataset.accordionReady = 'true'; }));
    adminMenuGroups.forEach((group) => {
      group.querySelector('[data-admin-menu-toggle]')?.addEventListener('click', () => {
        setAdminMenuGroup(group.classList.contains('is-open') ? null : group);
      });
    });
  }

  const adminSubmenus = [...doc.querySelectorAll('[data-admin-submenu]')];
  if (adminSubmenus.length) {
    const setAdminSubmenu = (nextSubmenu) => {
      animateAdminAccordion(adminSubmenus, nextSubmenu, {
        panelSelector: ':scope > .admin-subnav__items',
        toggleSelector: ':scope > [data-admin-submenu-toggle]',
        duration: 300,
        ready: adminNavigation?.dataset.submenusReady === 'true',
      });
    };
    const currentSubmenu = adminSubmenus.find((submenu) => submenu.querySelector('.is-current'))
      || adminSubmenus.find((submenu) => submenu.classList.contains('is-open'));
    setAdminSubmenu(currentSubmenu || null);
    adminSubmenus.forEach((submenu) => submenu.querySelector('[data-admin-submenu-toggle]')?.addEventListener('click', () => {
      setAdminSubmenu(submenu.classList.contains('is-open') ? null : submenu);
    }));
    requestAnimationFrame(() => doc.querySelector('.admin-nav')?.setAttribute('data-submenus-ready', 'true'));
  }

  const mediaGrid = doc.querySelector('[data-media-grid]');
  const mediaSizeButtons = doc.querySelectorAll('[data-media-preview-size]');
  if (mediaSizeButtons.length) {
    let storedSize = 'compact';
    try { storedSize = localStorage.getItem('cloud-diary-media-preview-size') || storedSize; } catch (_) { /* storage is optional */ }
    const applyMediaSize = (size) => {
      if (!['compact', 'standard', 'large'].includes(size)) size = 'compact';
      if (mediaGrid) mediaGrid.dataset.previewSize = size;
      mediaSizeButtons.forEach((button) => {
        const active = button.dataset.mediaPreviewSize === size;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
      });
      try { localStorage.setItem('cloud-diary-media-preview-size', size); } catch (_) { /* storage is optional */ }
    };
    applyMediaSize(storedSize);
    mediaSizeButtons.forEach((button) => button.addEventListener('click', () => applyMediaSize(button.dataset.mediaPreviewSize)));
  }

  const routeTransitionKey = 'cloud-diary-route-transition';
  const configuredTransitionDuration = () => Math.max(
    300,
    Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720)
  );
  const routeTransitionDurations = () => {
    const duration = configuredTransitionDuration();
    return {
      stretch: Math.round(duration * .58),
      fade: Math.round(duration * .27),
      'zoom-blur': Math.round(duration * .42),
      none: 0
    };
  };
  const currentTransitionStyle = () => (
    routeTransitionDurations()[root.dataset.pageTransition] !== undefined
      ? root.dataset.pageTransition
      : 'stretch'
  );
  const transitionTargetKind = (url) => (
    /^\/admin\/(?:posts\/(?:new\/|\d+\/edit\/)|pages\/(?:new\/|\d+\/edit\/))$/.test(url.pathname)
      ? 'editor'
      : 'page'
  );
  const rememberIncomingTransition = (target) => {
    try {
      sessionStorage.setItem(routeTransitionKey, JSON.stringify({
        startedAt: Date.now(),
        targetKind: transitionTargetKind(target)
      }));
    } catch (_) { /* storage is optional */ }
  };
  const beginPageLeave = (target) => {
    const style = currentTransitionStyle();
    if (motionIsReduced() || root.dataset.performance === 'low' || style === 'none') return 0;
    rememberIncomingTransition(target);
    root.classList.add('is-page-leaving');
    return routeTransitionDurations()[style];
  };
  if (root.classList.contains('is-page-entering')) {
    window.setTimeout(
      () => root.classList.remove('is-page-entering', 'is-editor-transition'),
      Math.max(1100, Math.round(configuredTransitionDuration() * 1.6))
    );
  }
  window.addEventListener('pageshow', () => root.classList.remove('is-page-leaving'));

  const themePreviewTimers = new WeakMap();
  const replayThemePreview = (target, className = 'is-preview-updating') => {
    if (!target || motionIsReduced()) return;
    window.clearTimeout(themePreviewTimers.get(target));
    target.classList.remove(className);
    void target.offsetWidth;
    window.requestAnimationFrame(() => target.classList.add(className));
    themePreviewTimers.set(target, window.setTimeout(() => {
      target.classList.remove(className);
      themePreviewTimers.delete(target);
    }, 620));
  };
  const fontSettings = doc.querySelector('[data-font-settings]');
  fontSettings?.querySelectorAll('input[name="font_style"]').forEach((input) => {
    input.addEventListener('change', () => {
      if (!input.checked) return;
      root.dataset.fontStyle = input.value;
      replayThemePreview(fontSettings);
      replayThemePreview(input.closest('.font-choice'), 'is-choice-switching');
    });
  });
  const hintSettings = doc.querySelector('[data-hint-settings]');
  const hintPreviewAttributes = {
    panel_descriptions_visible: 'panelDescriptions',
    card_descriptions_visible: 'cardDescriptions',
    field_descriptions_visible: 'fieldDescriptions'
  };
  hintSettings?.querySelectorAll('.hint-control-card input[type="checkbox"]').forEach((input) => {
    input.addEventListener('change', () => {
      const card = input.closest('.hint-control-card');
      if (input.name === 'admin_menu_subtitles_visible') {
        doc.querySelector('.admin-shell')?.classList.toggle('admin-menu--compact', !input.checked);
      } else if (hintPreviewAttributes[input.name]) {
        root.dataset[hintPreviewAttributes[input.name]] = input.checked ? 'visible' : 'hidden';
      }
      replayThemePreview(card, 'is-choice-switching');
      replayThemePreview(hintSettings);
    });
  });

  const transitionDurationInput = doc.querySelector('[data-transition-duration-input]');
  const transitionDurationRange = doc.querySelector('[data-transition-duration-range]');
  const transitionDurationOutput = doc.querySelector('[data-transition-duration-output]');
  const transitionSettings = doc.querySelector('[data-transition-settings]');
  const replayTransitionChoice = (input) => {
    if (!input) return;
    replayThemePreview(input.closest('.transition-choice'), 'is-choice-switching');
    replayThemePreview(input.closest('.transition-choice')?.querySelector('.transition-choice__demo'), 'is-preview-playing');
  };
  const syncTransitionDuration = (value) => {
    const duration = Math.max(300, Math.min(2400, Number.parseInt(value, 10) || 720));
    if (transitionDurationInput) transitionDurationInput.value = String(duration);
    if (transitionDurationRange) transitionDurationRange.value = String(duration);
    if (transitionDurationOutput) transitionDurationOutput.textContent = `${duration} ms`;
    root.dataset.transitionDuration = String(duration);
    root.style.setProperty('--route-duration', `${duration}ms`);
    root.style.setProperty('--theme-preview-duration', `${Math.min(duration, 1500)}ms`);
    replayTransitionChoice(transitionSettings?.querySelector('input[name="transition_style"]:checked'));
  };
  transitionDurationInput?.addEventListener('input', (event) => syncTransitionDuration(event.target.value));
  transitionDurationRange?.addEventListener('input', (event) => syncTransitionDuration(event.target.value));
  transitionSettings?.querySelectorAll('input[name="transition_style"]').forEach((input) => {
    input.addEventListener('change', () => {
      if (!input.checked) return;
      root.dataset.pageTransition = input.value;
      replayTransitionChoice(input);
      replayThemePreview(transitionSettings);
    });
  });
  const appearanceColorVariables = {
    transition_color_start: '--route-color-start',
    transition_color_middle: '--route-color-middle',
    transition_color_end: '--route-color-end',
    dialog_color_start: '--dialog-color-start',
    dialog_color_end: '--dialog-color-end',
    dialog_accent: '--dialog-accent'
  };
  doc.querySelectorAll('.appearance-color-field input[type="color"]').forEach((input) => {
    const syncAppearanceColor = () => {
      const variable = appearanceColorVariables[input.name];
      if (variable) root.style.setProperty(variable, input.value);
      const output = input.closest('.appearance-color-field')?.querySelector('[data-color-value]');
      if (output) output.textContent = input.value.toUpperCase();
      replayThemePreview(input.closest('.appearance-color-field'), 'is-choice-switching');
      replayThemePreview(input.closest('.appearance-color-card'));
    };
    input.addEventListener('input', syncAppearanceColor);
  });
  doc.querySelectorAll('input[name="dialog_style"]').forEach((input) => {
    input.addEventListener('change', () => {
      if (!input.checked) return;
      root.dataset.dialogStyle = input.value;
      replayThemePreview(input.closest('.dialog-style-choice'), 'is-choice-switching');
      replayThemePreview(input.closest('[data-dialog-appearance-settings]'));
    });
  });
  const dialogMetricConfig = {
    radius: { minimum: 14, maximum: 42, fallback: 30, variable: '--dialog-radius' },
    width: { minimum: 360, maximum: 720, fallback: 510, variable: '--dialog-width' },
    blur: { minimum: 0, maximum: 30, fallback: 6, variable: '--dialog-backdrop-blur' }
  };
  const syncDialogMetric = (name, rawValue) => {
    const config = dialogMetricConfig[name];
    if (!config) return;
    const parsed = Number.parseInt(rawValue, 10);
    const value = Math.max(
      config.minimum,
      Math.min(config.maximum, Number.isFinite(parsed) ? parsed : config.fallback)
    );
    doc.querySelectorAll(`[data-dialog-range="${name}"], [data-dialog-value="${name}"]`).forEach((control) => {
      control.value = String(value);
    });
    const output = doc.querySelector(`[data-dialog-output="${name}"]`);
    if (output) output.textContent = `${value} px`;
    root.style.setProperty(config.variable, `${value}px`);
    replayThemePreview(doc.querySelector(`[data-dialog-range="${name}"]`)?.closest('.dialog-metric-control'), 'is-choice-switching');
  };
  doc.querySelectorAll('[data-dialog-value]').forEach((input) => {
    syncDialogMetric(input.dataset.dialogValue, input.value);
    input.addEventListener('input', () => syncDialogMetric(input.dataset.dialogValue, input.value));
  });
  doc.querySelectorAll('[data-dialog-range]').forEach((input) => {
    input.addEventListener('input', () => syncDialogMetric(input.dataset.dialogRange, input.value));
  });
  doc.querySelectorAll('input[name="dialog_shadow"]').forEach((input) => {
    input.addEventListener('change', () => {
      if (!input.checked) return;
      root.dataset.dialogShadow = input.value;
      replayThemePreview(input.closest('.dialog-shadow-fieldset'));
    });
  });
  doc.querySelectorAll('[data-dialog-preview]').forEach((button) => {
    button.addEventListener('click', () => {
      if (button.dataset.dialogPreview === 'prompt') {
        themedPrompt('', '', '输入内容');
      } else if (button.dataset.dialogPreview === 'alert') {
        themedAlert('操作已完成。', '提示');
      } else {
        themedConfirm('是否继续？', '确认操作');
      }
    });
  });
  doc.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target === '_blank' || link.hasAttribute('download') || link.dataset.noTransition !== undefined) return;
    if (link.closest('[contenteditable="true"]')) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || !['http:', 'https:'].includes(target.protocol)) return;
    if (target.pathname === window.location.pathname && target.search === window.location.search && target.hash) return;
    const delay = beginPageLeave(target);
    if (!delay) return;
    event.preventDefault();
    window.setTimeout(() => window.location.assign(target.href), delay);
  });
  doc.addEventListener('submit', (event) => {
    const form = event.target;
    if (event.defaultPrevented || form.dataset.transitionSubmitting === 'true' || !form.checkValidity() || form.target === '_blank') return;
    const target = new URL(form.action || window.location.href, window.location.href);
    if (target.origin !== window.location.origin) return;
    const delay = beginPageLeave(target);
    if (!delay) return;
    event.preventDefault();
    const submitter = event.submitter;
    window.setTimeout(() => {
      form.dataset.transitionSubmitting = 'true';
      if (submitter?.isConnected) form.requestSubmit(submitter);
      else form.requestSubmit();
    }, delay);
  });

  const pressableSelector = 'button, a[href], summary, [role="button"], .card--interactive, .film-frame, .moment-note';
  let pressedControl = null;
  let pressedPointer = null;
  const releaseTimers = new WeakMap();
  const releaseControl = (cancelled = false) => {
    if (!pressedControl) return;
    const control = pressedControl;
    control.classList.remove('is-pressed');
    if (!cancelled && !motionIsReduced()) {
      window.clearTimeout(releaseTimers.get(control));
      control.classList.add('is-releasing');
      releaseTimers.set(control, window.setTimeout(() => control.classList.remove('is-releasing'), 260));
    }
    pressedControl = null;
    pressedPointer = null;
  };
  doc.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || event.isPrimary === false) return;
    const control = event.target.closest(pressableSelector);
    if (!control || control.matches(':disabled,[aria-disabled="true"]')) return;
    releaseControl(true);
    pressedControl = control;
    pressedPointer = event.pointerId;
    control.classList.remove('is-releasing');
    control.classList.add('is-pressed');
  }, { passive: true });
  window.addEventListener('pointerup', (event) => {
    if (event.pointerId === pressedPointer) releaseControl(false);
  }, { passive: true });
  window.addEventListener('pointercancel', (event) => {
    if (event.pointerId === pressedPointer) releaseControl(true);
  }, { passive: true });
  window.addEventListener('blur', () => releaseControl(true));

  const revealItems = [...doc.querySelectorAll('[data-reveal]')];
  const restoredNavigation = performance.getEntriesByType('navigation')[0]?.type === 'back_forward';
  if (revealItems.length) {
    revealItems.forEach((item) => item.style.setProperty('--reveal-order', item.dataset.revealOrder || '0'));
    if (motionIsReduced() || root.dataset.performance === 'low' || restoredNavigation || !('IntersectionObserver' in window)) {
      revealItems.forEach((item) => item.classList.add('is-revealed'));
    } else {
      root.classList.add('is-motion-ready');
      const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-revealed');
          observer.unobserve(entry.target);
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
      revealItems.forEach((item) => revealObserver.observe(item));
    }
  }

  doc.querySelectorAll('[data-tilt]').forEach((card) => {
    let tiltFrame = 0;
    card.addEventListener('pointermove', (event) => {
      if (motionIsReduced() || root.dataset.performance === 'low' || event.pointerType === 'touch') return;
      window.cancelAnimationFrame(tiltFrame);
      tiltFrame = requestAnimationFrame(() => {
        const rect = card.getBoundingClientRect();
        const x = Math.max(-1, Math.min(1, (event.clientX - rect.left) / rect.width * 2 - 1));
        const y = Math.max(-1, Math.min(1, (event.clientY - rect.top) / rect.height * 2 - 1));
        card.style.setProperty('--tilt-x', `${(-y * 0.7).toFixed(2)}deg`);
        card.style.setProperty('--tilt-y', `${(x * 0.7).toFixed(2)}deg`);
        card.classList.add('is-tilting');
      });
    }, { passive: true });
    card.addEventListener('pointerleave', () => {
      window.cancelAnimationFrame(tiltFrame);
      card.style.setProperty('--tilt-x', '0deg');
      card.style.setProperty('--tilt-y', '0deg');
      card.classList.remove('is-tilting');
    }, { passive: true });
  });

  const countItems = [...doc.querySelectorAll('[data-count]')];
  const revealCount = (item) => {
    if (item.dataset.counted === 'true') return;
    item.dataset.counted = 'true';
    const finalValue = Math.max(0, Number(item.dataset.count) || 0);
    if (motionIsReduced() || root.dataset.performance === 'low' || finalValue === 0) {
      item.textContent = String(finalValue);
      return;
    }
    const startedAt = performance.now();
    const draw = (now) => {
      const progress = Math.min(1, (now - startedAt) / 520);
      const eased = 1 - Math.pow(1 - progress, 3);
      item.textContent = String(Math.round(finalValue * eased));
      if (progress < 1) requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  };
  if (countItems.length && 'IntersectionObserver' in window && !motionIsReduced()) {
    const countObserver = new IntersectionObserver((entries, observer) => entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      revealCount(entry.target);
      observer.unobserve(entry.target);
    }), { threshold: 0.45 });
    countItems.forEach((item) => countObserver.observe(item));
  } else countItems.forEach(revealCount);

  const capsuleNavigation = doc.querySelector('[data-capsule-nav]');
  if (capsuleNavigation) {
    const capsuleViewport = window.matchMedia('(min-width: 621px)');
    let previousScrollY = Math.max(0, window.scrollY);
    let capsuleTicking = false;
    let arrivalTimer = 0;
    const pageCanScroll = () => doc.documentElement.scrollHeight > window.innerHeight + 24;
    const setCapsuleVisible = (visible) => {
      capsuleNavigation.classList.toggle('is-nav-visible', visible);
      capsuleNavigation.classList.toggle('is-nav-hidden', !visible);
    };
    const updateCapsuleNavigation = () => {
      const currentScrollY = Math.max(0, window.scrollY);
      const scrollDelta = currentScrollY - previousScrollY;
      if (!capsuleViewport.matches || !pageCanScroll()) {
        setCapsuleVisible(true);
      } else if (scrollDelta > 0) {
        setCapsuleVisible(false);
      } else if (scrollDelta < 0) {
        setCapsuleVisible(true);
      }
      previousScrollY = currentScrollY;
      capsuleTicking = false;
    };
    const requestCapsuleUpdate = () => {
      if (capsuleTicking) return;
      capsuleTicking = true;
      window.requestAnimationFrame(updateCapsuleNavigation);
    };
    const resetCapsuleNavigation = () => {
      previousScrollY = Math.max(0, window.scrollY);
      setCapsuleVisible(true);
      requestCapsuleUpdate();
    };
    const playCapsuleArrival = () => {
      window.clearTimeout(arrivalTimer);
      capsuleNavigation.classList.remove('is-nav-arriving');
      if (capsuleViewport.matches && !motionIsReduced()) {
        window.requestAnimationFrame(() => capsuleNavigation.classList.add('is-nav-arriving'));
      }
      arrivalTimer = window.setTimeout(() => capsuleNavigation.classList.remove('is-nav-arriving'), 680);
    };
    setCapsuleVisible(true);
    playCapsuleArrival();
    window.addEventListener('scroll', requestCapsuleUpdate, { passive: true });
    window.addEventListener('resize', resetCapsuleNavigation, { passive: true });
    capsuleViewport.addEventListener?.('change', resetCapsuleNavigation);
    window.addEventListener('pageshow', playCapsuleArrival);
  }

  const mobileCapsuleNavigation = doc.querySelector('[data-mobile-capsule-nav]');
  if (mobileCapsuleNavigation) {
    const mobileCapsuleViewport = window.matchMedia('(max-width: 860px)');
    let previousMobileScrollY = Math.max(0, window.scrollY);
    let mobileCapsuleTicking = false;
    let mobileArrivalTimer = 0;
    const mobilePageCanScroll = () => doc.documentElement.scrollHeight > window.innerHeight + 24;
    const setMobileCapsuleVisible = (visible) => {
      mobileCapsuleNavigation.classList.toggle('is-mobile-nav-visible', visible);
      mobileCapsuleNavigation.classList.toggle('is-mobile-nav-hidden', !visible);
    };
    const updateMobileCapsuleNavigation = () => {
      const currentScrollY = Math.max(0, window.scrollY);
      const scrollDelta = currentScrollY - previousMobileScrollY;
      if (!mobileCapsuleViewport.matches || !mobilePageCanScroll()) {
        setMobileCapsuleVisible(true);
      } else if (scrollDelta > 0) {
        setMobileCapsuleVisible(false);
      } else if (scrollDelta < 0) {
        setMobileCapsuleVisible(true);
      }
      previousMobileScrollY = currentScrollY;
      mobileCapsuleTicking = false;
    };
    const requestMobileCapsuleUpdate = () => {
      if (mobileCapsuleTicking) return;
      mobileCapsuleTicking = true;
      window.requestAnimationFrame(updateMobileCapsuleNavigation);
    };
    const resetMobileCapsuleNavigation = () => {
      previousMobileScrollY = Math.max(0, window.scrollY);
      setMobileCapsuleVisible(true);
      requestMobileCapsuleUpdate();
    };
    const playMobileCapsuleArrival = () => {
      window.clearTimeout(mobileArrivalTimer);
      mobileCapsuleNavigation.classList.remove('is-mobile-nav-arriving');
      if (mobileCapsuleViewport.matches && !motionIsReduced()) {
        window.requestAnimationFrame(() => mobileCapsuleNavigation.classList.add('is-mobile-nav-arriving'));
      }
      mobileArrivalTimer = window.setTimeout(
        () => mobileCapsuleNavigation.classList.remove('is-mobile-nav-arriving'),
        680
      );
    };
    setMobileCapsuleVisible(true);
    playMobileCapsuleArrival();
    window.addEventListener('scroll', requestMobileCapsuleUpdate, { passive: true });
    window.addEventListener('resize', resetMobileCapsuleNavigation, { passive: true });
    mobileCapsuleViewport.addEventListener?.('change', resetMobileCapsuleNavigation);
    window.addEventListener('pageshow', playMobileCapsuleArrival);
  }

  const navigationLinks = doc.querySelector('.site-nav__links');
  const currentNavigationLink = navigationLinks?.querySelector('.is-current');
  if (navigationLinks && currentNavigationLink && !navigationLinks.classList.contains('site-nav__links--account')) {
    const indicator = doc.createElement('span');
    indicator.className = 'nav-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    navigationLinks.prepend(indicator);
    const moveIndicator = (link) => {
      const linkRect = link.getBoundingClientRect();
      indicator.style.width = `${linkRect.width}px`;
      indicator.style.height = `${linkRect.height}px`;
      indicator.style.transform = `translate3d(${link.offsetLeft}px,${link.offsetTop}px,0)`;
    };
    requestAnimationFrame(() => moveIndicator(currentNavigationLink));
    navigationLinks.querySelectorAll('a').forEach((link) => link.addEventListener('pointerenter', () => moveIndicator(link), { passive: true }));
    navigationLinks.addEventListener('pointerleave', () => moveIndicator(currentNavigationLink), { passive: true });
    window.addEventListener('resize', () => moveIndicator(currentNavigationLink), { passive: true });
  }

  const localTime = doc.querySelector('[data-local-time]');
  if (localTime) {
    const updateLocalTime = () => {
      localTime.textContent = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date());
    };
    updateLocalTime();
    window.setInterval(updateLocalTime, 60_000);
  }

  const runtimeMetrics = doc.querySelector('[data-runtime-metrics]');
  if (runtimeMetrics) {
    const endpoint = runtimeMetrics.dataset.endpoint;
    const sampledAt = runtimeMetrics.querySelector('[data-runtime-sampled-at]');
    const state = runtimeMetrics.querySelector('[data-runtime-state]');
    let runtimeRequestActive = false;

    const updateResource = (key, resource) => {
      const card = runtimeMetrics.querySelector(`[data-runtime-resource="${key}"]`);
      if (!card || !resource) return;
      const percent = Math.min(100, Math.max(0, Number(resource.percent) || 0));
      const percentOutput = card.querySelector('[data-runtime-percent]');
      const currentOutput = card.querySelector('[data-runtime-current]');
      const totalOutput = card.querySelector('[data-runtime-total]');
      const progress = card.querySelector('.runtime-progress');
      const progressFill = card.querySelector('[data-runtime-progress]');
      if (percentOutput) percentOutput.textContent = `${percent.toFixed(1)}%`;
      if (currentOutput) currentOutput.textContent = resource.current || '暂不可用';
      if (totalOutput) totalOutput.textContent = resource.total || '总量暂不可用';
      progress?.setAttribute('aria-valuenow', `${percent}`);
      progressFill?.style.setProperty('--runtime-percent', `${percent}%`);
    };

    const refreshRuntimeMetrics = async () => {
      if (!endpoint || runtimeRequestActive || doc.visibilityState === 'hidden') return;
      runtimeRequestActive = true;
      try {
        const response = await fetch(endpoint, {
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) throw new Error(`runtime metrics ${response.status}`);
        const payload = await response.json();
        if (!payload.ok || !payload.data?.resources) throw new Error('invalid runtime metrics');
        Object.entries(payload.data.resources).forEach(([key, resource]) => updateResource(key, resource));
        if (sampledAt) sampledAt.textContent = payload.data.sampled_at || '--:--:--';
        if (state) state.textContent = '每 2 秒自动更新';
      } catch (_error) {
        if (state) state.textContent = '实时数据暂时无法更新';
      } finally {
        runtimeRequestActive = false;
      }
    };

    window.setInterval(refreshRuntimeMetrics, 2_000);
    doc.addEventListener('visibilitychange', () => {
      if (doc.visibilityState === 'visible') refreshRuntimeMetrics();
    });
  }

  doc.querySelectorAll('img').forEach((image) => {
    image.decoding = 'async';
    if (image.complete) image.classList.add('is-loaded');
    else image.addEventListener('load', () => image.classList.add('is-loaded'), { once: true });
  });

  const readingProgress = doc.querySelector('[data-reading-progress]');
  const readingFills = doc.querySelectorAll('[data-reading-progress-fill]');
  const readingValue = doc.querySelector('[data-reading-progress-value]');
  const readingRemaining = doc.querySelector('[data-reading-progress-remaining]');
  const article = doc.querySelector('[data-article-content]');
  if (readingProgress && readingFills.length && article) {
    let ticking = false;
    let articleStart = 0;
    let articleEnd = 1;
    const totalMinutes = Math.max(1, Number(readingProgress.dataset.readingMinutes) || 1);
    const viewportHeight = () => window.visualViewport?.height || window.innerHeight;
    const measureReadingRange = () => {
      const bounds = article.getBoundingClientRect();
      articleStart = window.scrollY + bounds.top;
      articleEnd = Math.max(articleStart + 1, articleStart + article.scrollHeight - viewportHeight());
    };
    const updateReadingProgress = () => {
      const progress = Math.min(1, Math.max(0, (window.scrollY - articleStart) / (articleEnd - articleStart)));
      const percent = Math.round(progress * 100);
      readingFills.forEach((fill) => { fill.style.transform = `scaleX(${progress})`; });
      if (readingValue) readingValue.textContent = `${percent}%`;
      if (readingRemaining) {
        const minutes = Math.max(0, Math.ceil(totalMinutes * (1 - progress)));
        readingRemaining.textContent = minutes ? `约剩 ${minutes} 分钟` : '已经读完啦';
      }
      readingProgress.classList.toggle('has-progress', progress > 0);
      ticking = false;
    };
    const requestReadingUpdate = () => {
      if (!ticking) { ticking = true; requestAnimationFrame(updateReadingProgress); }
    };
    window.addEventListener('scroll', () => {
      requestReadingUpdate();
    }, { passive: true });
    window.addEventListener('resize', () => {
      measureReadingRange();
      requestReadingUpdate();
    }, { passive: true });
    window.visualViewport?.addEventListener('resize', () => {
      measureReadingRange();
      requestReadingUpdate();
    }, { passive: true });
    if ('ResizeObserver' in window) {
      new ResizeObserver(() => {
        measureReadingRange();
        requestReadingUpdate();
      }).observe(article);
    }
    measureReadingRange();
    updateReadingProgress();
  }

  const lightbox = doc.querySelector('[data-image-lightbox]');
  article?.querySelectorAll('img').forEach((image) => {
    image.tabIndex = 0;
    image.setAttribute('role', 'button');
    image.setAttribute('aria-label', `${image.alt || '文章图片'}，点击放大`);
    const open = () => {
      if (!lightbox) return;
      lightbox.querySelector('img').src = image.currentSrc || image.src;
      lightbox.querySelector('img').alt = image.alt;
      openDialog(lightbox);
    };
    image.addEventListener('click', open);
    image.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
    });
  });
  lightbox?.querySelector('[data-close-lightbox]')?.addEventListener('click', () => closeDialog(lightbox));
  lightbox?.addEventListener('click', (event) => { if (event.target === lightbox) closeDialog(lightbox); });

  const editor = doc.querySelector('[data-content-editor-form]');
  if (editor?.dataset.autosaveUrl) {
    const status = doc.querySelector('[data-autosave-status]');
    let autosaveTimer;
    const autosave = async () => {
      const title = editor.querySelector('[name="title"]').value.trim();
      const content = editor.querySelector('[name="content_markdown"]').value;
      if (!title || !content) return;
      status.textContent = '正在自动保存…';
      try {
        const csrfToken = editor.querySelector('[name="csrf_token"]')?.value || '';
        const response = await fetch(editor.dataset.autosaveUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
          },
          body: JSON.stringify({ title, content_markdown: content, summary: editor.querySelector('[name="summary"]').value })
        });
        if (!response.ok) throw new Error('save failed');
        status.textContent = `已自动保存 ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      } catch (_) { status.textContent = '自动保存失败，请手动保存'; }
    };
    editor.addEventListener('input', () => {
      status.textContent = '有未保存修改';
      window.clearTimeout(autosaveTimer);
      autosaveTimer = window.setTimeout(autosave, 1200);
    });
  }

  const imageInput = doc.querySelector('[data-editor-image]');
  imageInput?.addEventListener('change', async () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    const status = doc.querySelector('[data-upload-status]');
    const textarea = doc.querySelector('[name="content_markdown"]');
    const data = new FormData();
    data.append('image', file);
    status.textContent = '正在处理图片…';
    try {
      const response = await fetch(imageInput.dataset.uploadUrl, {
        method: 'POST', headers: { 'X-CSRFToken': editor.querySelector('[name="csrf_token"]').value }, body: data
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || '上传失败');
      const start = textarea.selectionStart;
      textarea.setRangeText(`\n${payload.data.markdown}\n`, start, textarea.selectionEnd, 'end');
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      status.textContent = '图片已插入正文';
      showToast('图片已安全处理并插入正文。', 'success');
    } catch (error) { status.textContent = error.message; showToast(error.message, 'error'); }
    imageInput.value = '';
  });

  const commentForm = doc.querySelector('.comment-form');
  const parentInput = commentForm?.querySelector('[name="parent_id"]');
  const replyIndicator = commentForm?.querySelector('[data-reply-indicator]');
  doc.querySelectorAll('[data-reply-to]').forEach((button) => button.addEventListener('click', () => {
    if (!commentForm || !parentInput || !replyIndicator) return;
    parentInput.value = button.dataset.replyTo;
    replyIndicator.hidden = false;
    replyIndicator.querySelector('strong').textContent = button.dataset.replyName;
    commentForm.querySelector('[name="content"]')?.focus({ preventScroll: true });
    commentForm.scrollIntoView({ behavior: motionIsReduced() ? 'auto' : 'smooth', block: 'center' });
  }));
  commentForm?.querySelector('[data-cancel-reply]')?.addEventListener('click', () => {
    parentInput.value = '';
    replyIndicator.hidden = true;
  });

  const imageLightbox = doc.querySelector('[data-global-image-lightbox]');
  doc.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-image-preview],[data-gallery-image]');
    if (!trigger || !imageLightbox) return;
    event.preventDefault();
    const previewImage = imageLightbox.querySelector('img');
    const caption = imageLightbox.querySelector('[data-image-preview-caption]');
    const source = trigger.dataset.fullSrc || trigger.querySelector('img')?.src;
    if (!source) return;
    previewImage.src = source;
    previewImage.alt = trigger.dataset.alt || trigger.querySelector('img')?.alt || '';
    const captionText = trigger.dataset.caption || '';
    caption.textContent = captionText;
    caption.hidden = !captionText;
    openDialog(imageLightbox);
  });
  imageLightbox?.querySelector('[data-close-image-preview]')?.addEventListener('click', () => closeDialog(imageLightbox));
  imageLightbox?.addEventListener('click', (event) => { if (event.target === imageLightbox) closeDialog(imageLightbox); });

  doc.querySelectorAll('[data-gateway-auto-continue]').forEach((panel) => {
    const target = panel.dataset.continueUrl;
    if (!target) return;
    const requestedDelay = Number.parseInt(panel.dataset.continueDelay || '1000', 10);
    window.setTimeout(() => window.location.replace(target), motionIsReduced() ? 80 : Math.max(300, requestedDelay));
  });

  doc.querySelectorAll('[data-fallback-image]').forEach((image) => {
    const container = image.closest('[data-fallback-media]');
    const fallback = () => {
      image.hidden = true;
      container?.classList.add('is-fallback');
    };
    image.addEventListener('error', fallback, { once: true });
    image.addEventListener('load', () => container?.classList.add('has-image'), { once: true });
    if (image.complete && image.naturalWidth === 0) fallback();
  });

  window.CloudDiary = {
    showToast,
    setMotionPreference,
    confirm: themedConfirm,
    prompt: themedPrompt,
    alert: themedAlert
  };
})();
