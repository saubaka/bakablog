#!/usr/bin/env node

/* Cloudtrace responsive and synchronized-motion acceptance probe.
 * Run with the bundled Codex Playwright package through NODE_PATH.
 * A temporary QA administrator password must be supplied through the
 * CLOUDTRACE_QA_PASSWORD environment variable and is never written to disk.
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = (process.env.CLOUDTRACE_QA_URL || 'http://127.0.0.1:5019').replace(/\/$/, '');
const username = process.env.CLOUDTRACE_QA_USERNAME || 'visualqa';
const password = process.env.CLOUDTRACE_QA_PASSWORD;
const publicOnly = process.env.CLOUDTRACE_QA_PUBLIC_ONLY === '1';
const adminMatrixOnly = process.env.CLOUDTRACE_QA_ADMIN_MATRIX_ONLY === '1';
const editorSelectOnly = process.env.CLOUDTRACE_QA_EDITOR_SELECT_ONLY === '1';
const motionOnly = process.env.CLOUDTRACE_QA_MOTION_ONLY === '1';
const adminStartAt = process.env.CLOUDTRACE_QA_ADMIN_START || '';
const humanAnswer = process.env.CLOUDTRACE_QA_HUMAN_ANSWER || 'BAKA';
const outputDir = path.resolve(process.env.CLOUDTRACE_QA_OUTPUT || 'session-data/qa/v1.36.0-overlays-bootstrap');
if (!publicOnly && !password) throw new Error('CLOUDTRACE_QA_PASSWORD is required.');

const cacheRoot = path.join(process.env.HOME || '', 'Library', 'Caches', 'ms-playwright');
const chromiumFolders = fs.existsSync(cacheRoot)
  ? fs.readdirSync(cacheRoot).filter((name) => /^chromium-\d+$/.test(name)).sort().reverse()
  : [];
const executablePath = process.env.CLOUDTRACE_QA_CHROMIUM || chromiumFolders
  .map((folder) => path.join(
    cacheRoot,
    folder,
    'chrome-mac-arm64',
    'Google Chrome for Testing.app',
    'Contents',
    'MacOS',
    'Google Chrome for Testing'
  ))
  .find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error('A local Playwright Chromium executable was not found.');

fs.mkdirSync(outputDir, { recursive: true });

const viewports = [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 }
];
const publicPages = [
  ['home', '/'],
  ['blog', '/blog/'],
  ['article-comments', '/blog/visual-comment-demo/'],
  ['projects', '/projects/'],
  ['moments', '/moments/'],
  ['moment-comments', '/moments/1/'],
  ['gallery', '/gallery/'],
  ['links', '/links/'],
  ['guestbook', '/guestbook/'],
  ['about', '/about/'],
  ['search', '/search/'],
  ['admin-login', '/bakaadmin']
];
const adminPages = [
  ['dashboard', '/admin/'],
  ['access', '/admin/access/'],
  ['albums', '/admin/albums/'],
  ['album-editor', '/admin/albums/edit/'],
  ['dialogs', '/admin/appearance/dialogs/'],
  ['interface', '/admin/appearance/interface/'],
  ['seo', '/admin/appearance/seo/'],
  ['motion', '/admin/appearance/transitions/'],
  ['audit', '/admin/audit-logs/'],
  ['friends', '/admin/friends/'],
  ['friend-editor', '/admin/friends/edit/'],
  ['media', '/admin/media/'],
  ['admin-menu', '/admin/menu/admin-layout/'],
  ['primary-menu', '/admin/menu/primary/'],
  ['moderation', '/admin/moderation/'],
  ['moments', '/admin/moments/'],
  ['moment-editor', '/admin/moments/new/'],
  ['pages', '/admin/pages/'],
  ['front-pages', '/admin/pages/front/'],
  ['home-settings', '/admin/pages/home/'],
  ['page-editor', '/admin/pages/new/'],
  ['posts', '/admin/posts/'],
  ['post-editor', '/admin/posts/new/'],
  ['profile', '/admin/profile/'],
  ['projects', '/admin/projects/'],
  ['project-editor', '/admin/projects/new/'],
  ['site-content', '/admin/site-content/'],
  ['addresses', '/admin/site/addresses/'],
  ['footer', '/admin/site/footer/'],
  ['identity', '/admin/site/identity/'],
  ['logo', '/admin/site/logo/'],
  ['security', '/admin/site/security/'],
  ['external-links', '/admin/site/third-party-links/'],
  ['system', '/admin/system/'],
  ['about-system', '/admin/system/about/'],
  ['taxonomy', '/admin/taxonomy/'],
  ['categories', '/admin/taxonomy/categories/'],
  ['category-editor', '/admin/taxonomy/categories/new/'],
  ['tags', '/admin/taxonomy/tags/'],
  ['tag-editor', '/admin/taxonomy/tags/new/']
];

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

async function login(page) {
  await page.goto(`${baseUrl}/bakaadmin`, { waitUntil: 'networkidle' });
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('input[name="human_answer"]').fill(humanAnswer);
  await Promise.all([
    page.waitForURL(/\/admin\/$/),
    page.locator('button[type="submit"]').click()
  ]);
}

async function settlePage(page) {
  await page.waitForTimeout(1050);
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  const step = Math.max(280, Math.floor(page.viewportSize().height * .72));
  for (let y = 0; y < height; y += step) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(90);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForFunction(
    () => !document.querySelector('.motion-line-target.is-motion-active'),
    null,
    { timeout: 4000 }
  );
  await page.waitForTimeout(120);
}

async function inspectLayout(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const visible = (element) => {
      if (element.closest('[hidden],[aria-hidden="true"]')) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 1 && rect.height > 1;
    };
    const overflowNodes = [...document.querySelectorAll('*')].filter((element) => {
      if (!visible(element)) return false;
      // An absolutely positioned themed menu is intentionally wider than its
      // compact toolbar trigger. Its ancestors inherit that scrollWidth even
      // when the floating menu remains entirely inside the viewport; the
      // opened-menu probe validates the real floating bounds separately.
      if (element.matches('.themed-select.is-open') || element.querySelector('.themed-select.is-open')) return false;
      const style = getComputedStyle(element);
      if (['auto', 'scroll', 'hidden', 'clip'].includes(style.overflowX)) return false;
      // Children of a horizontal scroller (tab strips, thumbnail rails) are
      // expected to sit past the fold; the scroller itself owns that overflow.
      for (let ancestor = element.parentElement; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
        if (['auto', 'scroll'].includes(getComputedStyle(ancestor).overflowX)) return false;
      }
      const rect = element.getBoundingClientRect();
      return element.scrollWidth > element.clientWidth + 2 || rect.left < -1 || rect.right > innerWidth + 1;
    }).slice(0, 30).map((element) => ({
      tag: element.tagName,
      className: String(element.className).slice(0, 100),
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      left: Number(element.getBoundingClientRect().left.toFixed(1)),
      right: Number(element.getBoundingClientRect().right.toFixed(1))
    }));
    const cardOverflow = [...document.querySelectorAll('.card,[data-motion-surface]')].filter((element) => {
      if (!visible(element)) return false;
      const style = getComputedStyle(element);
      return element.scrollWidth > element.clientWidth + 2 && !['auto', 'scroll', 'hidden', 'clip'].includes(style.overflowX);
    }).map((element) => String(element.className).slice(0, 100));
    const textOverflow = [...document.querySelectorAll('h1,h2,h3,p,strong,small,button,a')].filter((element) => {
      if (!visible(element)) return false;
      const style = getComputedStyle(element);
      if (['auto', 'scroll', 'hidden', 'clip'].includes(style.overflowX)) return false;
      return element.scrollWidth > element.clientWidth + 2;
    }).slice(0, 30).map((element) => ({
      tag: element.tagName,
      text: (element.textContent || '').trim().slice(0, 80),
      className: String(element.className).slice(0, 80)
    }));
    const targets = [...document.querySelectorAll('.motion-line-target')];
    const componentCoverageMissing = [...document.querySelectorAll('.card,.dashboard-widget,.admin-post-row,.button,.icon-button,[data-motion-surface],[data-motion-control]')]
      .filter((element) => (
        visible(element) &&
        // `data-motion-skip` marks a subtree that deliberately stays outside the
        // card/button choreography (overlays, focused auth cards, settings forms).
        !element.closest('[data-motion-skip]') &&
        !element.matches('[data-motion-shell],.motion-line-target,.motion-child-control,.motion-control-target') &&
        !(element.matches('.card') && element.querySelector('.motion-line-target,.motion-child-control,.motion-control-target'))
      ))
      .slice(0, 20)
      .map((element) => ({ tag: element.tagName, className: String(element.className).slice(0, 100) }));
    const outlineMissing = targets.filter((target) => (
      visible(target) && target.dataset.motionState === 'settled' &&
      !target.classList.contains('is-outline-ready')
    )).length;
    return {
      viewport: [innerWidth, innerHeight],
      documentOverflow: root.scrollWidth - root.clientWidth,
      overflowNodes,
      cardOverflow,
      textOverflow,
      outlineMissing,
      componentCoverageMissing,
      motionTargets: targets.length,
      activeWillChange: targets.filter((target) => getComputedStyle(target).willChange !== 'auto').length,
      activeWillChangeTargets: targets.filter((target) => getComputedStyle(target).willChange !== 'auto').slice(0, 20).map((target) => ({
        className: String(target.className).slice(0, 120),
        state: target.dataset.motionState || '',
        willChange: getComputedStyle(target).willChange
      })),
      bodyHeight: document.body.scrollHeight
    };
  });
}

async function sampleHomeMotion(browser) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    reducedMotion: 'no-preference'
  });
  const page = await context.newPage();
  const runtimeErrors = [];
  page.on('pageerror', (error) => runtimeErrors.push(error.message));
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) runtimeErrors.push(`${message.type()}: ${message.text()}`);
  });
  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('.home-intro__surface')?.dataset.motionState === 'drawing');
  const fractions = [0, .08, .2, .4, .5, .78, .82, .86, 1];
  const samples = [];
  for (const fraction of fractions) {
    const sample = await page.evaluate((progress) => {
      const hero = document.querySelector('.home-intro__surface');
      window.__cloudtraceMotionDebug.setProgress(hero, progress);
      const timeline = window.__cloudtraceMotionDebug.timelineFor(hero);
      const content = hero.querySelector(':scope > .motion-content');
      const path = hero.querySelector(':scope > .motion-outline > .motion-outline__path');
      const surface = hero.querySelector(':scope > .motion-surface-layer');
      const controls = [...hero.querySelectorAll('.motion-child-control')];
      const child = controls[0] || null;
      const childPath = child?.querySelector(':scope > .motion-outline > .motion-outline__path') || null;
      const childSurface = child?.querySelector(':scope > .motion-surface-layer') || null;
      const childLabel = child?.querySelector(':scope > .motion-control-label') || null;
      const pathProgress = (node) => {
        if (!node) return null;
        const length = Number(node.dataset.motionPathLength);
        const dash = Number.parseFloat(getComputedStyle(node).strokeDashoffset);
        return Number((1 - dash / length).toFixed(4));
      };
      return {
        progress,
        animationCount: timeline?.animations.length || 0,
        rootPathCount: hero.querySelectorAll(':scope > .motion-outline > .motion-outline__path').length,
        childCount: controls.length,
        childPathCounts: controls.map((control) => control.querySelectorAll(':scope > .motion-outline > .motion-outline__path').length),
        clipPath: getComputedStyle(hero).clipPath,
        contentOpacity: content ? Number(getComputedStyle(content).opacity) : 0,
        contentFilter: content ? getComputedStyle(content).filter : 'none',
        lineProgress: pathProgress(path),
        surfaceOpacity: Number(getComputedStyle(surface).opacity),
        surfaceTransform: getComputedStyle(surface).transform,
        surfaceFilter: getComputedStyle(surface).filter,
        childLineProgress: pathProgress(childPath),
        childSurfaceOpacity: childSurface ? Number(getComputedStyle(childSurface).opacity) : null,
        childLabelOpacity: childLabel ? Number(getComputedStyle(childLabel).opacity) : null,
        targetBackground: getComputedStyle(hero).backgroundColor,
        childBackground: child ? getComputedStyle(child).backgroundColor : null,
        childShadow: child ? getComputedStyle(child).boxShadow : null,
        shadow: getComputedStyle(hero).boxShadow
      };
    }, fraction);
    samples.push(sample);
    if ([.2, .5, .82, .86, 1].includes(fraction)) {
      await page.screenshot({ path: path.join(outputDir, `home-motion-${String(fraction).replace('.', '-')}.png`) });
    }
  }
  const at = (progress) => samples.find((sample) => sample.progress === progress);
  assert(samples[0].contentOpacity <= .01, 'Hero content is visible at progress 0.');
  assert(samples[0].lineProgress <= .002, 'Hero outline is already drawn at progress 0.');
  assert(samples.every((sample) => sample.rootPathCount === 1), 'Hero has more than one outline path.');
  assert(samples.every((sample) => sample.childPathCounts.every((count) => count === 1)), 'A child control has more than one outline path.');
  assert(samples.every((sample) => sample.clipPath === 'none'), 'A directional clip wipe remains in the card timeline.');
  assert(at(.2).targetBackground === 'rgba(0, 0, 0, 0)' && at(.2).shadow === 'none', 'Legacy card background or shadow transition overlaps the physical timeline.');
  assert(at(.2).childBackground === 'rgba(0, 0, 0, 0)' && at(.2).childShadow === 'none', 'A child control has two surface owners.');
  assert(at(.2).lineProgress > .05 && at(.2).lineProgress < .95, 'Main line does not remain in progress during entry.');
  assert(at(.2).childLineProgress > .05, 'Child controls are still waiting for a serial card phase.');
  assert(at(.2).surfaceOpacity > .05 && at(.2).contentOpacity > .05 && at(.2).childLabelOpacity > .05, 'Content still waits behind a long empty-card phase.');
  assert(at(.78).surfaceOpacity >= .998 && at(.78).childSurfaceOpacity >= .998, 'Card and control surfaces do not finish together.');
  assert(at(.82).lineProgress >= .998 && at(.82).childLineProgress >= .998, 'Owned outlines do not complete together.');
  assert(at(.86).contentOpacity >= .998 && at(.86).childLabelOpacity >= .998, 'Card and control labels do not finish together.');
  assert(samples.at(-1).lineProgress >= .998, 'Hero outline does not complete.');
  assert(samples.at(-1).contentOpacity >= .998, 'Hero content does not complete.');
  assert(samples.every((sample, index) => index === 0 || sample.lineProgress >= samples[index - 1].lineProgress), 'Outline progress is not monotonic.');
  assert(samples.every((sample, index) => index === 0 || sample.contentOpacity >= samples[index - 1].contentOpacity), 'Content progress is not monotonic.');
  assert(runtimeErrors.length === 0, `Motion page errors: ${runtimeErrors.join(' | ')}`);
  await context.close();
  return samples;
}

async function inspectOutlineLifecycle(browser) {
  const results = [];
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // The setup page deliberately has no outlined card any more, so the outline geometry is
    // checked on the first outlined surface of the public home page (the hero card).
    const outlineUrl = process.env.CLOUDTRACE_QA_OUTLINE_URL || `${baseUrl}/`;
    await page.goto(outlineUrl, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => {
      const item = [...document.querySelectorAll('.motion-line-target')].find((node) => node.querySelector(':scope > .motion-outline'));
      return item?.dataset.motionState === 'settled';
    });
    const geometry = await page.evaluate(() => {
      const target = [...document.querySelectorAll('.motion-line-target')].find((item) => item.querySelector(':scope > .motion-outline'));
      const svg = target.querySelector(':scope > .motion-outline');
      const path = svg.querySelector('path');
      const start = path.getPointAtLength(0);
      const end = path.getPointAtLength(path.getTotalLength());
      const rect = svg.getBoundingClientRect();
      return {
        localWidth: svg.clientWidth, localHeight: svg.clientHeight,
        viewWidth: svg.viewBox.baseVal.width, viewHeight: svg.viewBox.baseVal.height,
        vectorEffect: getComputedStyle(path).vectorEffect,
        offset: Number.parseFloat(getComputedStyle(path).strokeDashoffset),
        endpointGap: Math.hypot(start.x - end.x, start.y - end.y),
        paths: target.querySelectorAll(':scope > .motion-outline path').length,
        closed: /Z\s*$/.test(path.getAttribute('d')),
        centerX: rect.left + rect.width / 2, topY: rect.top
      };
    });
    assert(Math.abs(geometry.localWidth - geometry.viewWidth) < 1 && Math.abs(geometry.localHeight - geometry.viewHeight) < 1, `${viewport.name}: transformed dimensions leaked into the viewBox.`);
    assert(geometry.vectorEffect === 'none' && geometry.closed && geometry.endpointGap < .01 && geometry.offset === 0 && geometry.paths === 1, `${viewport.name}: outline geometry does not close.`);
    await page.screenshot({path:path.join(outputDir,`${viewport.name}-setup-outline-closed.png`)});
    await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
    await settlePage(page);
    const initial = await page.evaluate(() => window.__cloudtraceMotionDebug.state());
    await page.evaluate(() => {
      const panel = document.createElement('section');
      panel.id = 'qa-motion-scroll';
      panel.setAttribute('data-motion-scroll-root', '');
      panel.style.cssText = 'position:fixed;top:120px;right:12px;width:280px;height:240px;overflow-y:auto;z-index:20;background:#f7f9fc;padding:8px';
      for (let i = 0; i < 6; i++) {
        const card = document.createElement('article');
        card.className = 'card';
        card.style.cssText = 'height:120px;margin-bottom:12px;padding:16px;border-radius:50% / 30%';
        card.innerHTML = `<p>局部滚动 ${i + 1}</p><button class="button" type="button">操作 ${i + 1}</button>`;
        panel.append(card);
      }
      document.body.append(panel);
    });
    await page.waitForFunction(() => document.querySelector('#qa-motion-scroll .card')?.dataset.motionState === 'settled');
    const roots = await page.evaluate(() => window.__cloudtraceMotionDebug.state());
    assert(roots.roots > initial.roots, `${viewport.name}: internal scroll root was not registered.`);
    // DOM test APIs deliberately exercise keyboard focus without a real account.
    await page.evaluate(() => document.querySelector('#qa-motion-scroll button').focus());
    await page.evaluate(() => document.querySelector('#qa-motion-scroll').scrollTop = 350);
    await page.waitForTimeout(100);
    const focusPreserved = await page.evaluate(() => document.querySelector('#qa-motion-scroll .card').dataset.motionState === 'settled');
    assert(focusPreserved, `${viewport.name}: focused content was hidden by a scroll callback.`);
    await page.evaluate(() => {
      document.activeElement.blur();
      document.querySelector('#qa-motion-scroll').scrollTop = 0;
    });
    const continuity = await page.evaluate(() => {
      const target = document.querySelector('#qa-motion-scroll .card');
      window.__cloudtraceMotionDebug.setProgress(target, .5);
      const before = window.__cloudtraceMotionDebug.timelineFor(target).animations[0].currentTime;
      window.__cloudtraceMotionDebug.setVisible(target, false);
      window.__cloudtraceMotionDebug.setVisible(target, true);
      const after = window.__cloudtraceMotionDebug.timelineFor(target).animations[0].currentTime;
      return {before,after};
    });
    assert(Math.abs(continuity.before - continuity.after) < 20, `${viewport.name}: reversal restarted at an endpoint.`);
    await page.evaluate(() => {
      const card = document.querySelector('#qa-motion-scroll .card');
      const button = document.createElement('button');
      button.className = 'button';
      button.type = 'button';
      button.textContent = '新操作';
      card.append(button);
      card.style.height = '150px';
    });
    await page.waitForFunction(() => document.querySelector('#qa-motion-scroll .card')?.dataset.motionState === 'settled');
    const refreshed = await page.evaluate(() => {
      const card = document.querySelector('#qa-motion-scroll .card');
      const svg = card.querySelector(':scope > .motion-outline');
      return {height:svg.viewBox.baseVal.height,local:svg.clientHeight,controls:card.querySelectorAll('.motion-child-control').length,paths:card.querySelectorAll(':scope > .motion-outline path').length};
    });
    assert(refreshed.paths === 1 && refreshed.controls === 2 && Math.abs(refreshed.height - refreshed.local) < 1, `${viewport.name}: dynamic content interrupted geometry or ownership.`);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.waitForTimeout(100);
    const reduced = await page.evaluate(() => ({
      active:document.querySelectorAll('.motion-line-target.is-motion-active').length,
      hidden:[...document.querySelectorAll('.motion-content,.motion-control-label')].filter(e=>Number(getComputedStyle(e).opacity)!==1).length
    }));
    assert(reduced.active === 0 && reduced.hidden === 0, `${viewport.name}: live reduced-motion toggle left content invisible.`);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.waitForTimeout(100);
    await page.evaluate(() => document.querySelector('#qa-motion-scroll').remove());
    await page.waitForTimeout(100);
    const removed = await page.evaluate(() => window.__cloudtraceMotionDebug.state());
    assert(removed.registered === initial.registered && removed.roots === initial.roots, `${viewport.name}: detached scroll root leaked registrations.`);
    await page.evaluate(() => window.CloudtraceMotion.dispose());
    const disposed = await page.evaluate(() => window.__cloudtraceMotionDebug.state());
    assert(disposed.disposed && disposed.registered === 0 && disposed.roots === 0 && disposed.pending === 0 && disposed.queueTimers === 0 && disposed.active.surface === 0 && disposed.active.light === 0, `${viewport.name}: motion disposal leaked resources.`);
    await page.evaluate(() => {window.CloudtraceMotion.init();window.CloudtraceMotion.init();});
    await settlePage(page);
    const restored = await page.evaluate(() => ({
      registered:window.__cloudtraceMotionDebug.state().registered,
      duplicates:[...document.querySelectorAll('.motion-line-target')].filter(e=>e.querySelectorAll(':scope > .motion-outline').length !== 1).length
    }));
    assert(restored.registered === initial.registered && restored.duplicates === 0, `${viewport.name}: repeated initialization duplicated outline layers.`);
    assert(errors.length === 0, `${viewport.name}: lifecycle errors: ${errors.join(' | ')}`);
    results.push({viewport:viewport.name,geometry,roots,focusPreserved,continuity,refreshed,reduced,removed,disposed,restored});
    await context.close();
  }
  return results;
}

async function inspectFirstPaint(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'no-preference' });
  const page = await context.newPage();
  await page.route('**/scripts/app.js*', async (route) => {
    await delay(360);
    await route.continue();
  });
  await page.goto(`${baseUrl}/`, { waitUntil: 'commit' });
  await page.locator('.home-intro__surface').waitFor({ state: 'attached' });
  await page.waitForTimeout(90);
  const result = await page.evaluate(() => {
    const hero = document.querySelector('.home-intro__surface');
    return {
      preparing: document.documentElement.classList.contains('motion-preparing'),
      opacity: Number(getComputedStyle(hero).opacity),
      width: hero.getBoundingClientRect().width,
      height: hero.getBoundingClientRect().height
    };
  });
  assert(result.preparing, 'The pre-paint motion guard was not active while app.js was delayed.');
  assert(result.opacity <= .01, 'The finished hero flashed before app.js initialized.');
  assert(result.width > 100 && result.height > 100, 'The pre-paint guard collapsed card layout.');
  await context.close();
  return result;
}

async function inspectReducedMotion(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
  const result = await page.evaluate(() => {
    const hero = document.querySelector('.home-intro__surface');
    const content = hero.querySelector('.motion-content');
    return {
      state: hero.dataset.motionState,
      clipPath: getComputedStyle(hero).clipPath,
      contentOpacity: Number(getComputedStyle(content).opacity),
      borderColor: getComputedStyle(hero).borderColor,
      preparing: document.documentElement.classList.contains('motion-preparing')
    };
  });
  assert(result.state === 'settled', 'Reduced-motion card was not settled immediately.');
  assert(result.clipPath === 'none', 'Reduced-motion card remains clipped.');
  assert(result.contentOpacity === 1, 'Reduced-motion content is not readable.');
  assert(!result.preparing, 'Reduced-motion mode entered the pre-paint animation guard.');
  await context.close();
  return result;
}

async function inspectAdminPreview(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'no-preference' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await page.goto(`${baseUrl}/admin/appearance/transitions/`, { waitUntil: 'networkidle' });
  await page.locator('[data-component-motion-settings]').scrollIntoViewIfNeeded();
  await page.waitForTimeout(1050);
  await page.locator('[data-component-motion-duration-range]').evaluate((input) => {
    input.value = '1100';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForFunction(() => document.documentElement.dataset.componentMotionDuration === '1100');
  await page.locator('input[name="component_motion_style"][value="snappy"]').check();
  await page.waitForTimeout(80);
  const settings = await page.evaluate(() => {
    const preview = document.querySelector('[data-motion-preview-card]');
    const controls = [...preview.querySelectorAll('.motion-child-control')];
    return {
      rootDuration: document.documentElement.dataset.componentMotionDuration,
      targetDuration: preview.dataset.motionDuration,
      style: document.documentElement.dataset.componentMotionStyle,
      rootPathCount: preview.querySelectorAll(':scope > .motion-outline > .motion-outline__path').length,
      childPathCounts: controls.map((control) => control.querySelectorAll(':scope > .motion-outline > .motion-outline__path').length),
      stageButtons: document.querySelectorAll('[data-component-motion-stage]').length
    };
  });
  assert(settings.rootDuration === '1100', 'Component duration control did not update the runtime.');
  assert(settings.targetDuration === '1100', 'Preview did not rebuild with the selected duration.');
  assert(settings.style === 'snappy', 'Damping preset did not update the runtime.');
  assert(settings.rootPathCount === 1 && settings.childPathCounts.every((count) => count === 1), 'Preview does not use one path per component.');
  assert(settings.stageButtons === 5, 'The staged preview controls are incomplete.');
  await page.locator('input[name="component_motion_style"][value="soft"]').check();
  await page.locator('[data-component-motion-duration-range]').evaluate((input) => {
    input.value = '920';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.locator('[data-component-motion-reverse]').click();
  await page.waitForFunction(() => document.querySelector('[data-motion-preview-card]')?.dataset.motionState === 'reversing');
  const before = await page.evaluate(() => {
    const preview = document.querySelector('[data-motion-preview-card]');
    const animation = window.__cloudtraceMotionDebug.timelineFor(preview)?.animations[0];
    return { currentTime: Number(animation.currentTime) };
  });
  await page.waitForTimeout(120);
  const after = await page.evaluate(() => {
    const preview = document.querySelector('[data-motion-preview-card]');
    const animation = window.__cloudtraceMotionDebug.timelineFor(preview)?.animations[0];
    return { currentTime: Number(animation.currentTime) };
  });
  assert(after.currentTime < before.currentTime, 'Preview reverse did not continue backward from its current frame.');
  await page.locator('[data-component-motion-stage="82"]').click();
  const staged = await page.evaluate(() => {
    const preview = document.querySelector('[data-motion-preview-card]');
    const surface = preview.querySelector(':scope > .motion-surface-layer');
    const control = preview.querySelector('.motion-child-control');
    return {
      pressed: document.querySelector('[data-component-motion-stage="82"]').getAttribute('aria-pressed'),
      surfaceOpacity: Number(getComputedStyle(surface).opacity),
      controlSurfaceOpacity: Number(getComputedStyle(control.querySelector(':scope > .motion-surface-layer')).opacity),
      contentOpacity: Number(getComputedStyle(preview.querySelector(':scope > .motion-content')).opacity)
    };
  });
  assert(staged.pressed === 'true' && staged.surfaceOpacity >= .998 && staged.controlSurfaceOpacity >= .998, 'The 82% stage does not complete both surfaces.');
  assert(staged.contentOpacity > .95, 'Content is still hidden at the outline-closed preview stage.');
  await page.locator('[data-component-motion-reduced]').click();
  const reduced = await page.evaluate(() => {
    const preview = document.querySelector('[data-motion-preview-card]');
    return {
      pressed: document.querySelector('[data-component-motion-reduced]').getAttribute('aria-pressed'),
      state: preview.dataset.motionState,
      clipPath: getComputedStyle(preview).clipPath,
      contentOpacity: Number(getComputedStyle(preview.querySelector('.motion-content')).opacity)
    };
  });
  assert(reduced.pressed === 'true' && reduced.state === 'settled', 'Preview reduced-motion toggle did not settle.');
  assert(reduced.clipPath === 'none' && reduced.contentOpacity === 1, 'Preview reduced-motion state is not readable.');
  await page.screenshot({ path: path.join(outputDir, 'admin-motion-settings-desktop.png') });
  assert(errors.length === 0, `Admin preview errors: ${errors.join(' | ')}`);
  await context.close();
  return { settings, reverse: { before, after }, staged, reduced };
}

async function inspectDynamicRegistration(browser) {
  const context = await browser.newContext({ viewport: { width: 768, height: 1024 }, reducedMotion: 'no-preference' });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
  const result = await page.evaluate(async () => {
    const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
    const host = document.querySelector('.home-modules');
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = '<div>动态插入卡片</div>';
    host.append(card);
    await wait(80);
    const registered = {
      paths: card.querySelectorAll(':scope > .motion-outline .motion-outline__path').length,
      contents: card.querySelectorAll(':scope > .motion-content').length,
      ready: card.classList.contains('is-outline-ready')
    };
    card.remove();
    return registered;
  });
  assert(result.paths === 1 && result.contents === 1 && result.ready, 'Dynamic motion target registration is incomplete.');
  await context.close();
  return result;
}

async function inspectMobileCapsuleAlignment(browser) {
  const results = [];
  for (const width of [390, 360, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 844 }, reducedMotion: 'no-preference' });
    const page = await context.newPage();
    await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1250);
    const result = await page.evaluate(() => {
      const nav = document.querySelector('[data-mobile-capsule-nav]');
      const item = nav.querySelector('.is-current');
      const indicator = nav.querySelector('.mobile-nav-indicator');
      const label = item.querySelector('small');
      const navRect = nav.getBoundingClientRect();
      const itemRect = item.getBoundingClientRect();
      const indicatorRect = indicator.getBoundingClientRect();
      const labelRect = label.getBoundingClientRect();
      const center = (rect) => rect.top + rect.height / 2;
      return {
        nav: { left: navRect.left, right: navRect.right, width: navRect.width },
        item: { top: itemRect.top, bottom: itemRect.bottom, height: itemRect.height },
        indicator: { top: indicatorRect.top, bottom: indicatorRect.bottom, height: indicatorRect.height },
        label: { top: labelRect.top, bottom: labelRect.bottom },
        indicatorLift: Number((itemRect.top - indicatorRect.top).toFixed(2)),
        centerDelta: Number((center(itemRect) - center(indicatorRect)).toFixed(2)),
        labelContained: labelRect.top >= indicatorRect.top && labelRect.bottom <= indicatorRect.bottom,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth
      };
    });
    assert(result.overflow === 0, `${width}px mobile capsule causes horizontal overflow.`);
    assert(result.nav.left >= 0 && result.nav.right <= width, `${width}px mobile capsule leaves the viewport.`);
    assert(result.indicatorLift >= 1 && result.indicatorLift <= 2.5, `${width}px indicator is not lifted by about 1.5px.`);
    assert(Math.abs(result.centerDelta - 1.5) <= 1, `${width}px indicator center is not optically aligned.`);
    assert(result.labelContained, `${width}px current label is outside the blue indicator.`);
    results.push({ width, ...result });
    await page.screenshot({ path: path.join(outputDir, `mobile-nav-${width}.png`) });
    await context.close();
  }
  return results;
}

// Home modules use content-visibility, so their real height is only known after the first
// scroll renders them. Center twice: once to render, once on the settled layout.
async function centerSection(section) {
  for (let pass = 0; pass < 2; pass += 1) {
    await section.evaluate((node) => node.scrollIntoView({ block: 'center', behavior: 'instant' }));
    await section.page().waitForTimeout(220);
  }
}

async function inspectHomeScrollReentry(browser) {
  const results = [];
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' });
    const page = await context.newPage();
    await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
    const section = page.locator('.home-about-v3');
    await centerSection(section);
    await page.waitForFunction(() => (
      [...document.querySelectorAll('.home-about-v3 > .motion-line-target')]
        .every((target) => target.dataset.motionState === 'settled')
    ));
    const entered = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.home-about-v3 > .motion-line-target')];
      return cards.map((card) => ({
        state: card.dataset.motionState,
        paths: card.querySelectorAll(':scope > .motion-outline > .motion-outline__path').length,
        contentOpacity: Math.min(...[...card.querySelectorAll('.motion-content')]
          .filter((content) => !content.closest('.motion-child-control'))
          .map((content) => Number(getComputedStyle(content).opacity)))
      }));
    });
    assert(entered.length === 2 && entered.every((card) => card.state === 'settled'), `${viewport.name} about cards did not enter.`);
    assert(entered.every((card) => card.paths === 1 && card.contentOpacity === 1), `${viewport.name} about cards are incomplete after entry.`);
    await page.screenshot({ path: path.join(outputDir, `${viewport.name}-home-about-visible.png`) });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(160);
    const exited = await page.evaluate(() => (
      [...document.querySelectorAll('.home-about-v3 > .motion-line-target')].map((card) => card.dataset.motionState)
    ));
    assert(exited.every((state) => state === 'idle' || state === 'reversing'), `${viewport.name} about cards did not exit after scrolling away.`);
    await centerSection(section);
    await page.waitForFunction(() => (
      [...document.querySelectorAll('.home-about-v3 > .motion-line-target')]
        .every((target) => target.dataset.motionState === 'settled')
    ));
    const reentered = await page.evaluate(() => (
      [...document.querySelectorAll('.home-about-v3 > .motion-line-target')].map((card) => ({
        state: card.dataset.motionState,
        contentOpacity: Math.min(...[...card.querySelectorAll('.motion-content')]
          .filter((content) => !content.closest('.motion-child-control'))
          .map((content) => Number(getComputedStyle(content).opacity))),
        active: card.classList.contains('is-motion-active')
      }))
    ));
    assert(reentered.every((card) => card.state === 'settled' && card.contentOpacity === 1 && !card.active), `${viewport.name} about cards did not re-enter cleanly.`);
    results.push({ viewport: viewport.name, entered, exited, reentered });
    await context.close();
  }
  return results;
}

async function inspectResponsivePages(browser, includeAdmin = true) {
  const results = [];
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
    page.on('console', (message) => {
      if (!['error', 'warning'].includes(message.type())) return;
      const text = message.text();
      // A closed registration policy answers /register/ with 403 on purpose;
      // the browser still logs a generic resource error for that response.
      if (/Failed to load resource/.test(text)) {
        try {
          if (new URL(page.url()).pathname === '/register/') return;
        } catch (_error) {
          /* Fall through and keep the console error when the URL is unusable. */
        }
      }
      errors.push(`${message.type()}: ${text}`);
    });
    page.on('response', (response) => {
      if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
    });
    for (const [name, route] of publicPages) {
      errors.length = 0;
      await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
      await settlePage(page);
      const layout = await inspectLayout(page);
      assert(layout.documentOverflow === 0, `${viewport.name}/${name} has document overflow.`);
      assert(layout.overflowNodes.length === 0, `${viewport.name}/${name} has overflow nodes: ${JSON.stringify(layout.overflowNodes)}`);
      assert(layout.cardOverflow.length === 0, `${viewport.name}/${name} has clipped cards: ${layout.cardOverflow.join(', ')}`);
      assert(layout.textOverflow.length === 0, `${viewport.name}/${name} has clipped text: ${JSON.stringify(layout.textOverflow)}`);
      assert(layout.outlineMissing === 0, `${viewport.name}/${name} has settled targets without outlines.`);
      assert(layout.componentCoverageMissing.length === 0, `${viewport.name}/${name} has cards or buttons outside the motion system: ${JSON.stringify(layout.componentCoverageMissing)}`);
      assert(layout.activeWillChange === 0, `${viewport.name}/${name} retained active will-change layers: ${JSON.stringify(layout.activeWillChangeTargets)}`);
      assert(errors.length === 0, `${viewport.name}/${name} runtime errors: ${errors.join(' | ')}`);
      results.push({ viewport: viewport.name, page: name, ...layout });
      if (['home', 'blog', 'article-comments', 'moment-comments', 'links', 'admin-login'].includes(name)) {
        await page.screenshot({ path: path.join(outputDir, `${viewport.name}-${name}.png`), fullPage: true });
      }
      if (['article-comments', 'moment-comments'].includes(name)) {
        const comments = page.locator('#comments');
        await comments.scrollIntoViewIfNeeded();
        await page.waitForTimeout(850);
        await page.screenshot({ path: path.join(outputDir, `${viewport.name}-${name}-visible.png`) });
        const visibleLayout = await inspectLayout(page);
        assert(visibleLayout.documentOverflow === 0, `${viewport.name}/${name} visible comment state has document overflow.`);
        assert(visibleLayout.overflowNodes.length === 0, `${viewport.name}/${name} visible comment state has overflow nodes: ${JSON.stringify(visibleLayout.overflowNodes)}`);
        assert(visibleLayout.textOverflow.length === 0, `${viewport.name}/${name} visible comment state has clipped text: ${JSON.stringify(visibleLayout.textOverflow)}`);
      }
    }
    if (!includeAdmin) {
      await context.close();
      continue;
    }
    await login(page);
    await page.goto(`${baseUrl}/admin/appearance/transitions/`, { waitUntil: 'networkidle' });
    await settlePage(page);
    const adminLayout = await inspectLayout(page);
    assert(adminLayout.documentOverflow === 0, `${viewport.name}/admin-motion has document overflow.`);
    assert(adminLayout.overflowNodes.length === 0, `${viewport.name}/admin-motion has overflow nodes: ${JSON.stringify(adminLayout.overflowNodes)}`);
    assert(adminLayout.cardOverflow.length === 0, `${viewport.name}/admin-motion has clipped cards.`);
    assert(adminLayout.textOverflow.length === 0, `${viewport.name}/admin-motion has clipped text.`);
    assert(adminLayout.componentCoverageMissing.length === 0, `${viewport.name}/admin-motion has cards or buttons outside the motion system: ${JSON.stringify(adminLayout.componentCoverageMissing)}`);
    assert(adminLayout.activeWillChange === 0, `${viewport.name}/admin-motion retained active will-change layers: ${JSON.stringify(adminLayout.activeWillChangeTargets)}`);
    assert(errors.length === 0, `${viewport.name}/admin-motion runtime errors: ${errors.join(' | ')}`);
    await page.locator('[data-component-motion-settings]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(1050);
    await page.screenshot({ path: path.join(outputDir, `${viewport.name}-admin-motion.png`) });
    results.push({ viewport: viewport.name, page: 'admin-motion', ...adminLayout });
    await context.close();
  }
  return results;
}

async function inspectAdminRouteMatrix(browser) {
  const results = [];
  const startIndex = Math.max(0, adminPages.findIndex(([name]) => name === adminStartAt));
  const routes = adminStartAt ? adminPages.slice(startIndex) : adminPages;
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) errors.push(`${message.type()}: ${message.text()}`);
    });
    page.on('response', (response) => {
      if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
    });
    await login(page);
    for (const [name, route] of routes) {
      errors.length = 0;
      const response = await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
      assert(response && response.status() < 400, `${viewport.name}/admin-${name} did not render.`);
      await settlePage(page);
      const layout = await inspectLayout(page);
      assert(layout.documentOverflow === 0, `${viewport.name}/admin-${name} has document overflow.`);
      assert(layout.overflowNodes.length === 0, `${viewport.name}/admin-${name} has overflow nodes: ${JSON.stringify(layout.overflowNodes)}`);
      assert(layout.cardOverflow.length === 0, `${viewport.name}/admin-${name} has clipped cards: ${layout.cardOverflow.join(', ')}`);
      assert(layout.textOverflow.length === 0, `${viewport.name}/admin-${name} has clipped text: ${JSON.stringify(layout.textOverflow)}`);
      assert(layout.outlineMissing === 0, `${viewport.name}/admin-${name} has settled targets without outlines.`);
      assert(layout.componentCoverageMissing.length === 0, `${viewport.name}/admin-${name} has cards or buttons outside the motion system: ${JSON.stringify(layout.componentCoverageMissing)}`);
      assert(layout.activeWillChange === 0, `${viewport.name}/admin-${name} retained active will-change layers.`);
      assert(errors.length === 0, `${viewport.name}/admin-${name} runtime errors: ${errors.join(' | ')}`);
      results.push({ viewport: viewport.name, page: name, ...layout });
    }
    await context.close();
  }
  return results;
}

async function inspectEditorSelectMenus(browser) {
  const results = [];
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'no-preference' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) errors.push(`${message.type()}: ${message.text()}`);
    });
    await login(page);
    await page.goto(`${baseUrl}/admin/pages/new/`, { waitUntil: 'networkidle' });
    await settlePage(page);
    const triggers = page.locator('.visual-editor__toolbar .themed-select__trigger');
    const count = await triggers.count();
    assert(count >= 2, `${viewport.name}/page-editor did not build the themed toolbar selects.`);
    for (let index = 0; index < count; index += 1) {
      const trigger = triggers.nth(index);
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();
      const shell = trigger.locator('..');
      const menu = shell.locator('.themed-select__menu');
      await menu.waitFor({ state: 'visible' });
      await page.waitForTimeout(220);
      const bounds = await menu.boundingBox();
      assert(bounds, `${viewport.name}/page-editor select ${index + 1} has no visible menu bounds.`);
      assert(bounds.x >= -1 && bounds.x + bounds.width <= viewport.width + 1,
        `${viewport.name}/page-editor select ${index + 1} menu exceeds the viewport: ${JSON.stringify(bounds)}`);
      assert(await page.locator('.themed-select.is-open').count() === 1,
        `${viewport.name}/page-editor opened more than one themed select.`);
      const layout = await inspectLayout(page);
      assert(layout.documentOverflow === 0 && layout.overflowNodes.length === 0,
        `${viewport.name}/page-editor open select overflow: ${JSON.stringify(layout.overflowNodes)}`);
      if (index === 0) {
        await page.screenshot({ path: path.join(outputDir, `${viewport.name}-page-editor-select-open.png`) });
      }
      await page.mouse.click(3, 3);
      await page.waitForTimeout(220);
      assert(await menu.isHidden(), `${viewport.name}/page-editor select ${index + 1} did not close outside.`);
    }
    assert(errors.length === 0, `${viewport.name}/page-editor select runtime errors: ${errors.join(' | ')}`);
    results.push({ viewport: viewport.name, selectCount: count, openStatePassed: true, outsideClosePassed: true });
    await context.close();
  }
  return results;
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath });
  try {
    const report = motionOnly ? {
      generatedAt: new Date().toISOString(), baseUrl,
      motionSamples: await sampleHomeMotion(browser),
      outlineLifecycle: await inspectOutlineLifecycle(browser),
      reducedMotion: await inspectReducedMotion(browser), adminRouteMatrix: []
    } : adminMatrixOnly ? {
      generatedAt: new Date().toISOString(),
      baseUrl,
      adminRouteMatrix: await inspectAdminRouteMatrix(browser)
    } : editorSelectOnly ? {
      generatedAt: new Date().toISOString(),
      baseUrl,
      editorSelectMenus: await inspectEditorSelectMenus(browser),
      adminRouteMatrix: []
    } : {
      generatedAt: new Date().toISOString(),
      baseUrl,
      firstPaint: await inspectFirstPaint(browser),
      motionSamples: await sampleHomeMotion(browser),
      reducedMotion: await inspectReducedMotion(browser),
      outlineLifecycle: await inspectOutlineLifecycle(browser),
      adminPreview: publicOnly ? null : await inspectAdminPreview(browser),
      dynamicRegistration: await inspectDynamicRegistration(browser),
      mobileCapsuleAlignment: await inspectMobileCapsuleAlignment(browser),
      homeScrollReentry: await inspectHomeScrollReentry(browser),
      responsivePages: await inspectResponsivePages(browser, !publicOnly),
      editorSelectMenus: publicOnly ? [] : await inspectEditorSelectMenus(browser),
      adminRouteMatrix: publicOnly ? [] : await inspectAdminRouteMatrix(browser)
    };
    fs.writeFileSync(path.join(outputDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
    console.log(JSON.stringify({
      ok: true,
      outputDir,
      motionSamples: report.motionSamples?.length || 0,
      responsivePages: report.responsivePages?.length || 0,
      adminRouteStates: report.adminRouteMatrix.length
    }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
