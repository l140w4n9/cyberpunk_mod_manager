async function request(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    let message = data.detail || data.error || `HTTP ${resp.status}`
    if (typeof message === 'object') {
      message = message.message || JSON.stringify(message)
    }
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message))
  }
  return data
}

function parseSseChunk(buffer) {
  const events = []
  const parts = buffer.split('\n\n')
  const rest = parts.pop() || ''
  for (const part of parts) {
    if (!part.trim()) continue
    let event = 'message'
    let data = ''
    for (const line of part.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) data = line.slice(5).trim()
    }
    if (data) {
      try {
        events.push({ event, data: JSON.parse(data) })
      } catch {
        events.push({ event, data: { raw: data } })
      }
    }
  }
  return { events, rest }
}

export async function chatStream(message, onEvent, sessionId = null) {
  const resp = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}))
    const msg = data.detail || data.error || `HTTP ${resp.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.rest
    for (const evt of parsed.events) {
      onEvent(evt.event, evt.data)
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseChunk(buffer + '\n\n')
    for (const evt of parsed.events) {
      onEvent(evt.event, evt.data)
    }
  }
}

export const api = {
  health: () => request('/api/health'),
  listMods: (refreshSummaries = false) =>
    request(`/api/mods?refresh_summaries=${refreshSummaries}`),
  installMod: (modId) =>
    request('/api/mods/install', {
      method: 'POST',
      body: JSON.stringify({ mod_id: modId }),
    }),
  installModWithDeps: (modId) =>
    request('/api/mods/install-with-deps', {
      method: 'POST',
      body: JSON.stringify({ mod_id: modId }),
    }),
  installLocalMod: (modId, archiveName) =>
    request('/api/mods/install-local', {
      method: 'POST',
      body: JSON.stringify({ mod_id: modId, archive_name: archiveName }),
    }),
  modDependencies: (modId) => request(`/api/mods/${modId}/dependencies`),
  uninstallCheck: (modId) => request(`/api/mods/${modId}/uninstall-check`),
  uninstallMod: (modId, force = false) =>
    request('/api/mods/uninstall', {
      method: 'POST',
      body: JSON.stringify({ mod_id: modId, force }),
    }),
  uninstallPlan: (modId) => request(`/api/mods/${modId}/uninstall-plan`),
  modSummary: (modId, refresh = false) =>
    request(`/api/mods/${modId}/summary?refresh=${refresh}`),
  chat: (message, sessionId = null) =>
    request('/api/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId }),
    }),
  chatStream,
  listSessions: () => request('/api/agent/sessions'),
  createSession: (title = '') =>
    request('/api/agent/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  getSession: (sessionId) => request(`/api/agent/sessions/${sessionId}`),
  saveSession: (sessionId, messages, title = null) =>
    request(`/api/agent/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify({ messages, title }),
    }),
  deleteSession: (sessionId) =>
    request(`/api/agent/sessions/${sessionId}`, { method: 'DELETE' }),
}

export const STATUS_LABELS = {
  installed: '已安装',
  downloaded: '已下载',
  not_installed: '未安装',
  disabled: '已禁用',
  error: '错误',
}

export const TOOL_STATE_LABELS = {
  running: '执行中',
  done: '完成',
  success: '完成',
  SUCCESS: '完成',
  ERROR: '失败',
  error: '失败',
  INTERRUPTED: '中断',
  interrupted: '中断',
  DENIED: '已拒绝',
  denied: '已拒绝',
}
