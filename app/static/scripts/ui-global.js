(() => {
  const doc = document;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches || doc.documentElement.dataset.motion === 'reduce';

  // 每个主题下拉各有一个观察者；页面区域被替换后立即断开，避免继续持有已移除的节点。
  const selectObservers = new Map();
  const releaseDetachedSelects = () => {
    selectObservers.forEach((observer, select) => {
      if (select.isConnected) return;
      observer.disconnect();
      selectObservers.delete(select);
    });
  };

  function enhanceSelect(select) {
    if (select.multiple || select.dataset.nativeSelect !== undefined || select.dataset.themedSelectReady) return;
    select.dataset.themedSelectReady = 'true';
    const shell = doc.createElement('span');
    shell.className = 'themed-select';
    select.parentNode.insertBefore(shell, select);
    shell.appendChild(select);
    select.classList.add('themed-select__native');
    const trigger = doc.createElement('button');
    trigger.type = 'button';
    trigger.className = 'themed-select__trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const value = doc.createElement('span');
    const arrow = doc.createElement('i');
    arrow.setAttribute('aria-hidden', 'true');
    trigger.append(value, arrow);
    const menu = doc.createElement('span');
    menu.className = 'themed-select__menu';
    menu.setAttribute('role', 'listbox');
    menu.hidden = true;
    shell.append(trigger, menu);

    const close = (restore = false) => {
      if (!shell.classList.contains('is-open')) return;
      shell.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
      window.setTimeout(() => { menu.hidden = true; }, reduced() ? 0 : 150);
      if (restore) trigger.focus();
    };
    const sync = () => {
      const chosen = select.options[select.selectedIndex];
      value.textContent = chosen?.textContent || '请选择';
      menu.querySelectorAll('[role="option"]').forEach((option) => {
        const active = option.dataset.value === select.value;
        option.classList.toggle('is-selected', active);
        option.setAttribute('aria-selected', String(active));
      });
    };
    const render = () => {
      menu.replaceChildren();
      [...select.options].forEach((option) => {
        const item = doc.createElement('button');
        item.type = 'button';
        item.setAttribute('role', 'option');
        item.dataset.value = option.value;
        item.disabled = option.disabled;
        const itemLabel = doc.createElement('span');
        const itemMark = doc.createElement('i');
        itemLabel.textContent = option.textContent;
        itemMark.textContent = '✓';
        itemMark.setAttribute('aria-hidden', 'true');
        item.append(itemLabel, itemMark);
        item.addEventListener('click', () => {
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          sync(); close(true);
        });
        menu.appendChild(item);
      });
      sync();
    };
    trigger.addEventListener('click', () => {
      const opening = !shell.classList.contains('is-open');
      doc.querySelectorAll('.themed-select.is-open').forEach((item) => { if (item !== shell) item.querySelector('.themed-select__trigger')?.click(); });
      if (!opening) return close();
      render(); menu.hidden = false;
      requestAnimationFrame(() => { shell.classList.add('is-open'); trigger.setAttribute('aria-expanded', 'true'); });
    });
    trigger.addEventListener('keydown', (event) => {
      if (!['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return;
      event.preventDefault();
      if (!shell.classList.contains('is-open')) trigger.click();
      requestAnimationFrame(() => menu.querySelector('.is-selected:not(:disabled),[role="option"]:not(:disabled)')?.focus());
    });
    menu.addEventListener('keydown', (event) => {
      const options = [...menu.querySelectorAll('[role="option"]:not(:disabled)')];
      const index = options.indexOf(doc.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); close(true); }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        options[(index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length]?.focus();
      }
    });
    select.addEventListener('change', sync);
    const selectObserver = new MutationObserver(render);
    selectObserver.observe(select, { childList: true, subtree: true, attributes: true });
    selectObservers.set(select, selectObserver);
    render();
  }

  function markSaveActions(scope = doc) {
    scope.querySelectorAll('select').forEach(enhanceSelect);
    scope.querySelectorAll('input[type="file"][accept*="image"]').forEach((input) => {
      input.setAttribute('data-image-crop', '');
      const form = input.closest('form[enctype="multipart/form-data"]');
      if (form && !input.dataset.visualEditorImage) form.setAttribute('data-animated-upload', '');
    });
    scope.querySelectorAll('button[type="submit"],input[type="submit"],[data-save-action]').forEach((button) => {
      const label = (button.value || button.textContent || '').trim();
      if (button.dataset.saveAction !== undefined || /^(保存|更新|应用|确认修改)/.test(label)) button.classList.add('is-save-action');
    });
  }
  markSaveActions();
  new MutationObserver((records) => {
    records.forEach((record) => record.addedNodes.forEach((node) => {
      if (node.nodeType === 1) markSaveActions(node.matches?.('select,button,input') ? node.parentElement : node);
    }));
    if (records.some((record) => record.removedNodes.length)) releaseDetachedSelects();
  }).observe(doc.body, { childList: true, subtree: true });
  doc.addEventListener('click', (event) => {
    if (!event.target.closest('.themed-select')) doc.querySelectorAll('.themed-select.is-open .themed-select__trigger').forEach((button) => button.click());
  });

  // Forms inside the page region are mounted again after enhanced navigation.
  const initForms = (scope) => {
    markSaveActions(scope);
    const seoForm = scope.querySelector('[data-seo-form]');
    if (seoForm) {
      const updatePreview = () => {
        const title = seoForm.querySelector('[data-seo-title]')?.value || '';
        const description = seoForm.querySelector('[data-seo-description]')?.value || '';
        scope.querySelectorAll('[data-seo-preview-title],[data-seo-social-title]').forEach((item) => { item.textContent = title; });
        scope.querySelectorAll('[data-seo-preview-description],[data-seo-social-description]').forEach((item) => { item.textContent = description; });
      };
      seoForm.addEventListener('input', updatePreview); updatePreview();
    }

    scope.querySelectorAll('form[data-animated-upload]').forEach((form) => form.addEventListener('submit', (event) => {
      if (form.dataset.uploading === 'true' || !form.querySelector('input[type="file"]')?.files?.length) return;
      event.preventDefault(); form.dataset.uploading = 'true';
      const bar = form.querySelector('[data-upload-progress]');
      const fill = bar?.querySelector('i'); const label = bar?.querySelector('small');
      if (bar) bar.hidden = false;
      const task = window.CloudDiary?.progress?.('正在上传…');
      let reportedStep = 0;
      const xhr = new XMLHttpRequest();
      xhr.open((form.method || 'POST').toUpperCase(), form.action || location.href);
      xhr.upload.addEventListener('progress', (progress) => {
        const percent = progress.lengthComputable ? Math.round(progress.loaded / progress.total * 100) : 35;
        if (fill) fill.style.setProperty('--upload-progress', `${percent}%`);
        if (label) label.textContent = `正在上传 ${percent}%`;
        const step = Math.min(3, Math.floor(percent / 34));
        if (step > reportedStep) { reportedStep = step; task?.update(percent >= 100 ? '上传完成，正在处理…' : `正在上传 ${percent}%`); }
      });
      xhr.addEventListener('load', () => {
        if (fill) fill.style.setProperty('--upload-progress', '100%');
        if (label) label.textContent = '上传完成';
        form.classList.add('is-upload-complete');
        window.setTimeout(() => { location.assign(xhr.responseURL || location.href); }, reduced() ? 0 : 260);
      });
      xhr.addEventListener('error', () => {
        form.dataset.uploading = 'false';
        if (label) label.textContent = '上传失败，请重试';
        bar?.classList.add('is-error');
        task?.fail('网络中断，上传失败，请重试。');
      });
      xhr.send(new FormData(form));
    }));
  };
  if (window.CloudtracePage?.define) window.CloudtracePage.define('ui-global-forms', initForms);
  else initForms(doc);

  const cropDialog = doc.querySelector('[data-image-crop-dialog]');
  if (!cropDialog) return;
  const canvas = cropDialog.querySelector('[data-crop-canvas]');
  const ctx = canvas.getContext('2d');
  const zoomInput = cropDialog.querySelector('[data-crop-zoom]');
  let state = null;
  let resolver = null;
  let dragging = false;
  let lastPoint = null;

  function drawCrop() {
    if (!state?.image) return;
    const maxWidth = Math.min(760, Math.max(280, cropDialog.clientWidth - 48));
    const ratio = state.avatar ? 1 : (state.ratio === 'free' ? state.image.width / state.image.height : Number(state.ratio));
    canvas.width = Math.round(maxWidth);
    canvas.height = Math.round(Math.min(520, maxWidth / ratio));
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(canvas.width / 2 + state.x, canvas.height / 2 + state.y);
    ctx.rotate(state.rotation * Math.PI / 180);
    const turned = Math.abs(state.rotation % 180) === 90;
    const iw = turned ? state.image.height : state.image.width;
    const ih = turned ? state.image.width : state.image.height;
    const scale = Math.max(canvas.width / iw, canvas.height / ih) * state.zoom;
    ctx.drawImage(state.image, -state.image.width * scale / 2, -state.image.height * scale / 2, state.image.width * scale, state.image.height * scale);
    ctx.restore();
  }
  function finishCrop(result) {
    if (window.CloudDiary?.closeDialog) window.CloudDiary.closeDialog(cropDialog);
    else if (cropDialog.open) cropDialog.close();
    cropDialog.classList.remove('is-avatar-mode', 'is-logo-mode');
    cropDialog.querySelector('#image-crop-title').textContent = '调整图片';
    const done = resolver; resolver = null; state = null; done?.(result);
  }
  function editImage(file, mode = 'image') {
    return new Promise((resolve) => {
      const avatar = mode === 'avatar';
      const logo = mode === 'logo';
      const image = new Image();
      const objectUrl = URL.createObjectURL(file);
      image.onload = () => {
        URL.revokeObjectURL(objectUrl);
        state = { file, image, avatar, logo, ratio: avatar ? '1' : 'free', zoom: 1, rotation: 0, x: 0, y: 0 };
        resolver = resolve; zoomInput.value = '1';
        cropDialog.classList.toggle('is-avatar-mode', avatar);
        cropDialog.classList.toggle('is-logo-mode', logo);
        cropDialog.querySelector('#image-crop-title').textContent = avatar ? '调整头像' : (logo ? '调整网站Logo' : '调整图片');
        cropDialog.querySelector('[data-crop-zoom-value]').textContent = '100%';
        cropDialog.querySelectorAll('[data-crop-ratio]').forEach((button) => button.classList.toggle('is-active', button.dataset.cropRatio === (avatar ? '1' : 'free')));
        if (window.CloudDiary?.openDialog) window.CloudDiary.openDialog(cropDialog);
        else { cropDialog.showModal(); cropDialog.classList.add('is-present'); }
        requestAnimationFrame(drawCrop);
      };
      image.onerror = () => { URL.revokeObjectURL(objectUrl); resolve(file); };
      image.src = objectUrl;
    });
  }
  cropDialog.querySelectorAll('[data-crop-ratio]').forEach((button) => button.addEventListener('click', () => {
    if (state?.avatar) return;
    state.ratio = button.dataset.cropRatio;
    state.x = 0; state.y = 0;
    cropDialog.querySelectorAll('[data-crop-ratio]').forEach((item) => item.classList.toggle('is-active', item === button)); drawCrop();
  }));
  cropDialog.querySelectorAll('[data-crop-rotate]').forEach((button) => button.addEventListener('click', () => { state.rotation = (state.rotation + Number(button.dataset.cropRotate) + 360) % 360; state.x = 0; state.y = 0; drawCrop(); }));
  zoomInput.addEventListener('input', () => { state.zoom = Number(zoomInput.value); cropDialog.querySelector('[data-crop-zoom-value]').textContent = `${Math.round(state.zoom * 100)}%`; drawCrop(); });
  canvas.addEventListener('pointerdown', (event) => { dragging = true; lastPoint = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener('pointermove', (event) => { if (!dragging) return; state.x += event.clientX - lastPoint[0]; state.y += event.clientY - lastPoint[1]; lastPoint = [event.clientX, event.clientY]; drawCrop(); });
  canvas.addEventListener('pointerup', () => { dragging = false; });
  cropDialog.querySelector('[data-crop-cancel]').addEventListener('click', () => finishCrop(null));
  cropDialog.querySelector('[data-crop-skip]').addEventListener('click', () => finishCrop(state.file));
  cropDialog.querySelector('[data-crop-apply]').addEventListener('click', () => {
    const turned = Math.abs(state.rotation % 180) === 90;
    const orientedWidth = turned ? state.image.height : state.image.width;
    const orientedHeight = turned ? state.image.width : state.image.height;
    const ratio = canvas.width / canvas.height;
    const output = doc.createElement('canvas');
    if (ratio >= 1) {
      output.width = Math.max(1, Math.min(2400, orientedWidth));
      output.height = Math.max(1, Math.round(output.width / ratio));
    } else {
      output.height = Math.max(1, Math.min(2400, orientedHeight));
      output.width = Math.max(1, Math.round(output.height * ratio));
    }
    const outputContext = output.getContext('2d');
    const outputScale = output.width / canvas.width;
    const imageScale = Math.max(canvas.width / orientedWidth, canvas.height / orientedHeight) * state.zoom * outputScale;
    outputContext.translate(output.width / 2 + state.x * outputScale, output.height / 2 + state.y * outputScale);
    outputContext.rotate(state.rotation * Math.PI / 180);
    outputContext.drawImage(state.image, -state.image.width * imageScale / 2, -state.image.height * imageScale / 2, state.image.width * imageScale, state.image.height * imageScale);
    const outputType = state.avatar ? 'image/png' : (state.file.type === 'image/png' ? 'image/png' : (state.file.type === 'image/webp' ? 'image/webp' : 'image/jpeg'));
    if (state.avatar) {
      outputContext.beginPath();
      outputContext.arc(output.width / 2, output.height / 2, Math.min(output.width, output.height) / 2, 0, Math.PI * 2);
      outputContext.clip();
    }
    output.toBlob((blob) => {
      if (!blob) return finishCrop(state.file);
      const extension = blob.type === 'image/png' ? 'png' : (blob.type === 'image/webp' ? 'webp' : 'jpg');
      const name = state.avatar ? `avatar-cloudtrace.${extension}` : (state.logo ? `site-logo-cloudtrace.${extension}` : state.file.name.replace(/\.[^.]+$/, '') + `-cloudtrace.${extension}`);
      finishCrop(new File([blob], name, { type: blob.type, lastModified: Date.now() }));
    }, outputType, .9);
  });
  cropDialog.addEventListener('cancel', (event) => { event.preventDefault(); finishCrop(null); });

  doc.addEventListener('change', async (event) => {
    const input = event.target.closest('input[type="file"][data-image-crop]');
    if (!input || event.cropReady || !input.files?.length) return;
    event.stopImmediatePropagation();
    const original = [...input.files];
    const adjusted = [];
    for (const file of original) {
      if (!file.type.startsWith('image/')) { adjusted.push(file); continue; }
      const mode = input.dataset.avatarCrop !== undefined ? 'avatar' : (input.dataset.logoCrop !== undefined ? 'logo' : 'image');
      const result = await editImage(file, mode);
      if (result) adjusted.push(result);
    }
    if (!adjusted.length) { input.value = ''; return; }
    const transfer = new DataTransfer(); adjusted.forEach((file) => transfer.items.add(file)); input.files = transfer.files;
    const ready = new Event('change', { bubbles: true }); ready.cropReady = true; input.dispatchEvent(ready);
  }, true);

})();
