import { REQUEST_CANCELLED, i18nState, statusLabel, t, toolStateLabel } from '../i18n'

function localeHeaders() {
  const locale = i18nState.locale
  return {
    'X-Locale': locale,
    'Accept-Language': locale === 'en' ? 'en-US' : 'zh-CN',
  }
}

function formatNetworkError(error) {
  if (error?.name === 'AbortError') {
    return t('api.requestCancelled')
  }
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000'
  return t('api.connectionFailed', { origin })
}

function cancelledError() {
  const err = new Error(t('api.requestCancelled'))
  err.code = REQUEST_CANCELLED
  return err
}

async function request(url, options = {}) {
  const { timeoutMs = 0, signal: userSignal, ...fetchOptions } = options
  const controller = new AbortController()
  let timeoutId
  let timedOut = false

  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
  }

  if (userSignal) {
    if (userSignal.aborted) {
      controller.abort()
    } else {
      userSignal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  let resp
  try {
    resp = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...localeHeaders(),
        ...fetchOptions.headers,
      },
      ...fetchOptions,
      signal: controller.signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      if (timedOut) {
        throw new Error(
          t('api.requestTimeout', { seconds: Math.round(timeoutMs / 1000) }),
        )
      }
      throw cancelledError()
    }
    const message =
      error?.message === 'Failed to fetch'
        ? formatNetworkError(error)
        : error?.message || formatNetworkError(error)
    throw new Error(message)
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }

  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    let message = data.detail || data.error || `HTTP ${resp.status}`
    let code = data.code || ''
    if (typeof message === 'object' && message !== null) {
      code = message.code || code
      message = message.message || message.detail || JSON.stringify(message)
    }
    const err = new Error(typeof message === 'string' ? message : JSON.stringify(message))
    if (code) err.code = code
    throw err
  }
  return data
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
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
  let resp
  try {
    resp = await fetch('/api/agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...localeHeaders(),
      },
      body: JSON.stringify({ message, session_id: sessionId }),
    })
  } catch (error) {
    const messageText = error?.message === 'Failed to fetch' ? formatNetworkError(error) : (error?.message || formatNetworkError(error))
    throw new Error(messageText)
  }
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
  scanLocalFolder: (folderPath) =>
    request('/api/mods/scan-local', {
      method: 'POST',
      body: JSON.stringify({ folder_path: folderPath }),
    }),
  installLocalFolder: (folderPath, modIds = null) =>
    request('/api/mods/install-local-folder', {
      method: 'POST',
      body: JSON.stringify({
        folder_path: folderPath,
        mod_ids: modIds,
        install_dependencies: true,
      }),
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
  parseCollection: (url, options = {}) =>
    request('/api/collections/parse', {
      method: 'POST',
      body: JSON.stringify({ url }),
      timeoutMs: 45000,
      ...options,
    }),
  installCollection: (payload) =>
    request('/api/collections/install', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  collectionQueueStatus: (modIds) =>
    request('/api/collections/queue-status', {
      method: 'POST',
      body: JSON.stringify({ mod_ids: modIds }),
    }),
  getCollectionJob: (jobId, options = {}) =>
    request(`/api/collections/jobs/${jobId}`, { timeoutMs: 10000, ...options }),
  cancelCollectionJob: (jobId) =>
    request(`/api/collections/jobs/${jobId}/cancel`, { method: 'POST' }),
  listPendingMods: () => request('/api/mods/pending'),
  listIncompleteMods: () => request('/api/mods/incomplete'),
  deleteMod: (modId) =>
    request(`/api/mods/${modId}`, { method: 'DELETE' }),
  cleanupPendingMods: (modIds = null) =>
    request('/api/mods/cleanup-pending', {
      method: 'POST',
      body: JSON.stringify({ mod_ids: modIds }),
    }),
  checkModUpdates: () =>
    request('/api/mods/check-updates', { method: 'POST' }),
  auditInstallation: (autoFix = false) =>
    request('/api/mods/audit', {
      method: 'POST',
      body: JSON.stringify({ auto_fix: autoFix }),
    }),
  startAuditJob: (autoFix = false) =>
    request('/api/mods/audit/start', {
      method: 'POST',
      body: JSON.stringify({ auto_fix: autoFix }),
    }),
  getAuditJob: (jobId) => request(`/api/mods/audit/jobs/${jobId}`),
  startCheckUpdatesJob: () =>
    request('/api/mods/check-updates/start', { method: 'POST' }),
  getTrendingMods: () => request('/api/mods/discovery/trending'),
  syncTrackedMods: () =>
    request('/api/mods/discovery/sync-tracked', { method: 'POST' }),
  getUpdatedFeed: (period = '1w', compareLocal = true) =>
    request(
      `/api/mods/discovery/updated-feed?period=${encodeURIComponent(period)}&compare_local=${compareLocal}`,
    ),
  batchModStatus: (modIds) =>
    request('/api/mods/discovery/batch-status', {
      method: 'POST',
      body: JSON.stringify({ mod_ids: modIds }),
    }),
  checkCollectionRevision: (slug, knownRevision = null, domain = 'cyberpunk2077') => {
    const params = new URLSearchParams({ slug, domain })
    if (knownRevision != null) params.set('known_revision', String(knownRevision))
    return request(`/api/collections/revision?${params}`)
  },
  getConfig: async (retries = 2) => {
    let lastError
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        return await request('/api/config')
      } catch (error) {
        if (error?.name === 'AbortError') throw error
        lastError = error
        if (attempt < retries) await sleep(400 * (attempt + 1))
      }
    }
    throw lastError
  },
  saveConfig: (payload) =>
    request('/api/config', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  startNexusAuth: () =>
    request('/api/nexus/auth/start', { method: 'POST' }),
  nexusAuthStatus: () => request('/api/nexus/auth/status'),
  disconnectNexus: () =>
    request('/api/nexus/auth', { method: 'DELETE' }),
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
  get installed() { return statusLabel('installed') },
  get downloaded() { return statusLabel('downloaded') },
  get not_installed() { return statusLabel('not_installed') },
  get disabled() { return statusLabel('disabled') },
  get error() { return statusLabel('error') },
}

export const TOOL_STATE_LABELS = {
  get running() { return toolStateLabel('running') },
  get done() { return toolStateLabel('done') },
  get success() { return toolStateLabel('success') },
  get SUCCESS() { return toolStateLabel('SUCCESS') },
  get ERROR() { return toolStateLabel('ERROR') },
  get error() { return toolStateLabel('error') },
  get INTERRUPTED() { return toolStateLabel('INTERRUPTED') },
  get interrupted() { return toolStateLabel('interrupted') },
  get DENIED() { return toolStateLabel('DENIED') },
  get denied() { return toolStateLabel('denied') },
}
