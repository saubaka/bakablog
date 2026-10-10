(() => {
  const editorRoot = document.querySelector('[data-visual-editor]');
  if (!editorRoot) return;

  const editorEntity = editorRoot.dataset.editorEntity || '内容';
  const form = editorRoot.closest('form');
  const richEditor = editorRoot.querySelector('[data-rich-editor]');
  const sourceEditor = editorRoot.querySelector('[data-editor-source]');
  const preview = editorRoot.querySelector('[data-editor-preview]');
  const workbench = editorRoot.querySelector('[data-editor-workbench]');
  const imageInput = editorRoot.querySelector('[data-visual-editor-image]');
  const imageInspector = editorRoot.querySelector('[data-image-inspector]');
  const uploadStatus = editorRoot.querySelector('[data-upload-status]');
  const editorStats = editorRoot.querySelector('[data-editor-stats]');
  const editorOutline = form?.querySelector('[data-editor-outline]');
  const titleInput = form?.querySelector('[name="title"]');
  const summaryInput = form?.querySelector('[name="summary"]');
  const csrfToken = form?.querySelector('[name="csrf_token"]')?.value || '';
  const imageClassGroups = {
    size: ['article-media--small', 'article-media--medium', 'article-media--large', 'article-media--full', 'article-media--custom'],
    align: ['article-media--left', 'article-media--center', 'article-media--right'],
    rotate: ['article-media--rotate-left', 'article-media--rotate-none', 'article-media--rotate-right'],
    ratio: ['article-media--ratio-original', 'article-media--ratio-square', 'article-media--ratio-landscape', 'article-media--ratio-wide']
  };
  let currentMode = 'visual';
  let selectedFigure = null;
  let draggedFigure = null;
  let savedRange = null;
  let dirty = false;
  let inspectorResizeObserver = null;

  // Keep the image controls above the editor's clipped workbench instead of in document flow.
  document.body.append(imageInspector);

  const safeHtml = (value) => {
    const parsed = new DOMParser().parseFromString(`<body>${value || ''}</body>`, 'text/html');
    parsed.querySelectorAll('script,style,iframe,object,embed,form,input,button,textarea,select').forEach((item) => item.remove());
    parsed.body.querySelectorAll('*').forEach((element) => {
      [...element.attributes].forEach((attribute) => {
        const name = attribute.name.toLowerCase();
        const valueText = attribute.value.trim().toLowerCase();
        if (name.startsWith('on') || ((name === 'href' || name === 'src') && valueText.startsWith('javascript:'))) element.removeAttribute(attribute.name);
      });
    });
    return parsed.body.innerHTML;
  };

  const blockForNode = (node) => {
    let element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    while (element && element.parentElement !== richEditor) element = element.parentElement;
    return element?.parentElement === richEditor ? element : null;
  };

  const ensureFigureDefaults = (figure) => {
    figure.classList.add('article-media');
    if (!imageClassGroups.size.some((name) => figure.classList.contains(name))) figure.classList.add('article-media--medium');
    if (!imageClassGroups.align.some((name) => figure.classList.contains(name))) figure.classList.add('article-media--center');
    if (!imageClassGroups.rotate.some((name) => figure.classList.contains(name))) figure.classList.add('article-media--rotate-none');
    if (!imageClassGroups.ratio.some((name) => figure.classList.contains(name))) figure.classList.add('article-media--ratio-original');
    figure.draggable = true;
    const image = figure.querySelector('img');
    if (image) image.draggable = false;
    let caption = figure.querySelector('figcaption');
    if (!caption) {
      caption = document.createElement('figcaption');
      caption.textContent = image?.alt || '';
      figure.append(caption);
    }
    caption.contentEditable = 'true';
    let settingsButton = figure.querySelector('[data-image-settings]');
    if (!settingsButton) {
      settingsButton = document.createElement('button');
      settingsButton.type = 'button';
      settingsButton.className = 'article-media__settings';
      settingsButton.dataset.imageSettings = '';
      settingsButton.dataset.editorTemporary = '';
      settingsButton.contentEditable = 'false';
      settingsButton.draggable = false;
      settingsButton.setAttribute('aria-label', '编辑图片');
      figure.append(settingsButton);
    }
  };

  const normalizeImages = () => {
    richEditor.querySelectorAll('img').forEach((image) => {
      let figure = image.closest('figure');
      if (!figure) {
        figure = document.createElement('figure');
        const parent = image.parentElement;
        if (parent?.tagName === 'P' && parent.querySelectorAll('img').length === 1 && !parent.textContent.trim()) parent.replaceWith(figure);
        else image.replaceWith(figure);
        figure.append(image);
      }
      ensureFigureDefaults(figure);
    });
  };

  const serializedHtml = () => {
    const clone = richEditor.cloneNode(true);
    clone.querySelectorAll('.is-selected').forEach((item) => item.classList.remove('is-selected'));
    clone.querySelectorAll('[contenteditable],[draggable]').forEach((item) => {
      item.removeAttribute('contenteditable');
      item.removeAttribute('draggable');
    });
    clone.querySelectorAll('[data-editor-temporary]').forEach((item) => item.remove());
    return clone.innerHTML.trim() || '<p><br></p>';
  };

  const updateStats = () => {
    if (!editorStats) return;
    const text = richEditor.textContent.replace(/\s+/g, ' ').trim();
    const imageCount = richEditor.querySelectorAll('figure.article-media').length;
    const minutes = Math.max(1, Math.round(text.replace(/\s/g, '').length / 500));
    editorStats.textContent = `${text.replace(/\s/g, '').length} 字 · ${imageCount} 图 · 约 ${minutes} 分钟`;
    updateEditorInsights();
  };

  const updateEditorInsights = () => {
    if (editorOutline) {
      const headings = [...richEditor.querySelectorAll('h2,h3,h4')]
        .map((heading) => ({ level: heading.tagName.toLowerCase(), text: heading.textContent.trim() }))
        .filter((heading) => heading.text);
      editorOutline.replaceChildren();
      if (!headings.length) {
        const empty = document.createElement('li');
        empty.className = 'is-empty';
        empty.textContent = '添加二至四级标题后会自动生成。';
        editorOutline.append(empty);
      } else {
        headings.forEach((heading) => {
          const item = document.createElement('li');
          item.dataset.level = heading.level;
          item.textContent = heading.text;
          editorOutline.append(item);
        });
      }
    }
    const textLength = richEditor.textContent.replace(/\s/g, '').length;
    const imagesHaveAlt = [...richEditor.querySelectorAll('img')].every((image) => image.alt.trim());
    const states = {
      title: Boolean(titleInput?.value.trim()),
      content: textLength > 0 || Boolean(richEditor.querySelector('img')),
      summary: Boolean(summaryInput?.value.trim()),
      images: imagesHaveAlt
    };
    Object.entries(states).forEach(([key, complete]) => {
      form?.querySelector(`[data-editor-check="${key}"]`)?.classList.toggle('is-complete', complete);
    });
  };

  const syncSource = (emit = true) => {
    sourceEditor.value = serializedHtml();
    updateStats();
    if (emit) sourceEditor.dispatchEvent(new Event('input', { bubbles: true }));
  };

  const rememberSelection = () => {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !richEditor.contains(selection.anchorNode)) return;
    savedRange = selection.getRangeAt(0).cloneRange();
  };

  const restoreSelection = () => {
    richEditor.focus();
    if (!savedRange) return;
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(savedRange);
  };

  const runCommand = (command, value = null) => {
    restoreSelection();
    document.execCommand(command, false, value);
    rememberSelection();
    syncSource();
    dirty = true;
  };

  const insertHtml = (html) => {
    restoreSelection();
    const before = richEditor.innerHTML;
    const insertedByCommand = document.execCommand('insertHTML', false, html);
    if (!insertedByCommand || richEditor.innerHTML === before) {
      const template = document.createElement('template');
      template.innerHTML = html;
      const range = savedRange && richEditor.contains(savedRange.commonAncestorContainer)
        ? savedRange.cloneRange()
        : document.createRange();
      if (!savedRange || !richEditor.contains(savedRange.commonAncestorContainer)) {
        range.selectNodeContents(richEditor);
        range.collapse(false);
      }
      range.deleteContents();
      const lastNode = template.content.lastChild;
      range.insertNode(template.content);
      if (lastNode) {
        range.setStartAfter(lastNode);
        range.collapse(true);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        savedRange = range.cloneRange();
      }
    }
    normalizeImages();
    syncSource();
    dirty = true;
  };

  const insertMediaFigure = ({ url, alt, width, height }) => {
    const figure = document.createElement('figure');
    figure.className = 'article-media article-media--medium article-media--center article-media--rotate-none article-media--ratio-original';
    const image = document.createElement('img');
    image.src = url;
    image.alt = alt || `${editorEntity}插图`;
    if (width) image.width = Number(width);
    if (height) image.height = Number(height);
    image.loading = 'lazy';
    image.decoding = 'async';
    const caption = document.createElement('figcaption');
    caption.textContent = image.alt;
    figure.append(image, caption);
    insertHtml(`${figure.outerHTML}<p><br></p>`);
    const inserted = [...richEditor.querySelectorAll('figure.article-media')].reverse().find((item) => item.querySelector('img')?.getAttribute('src') === url);
    if (inserted) {
      selectFigure(null);
      inserted.classList.add('is-just-inserted');
      inserted.scrollIntoView({ behavior: 'smooth', block: 'center' });
      window.setTimeout(() => inserted.classList.remove('is-just-inserted'), 900);
    }
  };

  const setClassChoice = (figure, group, value) => {
    imageClassGroups[group].forEach((name) => figure.classList.remove(name));
    figure.classList.add(`article-media--${group === 'ratio' ? 'ratio-' : group === 'rotate' ? 'rotate-' : ''}${value}`);
    if (group === 'size') figure.style.removeProperty('width');
  };

  const presetWidths = { small: 38, medium: 62, large: 84, full: 100 };

  const updateWidthControl = () => {
    const control = imageInspector.querySelector('[data-image-width]');
    const output = imageInspector.querySelector('[data-image-width-output]');
    if (!control || !output || !selectedFigure) return;
    const preset = Object.entries(presetWidths).find(([name]) => selectedFigure.classList.contains(`article-media--${name}`));
    const width = Number.parseInt(selectedFigure.style.width, 10) || (preset ? preset[1] : 62);
    control.value = String(width);
    output.textContent = `${width}%`;
  };

  const updateInspectorButtons = () => {
    if (!selectedFigure) return;
    imageInspector.querySelectorAll('[data-image-size],[data-image-align],[data-image-rotate],[data-image-ratio]').forEach((button) => {
      const entries = ['size', 'align', 'rotate', 'ratio'];
      const group = entries.find((name) => button.dataset[`image${name[0].toUpperCase()}${name.slice(1)}`] !== undefined);
      const value = button.dataset[`image${group[0].toUpperCase()}${group.slice(1)}`];
      const prefix = group === 'ratio' ? 'ratio-' : group === 'rotate' ? 'rotate-' : '';
      const active = selectedFigure.classList.contains(`article-media--${prefix}${value}`);
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  };

  const positionImageInspector = () => {
    if (!selectedFigure || imageInspector.hidden) return;
    const gap = 14;
    const edge = 12;
    const preferredWidth = Math.min(350, window.innerWidth - edge * 2);
    const minimumSideWidth = Math.min(230, Math.max(176, window.innerWidth * .46));
    richEditor.removeAttribute('data-inspector-side');
    imageInspector.style.width = `${Math.round(preferredWidth)}px`;

    let figureRect = selectedFigure.getBoundingClientRect();
    let rightSpace = window.innerWidth - edge - figureRect.right - gap;
    let leftSpace = figureRect.left - edge - gap;
    let side = selectedFigure.classList.contains('article-media--right')
      ? 'left'
      : selectedFigure.classList.contains('article-media--left')
        ? 'right'
        : (rightSpace >= leftSpace ? 'right' : 'left');
    if (side === 'right' && rightSpace < preferredWidth && leftSpace >= preferredWidth) side = 'left';
    if (side === 'left' && leftSpace < preferredWidth && rightSpace >= preferredWidth) side = 'right';

    let available = side === 'right' ? rightSpace : leftSpace;
    if (available < minimumSideWidth) {
      side = rightSpace >= leftSpace ? 'right' : 'left';
      richEditor.dataset.inspectorSide = side;
      figureRect = selectedFigure.getBoundingClientRect();
      rightSpace = window.innerWidth - edge - figureRect.right - gap;
      leftSpace = figureRect.left - edge - gap;
      available = side === 'right' ? rightSpace : leftSpace;
    }

    const panelWidth = Math.max(1, Math.min(preferredWidth, available));
    imageInspector.style.width = `${Math.round(panelWidth)}px`;
    const panelRect = imageInspector.getBoundingClientRect();
    let left = side === 'right'
      ? figureRect.right + gap
      : figureRect.left - panelRect.width - gap;
    let top = figureRect.top;
    left = Math.max(edge, Math.min(left, window.innerWidth - panelRect.width - edge));
    top = Math.max(edge, Math.min(top, window.innerHeight - panelRect.height - edge));
    imageInspector.dataset.side = side;
    imageInspector.style.left = `${Math.round(left)}px`;
    imageInspector.style.top = `${Math.round(top)}px`;
  };

  const selectFigure = (figure) => {
    selectedFigure?.classList.remove('is-selected');
    selectedFigure = figure;
    if (!figure) {
      inspectorResizeObserver?.disconnect();
      richEditor.removeAttribute('data-inspector-side');
      imageInspector.hidden = true;
      imageInspector.removeAttribute('data-side');
      imageInspector.style.removeProperty('left');
      imageInspector.style.removeProperty('top');
      imageInspector.style.removeProperty('width');
      return;
    }
    ensureFigureDefaults(figure);
    figure.classList.add('is-selected');
    imageInspector.hidden = false;
    imageInspector.querySelector('[data-image-alt]').value = figure.querySelector('img')?.alt || '';
    imageInspector.querySelector('[data-image-caption]').value = figure.querySelector('figcaption')?.textContent || '';
    updateInspectorButtons();
    updateWidthControl();
    inspectorResizeObserver?.disconnect();
    inspectorResizeObserver?.observe(figure);
    inspectorResizeObserver?.observe(imageInspector);
    requestAnimationFrame(positionImageInspector);
  };

  const refreshPreview = () => {
    const html = currentMode === 'source' ? sourceEditor.value : serializedHtml();
    preview.innerHTML = safeHtml(html);
  };

  const setMode = (mode) => {
    if (!['visual', 'source', 'preview'].includes(mode)) return;
    if (currentMode === 'source' && mode !== 'source') {
      richEditor.innerHTML = safeHtml(sourceEditor.value);
      normalizeImages();
    }
    if (mode === 'source') syncSource(false);
    if (mode === 'preview') refreshPreview();
    if (mode !== 'visual') selectFigure(null);
    currentMode = mode;
    workbench.dataset.mode = mode;
    updateStats();
    editorRoot.querySelectorAll('[data-editor-mode]').forEach((button) => {
      const active = button.dataset.editorMode === mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  };

  normalizeImages();
  syncSource(false);

  titleInput?.addEventListener('input', updateEditorInsights);
  summaryInput?.addEventListener('input', updateEditorInsights);

  document.addEventListener('selectionchange', rememberSelection);
  richEditor.addEventListener('input', () => {
    normalizeImages();
    syncSource();
    dirty = true;
  });
  richEditor.addEventListener('click', (event) => {
    const settingsButton = event.target.closest('[data-image-settings]');
    if (!settingsButton) return;
    event.preventDefault();
    event.stopPropagation();
    selectFigure(settingsButton.closest('figure.article-media'));
  });
  richEditor.addEventListener('keydown', async (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      const url = await window.CloudDiary?.prompt?.(
        '请输入包含协议的完整地址，例如 https://example.com。',
        'https://',
        '插入链接'
      );
      if (url) runCommand('createLink', url);
    }
  });

  editorRoot.querySelectorAll('[data-editor-command]').forEach((button) => button.addEventListener('click', () => runCommand(button.dataset.editorCommand)));
  editorRoot.querySelector('[data-editor-block]')?.addEventListener('change', (event) => runCommand('formatBlock', event.target.value));
  editorRoot.querySelector('[data-editor-font-size]')?.addEventListener('change', (event) => runCommand('fontSize', event.target.value));
  editorRoot.querySelector('[data-editor-color]')?.addEventListener('input', (event) => runCommand('foreColor', event.target.value));
  editorRoot.querySelector('[data-editor-highlight]')?.addEventListener('input', (event) => {
    restoreSelection();
    if (!document.execCommand('hiliteColor', false, event.target.value)) document.execCommand('backColor', false, event.target.value);
    syncSource();
  });

  editorRoot.querySelectorAll('[data-editor-action]').forEach((button) => button.addEventListener('click', async () => {
    const action = button.dataset.editorAction;
    if (action === 'link') {
      const url = await window.CloudDiary?.prompt?.(
        '请输入包含协议的完整地址，例如 https://example.com。',
        'https://',
        '插入链接'
      );
      if (url) runCommand('createLink', url);
    }
    if (action === 'divider') insertHtml('<hr><p><br></p>');
    if (action === 'callout') insertHtml('<div class="callout"><span>✦</span><div><strong>提示</strong><p>在这里填写需要强调的内容。</p></div></div><p><br></p>');
    if (action === 'table') insertHtml('<table><thead><tr><th>标题一</th><th>标题二</th><th>标题三</th></tr></thead><tbody><tr><td>内容</td><td>内容</td><td>内容</td></tr><tr><td>内容</td><td>内容</td><td>内容</td></tr></tbody></table><p><br></p>');
  }));

  editorRoot.querySelectorAll('[data-editor-mode]').forEach((button) => button.addEventListener('click', () => setMode(button.dataset.editorMode)));
  sourceEditor.addEventListener('input', () => { dirty = true; if (currentMode === 'preview') refreshPreview(); });

  editorRoot.querySelector('[data-editor-fullscreen]')?.addEventListener('click', (event) => {
    const active = editorRoot.classList.toggle('is-fullscreen');
    document.body.classList.toggle('visual-editor-fullscreen', active);
    event.currentTarget.setAttribute('aria-pressed', String(active));
    event.currentTarget.textContent = active ? '退出全屏' : '全屏';
    requestAnimationFrame(positionImageInspector);
  });

  imageInput?.addEventListener('change', async () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    const data = new FormData();
    data.append('image', file);
    uploadStatus.textContent = '正在清理元数据并生成图片…';
    const task = window.CloudDiary?.progress?.('正在上传图片…');
    let reportedStep = 0;
    try {
      const result = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', editorRoot.dataset.uploadUrl);
        xhr.setRequestHeader('X-CSRFToken', csrfToken);
        xhr.responseType = 'json';
        xhr.upload.addEventListener('progress', (event) => {
          if (!event.lengthComputable) return;
          const percent = Math.round(event.loaded / event.total * 100);
          uploadStatus.textContent = `正在上传 ${percent}%`;
          const step = Math.min(3, Math.floor(percent / 34));
          if (step > reportedStep) { reportedStep = step; task?.update(percent >= 100 ? '上传完成，正在清理元数据…' : `正在上传 ${percent}%`); }
        });
        xhr.addEventListener('load', () => resolve({ ok: xhr.status >= 200 && xhr.status < 300, payload: xhr.response || {} }));
        xhr.addEventListener('error', () => reject(new Error('网络中断，上传失败')));
        xhr.send(data);
      });
      const payload = result.payload;
      if (!result.ok) throw new Error(payload.error?.message || '上传失败');
      insertMediaFigure({ url: payload.data.url, alt: payload.data.alt_text || file.name, width: payload.data.width, height: payload.data.height });
      const optimizedSize = payload.data.size_bytes ? `${Math.max(1, Math.round(payload.data.size_bytes / 1024))} KB` : '本地优化完成';
      uploadStatus.textContent = `图片已插入（${optimizedSize}）；可拖动并调整尺寸、方向与位置。`;
      if (task) task.finish('图片已插入可视化编辑器。', 'success');
      else window.CloudDiary?.showToast?.('图片已插入可视化编辑器。', 'success');
    } catch (error) {
      uploadStatus.textContent = error.message;
      if (task) task.fail(error.message);
      else window.CloudDiary?.showToast?.(error.message, 'error');
    }
    imageInput.value = '';
  });

  editorRoot.querySelectorAll('[data-editor-media-item]').forEach((button) => button.addEventListener('click', () => {
    const media = {
      url: button.dataset.url,
      alt: button.dataset.alt,
      width: button.dataset.width,
      height: button.dataset.height
    };
    button.closest('dialog')?.querySelector('[data-close-dialog]')?.click();
    requestAnimationFrame(() => {
      insertMediaFigure(media);
      uploadStatus.textContent = '已从本地媒体库插入图片；悬浮图片可打开设置。';
      window.CloudDiary?.showToast?.('已从媒体库插入图片。', 'success');
    });
  }));

  richEditor.addEventListener('dragstart', (event) => {
    if (event.target.closest('[data-image-settings]')) {
      event.preventDefault();
      return;
    }
    const figure = event.target.closest('figure.article-media');
    if (!figure) return;
    draggedFigure = figure;
    figure.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', 'article-image');
  });
  richEditor.addEventListener('dragover', (event) => {
    if (!draggedFigure) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  });
  richEditor.addEventListener('drop', (event) => {
    if (!draggedFigure) return;
    event.preventDefault();
    const target = blockForNode(event.target);
    if (target && target !== draggedFigure) {
      const rect = target.getBoundingClientRect();
      target.parentElement.insertBefore(draggedFigure, event.clientY > rect.top + rect.height / 2 ? target.nextSibling : target);
      syncSource();
      dirty = true;
      requestAnimationFrame(positionImageInspector);
    }
  });
  richEditor.addEventListener('dragend', () => {
    draggedFigure?.classList.remove('is-dragging');
    draggedFigure = null;
    requestAnimationFrame(positionImageInspector);
  });

  imageInspector.querySelectorAll('[data-image-size],[data-image-align],[data-image-rotate],[data-image-ratio]').forEach((button) => button.addEventListener('click', () => {
    if (!selectedFigure) return;
    if (button.dataset.imageSize) setClassChoice(selectedFigure, 'size', button.dataset.imageSize);
    if (button.dataset.imageAlign) setClassChoice(selectedFigure, 'align', button.dataset.imageAlign);
    if (button.dataset.imageRotate) setClassChoice(selectedFigure, 'rotate', button.dataset.imageRotate);
    if (button.dataset.imageRatio) setClassChoice(selectedFigure, 'ratio', button.dataset.imageRatio);
    updateInspectorButtons();
    updateWidthControl();
    requestAnimationFrame(positionImageInspector);
    syncSource();
    dirty = true;
  }));
  imageInspector.querySelector('[data-image-width]')?.addEventListener('input', (event) => {
    if (!selectedFigure) return;
    const width = Math.min(100, Math.max(30, Number.parseInt(event.target.value, 10) || 62));
    imageClassGroups.size.forEach((name) => selectedFigure.classList.remove(name));
    selectedFigure.classList.add('article-media--custom');
    selectedFigure.style.width = `${width}%`;
    imageInspector.querySelector('[data-image-width-output]').textContent = `${width}%`;
    updateInspectorButtons();
    requestAnimationFrame(positionImageInspector);
    syncSource();
    dirty = true;
  });
  imageInspector.querySelector('[data-image-alt]')?.addEventListener('input', (event) => {
    const image = selectedFigure?.querySelector('img');
    if (image) image.alt = event.target.value;
    syncSource();
  });
  imageInspector.querySelector('[data-image-caption]')?.addEventListener('input', (event) => {
    const caption = selectedFigure?.querySelector('figcaption');
    if (caption) caption.textContent = event.target.value;
    syncSource();
  });
  imageInspector.querySelector('[data-image-deselect]')?.addEventListener('click', () => selectFigure(null));
  imageInspector.querySelectorAll('[data-image-move]').forEach((button) => button.addEventListener('click', () => {
    if (!selectedFigure) return;
    const sibling = button.dataset.imageMove === 'up' ? selectedFigure.previousElementSibling : selectedFigure.nextElementSibling;
    if (!sibling) return;
    if (button.dataset.imageMove === 'up') selectedFigure.parentElement.insertBefore(selectedFigure, sibling);
    else selectedFigure.parentElement.insertBefore(sibling, selectedFigure);
    selectedFigure.scrollIntoView({ behavior: 'smooth', block: 'center' });
    syncSource();
    requestAnimationFrame(positionImageInspector);
  }));
  imageInspector.querySelector('[data-image-remove]')?.addEventListener('click', async () => {
    if (!selectedFigure) return;
    const confirmed = await window.CloudDiary?.confirm?.(
      `媒体库中的原文件会继续保留，只从当前${editorEntity}正文移除。`,
      '移除这张图片？'
    );
    if (!confirmed) return;
    selectedFigure.remove();
    selectFigure(null);
    syncSource();
  });

  document.addEventListener('pointerdown', (event) => {
    if (!selectedFigure || imageInspector.contains(event.target) || event.target.closest('[data-image-settings]')) return;
    selectFigure(null);
  });
  let inspectorPositionFrame = 0;
  const queueInspectorPosition = () => {
    if (inspectorPositionFrame || !selectedFigure) return;
    inspectorPositionFrame = requestAnimationFrame(() => {
      inspectorPositionFrame = 0;
      positionImageInspector();
    });
  };
  if ('ResizeObserver' in window) inspectorResizeObserver = new ResizeObserver(queueInspectorPosition);
  window.addEventListener('resize', queueInspectorPosition);
  window.addEventListener('scroll', queueInspectorPosition, true);
  window.visualViewport?.addEventListener('resize', queueInspectorPosition);
  window.visualViewport?.addEventListener('scroll', queueInspectorPosition);

  const editorSidebar = form?.querySelector('[data-editor-sidebar]');
  editorSidebar?.querySelectorAll('[data-editor-widget]').forEach((widget) => {
    const toggle = widget.querySelector('[data-editor-widget-toggle]');
    toggle?.addEventListener('click', () => {
      const open = widget.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  });
  requestAnimationFrame(() => editorSidebar?.setAttribute('data-widgets-ready', 'true'));

  form?.addEventListener('submit', () => {
    if (currentMode === 'source') richEditor.innerHTML = safeHtml(sourceEditor.value);
    normalizeImages();
    syncSource(false);
    dirty = false;
  });
  window.addEventListener('beforeunload', (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
})();
