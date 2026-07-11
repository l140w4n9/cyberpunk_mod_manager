import { TOOL_STATE_LABELS } from '../api/client'

export function stateLabel(state) {
  return TOOL_STATE_LABELS[state] || state || '执行中'
}

export function formatJson(text) {
  if (!text) return ''
  try {
    const parsed = JSON.parse(text)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return text
  }
}

export function createTool(id, name, label) {
  return {
    id,
    name,
    label: label || name,
    arguments: '',
    result: '',
    state: 'running',
    stateLabel: '执行中',
    startedAt: Date.now(),
    endedAt: null,
  }
}

export function findTool(tools, id) {
  return tools.find((t) => t.id === id)
}

export function summarizeToolResult(result) {
  if (!result) return ''
  try {
    const data = JSON.parse(result)
    if (data.error) return `错误: ${data.error}`
    if (data.added_files_count != null) return `新增 ${data.added_files_count} 个文件`
    if (data.name) return data.name
    if (data.detected_count != null) return `识别 ${data.detected_count} 个模组`
    if (Array.isArray(data.succeeded)) return `安装成功 ${data.succeeded.length} 个`
    return '完成'
  } catch {
    return result.slice(0, 80)
  }
}
