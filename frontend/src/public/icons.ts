/* The icon ids of the hand-drawn sprite (ui/sprite.svg). The server's vocabulary (backend/app/defaults.py ICONS) is a subset of these. */
export const ICONS: ReadonlySet<string> = new Set([
  'home', 'book', 'chat', 'smile', 'search', 'menu', 'more', 'close', 'arrow-r', 'arrow-l', 'arrow-u', 'arrow-d', 'link', 'calendar', 'clock',
  'tag', 'folder', 'copy', 'check', 'image', 'star', 'pin', 'external', 'list', 'bulb', 'alert', 'heart', 'quote', 'code', 'mail',
  'info', 'sliders', 'sparkle', 'grid', 'rows', 'moon',
])

export const DOODLES = ['star', 'heart', 'sparkle', 'flower', 'paw', 'wave', 'loop'] as const
