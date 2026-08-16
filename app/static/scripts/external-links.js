(() => {
  const doc = document;
  const root = doc.documentElement;
  const gatewayPath = '/out/';
  const urlPattern = /(?:https?:\/\/|www\.)[^\s<>"'，。！？；：、）】）》”’]+/giu;
  const excludedSelector = 'a,script,style,code,pre,textarea,input,button,select,option,template,[contenteditable="true"],[data-no-linkify]';
  const trailingPunctuation = /[.,;:!?，。！？；：、)\]}】）》”’]+$/u;
  const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches || root.dataset.motion === 'reduce';

  function parsedHttpUrl(value) {
    try {
      const normalized = /^www\./iu.test(value) ? `https://${value}` : value;
      const parsed = new URL(normalized, window.location.href);
      return ['http:', 'https:'].includes(parsed.protocol) ? parsed : null;
    } catch (_error) {
      return null;
    }
  }

  function routeAnchor(anchor) {
    if (!anchor || anchor.dataset.externalLinkBypass !== undefined || anchor.closest('[contenteditable="true"]')) return;
    const parsed = parsedHttpUrl(anchor.getAttribute('href') || '');
    if (!parsed || parsed.origin === window.location.origin) return;
    const destination = parsed.href;
    const gateway = new URL(gatewayPath, window.location.origin);
    gateway.searchParams.set('url', destination);
    anchor.href = gateway.href;
    anchor.removeAttribute('target');
    anchor.rel = 'nofollow noopener noreferrer';
    anchor.dataset.externalLink = '';
    anchor.dataset.externalDestination = destination;
    anchor.classList.add('external-routed-link');
  }

  function linkifyTextNode(node) {
    if (!node?.parentElement || node.parentElement.closest(excludedSelector)) return;
    const text = node.nodeValue || '';
    urlPattern.lastIndex = 0;
    let match = urlPattern.exec(text);
    if (!match) return;
    const fragment = doc.createDocumentFragment();
    let cursor = 0;
    while (match) {
      const raw = match[0];
      const trailing = raw.match(trailingPunctuation)?.[0] || '';
      const visibleUrl = trailing ? raw.slice(0, -trailing.length) : raw;
      const parsed = parsedHttpUrl(visibleUrl);
      fragment.append(text.slice(cursor, match.index));
      if (parsed) {
        const anchor = doc.createElement('a');
        anchor.className = 'external-text-link';
        anchor.href = parsed.href;
        anchor.textContent = visibleUrl;
        routeAnchor(anchor);
        fragment.append(anchor);
      } else {
        fragment.append(visibleUrl);
      }
      if (trailing) fragment.append(trailing);
      cursor = match.index + raw.length;
      match = urlPattern.exec(text);
    }
    fragment.append(text.slice(cursor));
    node.replaceWith(fragment);
  }

  function enhanceScope(scope) {
    if (!scope) return;
    if (scope.nodeType === Node.TEXT_NODE) {
      linkifyTextNode(scope);
      return;
    }
    if (scope.nodeType !== Node.ELEMENT_NODE && scope !== doc.body) return;
    if (scope.matches?.('a[href]')) routeAnchor(scope);
    scope.querySelectorAll?.('a[href]').forEach(routeAnchor);
    const walker = doc.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return node.nodeValue?.match(/https?:\/\/|www\./iu) && !node.parentElement?.closest(excludedSelector)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(linkifyTextNode);
  }

  enhanceScope(doc.body);
  const queuedNodes = new Set();
  let enhancementQueued = false;
  const flushEnhancements = () => {
    enhancementQueued = false;
    [...queuedNodes].forEach(enhanceScope);
    queuedNodes.clear();
  };
  new MutationObserver((records) => {
    records.forEach((record) => record.addedNodes.forEach((node) => queuedNodes.add(node)));
    if (!enhancementQueued && queuedNodes.size) {
      enhancementQueued = true;
      queueMicrotask(flushEnhancements);
    }
  }).observe(doc.body, { childList: true, subtree: true });

  function toggleRuleEditor(button) {
    const card = button.closest('[data-external-rule]');
    const editor = card?.querySelector('[data-external-rule-editor]');
    if (!card || !editor) return;
    const opening = editor.hidden || !card.classList.contains('is-editing');
    card.querySelectorAll('[data-external-rule-toggle]').forEach((item) => item.setAttribute('aria-expanded', String(opening)));
    if (opening) {
      editor.hidden = false;
      editor.style.height = '0px';
      editor.getBoundingClientRect();
      card.classList.add('is-editing');
      editor.style.height = `${editor.scrollHeight}px`;
      window.setTimeout(() => {
        if (card.classList.contains('is-editing')) editor.style.height = 'auto';
        editor.querySelector('input:not([type="hidden"])')?.focus({ preventScroll: true });
      }, reducedMotion() ? 0 : 340);
      return;
    }
    editor.style.height = `${editor.scrollHeight}px`;
    editor.getBoundingClientRect();
    card.classList.remove('is-editing');
    editor.style.height = '0px';
    window.setTimeout(() => {
      if (!card.classList.contains('is-editing')) editor.hidden = true;
    }, reducedMotion() ? 0 : 340);
  }

  doc.addEventListener('click', (event) => {
    const editorToggle = event.target.closest('[data-external-rule-toggle]');
    if (editorToggle) {
      event.preventDefault();
      toggleRuleEditor(editorToggle);
      return;
    }
    const continueLink = event.target.closest('[data-external-continue]');
    const backButton = event.target.closest('[data-external-back]');
    if (!continueLink && !backButton) return;
    event.preventDefault();
    const stage = event.target.closest('[data-external-jump]');
    stage?.classList.add('is-leaving');
    const delay = reducedMotion() ? 40 : 520;
    window.setTimeout(() => {
      if (continueLink) {
        window.location.assign(continueLink.href);
      } else if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.assign('/');
      }
    }, delay);
  });
})();
