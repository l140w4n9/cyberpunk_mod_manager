/** 依赖列表默认展示条数，超出可展开 */
export const DEPS_PREVIEW_COUNT = 6

/** 依赖 chip 样式：可选未安装为黄色警告，必需未安装为红色 */
export function depChipClass(dep) {
  if (dep.installed) return 'ok'
  const isOptional = dep.source === 'optional' || dep.optional === true
  return isOptional ? 'warn' : 'miss'
}

export function depTypeLabel(dep) {
  const isOptional = dep.source === 'optional' || dep.optional === true
  return isOptional ? '可选' : '必需'
}

export function filterMods(mods, mode) {
  if (mode === 'pending') {
    return mods.filter((m) => m.status !== 'installed')
  }
  if (mode === 'incomplete') {
    return mods.filter(
      (m) => m.status === 'installed' && m.dependencies_satisfied === false,
    )
  }
  // installed: 已安装且依赖满足
  return mods.filter(
    (m) => m.status === 'installed' && m.dependencies_satisfied !== false,
  )
}
