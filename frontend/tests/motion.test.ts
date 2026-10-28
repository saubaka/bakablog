import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import Dropdown from '../src/public/components/Dropdown.vue'
import { dirOf } from '../src/public/motion'
import { useSlider } from '../src/public/slider'

const options = [{ value: 'new', label: '最新优先' }, { value: 'old', label: '最早优先' }, { value: 'views', label: '最多阅读' }]
const press = async (el: Element, key: string): Promise<void> => { await el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })); await nextTick() }

describe('which way a change reads', () => {
  it('a later value comes from the right, an earlier one from the left, the same one just fades', () => {
    expect(dirOf(3, 2)).toBe('next')
    expect(dirOf(1, 2)).toBe('prev')
    expect(dirOf(2, 2)).toBe('none')
    expect(dirOf('2026-10', '2026-09')).toBe('next')
    expect(dirOf('2026-08', '2026-09')).toBe('prev')
  })
})

describe('Dropdown (the site\'s own drop-down)', () => {
  const make = (value = 'new', extra: Record<string, unknown> = {}) => mount(Dropdown, { props: { modelValue: value, options, label: '排序', ...extra }, global: { stubs: { transition: false } }, attachTo: document.body })
  afterEach(() => { document.body.innerHTML = '' })

  it('shows the current choice on a combobox button and keeps the list closed', () => {
    const w = make('old')
    const btn = w.get('button')
    expect(btn.attributes('role')).toBe('combobox')
    expect(btn.attributes('aria-label')).toBe('排序')
    expect(btn.attributes('aria-expanded')).toBe('false')
    expect(btn.text()).toBe('最早优先')
    expect(w.find('[role="listbox"]').exists()).toBe(false)
    w.unmount()
  })

  it('opens with the arrow keys, moves with them, and chooses with Enter', async () => {
    const w = make('new')
    const btn = w.get('button')
    await press(btn.element, 'ArrowDown')
    expect(btn.attributes('aria-expanded')).toBe('true')
    const list = w.get('[role="listbox"]')
    expect(list.findAll('[role="option"]').map((o) => o.attributes('aria-selected'))).toEqual(['true', 'false', 'false'])
    expect(btn.attributes('aria-controls')).toBe(list.attributes('id'))
    expect(btn.attributes('aria-activedescendant')).toBe(list.findAll('[role="option"]')[0]?.attributes('id'))
    await press(btn.element, 'ArrowDown')
    await press(btn.element, 'ArrowDown')
    expect(btn.attributes('aria-activedescendant')).toBe(list.findAll('[role="option"]')[2]?.attributes('id'))
    await press(btn.element, 'ArrowDown')                                        // wraps round
    expect(btn.attributes('aria-activedescendant')).toBe(list.findAll('[role="option"]')[0]?.attributes('id'))
    await press(btn.element, 'End')
    await press(btn.element, 'Enter')
    expect(w.emitted('update:modelValue')).toEqual([['views']])
    expect(btn.attributes('aria-expanded')).toBe('false')
    w.unmount()
  })

  it('Escape closes it without choosing; choosing the current value says nothing', async () => {
    const w = make('new')
    const btn = w.get('button')
    await btn.trigger('click')
    expect(btn.attributes('aria-expanded')).toBe('true')
    await press(btn.element, 'Escape')
    expect(btn.attributes('aria-expanded')).toBe('false')
    await btn.trigger('click')
    await press(btn.element, 'Enter')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    w.unmount()
  })

  it('a press somewhere else closes it, a click on an option chooses it', async () => {
    const w = make('new')
    const btn = w.get('button')
    await btn.trigger('click')
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(btn.attributes('aria-expanded')).toBe('false')
    await btn.trigger('click')
    await w.findAll('[role="option"]')[1]?.trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['old']])
    w.unmount()
  })

  it('a disabled drop-down never opens', async () => {
    const w = make('new', { disabled: true })
    await press(w.get('button').element, 'ArrowDown')
    expect(w.find('[role="listbox"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('useSlider', () => {
  const Box = defineComponent({
    props: { current: { type: String, default: 'b' } },
    setup(props) {
      const box = ref<HTMLElement | null>(null)
      useSlider(box, '[aria-current]', () => props.current)
      return () => h('div', { ref: box }, [h('i', { class: 'slide' }), ...['a', 'b'].map((k) => h('a', { key: k, 'aria-current': k === props.current ? 'page' : undefined }, k))])
    },
  })

  it('places the marker on the current item, moves it only after the first placement, and clears when nothing is current', async () => {
    const w = mount(Box, { attachTo: document.body })
    await nextTick()
    expect(w.element.dataset.slide).toBe('placed')
    expect(w.element.style.getPropertyValue('--w')).toBe('0px')
    await new Promise((r) => setTimeout(r, 50))
    expect(w.element.dataset.slide).toBe('set')
    await w.setProps({ current: 'none' })
    await nextTick()
    expect(w.element.dataset.slide).toBeUndefined()
    w.unmount()
  })
})
