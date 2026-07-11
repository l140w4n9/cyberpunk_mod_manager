const STORAGE_KEY = 'cpmm_agent_handoff'

export function queueAgentHandoff(payload) {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        ...payload,
        createdAt: Date.now(),
      }),
    )
  } catch {
    /* ignore */
  }
}

export function consumeAgentHandoff() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    sessionStorage.removeItem(STORAGE_KEY)
    return JSON.parse(raw)
  } catch {
    sessionStorage.removeItem(STORAGE_KEY)
    return null
  }
}

function formatModLines(items, formatter, limit = 20) {
  if (!items?.length) return []
  const lines = items.slice(0, limit).map(formatter)
  if (items.length > limit) {
    lines.push(`… 另有 ${items.length - limit} 个未列出`)
  }
  return lines
}

export function buildMaintenanceHandoffMessage({ report, updatesResult }) {
  if (report) {
    const issues = report.issues || {}
    const parts = [
      '请根据以下健康审查结果，调用工具自动处理问题。',
      '优先级：1) 依赖不全 → install_mod_with_dependencies；2) 待安装 → install_mod_with_dependencies；3) 有更新 → install_mod_with_dependencies（强制重装，skip_installed=false）。',
      '每步汇报进展，全部完成后汇总成功/失败/跳过。',
      '',
      `【概览】依赖不全 ${issues.incomplete_count || 0}，待安装 ${issues.pending_count || 0}，有更新 ${issues.update_count || 0}`,
    ]

    if (report.llm_report?.summary) {
      parts.push(`【审查结论】${report.llm_report.summary}`)
    }

    const incompleteLines = formatModLines(
      report.incomplete,
      (m) => `- #${m.nexus_mod_id} ${m.name}（缺 ${m.dependencies_missing_count} 个依赖）`,
    )
    if (incompleteLines.length) {
      parts.push('', '【依赖不全模组】', ...incompleteLines)
    }

    const pendingLines = formatModLines(
      report.pending,
      (m) => `- #${m.nexus_mod_id} ${m.name}（${m.status}）`,
      15,
    )
    if (pendingLines.length) {
      parts.push('', '【待安装模组】', ...pendingLines)
    }

    const updateItems = report.updates?.length ? report.updates : updatesResult?.updates
    const updateLines = formatModLines(
      updateItems,
      (u) => `- #${u.mod_id} ${u.name}${u.latest_version ? ` → ${u.latest_version}` : ''}`,
      15,
    )
    if (updateLines.length) {
      parts.push('', '【有更新模组】', ...updateLines)
    }

    return parts.join('\n')
  }

  if (updatesResult?.updates?.length) {
    const parts = [
      '请根据以下更新检查结果，对有更新的已安装模组执行强制重装（install_mod_with_dependencies，skip_installed=false）。',
      `共 ${updatesResult.update_count || updatesResult.updates.length} 个模组有更新。`,
      '',
      '【有更新模组】',
      ...formatModLines(
        updatesResult.updates,
        (u) => `- #${u.mod_id} ${u.name}${u.installed_version && u.latest_version ? `（${u.installed_version} → ${u.latest_version}）` : ''}`,
      ),
      '',
      '逐项执行并汇总结果。',
    ]
    return parts.join('\n')
  }

  return ''
}

export function hasMaintenanceHandoffData({ report, updatesResult }) {
  if (report?.issues) {
    const issues = report.issues
    if (
      issues.incomplete_count > 0 ||
      issues.pending_count > 0 ||
      issues.update_count > 0
    ) {
      return true
    }
  }
  return Boolean(updatesResult?.updates?.length)
}
