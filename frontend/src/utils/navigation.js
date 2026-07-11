export const VALID_VIEWS = new Set([
  'agent',
  'settings',
  'mods',
  'mods-pending',
  'mods-incomplete',
  'collections',
  'maintenance',
])

export function viewFromHash() {
  const raw = (window.location.hash || '').replace(/^#\/?/, '').trim()
  return VALID_VIEWS.has(raw) ? raw : null
}

export function readSavedView() {
  const fromHash = viewFromHash()
  if (fromHash) return fromHash
  try {
    const saved = localStorage.getItem('cpmm_active_view')
    if (saved && VALID_VIEWS.has(saved)) return saved
  } catch {
    /* ignore */
  }
  return 'agent'
}

export function writeView(view) {
  if (!VALID_VIEWS.has(view)) return
  const nextHash = `#/${view}`
  if (window.location.hash !== nextHash) {
    window.location.hash = nextHash
  }
  try {
    localStorage.setItem('cpmm_active_view', view)
  } catch {
    /* ignore */
  }
}

export function installHashListener(callback) {
  const handler = () => {
    const view = viewFromHash()
    if (view) callback(view)
  }
  window.addEventListener('hashchange', handler)
  return () => window.removeEventListener('hashchange', handler)
}
