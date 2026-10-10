(() => {
  const doc = document;
  const root = doc.documentElement;
  /* Page-scoped behaviour is registered with the navigation runtime so it is
     disposed and mounted again whenever an enhanced navigation swaps the page
     region. Listeners on region elements need no cleanup: the nodes go away.
     Timers, observers and window/document listeners are tied to `signal`. */
  const pageModule = (name, init) => {
    if (window.CloudtracePage?.define) window.CloudtracePage.define(name, init);
    else init(doc, new AbortController().signal);
  };
  const mobileDrawer = doc.querySelector('#mobile-drawer');
  const mobileBackdrop = doc.querySelector('[data-mobile-backdrop]');
  const adminSidebar = doc.querySelector('#admin-sidebar');
  const adminBackdrop = doc.querySelector('[data-admin-backdrop]');
  const adminDrawerMedia = window.matchMedia('(max-width: 1000px)');
  let lastTrigger = null;
  let mobileDrawerState = 'closed';
  let mobileDrawerCloseTimer = 0;
  const systemReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const themeVariables = {
    componentMotionColor: '--component-motion-color',
    toastBackground: '--toast-background', toastText: '--toast-text',
    toastAccent: '--toast-accent', toastSuccess: '--toast-success',
    toastWarning: '--toast-warning', toastError: '--toast-error'
  };
  Object.entries(themeVariables).forEach(([key, property]) => {
    if (root.dataset[key] && CSS.supports('color', root.dataset[key])) {
      root.style.setProperty(property, root.dataset[key]);
    }
  });
  if (root.dataset.toastRadius) root.style.setProperty('--toast-radius', `${root.dataset.toastRadius}px`);

  function motionIsReduced() {
    return root.dataset.motion === 'reduce' || (root.dataset.motion === 'system' && systemReducedMotion.matches);
  }

  if ((navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) || (navigator.deviceMemory && navigator.deviceMemory <= 4)) {
    root.dataset.performance = 'low';
  }

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

  /* One lifecycle per dialog: reopening cancels a pending close, a second close
     is ignored, the modal stays modal until its exit has finished, and focus
     returns to whatever opened it. */
  const dialogLifecycles = new WeakMap();
  const dialogLifecycle = (dialog) => {
    let state = dialogLifecycles.get(dialog);
    if (!state) {
      state = { version: 0, timer: 0, opener: null };
      dialogLifecycles.set(dialog, state);
    }
    return state;
  };

  function openDialog(dialog) {
    if (!dialog) return;
    const state = dialogLifecycle(dialog);
    const version = ++state.version;
    window.clearTimeout(state.timer);
    state.timer = 0;
    const active = doc.activeElement;
    if (!dialog.open && active && active !== doc.body && !dialog.contains(active)) state.opener = active;
    dialog.classList.remove('is-closing');
    if (!dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    }
    // A throttled frame (background tab, busy main thread) must never leave an
    // invisible modal blocking the page, so a short timer backs up the frame.
    const present = () => {
      if (state.version === version && dialog.open) dialog.classList.add('is-present');
    };
    requestAnimationFrame(present);
    window.setTimeout(present, 80);
  }

  function finishDialogClose(dialog, state) {
    state.timer = 0;
    dialog.classList.remove('is-closing');
    const focusWasInside = dialog.contains(doc.activeElement) || doc.activeElement === doc.body || !doc.activeElement;
    if (typeof dialog.close === 'function') { if (dialog.open) dialog.close(); }
    else dialog.removeAttribute('open');
    const opener = state.opener;
    state.opener = null;
    if (focusWasInside && opener?.isConnected && !opener.closest('[inert]')) opener.focus({ preventScroll: true });
  }

  function closeDialog(dialog) {
    if (!dialog || !dialog.open) return;
    const state = dialogLifecycle(dialog);
    if (state.timer) return;
    state.version += 1;
    dialog.classList.remove('is-present');
    if (motionIsReduced()) {
      finishDialogClose(dialog, state);
      return;
    }
    dialog.classList.add('is-closing');
    const version = state.version;
    state.timer = window.setTimeout(() => {
      if (state.version === version) finishDialogClose(dialog, state);
    }, 240);
  }

  /* Escape on any themed dialog runs the same animated close. Dialogs that own
     a result (system dialog, image studio) handle their own cancel event. */
  doc.addEventListener('cancel', (event) => {
    const dialog = event.target;
    if (!(dialog instanceof HTMLDialogElement)) return;
    if (dialog.matches('[data-app-system-dialog], [data-image-crop-dialog]')) return;
    event.preventDefault();
    closeDialog(dialog);
  }, true);

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
    adminSidebar.removeAttribute('inert');
    adminSidebar.setAttribute('aria-hidden', 'false');
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
    if (adminDrawerMedia.matches) {
      adminSidebar.setAttribute('aria-hidden', 'true');
      adminSidebar.setAttribute('inert', '');
    }
    adminBackdrop?.classList.remove('is-visible');
    doc.body.classList.remove('drawer-open');
    doc.querySelector('[data-admin-drawer]')?.setAttribute('aria-expanded', 'false');
    window.setTimeout(() => { if (adminBackdrop) adminBackdrop.hidden = true; }, 180);
    lastTrigger?.focus();
  }

  function syncAdminDrawerAccessibility() {
    if (!adminSidebar) return;
    if (adminDrawerMedia.matches) {
      if (!adminSidebar.classList.contains('is-open')) {
        adminSidebar.setAttribute('aria-hidden', 'true');
        adminSidebar.setAttribute('inert', '');
      }
      return;
    }
    adminSidebar.classList.remove('is-open');
    adminSidebar.removeAttribute('inert');
    adminSidebar.setAttribute('aria-hidden', 'false');
    adminBackdrop?.classList.remove('is-visible');
    if (adminBackdrop) adminBackdrop.hidden = true;
    doc.body.classList.remove('drawer-open');
    doc.querySelector('[data-admin-drawer]')?.setAttribute('aria-expanded', 'false');
  }

  /* Compatibility entry: every legacy toast call now becomes a top capsule. */
  function showToast(message, tone = 'info', options) {
    return window.CloudtraceNotifications?.notify(message, tone, options) || null;
  }

  function progressNotice(message, options) {
    const api = window.CloudtraceNotifications;
    if (api) return api.progress(message, options);
    return { update() {}, finish(text, tone) { showToast(text, tone); }, fail(text) { showToast(text, 'error'); }, cancel() {} };
  }

  const appSystemDialog = doc.querySelector('[data-app-system-dialog]');
  let pendingSystemDialog = null;
  const settleSystemDialog = (value) => {
    if (!pendingSystemDialog) return;
    const resolve = pendingSystemDialog.resolve;
    pendingSystemDialog = null;
    closeDialog(appSystemDialog);
    resolve(value);
  };
  const requestSystemDialog = ({ mode = 'confirm', title, message, value = '', inputLabel = '请输入内容' }) => {
    if (!appSystemDialog) return Promise.resolve(mode === 'prompt' ? null : false);
    if (pendingSystemDialog) settleSystemDialog(pendingSystemDialog.cancelValue);
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
        cancelValue: isPrompt ? null : false
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

  doc.addEventListener('click', (event) => {
    const target = event.target.closest('button, a');
    if (!target) return;
    if (target.matches('[data-mobile-drawer]')) openMobileDrawer(target);
    if (target.matches('[data-close-mobile-drawer]')) closeMobileDrawer();
    if (target.matches('[data-admin-drawer]')) openAdminDrawer(target);
    if (target.matches('[data-open-dialog]')) {
      const dialog = doc.getElementById(target.dataset.openDialog);
      if (dialog) { lastTrigger = target; openDialog(dialog); }
    }
    if (target.matches('[data-close-dialog]')) closeDialog(target.closest('dialog'));
  });

  mobileBackdrop?.addEventListener('click', closeMobileDrawer);
  adminBackdrop?.addEventListener('click', closeAdminDrawer);

  pageModule('component-gallery', (scope, signal) => {
  const initialFontStyle = root.dataset.fontStyle;
    scope.querySelectorAll('[data-demo-toast]').forEach((button) => button.addEventListener('click', () => {
      if (button.dataset.demoTone === 'progress') {
        const task = progressNotice(button.dataset.demoToast || '正在处理…');
        window.setTimeout(() => task.update('仍在处理，请稍候…'), 1400);
        window.setTimeout(() => task.finish(button.dataset.demoResult || '处理完成。', button.dataset.demoResultTone || 'success'), 2900);
        return;
      }
      showToast(button.dataset.demoToast, button.dataset.demoTone || 'info');
    }));

    scope.querySelectorAll('[data-demo-form]').forEach((form) => form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      showToast('表单验证通过', 'success');
    }));

    scope.querySelectorAll('[data-component-motion]').forEach((button) => button.addEventListener('click', () => {
      const stage = scope.querySelector('[data-component-motion-stage]');
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

    scope.querySelectorAll('[data-component-segment]').forEach((button) => button.addEventListener('click', () => {
      button.parentElement?.querySelectorAll('[data-component-segment]').forEach((item) => {
        item.classList.toggle('is-active', item === button);
        item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
      });
      const labels = { all: '全部', published: '已发布', draft: '草稿' };
      const copy = button.closest('.component-preview-panel')?.querySelector('[data-component-segment-copy]');
      if (copy) copy.textContent = `当前显示：${labels[button.dataset.componentSegment] || '全部'}`;
    }));

    scope.querySelectorAll('[data-component-font]').forEach((card) => {
      const activate = () => {
        root.dataset.fontStyle = card.dataset.componentFont;
        scope.querySelectorAll('[data-component-font]').forEach((item) => {
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

    scope.querySelectorAll('[data-component-action]').forEach((button) => button.addEventListener('click', () => {
      showToast(`${button.dataset.componentAction}已触发`, button.classList.contains('button--danger') ? 'warning' : 'success');
    }));
    scope.querySelectorAll('[data-component-icon]').forEach((button) => button.addEventListener('click', () => {
      showToast(`${button.dataset.componentIcon}图标按钮已触发`, 'info');
    }));
    scope.querySelectorAll('[data-component-loading]').forEach((button) => button.addEventListener('click', () => {
      if (button.getAttribute('aria-busy') === 'true') return;
      button.setAttribute('aria-busy', 'true');
      button.querySelector('span').textContent = '处理中';
      window.setTimeout(() => {
        button.setAttribute('aria-busy', 'false');
        button.querySelector('span').textContent = '体验加载';
        showToast('加载状态演示完成', 'success');
      }, motionIsReduced() ? 300 : 1200);
    }));

    scope.querySelectorAll('[data-component-capsule]').forEach((nav) => nav.addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      nav.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
    }));
    scope.querySelectorAll('[data-component-admin-parent]').forEach((button) => button.addEventListener('click', () => {
      const parent = button.parentElement;
      parent?.querySelectorAll('[data-component-admin-parent]').forEach((item) => {
        const active = item === button && !item.classList.contains('is-open');
        item.classList.toggle('is-open', active);
        const indicator = item.querySelector(':scope > span:first-child > i');
        if (indicator) indicator.textContent = active ? '⌃' : '⌄';
      });
    }));

    scope.querySelectorAll('[data-component-accent]').forEach((input) => input.addEventListener('input', () => {
      input.closest('.component-showcase')?.style.setProperty('--component-accent', input.value);
      showToast(`预览强调色：${input.value.toUpperCase()}`, 'info');
    }));

    scope.querySelectorAll('[data-component-media-select]').forEach((button) => {
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
    scope.querySelectorAll('[data-component-size-options]').forEach((group) => group.addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      group.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
    }));
    scope.querySelectorAll('[data-component-crop-scale]').forEach((input) => input.addEventListener('input', () => {
      const canvas = input.closest('.component-crop-preview')?.querySelector('[data-component-crop-canvas]');
      canvas?.style.setProperty('--crop-scale', String(1 + Number(input.value) / 180));
    }));
    scope.querySelectorAll('[data-component-ratios]').forEach((group) => group.addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      group.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
      const canvas = group.closest('.component-crop-preview')?.querySelector('[data-component-crop-canvas]');
      if (canvas) canvas.style.aspectRatio = button.dataset.ratio;
    }));

    const componentEditor = scope.querySelector('[data-component-editor-content]');
    const updateComponentEditorCount = () => {
      const count = componentEditor?.innerText.replace(/\s/g, '').length || 0;
      const counter = scope.querySelector('[data-component-editor-count]');
      if (counter) counter.textContent = `${count} 字 · 预计阅读 ${Math.max(1, Math.ceil(count / 400))} 分钟`;
    };
    componentEditor?.addEventListener('input', updateComponentEditorCount);
    updateComponentEditorCount();
    scope.querySelectorAll('[data-component-command]').forEach((button) => button.addEventListener('click', () => {
      componentEditor?.focus();
      document.execCommand(button.dataset.componentCommand, false, button.dataset.commandValue || null);
      updateComponentEditorCount();
    }));
    scope.querySelectorAll('[data-component-editor-modes]').forEach((group) => group.addEventListener('click', (event) => {
      const button = event.target.closest('[data-editor-mode]');
      if (!button || !componentEditor) return;
      group.querySelectorAll('[data-editor-mode]').forEach((item) => item.classList.toggle('is-active', item === button));
      const sourceMode = button.dataset.editorMode === 'source';
      componentEditor.classList.toggle('is-source-mode', sourceMode);
      componentEditor.contentEditable = String(!sourceMode);
      const status = scope.querySelector('[data-component-editor-status]');
      if (status) status.textContent = sourceMode ? '源码模式仅用于结构预览' : '可直接编辑预览内容';
    }));
  return () => { if (root.dataset.fontStyle !== initialFontStyle) root.dataset.fontStyle = initialFontStyle; };
  });

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

  pageModule('update-center', (scope, signal) => {
    const updateCenter = scope.querySelector('[data-update-center]');
    if (updateCenter) {
      const updateForms = [...updateCenter.querySelectorAll('[data-update-action]')];
      const updateProgress = updateCenter.querySelector('[data-update-progress]');
      const progressTrack = updateProgress?.parentElement;
      let updatePollTimer = 0;
      let updateFailures = 0;
      signal.addEventListener('abort', () => window.clearTimeout(updatePollTimer));

      const renderUpdateState = (state) => {
        if (!state) return;
        const busy = ['checking', 'downloading', 'queued', 'installing', 'rolling_back'].includes(state.status);
        updateCenter.dataset.updateStatus = state.status || 'idle';
        updateCenter.querySelector('[data-update-state]').textContent = state.message || '等待操作';
        updateCenter.querySelector('[data-update-message]').textContent = state.message || '等待操作';
        updateCenter.querySelector('[data-update-time]').textContent = state.updated_at || '等待操作';
        updateCenter.querySelector('[data-update-current]').textContent = `v${state.current_version}`;
        updateCenter.querySelector('[data-update-latest]').textContent = `v${state.latest_version}`;
        updateCenter.querySelector('[data-update-free]').textContent = state.disk?.free_label || '—';
        updateCenter.querySelector('[data-update-rollback]').textContent = state.can_rollback ? '可以回退' : '暂无备份';
        const percent = Math.max(0, Math.min(100, Number(state.progress) || 0));
        updateProgress?.style.setProperty('--update-progress', `${percent}%`);
        progressTrack?.setAttribute('aria-valuenow', String(percent));
        const notes = updateCenter.querySelector('[data-update-notes]');
        if (notes) {
          const value = state.release?.notes || '';
          notes.hidden = !value;
          notes.querySelector('p').textContent = value;
        }
        const events = updateCenter.querySelector('[data-update-events]');
        if (events) {
          events.replaceChildren(...(state.events || []).slice().reverse().map((item) => {
            const row = doc.createElement('li');
            const marker = doc.createElement('i');
            const body = doc.createElement('div');
            const message = doc.createElement('strong');
            const time = doc.createElement('small');
            message.textContent = item.message;
            time.textContent = item.at;
            body.append(message, time);
            row.append(marker, body);
            return row;
          }));
        }
        updateForms.forEach((form) => {
          const action = form.dataset.updateAction;
          const button = form.querySelector('button');
          button.disabled = busy
            || (action === 'download' && !state.available)
            || (action === 'install' && !state.can_install)
            || (action === 'rollback' && !state.can_rollback);
          button.classList.toggle('button--loading', busy && (
            action === state.status || (state.status === 'queued' && ['install', 'rollback'].includes(action))
          ));
        });
        if (busy) scheduleUpdatePoll(700);
      };

      const pollUpdateState = async () => {
        window.clearTimeout(updatePollTimer);
        try {
          const response = await fetch(updateCenter.dataset.statusUrl, {
            headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            cache: 'no-store'
          });
          if (!response.ok) throw new Error('暂时无法读取更新状态');
          const payload = await response.json();
          updateFailures = 0;
          renderUpdateState(payload.data);
          if (['queued', 'installing', 'rolling_back'].includes(payload.data.status)) scheduleUpdatePoll(900);
        } catch (_) {
          updateFailures += 1;
          if (updateFailures < 45) scheduleUpdatePoll(Math.min(5000, 800 + updateFailures * 180));
        }
      };
      function scheduleUpdatePoll(delay) {
        window.clearTimeout(updatePollTimer);
        if (signal.aborted) return;
        updatePollTimer = window.setTimeout(pollUpdateState, delay);
      }

      updateForms.forEach((form) => form.addEventListener('submit', async (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        const button = event.submitter || form.querySelector('button');
        if (button.disabled) return;
        if (form.dataset.confirm && !await themedConfirm(form.dataset.confirm)) return;
        button.disabled = true;
        button.classList.add('button--loading');
        const task = progressNotice(`正在${(button.textContent || '处理').trim()}…`);
        try {
          const response = await fetch(form.action, {
            method: 'POST',
            headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: new FormData(form)
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok || !payload.ok) throw new Error(payload.message || payload.data?.message || '更新操作未能开始');
          renderUpdateState(payload.data);
          task.finish(payload.data.message || '更新任务已经开始。', 'success');
          scheduleUpdatePoll(500);
        } catch (error) {
          button.disabled = false;
          button.classList.remove('button--loading');
          task.fail(error.message || '更新操作未能开始');
        }
      }));
      scheduleUpdatePoll(250);
    }
  });

  pageModule('admin-forms', (scope, signal) => {
    scope.querySelectorAll('form[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
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

    scope.querySelectorAll('[data-moderation-edit-toggle]').forEach((button) => {
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

    scope.querySelectorAll('form[data-card-delete]').forEach((form) => form.addEventListener('submit', (event) => {
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
  });

  doc.addEventListener('keydown', (event) => {
    if (mobileDrawer?.classList.contains('is-open')) trapFocus(event, mobileDrawer);
    if (adminSidebar?.classList.contains('is-open')) trapFocus(event, adminSidebar);
    if (event.key !== 'Escape') return;
    if (mobileDrawer?.classList.contains('is-open')) closeMobileDrawer();
    if (adminSidebar?.classList.contains('is-open')) closeAdminDrawer();
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 860 && mobileDrawerState !== 'closed') closeMobileDrawer();
    syncAdminDrawerAccessibility();
  }, { passive: true });
  adminDrawerMedia.addEventListener?.('change', syncAdminDrawerAccessibility);
  syncAdminDrawerAccessibility();

  doc.addEventListener('visibilitychange', () => root.classList.toggle('page-hidden', doc.hidden));

  pageModule('open-on-load-dialogs', (scope, signal) => {
    scope.querySelectorAll('dialog[data-open-on-load]').forEach((dialog) => {
      window.requestAnimationFrame(() => openDialog(dialog));
    });
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
    window.addEventListener('cloudtrace:navigated', () => {
      const group = adminMenuGroups.find((item) => item.querySelector('.is-current'));
      if (group && !group.classList.contains('is-open')) setAdminMenuGroup(group, false);
    });
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

  pageModule('media-preview-size', (scope, signal) => {
    const mediaGrid = scope.querySelector('[data-media-grid]');
    const mediaSizeButtons = scope.querySelectorAll('[data-media-preview-size]');
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
  });

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
  const pageReadyEvent = 'cloudtrace:page-ready';
  const signalPageReady = () => {
    root.classList.remove('is-page-entering', 'is-editor-transition');
    root.dataset.pageReady = 'true';
    window.dispatchEvent(new CustomEvent(pageReadyEvent));
  };
  if (root.classList.contains('is-page-entering')) {
    const readyRatio = {
      stretch: 1.18,
      fade: .62,
      'zoom-blur': .85,
      none: 0
    }[currentTransitionStyle()] ?? .62;
    window.setTimeout(
      signalPageReady,
      Math.max(220, Math.round(configuredTransitionDuration() * readyRatio))
    );
  } else {
    requestAnimationFrame(() => requestAnimationFrame(signalPageReady));
  }
  window.addEventListener('pageshow', (event) => {
    root.classList.remove('is-page-leaving');
    if (event.persisted) requestAnimationFrame(signalPageReady);
  });

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
  pageModule('appearance-settings', (scope, signal) => {
  const appearanceForm = scope.querySelector('[data-font-settings],[data-hint-settings],[data-transition-settings],[data-component-motion-settings],[data-dialog-appearance-settings],.appearance-color-field');
  const rootStyleSnapshot = appearanceForm ? root.getAttribute('style') : null;
  const rootDataSnapshot = appearanceForm ? { ...root.dataset } : null;
  const compactSnapshot = appearanceForm ? doc.querySelector('.admin-shell')?.classList.contains('admin-menu--compact') : null;
    const fontSettings = scope.querySelector('[data-font-settings]');
    fontSettings?.querySelectorAll('input[name="font_style"]').forEach((input) => {
      input.addEventListener('change', () => {
        if (!input.checked) return;
        root.dataset.fontStyle = input.value;
        replayThemePreview(fontSettings);
        replayThemePreview(input.closest('.font-choice'), 'is-choice-switching');
      });
    });
    const hintSettings = scope.querySelector('[data-hint-settings]');
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

    const transitionDurationInput = scope.querySelector('[data-transition-duration-input]');
    const transitionDurationRange = scope.querySelector('[data-transition-duration-range]');
    const transitionDurationOutput = scope.querySelector('[data-transition-duration-output]');
    const transitionSettings = scope.querySelector('[data-transition-settings]');
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
    const componentMotionSettings = scope.querySelector('[data-component-motion-settings]');
    const componentMotionDurationInput = scope.querySelector('[data-component-motion-duration-input]');
    const componentMotionDurationRange = scope.querySelector('[data-component-motion-duration-range]');
    const componentMotionDurationOutput = scope.querySelector('[data-component-motion-duration-output]');
    const announceComponentMotionChange = () => {
      window.dispatchEvent(new CustomEvent('cloudtrace:component-motion-settings'));
    };
    const syncComponentMotionDuration = (value) => {
      const duration = Math.max(520, Math.min(1100, Number.parseInt(value, 10) || 760));
      if (componentMotionDurationInput) componentMotionDurationInput.value = String(duration);
      if (componentMotionDurationRange) componentMotionDurationRange.value = String(duration);
      if (componentMotionDurationOutput) componentMotionDurationOutput.textContent = `${duration} ms`;
      root.dataset.componentMotionDuration = String(duration);
      announceComponentMotionChange();
    };
    componentMotionDurationInput?.addEventListener('input', (event) => syncComponentMotionDuration(event.target.value));
    componentMotionDurationRange?.addEventListener('input', (event) => syncComponentMotionDuration(event.target.value));
    componentMotionSettings?.querySelectorAll('input[name="component_motion_style"]').forEach((input) => {
      input.addEventListener('change', () => {
        if (!input.checked) return;
        root.dataset.componentMotionStyle = input.value;
        announceComponentMotionChange();
      });
    });
    componentMotionSettings?.querySelectorAll('input[name="component_motion_softness"]').forEach((input) => {
      input.addEventListener('change', () => {
        if (!input.checked) return;
        root.dataset.componentMotionSoftness = input.value;
        announceComponentMotionChange();
      });
    });
    const appearanceColorVariables = {
      transition_color_start: '--route-color-start',
      transition_color_middle: '--route-color-middle',
      transition_color_end: '--route-color-end',
      dialog_accent: '--dialog-accent',
      component_motion_color: '--component-motion-color',
      toast_background: '--toast-background',
      toast_text: '--toast-text',
      toast_accent: '--toast-accent',
      toast_success: '--toast-success',
      toast_warning: '--toast-warning',
      toast_error: '--toast-error'
    };
    scope.querySelectorAll('.appearance-color-field input[type="color"]').forEach((input) => {
      const syncAppearanceColor = () => {
        const variable = appearanceColorVariables[input.name];
        if (variable) root.style.setProperty(variable, input.value);
        if (input.name === 'component_motion_color') root.dataset.componentMotionColor = input.value;
        const output = input.closest('.appearance-color-field')?.querySelector('[data-color-value]');
        if (output) output.textContent = input.value.toUpperCase();
        replayThemePreview(input.closest('.appearance-color-field'), 'is-choice-switching');
        replayThemePreview(input.closest('.appearance-color-card'));
        if (input.name.startsWith('component_motion_')) announceComponentMotionChange();
      };
      input.addEventListener('input', syncAppearanceColor);
    });
    const dialogMetricConfig = {
      radius: { minimum: 14, maximum: 42, fallback: 22, variable: '--dialog-radius', unit: 'px' },
      width: { minimum: 360, maximum: 720, fallback: 510, variable: '--dialog-width', unit: 'px' },
      blur: { minimum: 0, maximum: 30, fallback: 6, variable: '--dialog-backdrop-blur', unit: 'px' },
      'toast-radius': { minimum: 12, maximum: 32, fallback: 28, variable: '--toast-radius', unit: 'px' },
      'toast-duration': { minimum: 2000, maximum: 12000, fallback: 5200, variable: null, dataset: 'toastDuration', unit: 'ms' }
    };
    const syncDialogMetric = (name, rawValue) => {
      const config = dialogMetricConfig[name];
      if (!config) return;
      const parsed = Number.parseInt(rawValue, 10);
      const value = Math.max(
        config.minimum,
        Math.min(config.maximum, Number.isFinite(parsed) ? parsed : config.fallback)
      );
      scope.querySelectorAll(`[data-dialog-range="${name}"], [data-dialog-value="${name}"]`).forEach((control) => {
        control.value = String(value);
      });
      const output = scope.querySelector(`[data-dialog-output="${name}"]`);
      if (output) output.textContent = `${value} ${config.unit}`;
      if (config.variable) root.style.setProperty(config.variable, `${value}${config.unit}`);
      if (config.dataset) root.dataset[config.dataset] = String(value);
      replayThemePreview(scope.querySelector(`[data-dialog-range="${name}"]`)?.closest('.dialog-metric-control'), 'is-choice-switching');
    };
    scope.querySelectorAll('[data-dialog-value]').forEach((input) => {
      syncDialogMetric(input.dataset.dialogValue, input.value);
      input.addEventListener('input', () => syncDialogMetric(input.dataset.dialogValue, input.value));
    });
    scope.querySelectorAll('[data-dialog-range]').forEach((input) => {
      input.addEventListener('input', () => syncDialogMetric(input.dataset.dialogRange, input.value));
    });
    scope.querySelectorAll('input[name="dialog_shadow"]').forEach((input) => {
      input.addEventListener('change', () => {
        if (!input.checked) return;
        root.dataset.dialogShadow = input.value;
        replayThemePreview(input.closest('.dialog-shadow-fieldset'));
      });
    });
    const noticeEditor = scope.querySelector('[data-notice-motion-editor]');
    if (noticeEditor) {
      let presets = {};
      try { presets = JSON.parse(noticeEditor.dataset.noticePresets || '{}'); } catch (_) { presets = {}; }
      const noticeFields = [...noticeEditor.querySelectorAll('[data-notice-field]')];
      const noticeApi = () => window.CloudtraceNotifications;
      const draftMotion = () => {
        const config = { types: {}, stack: 0 };
        noticeFields.forEach((input) => {
          const [kind, name] = input.dataset.noticeField.split('.');
          const value = Number.parseInt(input.value, 10);
          if (kind === 'stack') config.stack = value;
          else (config.types[kind] ||= {})[name] = value;
        });
        return config;
      };
      const syncPresetButtons = () => {
        const draft = draftMotion();
        noticeEditor.querySelectorAll('[data-notice-preset]').forEach((button) => {
          const preset = presets[button.dataset.noticePreset];
          const matches = preset && draft.stack === preset.stack && Object.values(draft.types).every((values) => (
            ['enter', 'exit', 'text_out', 'text_in'].every((name) => values[name] === preset[name])
          ));
          button.classList.toggle('is-active', Boolean(matches));
          button.setAttribute('aria-pressed', String(Boolean(matches)));
        });
      };
      noticeEditor.querySelectorAll('[data-notice-preset]').forEach((button) => button.addEventListener('click', () => {
        const preset = presets[button.dataset.noticePreset];
        if (!preset) return;
        noticeFields.forEach((input) => {
          const [kind, name] = input.dataset.noticeField.split('.');
          input.value = String(kind === 'stack' ? preset.stack : preset[name]);
        });
        const form = noticeEditor.closest('form');
        if (form) form.dataset.dirty = 'true';
        syncPresetButtons();
        replayThemePreview(noticeEditor);
      }));
      noticeEditor.addEventListener('input', syncPresetButtons);
      syncPresetButtons();

      // Preview notices use the unsaved draft and are withdrawn with the page.
      const previewTimers = new Set();
      const later = (callback, delay) => {
        const timer = window.setTimeout(() => { previewTimers.delete(timer); callback(); }, delay);
        previewTimers.add(timer);
      };
      signal.addEventListener('abort', () => previewTimers.forEach((timer) => window.clearTimeout(timer)));
      const previewOptions = (extra = {}) => ({ previewConfig: draftMotion(), signal, ...extra });
      const previews = {
        success: () => noticeApi()?.notify('设置已保存。', 'success', previewOptions()),
        info: () => noticeApi()?.notify('有 3 条新评论等待查看。', 'info', previewOptions()),
        warning: () => noticeApi()?.notify('封面图片较大，保存可能需要一点时间。', 'warning', previewOptions()),
        error: () => noticeApi()?.notify('保存失败，请稍后重试。', 'error', previewOptions()),
        long: () => noticeApi()?.notify('这是一条较长的提醒：发布前请确认标题、摘要和封面都已经填写，长网址 https://example.com/a/very/long/path/that/should/wrap/without/overflow?from=preview 也会正常换行。', 'warning', previewOptions()),
        action: () => noticeApi()?.notify('草稿已自动保存。', 'info', previewOptions({
          action: { label: '撤销', run: () => noticeApi()?.notify('已撤销刚才的保存。', 'success', previewOptions()) }
        })),
        stack: () => {
          [['第一条：评论已通过', 'success'], ['第二条：新留言', 'info'], ['第三条：图片较大', 'warning'], ['第四条：同步失败', 'error']]
            .forEach(([text, tone], index) => later(() => noticeApi()?.notify(text, tone, previewOptions()), index * 140));
        },
        clear: () => noticeApi()?.dismissAll(),
        'progress-success': () => {
          const task = noticeApi()?.progress('正在保存设置…', previewOptions());
          later(() => task?.update('仍在处理，请稍候…'), 1300);
          later(() => task?.finish('设置已保存。', 'success'), 2700);
        },
        'progress-error': () => {
          const task = noticeApi()?.progress('正在发布文章…', previewOptions());
          later(() => task?.fail('发布失败：网络连接中断。'), 2200);
        }
      };
      noticeEditor.querySelectorAll('[data-notice-preview]').forEach((button) => button.addEventListener('click', () => {
        previews[button.dataset.noticePreview]?.();
      }));
    }
    scope.querySelectorAll('[data-dialog-preview]').forEach((button) => {
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
  // Unsaved live previews must not leak into the next page of the shell.
  return () => {
    if (!appearanceForm) return;
    if (rootStyleSnapshot === null) root.removeAttribute('style');
    else root.setAttribute('style', rootStyleSnapshot);
    const runtimeKeys = new Set(['pageReady', 'motion', 'performance']);
    Object.entries(rootDataSnapshot).forEach(([key, value]) => {
      if (!runtimeKeys.has(key) && root.dataset[key] !== value) root.dataset[key] = value;
    });
    doc.querySelector('.admin-shell')?.classList.toggle('admin-menu--compact', Boolean(compactSnapshot));
  };
  });

  doc.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target === '_blank' || link.hasAttribute('download') || link.dataset.noTransition !== undefined) return;
    if (link.closest('[contenteditable="true"]')) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || !['http:', 'https:'].includes(target.protocol)) return;
    if (target.pathname === window.location.pathname && target.search === window.location.search && target.hash) return;
    const navigation = window.CloudtracePage;
    if (navigation?.shouldHandle(target, link)) {
      event.preventDefault();
      navigation.navigate(target.href, { mode: target.href === window.location.href ? 'replace' : 'push' });
      return;
    }
    const leaveNatively = () => {
      const delay = beginPageLeave(target);
      if (delay) window.setTimeout(() => window.location.assign(target.href), delay);
      else window.location.assign(target.href);
    };
    if (navigation?.hasUnsavedChanges()) {
      event.preventDefault();
      navigation.confirmLeave().then((approved) => { if (approved) leaveNatively(); });
      return;
    }
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
    const navigation = window.CloudtracePage;
    if ((form.getAttribute('method') || 'get').toLowerCase() === 'get' && navigation) {
      let data;
      try { data = new FormData(form, event.submitter || null); } catch (_) { data = new FormData(form); }
      target.search = new URLSearchParams([...data].filter(([, value]) => typeof value === 'string')).toString();
      if (navigation.shouldHandle(target, form)) {
        event.preventDefault();
        navigation.navigate(target.href, { mode: target.href === window.location.href ? 'replace' : 'push' });
        return;
      }
    }
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
  const releaseTimers = new Map();
  const releaseControl = (cancelled = false) => {
    if (!pressedControl) return;
    const control = pressedControl;
    control.classList.remove('is-pressed');
    if (!cancelled && !motionIsReduced()) {
      window.clearTimeout(releaseTimers.get(control));
      control.classList.add('is-releasing');
      releaseTimers.set(control, window.setTimeout(() => {
        control.classList.remove('is-releasing');
        releaseTimers.delete(control);
      }, 280));
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
  doc.addEventListener('keydown', (event) => {
    if (event.repeat || event.defaultPrevented || !['Enter', ' '].includes(event.key)) return;
    const control = event.target.closest('button,summary,[role="button"],a[href]');
    if (!control || control.matches(':disabled,[aria-disabled="true"]') || (event.key === ' ' && control.matches('a'))) return;
    releaseControl(true);
    pressedControl = control;
    control.classList.add('is-pressed');
  });
  doc.addEventListener('keyup', (event) => {
    if (['Enter', ' '].includes(event.key) && pressedControl && pressedPointer === null) releaseControl(false);
  });

  const revealItems = [...doc.querySelectorAll('[data-reveal]')].filter((item) => !item.classList.contains('card'));
  const cardItems = [...doc.querySelectorAll('.card')];
  const homeShellItems = [...new Set([
    ...doc.querySelectorAll('[data-motion-shell]'),
    ...revealItems.filter((item) => item.matches('.home-module,.home-duo'))
  ])];
  const motionSurfaceSelector = '[data-motion-surface],.card,.dashboard-widget,.admin-post-row';
  const motionControlSelector = '[data-motion-control],.button,.icon-button';
  const motionCandidateSelector = `${motionSurfaceSelector},${motionControlSelector},[data-motion-heading],[data-reveal]`;
  const isSurfaceMotionCandidate = (target) => {
    if (!(target instanceof Element) || target.matches('[data-motion-shell]')) return false;
    // The live motion preview opts back in: its settings form is skipped so the
    // rest of that surface stays still, but the preview card itself must draw.
    if (!target.matches('[data-motion-preview-card]') && target.closest('[data-motion-skip]')) return false;
    if (target.matches('[data-motion-surface]')) {
      return !target.parentElement?.closest('[data-motion-surface]');
    }
    if (!target.matches('.card,.dashboard-widget,.admin-post-row')) return false;
    if (target.parentElement?.closest('[data-motion-surface]')) return false;
    return !target.querySelector(motionSurfaceSelector);
  };
  const nearestMotionSurface = (target) => {
    let candidate = target.parentElement?.closest(motionSurfaceSelector) || null;
    while (candidate && !isSurfaceMotionCandidate(candidate)) {
      candidate = candidate.parentElement?.closest(motionSurfaceSelector) || null;
    }
    return candidate;
  };
  const isMotionCandidate = (target) => {
    if (!(target instanceof Element) || target.matches('dialog,[aria-hidden="true"]')) return false;
    if (target.matches('[data-motion-preview-card]')) return true;
    if (target.closest('[data-motion-skip]')) return false;
    if (target.matches('[data-motion-heading]')) return true;
    if (target.matches(motionControlSelector)) {
      return !target.matches('input') && !nearestMotionSurface(target);
    }
    return isSurfaceMotionCandidate(target);
  };
  const svgNamespace = 'http://www.w3.org/2000/svg';
  const createMotionOutline = () => {
    const outline = doc.createElementNS(svgNamespace, 'svg');
    outline.classList.add('motion-outline');
    outline.setAttribute('aria-hidden', 'true');
    outline.setAttribute('focusable', 'false');
    outline.setAttribute('viewBox', '0 0 100 100');
    outline.setAttribute('preserveAspectRatio', 'none');
    const path = doc.createElementNS(svgNamespace, 'path');
    path.classList.add('motion-outline__path');
    // Dash lengths and the outline share the same local coordinate system.
    // A non-scaling stroke breaks that contract during ancestor transforms.
    outline.append(path);
    return outline;
  };
  const parseMotionRadius = (value, width, height) => {
    const raw = String(value).trim().split(/\s+/);
    const parts = [raw[0], raw[1] || raw[0]].map((part, axis) => (
      Number.parseFloat(part) * (part?.endsWith('%') ? [width, height][axis] / 100 : 1)
    ));
    const x = Number.isFinite(parts[0]) ? parts[0] : 0;
    const y = Number.isFinite(parts[1]) ? parts[1] : x;
    return { x, y };
  };
  const getMotionRadii = (target, width, height, inset) => {
    const styles = getComputedStyle(target);
    const corners = {
      topLeft: parseMotionRadius(styles.borderTopLeftRadius, width, height),
      topRight: parseMotionRadius(styles.borderTopRightRadius, width, height),
      bottomRight: parseMotionRadius(styles.borderBottomRightRadius, width, height),
      bottomLeft: parseMotionRadius(styles.borderBottomLeftRadius, width, height)
    };
    const innerWidth = Math.max(0, width - inset * 2);
    const innerHeight = Math.max(0, height - inset * 2);
    const ratios = [
      innerWidth / Math.max(1, corners.topLeft.x + corners.topRight.x),
      innerWidth / Math.max(1, corners.bottomLeft.x + corners.bottomRight.x),
      innerHeight / Math.max(1, corners.topLeft.y + corners.bottomLeft.y),
      innerHeight / Math.max(1, corners.topRight.y + corners.bottomRight.y)
    ];
    const scale = Math.min(1, ...ratios);
    Object.values(corners).forEach((corner) => {
      corner.x = Math.max(0, corner.x * scale - inset);
      corner.y = Math.max(0, corner.y * scale - inset);
    });
    return corners;
  };
  const getRenderedPathLength = (path) => path.getTotalLength();
  const configureMotionOutline = (target) => {
    const outline = target.querySelector(':scope > .motion-outline');
    if (!outline) return false;
    // SVG client dimensions are untransformed CSS pixels, including subtrees
    // scaled by the page entry, hover or press animation.
    const width = outline.clientWidth || target.clientWidth;
    const height = outline.clientHeight || target.clientHeight;
    if (width < 2 || height < 2) {
      target.classList.remove('is-outline-ready');
      return false;
    }
    const center = width / 2;
    const inset = .7;
    const radius = getMotionRadii(target, width, height, inset);
    const geometryKey = `${width}:${height}:${JSON.stringify(radius)}`;
    if (outline.dataset.motionGeometryKey === geometryKey) {
      target.classList.add('is-outline-ready');
      return true;
    }
    outline.dataset.motionGeometryKey = geometryKey;
    const point = (value) => Number(value.toFixed(3));
    outline.setAttribute('viewBox', `0 0 ${point(width)} ${point(height)}`);
    const path = outline.querySelector('.motion-outline__path');
    path.setAttribute('d', [
      `M ${point(center)} ${inset}`,
      `H ${point(width - inset - radius.topRight.x)}`,
      `A ${point(radius.topRight.x)} ${point(radius.topRight.y)} 0 0 1 ${point(width - inset)} ${point(inset + radius.topRight.y)}`,
      `V ${point(height - inset - radius.bottomRight.y)}`,
      `A ${point(radius.bottomRight.x)} ${point(radius.bottomRight.y)} 0 0 1 ${point(width - inset - radius.bottomRight.x)} ${point(height - inset)}`,
      `H ${point(inset + radius.bottomLeft.x)}`,
      `A ${point(radius.bottomLeft.x)} ${point(radius.bottomLeft.y)} 0 0 1 ${inset} ${point(height - inset - radius.bottomLeft.y)}`,
      `V ${point(inset + radius.topLeft.y)}`,
      `A ${point(radius.topLeft.x)} ${point(radius.topLeft.y)} 0 0 1 ${point(inset + radius.topLeft.x)} ${inset}`,
      `H ${point(center)} Z`
    ].join(' '));
    const length = getRenderedPathLength(path);
    const pathsReady = Number.isFinite(length) && length > 0;
    path.dataset.motionPathLength = String(length);
    path.style.setProperty('--motion-path-length', String(length));
    path.style.strokeDasharray = `${length} ${length}`;
    target.classList.toggle('is-outline-ready', pathsReady);
    return pathsReady;
  };
  const motionTargetRegistry = new Set();
  const motionTimelines = new WeakMap();
  const motionChildControls = new WeakMap();
  const motionContentFragments = new WeakMap();
  const motionSurfaceSnapFrames = new WeakMap();
  const pendingMotionStates = new Map();
  const componentMotionDuration = () => Math.max(
    520,
    Math.min(1100, Number.parseInt(root.dataset.componentMotionDuration, 10) || 760)
  );
  const componentMotionBlur = () => {
    return { none: 0, light: 1.5, soft: 3 }[root.dataset.componentMotionSoftness] ?? 3;
  };
  const motionProfileFor = (kind) => {
    const duration = componentMotionDuration();
    const profiles = {
      feature: { duration, blur: Math.min(2, componentMotionBlur()), surfaceScale: .982 },
      compact: { duration: Math.max(400, Math.round(duration * .66)), blur: Math.min(1.5, componentMotionBlur()), surfaceScale: .986 },
      control: { duration: Math.max(360, Math.round(duration * .5)), blur: Math.min(2, componentMotionBlur()), surfaceScale: .968 },
      heading: { duration: Math.max(300, Math.round(duration * .45)), blur: Math.min(2, componentMotionBlur()), surfaceScale: .992 }
    };
    return profiles[kind] || profiles.compact;
  };
  const motionSlotLimits = { surface: 8, light: 12 };
  const motionQueueTimers = new Map();
  const activeMotionCounts = { surface: 0, light: 0 };
  let motionObserver = null;
  const motionObservers = new Map();
  const motionRoots = new WeakMap();
  let motionMutation = null;
  let motionPreferenceObserver = null;
  let motionResizeFrame = 0;
  const pendingMotionTargets = new Set();
  let motionDisposed = false;
  let motionResizeObserver = null;
  let motionObservationStarted = false;
  let skipScrollReveal = false;
  let observeMotionTarget = () => {};
  const ensureMotionLayers = (target) => {
    const outlines = [...target.querySelectorAll(':scope > .motion-outline')];
    outlines.slice(1).forEach((outline) => outline.remove());
    const outline = outlines[0] || createMotionOutline();
    if (!outlines[0]) target.prepend(outline);
    const surfaces = [...target.querySelectorAll(':scope > .motion-surface-layer')];
    surfaces.slice(1).forEach((surface) => surface.remove());
    const surface = surfaces[0] || doc.createElement('span');
    if (!surfaces[0]) {
      surface.className = 'motion-surface-layer';
      surface.setAttribute('aria-hidden', 'true');
      target.prepend(surface);
    }
    return { outline, surface };
  };
  const snapshotMotionSurface = (target) => {
    const surface = target.querySelector(':scope > .motion-surface-layer');
    if (!surface || target.classList.contains('motion-surface-owned')) return;
    const styles = getComputedStyle(target);
    surface.style.backgroundColor = styles.backgroundColor;
    surface.style.backgroundImage = styles.backgroundImage;
    surface.style.backgroundPosition = styles.backgroundPosition;
    surface.style.backgroundSize = styles.backgroundSize;
    surface.style.backgroundRepeat = styles.backgroundRepeat;
    surface.style.backgroundOrigin = styles.backgroundOrigin;
    surface.style.backgroundClip = styles.backgroundClip;
    surface.style.boxShadow = styles.boxShadow;
    surface.style.backdropFilter = styles.backdropFilter;
    surface.style.webkitBackdropFilter = styles.webkitBackdropFilter;
    if (!target.style.getPropertyValue('--motion-static-border')) {
      target.style.setProperty('--motion-static-border', styles.borderTopColor);
    }
  };
  const setMotionSurfaceOwned = (target, owned) => {
    if (owned) snapshotMotionSurface(target);
    target.classList.toggle('motion-surface-owned', owned);
  };
  const snapMotionSurface = (target) => {
    cancelAnimationFrame(motionSurfaceSnapFrames.get(target) || 0);
    target.classList.add('motion-surface-snap');
    motionSurfaceSnapFrames.set(target, requestAnimationFrame(() => {
      target.classList.remove('motion-surface-snap');
      motionSurfaceSnapFrames.delete(target);
    }));
  };
  const wrapMotionControlLabel = (control) => {
    let label = control.querySelector(':scope > .motion-control-label');
    if (label || control.matches('input')) return label;
    label = doc.createElement('span');
    label.className = 'motion-control-label';
    [...control.childNodes]
      .filter((node) => !(node instanceof Element) || !node.matches('.motion-outline,.motion-surface-layer'))
      .forEach((node) => label.append(node));
    control.append(label);
    return label;
  };
  const prepareMotionControl = (control, child = false) => {
    wrapMotionControlLabel(control);
    ensureMotionLayers(control);
    control.classList.add(child ? 'motion-child-control' : 'motion-control-target');
    snapshotMotionSurface(control);
    configureMotionOutline(control);
    setMotionSurfaceOwned(control, true);
    if (child) motionResizeObserver?.observe(control);
    return control;
  };
  const controlsOwnedBy = (target) => {
    if (target.dataset.motionControls === 'none') return [];
    return [...target.querySelectorAll(motionControlSelector)].filter((control) => (
      !control.matches('input') && nearestMotionSurface(control) === target
    ));
  };
  const collectMotionContent = (target, controls) => {
    target.querySelectorAll('.motion-content').forEach((item) => item.classList.remove('motion-content'));
    const fragments = new Set();
    const containsOwnedControl = (element) => controls.some((control) => element.contains(control));
    const visit = (element) => {
      if (!(element instanceof Element)) return;
      if (element.matches('.motion-outline,.motion-surface-layer') || controls.includes(element)) return;
      if (element.matches(motionSurfaceSelector) && element !== target) return;
      if (!containsOwnedControl(element)) {
        fragments.add(element);
        return;
      }
      [...element.children].forEach(visit);
    };
    [...target.children].forEach(visit);
    fragments.forEach((fragment) => fragment.classList.add('motion-content'));
    motionContentFragments.set(target, [...fragments]);
    return [...fragments];
  };
  const refreshMotionChildren = (target) => {
    if (!isSurfaceMotionCandidate(target)) return [];
    const nextControls = controlsOwnedBy(target);
    (motionChildControls.get(target) || []).filter((control) => !nextControls.includes(control))
      .forEach((control) => motionResizeObserver?.unobserve(control));
    const controls = nextControls.map((control) => prepareMotionControl(control, true));
    motionChildControls.set(target, controls);
    collectMotionContent(target, controls);
    return controls;
  };
  const configureMotionGeometry = (target) => {
    if (target.dataset.motionKind === 'heading') return true;
    const ready = configureMotionOutline(target);
    (motionChildControls.get(target) || []).forEach(configureMotionOutline);
    return ready;
  };
  const registerMotionTarget = (target) => {
    if (!isMotionCandidate(target) || motionTargetRegistry.has(target)) return false;
    target.dataset.motionState = 'idle';
    target.dataset.motionKind = (
      target.matches('[data-motion-heading]')
        ? 'heading'
        : target.matches(motionControlSelector)
        ? 'control'
        : target.dataset.motionSurface || 'compact'
    );
    const isHeading = target.dataset.motionKind === 'heading';
    target.classList.add(isHeading ? 'motion-heading-target' : 'motion-line-target');
    if (!isHeading) {
      target.dataset.motionOutline = 'true';
      target.querySelectorAll(':scope > .motion-line').forEach((line) => line.remove());
      ensureMotionLayers(target);
      if (target.dataset.motionKind === 'control') {
        prepareMotionControl(target);
        motionContentFragments.set(target, []);
        motionChildControls.set(target, []);
      } else {
        snapshotMotionSurface(target);
        refreshMotionChildren(target);
        setMotionSurfaceOwned(target, true);
      }
      configureMotionGeometry(target);
    }
    motionTargetRegistry.add(target);
    if (!isHeading) motionResizeObserver?.observe(target);
    if (motionObservationStarted) {
      if (skipScrollReveal) {
        settleMotionState(target, true);
      } else {
        observeMotionTarget(target);
      }
    }
    return true;
  };
  homeShellItems.forEach((item) => { item.dataset.motionShell = 'true'; });
  const motionAnimationDisabled = (target = null) => (
    motionIsReduced() ||
    root.dataset.performance === 'low' ||
    target?.dataset.motionPreviewReduced === 'true' ||
    !Element.prototype.animate
  );
  const springSampleCache = new Map();
  const springParameters = {
    line: { mass: 1, stiffness: 32, damping: 10 },
    surface: { mass: 1, stiffness: 22, damping: 8.5 },
    control: { mass: 1, stiffness: 30, damping: 10 },
    text: { mass: 1, stiffness: 26, damping: 9.5 }
  };
  const springPresetScale = {
    calm: { stiffness: .78, damping: 1.1 },
    soft: { stiffness: 1, damping: 1 },
    snappy: { stiffness: 1.24, damping: 1.06 }
  };
  const currentSpringPreset = () => (
    ['calm', 'soft', 'snappy'].includes(root.dataset.componentMotionStyle)
      ? root.dataset.componentMotionStyle
      : 'soft'
  );
  const springSamples = (role) => {
    const preset = currentSpringPreset();
    const cacheKey = `${preset}:${role}`;
    if (springSampleCache.has(cacheKey)) return springSampleCache.get(cacheKey);
    const base = springParameters[role] || springParameters.surface;
    const scale = springPresetScale[preset];
    const stiffness = base.stiffness * scale.stiffness;
    const damping = base.damping * scale.damping;
    const step = 1 / 120;
    const raw = [{ time: 0, value: 0 }];
    let position = 0;
    let velocity = 0;
    for (let index = 1; index <= 120; index += 1) {
      const acceleration = (stiffness * (1 - position) - damping * velocity) / base.mass;
      velocity += acceleration * step;
      position += velocity * step;
      position = Math.max(raw[raw.length - 1].value, Math.min(1, position));
      raw.push({ time: index / 120, value: position });
    }
    const finalValue = Math.max(.0001, raw[raw.length - 1].value);
    const samples = Array.from({ length: 25 }, (_item, index) => {
      const source = raw[index * 5];
      return {
        time: index / 24,
        value: index === 24 ? 1 : Math.max(0, Math.min(1, source.value / finalValue))
      };
    });
    springSampleCache.set(cacheKey, samples);
    return samples;
  };
  const springValue = (role, progress) => {
    const bounded = Math.max(0, Math.min(1, progress));
    const samples = springSamples(role);
    const scaled = bounded * (samples.length - 1);
    const lower = Math.floor(scaled);
    const upper = Math.min(samples.length - 1, lower + 1);
    const blend = scaled - lower;
    return samples[lower].value + (samples[upper].value - samples[lower].value) * blend;
  };
  const cardSurfaceProgress = (progress, _middle = .4, end = .78) => (
    springValue('surface', Math.min(1, Math.max(0, progress / end)))
  );
  const localMotionProgress = (progress, start, end, role) => {
    if (progress <= start) return 0;
    if (progress >= end) return 1;
    return springValue(role, (progress - start) / (end - start));
  };
  const motionTimelineOffsets = [...new Set([
    ...Array.from({ length: 26 }, (_item, index) => index / 25),
    .04, .06, .08, .4, .78, .82, .86, 1
  ])].sort((left, right) => left - right);
  const motionFrames = (factory) => motionTimelineOffsets.map((offset) => ({
    ...factory(offset),
    offset
  }));
  const scaledValue = (start, progress) => start + (1 - start) * progress;
  const createMotionTimeline = (target, initialProgress) => {
    const profile = motionProfileFor(target.dataset.motionKind);
    const options = {
      duration: profile.duration,
      easing: 'linear',
      fill: 'both'
    };
    const animations = [];
    target.dataset.motionDuration = String(profile.duration);
    if (target.dataset.motionKind === 'heading') {
      animations.push(target.animate(motionFrames((progress) => {
        const value = springValue('text', progress);
        return {
          opacity: value,
          filter: `blur(${(profile.blur * (1 - value)).toFixed(3)}px)`,
          transform: `scale(${scaledValue(profile.surfaceScale, value).toFixed(5)})`
        };
      }), options));
    } else {
      setMotionSurfaceOwned(target, true);
      const standaloneControl = target.dataset.motionKind === 'control';
      const controls = standaloneControl ? [] : (motionChildControls.get(target) || []);
      // One interruptible timeline, overlapping layers instead of an empty
      // card waiting for three serial phases. Child controls share its clock.
      const phases = { lineEnd: .82, surfaceMiddle: .4, surfaceEnd: .78, textStart: .06, textEnd: .86 };
      const path = target.querySelector(':scope > .motion-outline > .motion-outline__path');
      const outline = target.querySelector(':scope > .motion-outline');
      const surface = target.querySelector(':scope > .motion-surface-layer');
      const pathLength = Number.parseFloat(path?.dataset.motionPathLength) || 260;
      if (path) {
        animations.push(path.animate(motionFrames((progress) => {
          const value = localMotionProgress(progress, 0, phases.lineEnd, standaloneControl ? 'control' : 'line');
          return { strokeDashoffset: pathLength * (1 - value) };
        }), options));
      }
      if (outline) {
        animations.push(outline.animate(motionFrames((progress) => {
          const value = localMotionProgress(progress, 0, phases.lineEnd, standaloneControl ? 'control' : 'line');
          return {
            opacity: .18 + value * .82,
            filter: `blur(${(.7 * (1 - value)).toFixed(3)}px)`,
            transform: `scale(${scaledValue(standaloneControl ? .975 : .988, value).toFixed(5)})`
          };
        }), options));
      }
      if (surface) {
        animations.push(surface.animate(motionFrames((progress) => {
          const value = standaloneControl
            ? localMotionProgress(progress, 0, phases.surfaceEnd, 'control')
            : cardSurfaceProgress(progress, phases.surfaceMiddle, phases.surfaceEnd);
          return {
            opacity: value,
            filter: `blur(${(Math.min(.7, profile.blur) * (1 - value)).toFixed(3)}px)`,
            transform: `scale(${scaledValue(profile.surfaceScale, value).toFixed(5)})`
          };
        }), options));
      }
      if (standaloneControl) {
        const label = target.querySelector(':scope > .motion-control-label');
        if (label) {
          animations.push(label.animate(motionFrames((progress) => {
            const value = localMotionProgress(progress, phases.textStart, phases.textEnd, 'text');
            return {
              opacity: value,
              filter: `blur(${(profile.blur * (1 - value)).toFixed(3)}px)`,
              transform: `scale(${scaledValue(.988, value).toFixed(5)})`
            };
          }), options));
        }
      } else {
        (motionContentFragments.get(target) || []).forEach((content) => {
          const mediaBlur = content.matches('img,picture,video') || content.querySelector('img,picture,video')
            ? Math.min(1, profile.blur)
            : profile.blur;
          animations.push(content.animate(motionFrames((progress) => {
            const value = localMotionProgress(progress, phases.textStart, phases.textEnd, 'text');
            return {
              opacity: value,
              filter: `blur(${(mediaBlur * (1 - value)).toFixed(3)}px)`,
              transform: `scale(${scaledValue(.992, value).toFixed(5)})`
            };
          }), options));
        });
        controls.forEach((control) => {
          setMotionSurfaceOwned(control, true);
          const controlPath = control.querySelector(':scope > .motion-outline > .motion-outline__path');
          const controlOutline = control.querySelector(':scope > .motion-outline');
          const controlSurface = control.querySelector(':scope > .motion-surface-layer');
          const controlLabel = control.querySelector(':scope > .motion-control-label');
          const controlLength = Number.parseFloat(controlPath?.dataset.motionPathLength) || 120;
          if (controlPath) {
            animations.push(controlPath.animate(motionFrames((progress) => {
              const value = localMotionProgress(progress, .04, .82, 'control');
              return { strokeDashoffset: controlLength * (1 - value) };
            }), options));
          }
          if (controlOutline) {
            animations.push(controlOutline.animate(motionFrames((progress) => {
              const value = localMotionProgress(progress, .04, .82, 'control');
              return {
                opacity: value,
                filter: `blur(${(.55 * (1 - value)).toFixed(3)}px)`,
                transform: `scale(${scaledValue(.975, value).toFixed(5)})`
              };
            }), options));
          }
          if (controlSurface) {
            animations.push(controlSurface.animate(motionFrames((progress) => {
              const value = localMotionProgress(progress, .04, phases.surfaceEnd, 'surface');
              return {
                opacity: value,
                filter: `blur(${(Math.min(2, profile.blur) * (1 - value)).toFixed(3)}px)`,
                transform: `scale(${scaledValue(.968, value).toFixed(5)})`
              };
            }), options));
          }
          if (controlLabel) {
            animations.push(controlLabel.animate(motionFrames((progress) => {
              const value = localMotionProgress(progress, phases.textStart, phases.textEnd, 'text');
              return {
                opacity: value,
                filter: `blur(${(Math.min(3, profile.blur) * (1 - value)).toFixed(3)}px)`,
                transform: `scale(${scaledValue(.992, value).toFixed(5)})`
              };
            }), options));
          }
        });
      }
    }
    const currentTime = initialProgress * profile.duration;
    animations.forEach((animation) => {
      animation.pause();
      animation.currentTime = currentTime;
    });
    const timeline = { animations, duration: profile.duration, token: 0 };
    motionTimelines.set(target, timeline);
    return timeline;
  };
  const motionSlotBucket = (target) => (
    ['control', 'heading'].includes(target.dataset.motionKind) ? 'light' : 'surface'
  );
  const motionSlotAvailable = (target) => {
    const bucket = motionSlotBucket(target);
    return activeMotionCounts[bucket] < motionSlotLimits[bucket];
  };
  const flushMotionQueue = () => {
    let advanced = true;
    while (advanced && pendingMotionStates.size) {
      advanced = false;
      const next = [...pendingMotionStates.entries()].find(([target]) => motionSlotAvailable(target));
      if (!next) break;
      const [target, revealed] = next;
      pendingMotionStates.delete(target);
      window.clearTimeout(motionQueueTimers.get(target));
      motionQueueTimers.delete(target);
      if (!target.isConnected) continue;
      runMotionState(target, revealed);
      advanced = true;
    }
  };
  const releaseMotionSlot = (target) => {
    const bucket = target.dataset.motionSlot;
    if (!['surface', 'light'].includes(bucket)) return;
    delete target.dataset.motionSlot;
    activeMotionCounts[bucket] = Math.max(0, activeMotionCounts[bucket] - 1);
    queueMicrotask(flushMotionQueue);
  };
  const settleMotionState = (target, revealed) => {
    window.clearTimeout(motionQueueTimers.get(target));
    motionQueueTimers.delete(target);
    target.classList.toggle('is-revealed', revealed);
    target.dataset.motionState = revealed ? 'settled' : 'idle';
    if (revealed) target.dataset.motionVisited = 'true';
    target.classList.remove('is-motion-active');
    if (target.dataset.motionKind !== 'heading') {
      if (revealed) snapMotionSurface(target);
      setMotionSurfaceOwned(target, !revealed);
      (motionChildControls.get(target) || []).forEach((control) => {
        if (revealed) snapMotionSurface(control);
        setMotionSurfaceOwned(control, !revealed);
      });
    }
    const timeline = motionTimelines.get(target);
    if (timeline) {
      timeline.animations.forEach((animation) => animation.cancel());
      motionTimelines.delete(target);
    }
    releaseMotionSlot(target);
    if (target.dataset.motionResizePending === 'true') {
      delete target.dataset.motionResizePending;
      configureMotionGeometry(target);
    }
  };
  const runMotionState = (target, revealed) => {
    const state = target.dataset.motionState;
    if (target.dataset.motionKind !== 'heading' && !motionTimelines.has(target) && !configureMotionGeometry(target)) {
      settleMotionState(target, revealed);
      return;
    }
    if (!target.dataset.motionSlot) {
      const bucket = motionSlotBucket(target);
      target.dataset.motionSlot = bucket;
      activeMotionCounts[bucket] += 1;
    }
    const timeline = motionTimelines.get(target) || createMotionTimeline(
      target,
      state === 'settled' || state === 'reversing' ? 1 : 0
    );
    const token = ++timeline.token;
    target.classList.toggle('is-revealed', revealed);
    target.dataset.motionState = revealed ? 'drawing' : 'reversing';
    target.classList.add('is-motion-active');
    const reentryRate = revealed && target.dataset.motionVisited === 'true' ? 1 / .82 : 1;
    const playbackRate = revealed ? reentryRate : -1 / .72;
    timeline.animations.forEach((animation) => {
      animation.playbackRate = playbackRate;
      animation.play();
    });
    const anchor = timeline.animations[0];
    if (!anchor) {
      settleMotionState(target, revealed);
      return;
    }
    anchor.finished.then(() => {
      if (timeline.token !== token) return;
      settleMotionState(target, revealed);
    }).catch(() => {
      // Reversing an in-flight Web Animation replaces its finished promise.
    });
  };
  const setMotionState = (target, revealed, immediate = false) => {
    if (motionDisposed || !target.isConnected) return;
    const state = target.dataset.motionState;
    if (revealed && (state === 'drawing' || state === 'settled')) return;
    if (!revealed && (state === 'reversing' || state === 'idle')) {
      pendingMotionStates.delete(target);
      return;
    }
    if (immediate || motionAnimationDisabled(target)) {
      pendingMotionStates.delete(target);
      settleMotionState(target, revealed);
      return;
    }
    if (target.dataset.motionSlot || motionSlotAvailable(target)) {
      pendingMotionStates.delete(target);
      runMotionState(target, revealed);
      return;
    }
    pendingMotionStates.set(target, revealed);
    // Dense first screens never queue invisible content for whole animations.
    // Overflow starts after at most 90ms, using the same lighter local layers.
    if (!motionQueueTimers.has(target)) {
      motionQueueTimers.set(target, window.setTimeout(() => {
        motionQueueTimers.delete(target);
        if (!pendingMotionStates.has(target) || !target.isConnected || motionDisposed) return;
        const nextState = pendingMotionStates.get(target);
        pendingMotionStates.delete(target);
        runMotionState(target, nextState);
      }, 90));
    }
  };
  if ('ResizeObserver' in window) {
    motionResizeObserver = new ResizeObserver((entries) => {
      entries.forEach((entry) => pendingMotionTargets.add(
        motionTargetRegistry.has(entry.target) ? entry.target : nearestMotionSurface(entry.target)
      ));
      if (motionResizeFrame) return;
      motionResizeFrame = requestAnimationFrame(() => {
        pendingMotionTargets.forEach((target) => {
          if (!target || !target.isConnected) return;
          if (target.classList.contains('is-motion-active')) {
            target.dataset.motionResizePending = 'true';
          } else if (target.dataset.motionKind !== 'heading') {
            configureMotionGeometry(target);
          }
        });
        pendingMotionTargets.clear();
        motionResizeFrame = 0;
      });
    });
  }
  const discoverMotionTargets = (node) => {
    if (!(node instanceof Element)) return [];
    return [
      ...(node.matches(motionCandidateSelector) ? [node] : []),
      ...node.querySelectorAll(motionCandidateSelector)
    ].filter(isMotionCandidate);
  };
  const initialMotionTargets = [...doc.querySelectorAll(motionCandidateSelector)].filter(isMotionCandidate);
  initialMotionTargets.forEach(registerMotionTarget);
  window.clearTimeout(window.__cloudtraceMotionFallback);
  root.classList.remove('motion-preparing');
  skipScrollReveal = motionIsReduced() || root.dataset.performance === 'low' || !('IntersectionObserver' in window);
  if (doc.body) {
    revealItems.forEach((item) => item.style.setProperty('--reveal-order', item.dataset.revealOrder || '0'));
    const cardOrderGroups = new Map();
    cardItems.forEach((card) => {
      const parent = card.parentElement || doc.body;
      const order = cardOrderGroups.get(parent) || 0;
      card.style.setProperty('--reveal-order', card.dataset.revealOrder || String(order));
      cardOrderGroups.set(parent, order + 1);
    });
    root.classList.add('is-motion-ready');
    revealItems.filter((item) => !motionTargetRegistry.has(item)).forEach((item) => item.classList.add('is-revealed'));
    cardItems.filter((item) => !motionTargetRegistry.has(item)).forEach((item) => item.classList.add('is-revealed'));
    if (skipScrollReveal) {
      revealItems.forEach((item) => item.classList.add('is-revealed'));
      motionTargetRegistry.forEach((target) => setMotionState(target, true, true));
      motionObservationStarted = true;
    }
    if ('IntersectionObserver' in window) {
      // Layout shells stay stable. Explicit surfaces and controls own their
      // outlines, including nested controls and cards inserted after load.
      homeShellItems.forEach((item) => item.classList.add('is-revealed'));
      const previousMotionTops = new WeakMap();
      const visibleMotionRatio = (entry) => {
        const bounds = entry.rootBounds || { top: 0, bottom: window.innerHeight, height: window.innerHeight };
        const visibleStart = Math.max(entry.boundingClientRect.top, bounds.top);
        const visibleEnd = Math.min(entry.boundingClientRect.bottom, bounds.bottom);
        const visibleHeight = Math.max(0, visibleEnd - visibleStart);
        return visibleHeight / Math.max(1, Math.min(entry.boundingClientRect.height, bounds.height));
      };
      const handleMotionIntersections = (entries) => {
        entries.forEach((entry) => {
          const target = entry.target;
          if (motionAnimationDisabled(target) || target.contains(doc.activeElement)) {
            setMotionState(target, true, true);
            return;
          }
          const previousTop = previousMotionTops.get(target);
          const motionScrollDirection = previousTop === undefined || entry.boundingClientRect.top <= previousTop ? 'down' : 'up';
          previousMotionTops.set(target, entry.boundingClientRect.top);
          const ratio = visibleMotionRatio(entry);
          target.dataset.motionVisibleRatio = ratio.toFixed(3);
          if (entry.isIntersecting && ratio >= .16) {
            if (target.dataset.motionPreviewLock === 'reverse') return;
            setMotionState(target, true);
            return;
          }
          if (!entry.isIntersecting) {
            // A jump, anchor navigation, or restored scroll position can move
            // many cards offscreen in one frame. Settle those immediately so
            // invisible reversals never occupy the visible motion slots.
            setMotionState(target, false, true);
            return;
          }
          if (target.dataset.motionPersist !== 'true' || !target.classList.contains('is-revealed')) return;
          const bounds = entry.rootBounds || { top: 0, bottom: window.innerHeight };
          const leavingAtTop = motionScrollDirection === 'down' && entry.boundingClientRect.top < bounds.top;
          const leavingAtBottom = motionScrollDirection === 'up' && entry.boundingClientRect.bottom > bounds.bottom;
          if (ratio <= .12 && (leavingAtTop || leavingAtBottom)) {
            setMotionState(target, false);
          }
        });
      };
      const motionRootFor = (target) => {
        let parent = target.parentElement;
        while (parent && parent !== doc.body) {
          const styles = getComputedStyle(parent);
          if (parent.hasAttribute('data-motion-scroll-root') || (
            /(auto|scroll)/.test(styles.overflowY) && parent.scrollHeight > parent.clientHeight + 2
          )) return parent;
          parent = parent.parentElement;
        }
        return null;
      };
      observeMotionTarget = (target) => {
        const scrollRoot = motionRootFor(target);
        let observer = motionObservers.get(scrollRoot);
        if (!observer) {
          motionObserver = new IntersectionObserver(handleMotionIntersections, {
            root: scrollRoot, rootMargin: '0px', threshold: [0, .08, .12, .16, .28, .5]
          });
          observer = motionObserver;
          motionObservers.set(scrollRoot, observer);
        }
        motionRoots.get(target)?.unobserve(target);
        motionRoots.set(target, observer);
        target.dataset.motionPersist = 'true';
        target.dataset.scrollReveal = 'motion';
        observer.observe(target);
      };
      const startMotionObservation = () => {
        if (motionDisposed) return;
        motionObservationStarted = true;
        motionTargetRegistry.forEach(observeMotionTarget);
      };
      if (root.dataset.pageReady === 'true') startMotionObservation();
      else window.addEventListener(pageReadyEvent, startMotionObservation, { once: true });
    }
    const unregisterMotionTarget = (target) => {
      motionRoots.get(target)?.unobserve(target);
      motionRoots.delete(target);
      motionResizeObserver?.unobserve(target);
      (motionChildControls.get(target) || []).forEach((control) => motionResizeObserver?.unobserve(control));
      pendingMotionStates.delete(target);
      window.clearTimeout(motionQueueTimers.get(target));
      motionQueueTimers.delete(target);
      settleMotionState(target, true);
      [target, ...(motionChildControls.get(target) || [])].forEach((item) => {
        cancelAnimationFrame(motionSurfaceSnapFrames.get(item) || 0);
        motionSurfaceSnapFrames.delete(item);
        item.classList.remove('motion-surface-snap');
      });
      releaseMotionSlot(target);
      motionTargetRegistry.delete(target);
      motionObservers.forEach((observer, scrollRoot) => {
        if (![...motionTargetRegistry].some((item) => motionRoots.get(item) === observer)) {
          observer.disconnect();
          motionObservers.delete(scrollRoot);
        }
      });
    };
    const refreshMotionOwner = (owner) => {
      const timeline = motionTimelines.get(owner);
      const state = owner.dataset.motionState;
      const progress = timeline ? Math.max(0, Math.min(1, Number(timeline.animations[0]?.currentTime || 0) / timeline.duration)) : 1;
      if (timeline) {
        timeline.token += 1;
        timeline.animations.forEach((animation) => animation.cancel());
        motionTimelines.delete(owner);
      }
      refreshMotionChildren(owner);
      configureMotionGeometry(owner);
      if (timeline && !motionAnimationDisabled(owner)) {
        createMotionTimeline(owner, progress);
        runMotionState(owner, state !== 'reversing');
      } else settleMotionState(owner, state !== 'idle');
    };
    motionMutation = new MutationObserver((mutations) => {
      const changedOwners = new Set();
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node instanceof Element && node.matches('.motion-outline,.motion-surface-layer,.motion-control-label')) return;
          discoverMotionTargets(node).forEach(registerMotionTarget);
          if (!(node instanceof Element)) return;
          const controls = [
            ...(node.matches(motionControlSelector) ? [node] : []),
            ...node.querySelectorAll(motionControlSelector)
          ];
          const owners = new Set(controls.map(nearestMotionSurface).filter((owner) => motionTargetRegistry.has(owner)));
          owners.forEach((owner) => changedOwners.add(owner));
        });
        mutation.removedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          [...motionTargetRegistry].forEach((target) => {
            if (!target.isConnected && (target === node || node.contains(target))) unregisterMotionTarget(target);
          });
          if (node.matches(motionControlSelector) || node.querySelector(motionControlSelector)) {
            const owner = mutation.target.closest(motionSurfaceSelector);
            if (motionTargetRegistry.has(owner)) changedOwners.add(owner);
          }
        });
      });
      changedOwners.forEach(refreshMotionOwner);
    });
    motionMutation.observe(doc.body, { childList: true, subtree: true });
    const updateMotionPreference = () => {
      if (motionDisposed) return;
      motionTargetRegistry.forEach((target) => {
        settleMotionState(target, true);
        observeMotionTarget(target);
      });
    };
    systemReducedMotion.addEventListener?.('change', updateMotionPreference);
    motionPreferenceObserver = new MutationObserver(updateMotionPreference);
    motionPreferenceObserver.observe(root, { attributes: true, attributeFilter: ['data-motion', 'data-performance'] });
    const disposeMotion = () => {
      releaseControl(true);
      releaseTimers.forEach((timer, control) => {
        window.clearTimeout(timer);
        control.classList.remove('is-releasing');
      });
      releaseTimers.clear();
      motionMutation?.disconnect();
      motionPreferenceObserver?.disconnect();
      motionObservers.forEach((observer) => observer.disconnect());
      motionObservers.clear();
      motionResizeObserver?.disconnect();
      cancelAnimationFrame(motionResizeFrame);
      pendingMotionTargets.clear();
      pendingMotionStates.clear();
      motionQueueTimers.forEach((timer) => window.clearTimeout(timer));
      motionQueueTimers.clear();
      window.clearTimeout(motionPreviewReverseTimer);
      [...motionTargetRegistry].forEach(unregisterMotionTarget);
      motionDisposed = true;
      systemReducedMotion.removeEventListener?.('change', updateMotionPreference);
    };
    const initMotion = (scope = doc.body) => {
      motionDisposed = false;
      systemReducedMotion.addEventListener?.('change', updateMotionPreference);
      discoverMotionTargets(scope).forEach(registerMotionTarget);
      motionTargetRegistry.forEach((target) => {
        if (!motionAnimationDisabled(target)) observeMotionTarget(target);
        else settleMotionState(target, true);
      });
      motionMutation?.observe(doc.body, { childList: true, subtree: true });
      motionPreferenceObserver?.observe(root, { attributes: true, attributeFilter: ['data-motion', 'data-performance'] });
    };
    /* A region swapped in by enhanced navigation gets the same bookkeeping the
       first document received, before the mutation observer sees it. */
    const prepareMotionScope = (scope) => {
      if (!(scope instanceof Element)) return;
      const scopeReveals = [...scope.querySelectorAll('[data-reveal]')].filter((item) => !item.classList.contains('card'));
      const scopeCards = [...scope.querySelectorAll('.card')];
      const scopeShells = new Set([
        ...scope.querySelectorAll('[data-motion-shell]'),
        ...scopeReveals.filter((item) => item.matches('.home-module,.home-duo'))
      ]);
      scopeShells.forEach((item) => { item.dataset.motionShell = 'true'; item.classList.add('is-revealed'); });
      scopeReveals.forEach((item) => item.style.setProperty('--reveal-order', item.dataset.revealOrder || '0'));
      const orders = new Map();
      scopeCards.forEach((card) => {
        const parent = card.parentElement || scope;
        const order = orders.get(parent) || 0;
        card.style.setProperty('--reveal-order', card.dataset.revealOrder || String(order));
        orders.set(parent, order + 1);
      });
      discoverMotionTargets(scope).forEach(registerMotionTarget);
      scopeReveals.filter((item) => !motionTargetRegistry.has(item)).forEach((item) => item.classList.add('is-revealed'));
      scopeCards.filter((item) => !motionTargetRegistry.has(item)).forEach((item) => item.classList.add('is-revealed'));
    };
    window.CloudtraceMotion = { init: initMotion, dispose: disposeMotion, refresh: refreshMotionOwner, prepare: prepareMotionScope };
    window.addEventListener('pagehide', disposeMotion);
    window.addEventListener('pageshow', (event) => { if (event.persisted) initMotion(); });
    doc.fonts?.ready.then(() => {
      if (motionDisposed) return;
      motionTargetRegistry.forEach((target) => {
        if (target.classList.contains('is-motion-active')) target.dataset.motionResizePending = 'true';
        else configureMotionGeometry(target);
      });
    });
  }

  let motionPreviewCard = doc.querySelector('[data-motion-preview-card]');
  let motionPreviewReverseTimer = 0;
  const clearMotionTimeline = (target) => {
    const timeline = motionTimelines.get(target);
    if (!timeline) return;
    timeline.animations.forEach((animation) => animation.cancel());
    motionTimelines.delete(target);
    target.classList.remove('is-motion-active');
    releaseMotionSlot(target);
  };
  const replayMotionPreview = () => {
    if (!motionPreviewCard) return;
    window.clearTimeout(motionPreviewReverseTimer);
    delete motionPreviewCard.dataset.motionPreviewLock;
    doc.querySelectorAll('[data-component-motion-stage]').forEach((button) => button.setAttribute('aria-pressed', 'false'));
    clearMotionTimeline(motionPreviewCard);
    settleMotionState(motionPreviewCard, false);
    requestAnimationFrame(() => requestAnimationFrame(() => setMotionState(motionPreviewCard, true)));
  };
  const setMotionPreviewProgress = (progress) => {
    if (!motionPreviewCard) return;
    const bounded = Math.max(0, Math.min(1, progress));
    window.clearTimeout(motionPreviewReverseTimer);
    clearMotionTimeline(motionPreviewCard);
    settleMotionState(motionPreviewCard, false);
    if (bounded >= 1) {
      settleMotionState(motionPreviewCard, true);
    } else {
      setMotionSurfaceOwned(motionPreviewCard, true);
      (motionChildControls.get(motionPreviewCard) || []).forEach((control) => setMotionSurfaceOwned(control, true));
      motionPreviewCard.dataset.motionState = 'drawing';
      motionPreviewCard.classList.add('is-motion-active');
      createMotionTimeline(motionPreviewCard, bounded);
    }
    doc.querySelectorAll('[data-component-motion-stage]').forEach((button) => {
      button.setAttribute('aria-pressed', String(Number(button.dataset.componentMotionStage) / 100 === bounded));
    });
  };
  window.addEventListener('cloudtrace:component-motion-settings', () => {
    motionTargetRegistry.forEach((target) => {
      if (!target.classList.contains('is-motion-active')) motionTimelines.delete(target);
    });
    replayMotionPreview();
  });
  pageModule('motion-preview', (scope, signal) => {
  motionPreviewCard = scope.querySelector('[data-motion-preview-card]') || (scope === doc ? motionPreviewCard : null);
    scope.querySelector('[data-component-motion-replay]')?.addEventListener('click', replayMotionPreview);
    scope.querySelectorAll('[data-component-motion-stage]').forEach((button) => {
      button.addEventListener('click', () => setMotionPreviewProgress(Number(button.dataset.componentMotionStage) / 100));
    });
    scope.querySelector('[data-component-motion-reverse]')?.addEventListener('click', () => {
      if (!motionPreviewCard) return;
      replayMotionPreview();
      motionPreviewReverseTimer = window.setTimeout(() => {
        motionPreviewCard.dataset.motionPreviewLock = 'reverse';
        setMotionState(motionPreviewCard, false);
      }, Math.round(componentMotionDuration() * .5));
    });
    scope.querySelector('[data-component-motion-reduced]')?.addEventListener('click', (event) => {
      if (!motionPreviewCard) return;
      const reduced = motionPreviewCard.dataset.motionPreviewReduced !== 'true';
      motionPreviewCard.dataset.motionPreviewReduced = String(reduced);
      event.currentTarget.setAttribute('aria-pressed', String(reduced));
      if (reduced) settleMotionState(motionPreviewCard, true);
      else replayMotionPreview();
    });
  return () => {
    window.clearTimeout(motionPreviewReverseTimer);
    motionPreviewCard = null;
  };
  });

  window.__cloudtraceMotionDebug = {
    setProgress: (target, progress) => {
      if (!motionTargetRegistry.has(target)) return false;
      clearMotionTimeline(target);
      settleMotionState(target, false);
      if (progress >= 1) settleMotionState(target, true);
      else {
        target.dataset.motionState = 'drawing';
        target.classList.add('is-motion-active');
        createMotionTimeline(target, Math.max(0, progress));
      }
      return true;
    },
    timelineFor: (target) => motionTimelines.get(target) || null,
    setVisible: (target, revealed) => setMotionState(target, revealed),
    state: () => ({
      registered: motionTargetRegistry.size, roots: motionObservers.size,
      pending: pendingMotionStates.size, queueTimers: motionQueueTimers.size,
      active: { ...activeMotionCounts }, disposed: motionDisposed
    })
  };

  pageModule('tilt-and-counters', (scope, signal) => {
    scope.querySelectorAll('[data-tilt]').forEach((card) => {
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

    const countItems = [...scope.querySelectorAll('[data-count]')];
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
      signal.addEventListener('abort', () => countObserver.disconnect());
    } else countItems.forEach(revealCount);
  });

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
    window.addEventListener('cloudtrace:navigated', resetCapsuleNavigation);
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

    const mobileIndicator = mobileCapsuleNavigation.querySelector('.mobile-nav-indicator');
    const mobileNavItems = [...mobileCapsuleNavigation.querySelectorAll('a,button')];
    const mobileCurrentItem = () => mobileCapsuleNavigation.querySelector('.is-current') || mobileNavItems[0];
    const moveMobileIndicator = (item) => {
      if (!mobileIndicator || !item) return;
      const lift = Number.parseFloat(
        getComputedStyle(mobileCapsuleNavigation).getPropertyValue('--mobile-nav-indicator-lift')
      ) || 1.5;
      mobileIndicator.style.width = `${item.offsetWidth}px`;
      mobileIndicator.style.height = `${item.offsetHeight}px`;
      const indicatorX = item.offsetLeft;
      const indicatorY = item.offsetTop - lift;
      mobileIndicator.style.transform = `translate3d(${indicatorX}px,${indicatorY}px,0)`;
    };
    const restoreMobileIndicator = () => moveMobileIndicator(mobileCurrentItem());
    requestAnimationFrame(restoreMobileIndicator);
    mobileNavItems.forEach((item) => {
      item.addEventListener('pointerenter', () => moveMobileIndicator(item), { passive: true });
      item.addEventListener('focus', () => moveMobileIndicator(item), { passive: true });
    });
    mobileCapsuleNavigation.addEventListener('pointerleave', restoreMobileIndicator, { passive: true });
    window.addEventListener('resize', restoreMobileIndicator, { passive: true });
    window.addEventListener('cloudtrace:navigated', () => {
      resetMobileCapsuleNavigation();
      requestAnimationFrame(restoreMobileIndicator);
    });
  }

  const navigationLinks = doc.querySelector('.site-nav__links');
  if (navigationLinks && !navigationLinks.classList.contains('site-nav__links--account')) {
    const indicator = doc.createElement('span');
    indicator.className = 'nav-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    navigationLinks.prepend(indicator);
    const currentLink = () => navigationLinks.querySelector('a.is-current');
    const moveIndicator = (link) => {
      indicator.style.opacity = link ? '' : '0';
      if (!link) return;
      const linkRect = link.getBoundingClientRect();
      indicator.style.width = `${linkRect.width}px`;
      indicator.style.height = `${linkRect.height}px`;
      indicator.style.transform = `translate3d(${link.offsetLeft}px,${link.offsetTop}px,0)`;
    };
    requestAnimationFrame(() => moveIndicator(currentLink()));
    navigationLinks.querySelectorAll('a').forEach((link) => link.addEventListener('pointerenter', () => moveIndicator(link), { passive: true }));
    navigationLinks.addEventListener('pointerleave', () => moveIndicator(currentLink()), { passive: true });
    window.addEventListener('resize', () => moveIndicator(currentLink()), { passive: true });
    window.addEventListener('cloudtrace:navigated', () => requestAnimationFrame(() => moveIndicator(currentLink())));
  }

  pageModule('local-time', (scope, signal) => {
    const localTime = scope.querySelector('[data-local-time]');
    if (localTime) {
      const updateLocalTime = () => {
        localTime.textContent = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date());
      };
      updateLocalTime();
      const localTimer = window.setInterval(updateLocalTime, 60_000);
      signal.addEventListener('abort', () => window.clearInterval(localTimer));
    }
  });

  pageModule('runtime-metrics', (scope, signal) => {
    const runtimeMetrics = scope.querySelector('[data-runtime-metrics]');
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

      const runtimeTimer = window.setInterval(refreshRuntimeMetrics, 2_000);
      signal.addEventListener('abort', () => window.clearInterval(runtimeTimer));
      doc.addEventListener('visibilitychange', () => {
        if (doc.visibilityState === 'visible') refreshRuntimeMetrics();
      }, { signal });
    }
  });

  pageModule('image-loading', (scope, signal) => {
    scope.querySelectorAll('img').forEach((image) => {
      image.decoding = 'async';
      if (image.complete) image.classList.add('is-loaded');
      else image.addEventListener('load', () => image.classList.add('is-loaded'), { once: true });
    });
  });

  pageModule('article-reading', (scope, signal) => {
    const readingProgress = scope.querySelector('[data-reading-progress]');
    const readingFills = scope.querySelectorAll('[data-reading-progress-fill]');
    const readingValue = scope.querySelector('[data-reading-progress-value]');
    const readingRemaining = scope.querySelector('[data-reading-progress-remaining]');
    const article = scope.querySelector('[data-article-content]');
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
      }, { passive: true, signal });
      window.addEventListener('resize', () => {
        measureReadingRange();
        requestReadingUpdate();
      }, { passive: true, signal });
      window.visualViewport?.addEventListener('resize', () => {
        measureReadingRange();
        requestReadingUpdate();
      }, { passive: true, signal });
      if ('ResizeObserver' in window) {
        const readingObserver = new ResizeObserver(() => {
          measureReadingRange();
          requestReadingUpdate();
        });
        readingObserver.observe(article);
        signal.addEventListener('abort', () => readingObserver.disconnect());
      }
      measureReadingRange();
      updateReadingProgress();
    }

    const lightbox = scope.querySelector('[data-image-lightbox]');
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
  });

  pageModule('editor-and-comments', (scope, signal) => {
    const editor = scope.querySelector('[data-content-editor-form]');
    if (editor?.dataset.autosaveUrl) {
      const status = scope.querySelector('[data-autosave-status]');
      let autosaveTimer;
      signal.addEventListener('abort', () => window.clearTimeout(autosaveTimer));
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

    const imageInput = scope.querySelector('[data-editor-image]');
    imageInput?.addEventListener('change', async () => {
      const file = imageInput.files?.[0];
      if (!file) return;
      const status = scope.querySelector('[data-upload-status]');
      const textarea = scope.querySelector('[name="content_markdown"]');
      const data = new FormData();
      data.append('image', file);
      status.textContent = '正在处理图片…';
      const task = progressNotice('正在上传并处理图片…');
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
        task.finish('图片已安全处理并插入正文。', 'success');
      } catch (error) { status.textContent = error.message; task.fail(error.message); }
      imageInput.value = '';
    });

    const commentForm = scope.querySelector('.comment-form');
    const parentInput = commentForm?.querySelector('[name="parent_id"]');
    const replyIndicator = commentForm?.querySelector('[data-reply-indicator]');
    scope.querySelectorAll('[data-reply-to]').forEach((button) => button.addEventListener('click', () => {
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

  pageModule('fallback-images', (scope, signal) => {
    scope.querySelectorAll('[data-fallback-image]').forEach((image) => {
      const container = image.closest('[data-fallback-media]');
      const fallback = () => {
        image.hidden = true;
        container?.classList.add('is-fallback');
      };
      image.addEventListener('error', fallback, { once: true });
      image.addEventListener('load', () => container?.classList.add('has-image'), { once: true });
      if (image.complete && image.naturalWidth === 0) fallback();
    });
  });

  window.CloudDiary = {
    showToast,
    notify: showToast,
    progress: progressNotice,
    openDialog,
    closeDialog,
    closeDrawers() {
      if (mobileDrawerState !== 'closed') closeMobileDrawer();
      if (adminSidebar?.classList.contains('is-open')) {
        const trigger = lastTrigger;
        lastTrigger = null;
        closeAdminDrawer();
        lastTrigger = trigger;
      }
    },
    confirm: themedConfirm,
    prompt: themedPrompt,
    alert: themedAlert
  };
})();
