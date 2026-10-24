/* Design-system gallery: swatches, live contrast table, icon / doodle / mood lists, dialog demo. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const root = document.documentElement;

const probe = document.createElement('span');
probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none';
document.body.append(probe);

const toRgb = (prop, v) => {
  probe.style[prop] = '';
  probe.style[prop] = `var(${v})`;
  const m = getComputedStyle(probe)[prop].match(/[\d.]+/g).map(Number);
  return m.slice(0, 3);
};
const hex = (rgb) => `#${rgb.map((x) => Math.round(x).toString(16).padStart(2, '0')).join('')}`;
const lum = ([r, g, b]) => {
  const f = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

const SWATCHES = [
  ['--sky-25', '页面底 · 极浅蓝'], ['--sky-50', '浅蓝 50'], ['--sky-100', '浅蓝 100 · 选中 / 填充'], ['--sky-200', '浅蓝 200 · 轨道'],
  ['--sky-300', '浅蓝 300 · 仅图形'], ['--line', '线（唯一的线色）'], ['--paper', '卡片白'],
  ['--mist-50', '浅灰 50'], ['--mist-100', '浅灰 100 · 代码底'], ['--mist-200', '浅灰 200'],
  ['--rose-50', '浅粉 50'], ['--rose-100', '浅粉 100'], ['--rose-200', '浅粉 200'], ['--rose-300', '浅粉 300 · 仅图形'], ['--rose-line', '粉色线（只配粉色填充）'],
  ['--ink', '文字 · 墨蓝灰'], ['--ink-2', '次要文字'], ['--link', '链接'], ['--accent-ink', '粉底上的文字'], ['--ring', '键盘焦点环'],
];

function swatches() {
  const box = $('[data-swatches]');
  const TEXT = ['--ink', '--ink-2', '--link', '--accent-ink'];
  box.innerHTML = SWATCHES.map(([v, name]) => {
    // text colours are shown as text on white, not as filled blocks: nothing on these pages is a dark block
    let chip = `<div class="swatch__chip" style="background:var(${v})"></div>`;
    if (TEXT.includes(v)) chip = `<div class="swatch__chip" style="display:grid;place-items:center;background:var(--paper);color:var(${v});font-size:22px;font-weight:700">Aa 文字</div>`;
    if (v === '--ring') chip = `<div class="swatch__chip" style="display:grid;place-items:center;background:var(--paper)"><span style="padding:6px 16px;border-radius:12px;outline:2px solid var(--ring);outline-offset:3px;box-shadow:0 0 0 5px var(--fill);font-weight:700">焦点</span></div>`;
    return `<div class="swatch">${chip}<b>${name}</b><small data-hex="${v}"></small></div>`;
  }).join('');
}

function paint() {
  $$('[data-hex]').forEach((el) => { el.textContent = `${el.dataset.hex}  ${hex(toRgb('backgroundColor', el.dataset.hex))}`; });
  $$('[data-contrast] tr').forEach((tr) => {
    const fg = tr.dataset.fg; const bg = tr.dataset.bg; const min = Number(tr.dataset.min);
    const r = ratio(toRgb('color', fg), toRgb('backgroundColor', bg));
    const ok = r >= min;
    tr.innerHTML = `<td>${tr.firstElementChild ? tr.firstElementChild.textContent : ''}</td>`
      + `<td><span ${min < 4.5 ? 'data-audit-skip ' : ''}style="display:inline-block;padding:4px 14px;border-radius:10px;border:1px solid var(--line);color:var(${fg});background:var(${bg});font-weight:700">Aa 示例文字</span></td>`
      + `<td><b>${r.toFixed(2)}:1</b></td><td>≥ ${min}:1</td><td><span class="tag ${ok ? 'tag--sky' : 'tag--rose'}">${ok ? '通过' : '不通过'}</span></td>`;
  });
}

function lists() {
  const symbols = (prefix) => $$(`symbol[id^="${prefix}"]`).map((s) => s.id);
  const icons = $('[data-icons]');
  icons.innerHTML = symbols('i-').map((id) => `<div><svg class="i" aria-hidden="true"><use href="#${id}"/></svg>${id.slice(2)}</div>`).join('')
    + symbols('d-').map((id) => `<div><svg class="doodle" aria-hidden="true"><use href="#${id}"/></svg>${id}</div>`).join('');
  $('[data-doodles]').innerHTML = symbols('d-').map((id, k) => `<svg class="doodle" style="color:var(${k % 2 ? '--sky-300' : '--rose-300'});width:52px;height:52px" aria-hidden="true"><use href="#${id}"/></svg>`).join('');
  const names = { 'mood-happy': '开心', 'mood-energy': '元气', 'mood-calm': '平静', 'mood-sleepy': '犯困', 'mood-think': '思考', 'mood-party': '庆祝' };
  $('[data-moods]').innerHTML = symbols('mood-').map((id) => `<span class="mood"><svg style="width:34px;height:34px" aria-hidden="true"><use href="#${id}"/></svg>${names[id] || id}</span>`).join('');
}

$$('[data-open-dialog]').forEach((b) => b.addEventListener('click', () => $(b.dataset.openDialog).showModal()));
$$('[data-close-dialog]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
$$('dialog.dialog').forEach((d) => d.addEventListener('click', (e) => { if (e.target === d) d.close(); }));

swatches(); lists(); paint();
new MutationObserver(paint).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
