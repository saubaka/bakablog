import { defineComponent, h } from 'vue'

/** An icon of the shared sprite ("search" -> i-search) or of the admin sprite ("a-edit"). Size and colour come from CSS (.i). */
export default defineComponent({
  name: 'AIcon',
  props: { name: { type: String, required: true } },
  setup(props) {
    return () => h('svg', { class: 'i', 'aria-hidden': 'true', focusable: 'false' }, [h('use', { href: props.name.startsWith('a-') ? `#${props.name}` : `#i-${props.name}` })])
  },
})
