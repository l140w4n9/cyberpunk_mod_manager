const ACTIVE_SESSION_KEY = 'cpmm_active_session_id'

export function getActiveSessionId() {
  try {
    return localStorage.getItem(ACTIVE_SESSION_KEY)
  } catch {
    return null
  }
}

export function setActiveSessionId(sessionId) {
  try {
    if (sessionId) localStorage.setItem(ACTIVE_SESSION_KEY, sessionId)
    else localStorage.removeItem(ACTIVE_SESSION_KEY)
  } catch {
    /* ignore */
  }
}

/** 序列化消息，去掉运行中状态 */
export function serializeMessages(messages) {
  return messages.map((msg) => {
    if (msg.role !== 'turn') return { ...msg }
    return {
      ...msg,
      loading: false,
      status: msg.status === 'running' ? 'done' : msg.status,
      endedAt: msg.endedAt || Date.now(),
    }
  })
}

export function formatSessionTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
