/* Motion lab: controls, live numbers and a self-test that checks the scroll engine against the rules in js/fx.js. */
import FX from './fx.js';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const root = document.documentElement;

/* ---- controls */
const syncTags = () => $$('[data-motion]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.motion === FX.getMode())));
$$('[data-motion]').forEach((b) => b.addEventListener('click', () => { FX.setMode(b.dataset.motion); syncTags(); }));
syncTags();
$('[data-debug]').addEventListener('change', (e) => FX.debug(e.target.checked));
$$('[data-jump]').forEach((b) => b.addEventListener('click', () => $(b.dataset.jump).scrollIntoView({ block: 'center', behavior: 'instant' })));

const stats = $('[data-stats]');
setInterval(() => {
  const s = FX.stats();
  stats.textContent = `元素 ${s.items} · 活跃 ${s.active} · 每帧 ${s.frameMs} ms`;
}, 300);

const bw = $('[data-bwrange]'); const bwOut = $('[data-bw]');
bw.addEventListener('input', () => {
  bwOut.textContent = bw.value;
  $$('[data-wrap]').forEach((w) => w.style.setProperty('--bw', `${bw.value}px`));
  FX.refresh();
});
$$('[data-wrap]').forEach((w) => w.style.setProperty('--bw', `${bw.value}px`));

/* ---- fling: a fast programmatic scroll to the bottom and back, like a flick on a phone */
function scrollTween(to, ms) {
  return new Promise((resolve) => {
    const from = scrollY; const t0 = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - t0) / ms);
      const e = p < 0.5 ? 2 * p * p : 1 - ((-2 * p + 2) ** 2) / 2;
      scrollTo({ top: from + (to - from) * e, behavior: 'instant' });
      if (p < 1) requestAnimationFrame(step); else resolve();
    };
    requestAnimationFrame(step);
  });
}
$('[data-fling]').addEventListener('click', async () => {
  const max = root.scrollHeight - innerHeight;
  await scrollTween(max, 520); await scrollTween(0, 520);
});

/* ---- self-test */
const BLOCKS = ['#t-rise', '#t-fade', '#t-slide', '#t-mask', '#t-text', '#t-tall', '#t-spine'];
$('[data-selftest]').addEventListener('click', async () => {
  const out = $('[data-report]');
  out.hidden = false; out.textContent = '检查中……';
  if (FX.getMode() === 'off') { out.textContent = '动效处于「关闭」状态，没有可检查的内容。请先切到「标准」。'; return; }
  const lines = []; let bad = 0;
  const vh = root.clientHeight;
  // after a jump the elements glide for at least ~0.4 s: look at the result once they have arrived
  const settle = async () => { await wait(60); const t0 = performance.now(); while (FX.stats().moving && performance.now() - t0 < 2500) await wait(30); await wait(30); };
  // 1. at rest in the middle of the screen every element must be fully there
  for (const sel of BLOCKS) {
    $(sel).scrollIntoView({ block: 'center', behavior: 'instant' });
    await settle();
    const els = $$('[data-fx]', $(sel)).filter((el) => !['drift', 'spine'].includes(el.dataset.fx));
    const mid = els.filter((el) => { const r = el.getBoundingClientRect(); return r.top >= vh * 0.2 && r.top <= vh * 0.58 && r.height < vh * 0.5; });
    const fail = mid.filter((el) => { const s = FX.read(el); return !s || s.in < 1 || s.out > 0 || Number(getComputedStyle(el).opacity) < 0.999; });
    bad += fail.length;
    lines.push(`${fail.length ? '✗' : '✓'} ${sel.slice(3)}：屏幕中部 ${mid.length} 个元素，${fail.length ? `${fail.length} 个没有完全显示` : '全部完全显示'}`);
  }
  // 2. a fling must end in the right picture
  const max = root.scrollHeight - innerHeight;
  await scrollTween(max, 400); await scrollTween(Math.round(max * 0.5), 400); await settle();
  const stuck = $$('[data-fx]').filter((el) => {
    if (['drift', 'spine'].includes(el.dataset.fx)) return false;
    const r = el.getBoundingClientRect();
    return r.top >= vh * 0.2 && r.top <= vh * 0.58 && r.height < vh * 0.5 && (FX.read(el).in < 1 || FX.read(el).out > 0);
  });
  bad += stuck.length;
  lines.push(`${stuck.length ? '✗' : '✓'} 甩动之后：屏幕中部没有卡在半透明的元素（${stuck.length} 个异常）`);
  // 3. jumping straight to the bottom and back to the top
  scrollTo({ top: max, behavior: 'instant' }); await settle();
  scrollTo({ top: 0, behavior: 'instant' }); await settle();
  const head = $$('.page-head [data-fx]').filter((el) => FX.read(el)).filter((el) => FX.read(el).in < 1);
  bad += head.length;
  lines.push(`${head.length ? '✗' : '✓'} 直接跳到底部再跳回顶部：页首元素 ${head.length ? `有 ${head.length} 个没有恢复` : '全部恢复'}`);
  // 4. a big jump must not pop: right after it nothing in the middle of the screen is complete yet, then everything arrives
  scrollTo({ top: 0, behavior: 'instant' }); await settle();
  $(BLOCKS[BLOCKS.length - 1]).scrollIntoView({ block: 'center', behavior: 'instant' }); await wait(50);
  const midNow = $$('[data-fx]').filter((el) => {
    if (['drift', 'spine'].includes(el.dataset.fx)) return false;
    const r = el.getBoundingClientRect();
    return r.top >= vh * 0.2 && r.top <= vh * 0.58 && r.height < vh * 0.5 && FX.read(el);
  });
  const popped = midNow.filter((el) => FX.read(el).in >= 1).length;
  const started = midNow.filter((el) => FX.read(el).in > 0).length;
  await settle();
  const arrived = midNow.filter((el) => FX.read(el).in >= 1 && FX.read(el).out <= 0).length;
  const okJump = midNow.length > 0 && popped === 0 && started > 0 && arrived === midNow.length;
  if (!okJump) bad += 1;
  lines.push(`${okJump ? '✓' : '✗'} 大幅跳转不瞬移：跳转后 50 ms 时屏幕中部 ${midNow.length} 个元素没有一个已完成（${popped} 个已瞬间出现），已经开始过渡 ${started} 个，稍后全部到位（${arrived}/${midNow.length}）`);
  // 5. tall element never leaves
  $('#t-tall').scrollIntoView({ block: 'end', behavior: 'instant' }); await settle();
  const tall = $('#t-tall [data-fx]');
  const st = FX.read(tall);
  const okTall = st && st.tall && st.out === 0;
  if (!okTall) bad += 1;
  lines.push(`${okTall ? '✓' : '✗'} 超高元素：被识别为超高，退场进度保持 0`);
  const s = FX.stats();
  lines.push(`每帧脚本耗时 ${s.frameMs} ms（目标 < 4 ms）`);
  out.innerHTML = `<b>${bad ? `有 ${bad} 项没通过` : '全部通过'}</b><br>${lines.join('<br>')}`;
  scrollTo({ top: 0, behavior: 'instant' });
});
