import { defineComponent, h, type VNode } from 'vue'
import { words, WRAP_MAX } from './text'

/** Keeps the words of a plain title together so lines break between words, never inside one (差|点).
    Renders text nodes and <span class="ph"> pieces only, wrapped in one inline run, so it also works inside flex and grid containers. */
export default defineComponent({
  name: 'Phrase',
  props: { text: { type: String, required: true } },
  setup(props) {
    return () => {
      const toks = words(props.text)
      const out: (VNode | string)[] = []
      toks.forEach((tk, i) => {
        if (tk.space) { out.push(' '); return }
        out.push(tk.t.length > WRAP_MAX ? tk.t : h('span', { class: 'ph' }, tk.t))
        const next = toks[i + 1]
        if (next && !next.space) out.push(h('wbr'))
      })
      return h('span', { class: 'ph-run' }, out)
    }
  },
})
