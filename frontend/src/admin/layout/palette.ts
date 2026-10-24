import { ref } from 'vue'

export const paletteOpen = ref(false)
export const openPalette = (): void => { paletteOpen.value = true }
export const closePalette = (): void => { paletteOpen.value = false }
