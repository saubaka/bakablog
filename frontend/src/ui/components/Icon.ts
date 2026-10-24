import { defineComponent, h } from 'vue'

/** A hand-drawn icon from the sprite (ui/sprite.svg, ids "i-*"). Size and colour come from CSS: .i is 1.25em and uses currentColor. */
export default defineComponent({
  name: 'Icon',
  props: { name: { type: String, required: true } },
  setup(props) {
    return () => h('svg', { class: 'i', 'aria-hidden': 'true', focusable: 'false' }, [h('use', { href: `#i-${props.name}` })])
  },
})
