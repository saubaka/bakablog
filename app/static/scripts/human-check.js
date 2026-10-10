(() => {
  'use strict';

  const init = (scope) => scope.querySelectorAll('[data-human-check]').forEach((panel) => {
    const button = panel.querySelector('[data-human-check-refresh]');
    const image = panel.querySelector('[data-human-check-image]');
    const answer = panel.querySelector('[data-human-check-answer]');
    const nonce = panel.closest('form')?.querySelector('input[name="human_nonce"]');
    const status = panel.querySelector('[data-human-check-status]');
    if (!button || !image || !nonce || !panel.dataset.refreshUrl) return;

    button.addEventListener('click', async () => {
      if (button.disabled) return;
      button.disabled = true;
      panel.classList.add('is-loading');
      if (status) status.textContent = '正在换一张…';
      try {
        const response = await fetch(panel.dataset.refreshUrl, {
          headers: { Accept: 'application/json' },
          credentials: 'same-origin'
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error('refresh failed');
        image.src = payload.image;
        await image.decode?.().catch(() => {});
        nonce.value = payload.nonce;
        if (answer) {
          answer.value = '';
          answer.focus({ preventScroll: true });
        }
        panel.classList.remove('is-error');
        panel.classList.add('is-refreshed');
        if (status) status.textContent = '已换新，请输入四位字符';
        window.setTimeout(() => panel.classList.remove('is-refreshed'), 360);
      } catch (_error) {
        panel.classList.add('is-error');
        if (status) status.textContent = '刷新失败，请稍后再试';
      } finally {
        panel.classList.remove('is-loading');
        button.disabled = false;
      }
    });
  });
  if (window.CloudtracePage?.define) window.CloudtracePage.define('human-check', init);
  else init(document);
})();
