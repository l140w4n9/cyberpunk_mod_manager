<script setup>
import { computed, ref, nextTick, onMounted } from 'vue'
import { api } from '../api/client'
import {
  createTool,
  findTool,
  stateLabel,
} from '../utils/agent'
import {
  formatSessionTime,
  getActiveSessionId,
  serializeMessages,
  setActiveSessionId,
} from '../utils/chatSession'
import { consumeAgentHandoff } from '../utils/agentHandoff'
import ToolStep from '../components/agent/ToolStep.vue'
import TraceInspector from '../components/agent/TraceInspector.vue'
import { useI18n } from '../i18n'

const emit = defineEmits(['done'])

const { t } = useI18n()

const props = defineProps({
  health: {
    type: Object,
    default: () => ({ ready: false, label: '', llm_configured: false, config_file: '' }),
  },
})

const welcomeMessage = computed(() => ({
  id: 'welcome',
  role: 'assistant',
  content: t('agent.greeting'),
}))

const sessions = ref([])
const activeSessionId = ref(null)
const messages = ref([welcomeMessage.value])
const input = ref('')
const sending = ref(false)
const selectedTool = ref(null)
const selectedTurn = ref(null)
const logRef = ref(null)
const sessionsLoading = ref(true)

async function scrollToBottom() {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
}

function selectTool(tool, turn) {
  selectedTool.value = tool
  selectedTurn.value = turn
}

async function persistMessages() {
  if (!activeSessionId.value) return
  try {
    await api.saveSession(activeSessionId.value, serializeMessages(messages.value))
    await refreshSessions()
  } catch {
    /* 保存失败不阻断对话 */
  }
}

async function refreshSessions() {
  try {
    sessions.value = await api.listSessions()
  } catch {
    sessions.value = []
  }
}

async function loadSession(sessionId) {
  const data = await api.getSession(sessionId)
  activeSessionId.value = sessionId
  setActiveSessionId(sessionId)
  messages.value = data.messages?.length ? data.messages : [welcomeMessage.value]
  selectedTool.value = null
  selectedTurn.value = null
  await scrollToBottom()
}

async function ensureSession() {
  if (activeSessionId.value) return activeSessionId.value
  const data = await api.createSession()
  activeSessionId.value = data.id
  setActiveSessionId(data.id)
  messages.value = data.messages?.length ? data.messages : [welcomeMessage.value]
  await refreshSessions()
  return data.id
}

async function startNewSession() {
  const data = await api.createSession()
  activeSessionId.value = data.id
  setActiveSessionId(data.id)
  messages.value = data.messages?.length ? data.messages : [welcomeMessage.value]
  selectedTool.value = null
  selectedTurn.value = null
  await refreshSessions()
  await scrollToBottom()
}

async function switchSession(sessionId) {
  if (sessionId === activeSessionId.value) return
  await loadSession(sessionId)
}

async function removeSession(sessionId) {
  await api.deleteSession(sessionId)
  await refreshSessions()
  if (activeSessionId.value === sessionId) {
    if (sessions.value.length) {
      await loadSession(sessions.value[0].id)
    } else {
      await startNewSession()
    }
  }
}

function handleStreamEvent(turn, event, data) {
  if (event === 'tool_start') {
    const tool = createTool(data.id, data.name, data.label)
    turn.tools.push(tool)
    selectTool(tool, turn)
  } else if (event === 'tool_args_delta' || event === 'tool_args') {
    const tool = findTool(turn.tools, data.id)
    if (tool) {
      tool.arguments = data.arguments || tool.arguments
      if (event === 'tool_args') selectTool(tool, turn)
    }
  } else if (event === 'tool_result_delta' || event === 'tool_result') {
    const tool = findTool(turn.tools, data.id)
    if (tool) {
      tool.result = data.result || tool.result
      if (event === 'tool_result') {
        tool.state = data.state || 'done'
        tool.stateLabel = stateLabel(tool.state)
        tool.endedAt = Date.now()
        selectTool(tool, turn)
      }
    }
  } else if (event === 'text_delta') {
    turn.reply += data.delta || ''
    turn.phase = 'reply'
  } else if (event === 'done') {
    turn.reply = data.reply || turn.reply
    turn.status = 'done'
    turn.phase = 'done'
    turn.endedAt = Date.now()
    turn.loading = false
    if (data.tool_calls?.length) {
      for (const tc of data.tool_calls) {
        let tool = findTool(turn.tools, tc.id)
        if (!tool) {
          tool = createTool(tc.id, tc.name, tc.label)
          turn.tools.push(tool)
        }
        tool.arguments = tc.arguments || tool.arguments
        tool.result = tc.result || tool.result
        tool.state = tc.state || tool.state
        tool.stateLabel = stateLabel(tool.state)
        tool.endedAt = tool.endedAt || Date.now()
      }
    }
    selectedTurn.value = turn
    selectedTool.value = null
  } else if (event === 'error') {
    turn.reply = t('agent.error', { error: data.message || t('agent.unknownError') })
    turn.status = 'error'
    turn.loading = false
    turn.endedAt = Date.now()
  }
}

async function sendMessage(rawMsg) {
  const msg = (typeof rawMsg === 'string' ? rawMsg : input.value).trim()
  if (!msg || sending.value) return false
  if (!props.health.llm_configured) {
    messages.value.push({
      id: `u-${Date.now()}`,
      role: 'user',
      content: msg,
    })
    messages.value.push({
      id: `e-${Date.now()}`,
      role: 'assistant',
      content:
        t('agent.llmRequired'),
    })
    if (typeof rawMsg !== 'string') input.value = ''
    return false
  }

  const sessionId = await ensureSession()

  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content: msg })
  if (typeof rawMsg !== 'string') input.value = ''
  sending.value = true
  selectedTool.value = null

  const turn = {
    id: `t-${Date.now()}`,
    role: 'turn',
    tools: [],
    reply: '',
    status: 'running',
    phase: 'tools',
    loading: true,
    startedAt: Date.now(),
    endedAt: null,
  }
  messages.value.push(turn)
  selectedTurn.value = turn
  await persistMessages()
  await scrollToBottom()

  try {
    await api.chatStream(
      msg,
      (event, data) => {
        handleStreamEvent(turn, event, data)
        scrollToBottom()
      },
      sessionId,
    )
    if (turn.loading) {
      turn.loading = false
      turn.status = turn.status === 'running' ? 'done' : turn.status
      turn.endedAt = Date.now()
    }
    if (!turn.reply && !turn.tools.length) turn.reply = t('agent.noReply')
    await persistMessages()
    emit('done')
  } catch (e) {
    turn.loading = false
    turn.status = 'error'
    turn.reply = t('agent.error', { error: e.message })
    turn.endedAt = Date.now()
    await persistMessages()
  } finally {
    sending.value = false
    await scrollToBottom()
  }
  return true
}

async function send() {
  await sendMessage()
}

async function applyPendingHandoff() {
  const handoff = consumeAgentHandoff()
  if (!handoff?.message) return false

  const data = await api.createSession(handoff.title || t('maintenance.handoffTitle'))
  activeSessionId.value = data.id
  setActiveSessionId(data.id)
  messages.value = data.messages?.length ? data.messages : [welcomeMessage.value]
  selectedTool.value = null
  selectedTurn.value = null
  await refreshSessions()
  await sendMessage(handoff.message)
  return true
}

onMounted(async () => {
  sessionsLoading.value = true
  try {
    await refreshSessions()
    if (await applyPendingHandoff()) return

    const savedId = getActiveSessionId()
    if (savedId && sessions.value.some((s) => s.id === savedId)) {
      await loadSession(savedId)
    } else if (sessions.value.length) {
      await loadSession(sessions.value[0].id)
    } else {
      await startNewSession()
    }
  } catch {
    messages.value = [welcomeMessage.value]
  } finally {
    sessionsLoading.value = false
  }
})
</script>

<template>
  <div class="workspace">
    <aside class="session-panel">
      <div class="session-header">
        <span class="session-title">{{ t('agent.session') }}</span>
        <button class="btn-ghost btn-sm" type="button" @click="startNewSession">{{ t('agent.newSession') }}</button>
      </div>
      <div v-if="sessionsLoading" class="session-empty">{{ t('agent.loading') }}</div>
      <div v-else-if="!sessions.length" class="session-empty">{{ t('agent.noSessions') }}</div>
      <ul v-else class="session-list">
        <li
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === activeSessionId }"
          @click="switchSession(s.id)"
        >
          <div class="session-item-top">
            <span class="session-name">{{ s.title || t('agent.newChat') }}</span>
            <button
              class="session-del"
              type="button"
              :title="t('agent.deleteSession')"
              @click.stop="removeSession(s.id)"
            >
              ×
            </button>
          </div>
          <div class="session-preview">{{ s.preview || t('agent.emptyPreview') }}</div>
          <div class="session-time mono">{{ formatSessionTime(s.updated_at) }}</div>
        </li>
      </ul>
    </aside>

    <div class="workspace-main">
      <header class="workspace-header">
        <div>
          <h2>{{ t('agent.title') }}</h2>
          <p>{{ t('agent.subtitle') }}</p>
        </div>
        <div v-if="sending" class="run-badge">
          <span class="spinner" /> {{ t('agent.running') }}
        </div>
      </header>

      <div v-if="!health.data_dir_configured" class="config-alert warn-box">
        <strong>{{ t('agent.noDataDir') }}</strong>
        <p>{{ t('agent.noDataDirHint') }}</p>
      </div>

      <div v-else-if="!health.llm_configured" class="config-alert">
        <strong>{{ t('agent.noLlm') }}</strong>
        <p>{{ t('agent.noLlmHint') }}</p>
        <p v-if="health.config_file" class="mono">
          {{ t('agent.configFile', { path: health.config_file || t('agent.configNotFound') }) }}
        </p>
      </div>

      <div ref="logRef" class="timeline-scroll">
        <div class="timeline">
          <template v-for="msg in messages" :key="msg.id">
            <div v-if="msg.role === 'user'" class="msg user-msg">
              <div class="msg-avatar user">U</div>
              <div class="msg-bubble user">{{ msg.content }}</div>
            </div>

            <div v-else-if="msg.role === 'assistant'" class="msg agent-msg">
              <div class="msg-avatar agent">A</div>
              <div class="msg-bubble agent">{{ msg.content }}</div>
            </div>

            <div v-else-if="msg.role === 'turn'" class="msg turn-msg">
              <div class="msg-avatar agent">A</div>
              <div class="turn-panel">
                <div class="turn-header">
                  <span class="turn-label">{{ t('agent.turnLabel') }}</span>
                  <span class="turn-status" :class="msg.status">
                    {{
                      msg.status === 'running'
                        ? msg.phase === 'reply'
                          ? t('agent.generating')
                          : t('agent.callingTool')
                        : msg.status === 'error'
                          ? t('agent.failed')
                          : t('agent.done')
                    }}
                  </span>
                </div>

                <div v-if="msg.tools.length" class="steps">
                  <ToolStep
                    v-for="(tool, idx) in msg.tools"
                    :key="tool.id"
                    :tool="tool"
                    :index="idx"
                    :is-last="idx === msg.tools.length - 1 && !msg.reply && msg.loading"
                    :active="selectedTool?.id === tool.id"
                    @select="selectTool($event, msg)"
                  />
                </div>

                <div v-else-if="msg.loading" class="turn-waiting">
                  <span class="spinner" /> {{ t('agent.waiting') }}
                </div>

                <div v-if="msg.reply" class="reply-block">
                  <div class="reply-label">{{ t('agent.finalReply') }}</div>
                  <div class="reply-text">
                    {{ msg.reply }}<span v-if="msg.loading && msg.phase === 'reply'" class="cursor">▍</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <form class="composer" @submit.prevent="send">
        <textarea
          v-model="input"
          rows="2"
          :placeholder="t('agent.placeholder')"
          :disabled="sending"
          @keydown.enter.exact.prevent="send"
        />
        <button class="btn-primary" type="submit" :disabled="sending || !input.trim()">
          {{ sending ? t('agent.running') : t('agent.send') }}
        </button>
      </form>
    </div>

    <aside class="workspace-trace">
      <TraceInspector :tool="selectedTool" :turn="selectedTurn" />
    </aside>
  </div>
</template>

<style scoped>
.workspace {
  display: grid;
  grid-template-columns: 200px 1fr 340px;
  height: calc(100vh - var(--topbar-height));
  min-height: 520px;
  background: var(--bg);
}

.session-panel {
  border-right: 1px solid var(--border);
  background: var(--bg-elevated);
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px;
  border-bottom: 1px solid var(--border);
}
.session-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.session-list {
  list-style: none;
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.session-item {
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  margin-bottom: 4px;
}
.session-item:hover {
  background: rgba(255, 255, 255, 0.04);
}
.session-item.active {
  background: rgba(0, 212, 255, 0.08);
  border-color: rgba(0, 212, 255, 0.2);
}
.session-item-top {
  display: flex;
  align-items: center;
  gap: 6px;
}
.session-name {
  font-size: 12px;
  font-weight: 600;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-del {
  padding: 0 4px;
  font-size: 14px;
  line-height: 1;
  color: var(--muted);
  background: transparent;
  border: none;
}
.session-del:hover { color: var(--danger); }
.session-preview {
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-time {
  font-size: 10px;
  color: var(--muted);
  margin-top: 4px;
  opacity: 0.7;
}
.session-empty {
  padding: 20px 12px;
  font-size: 12px;
  color: var(--muted);
}

.workspace-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--border);
}
.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-elevated);
}
.workspace-header h2 {
  font-size: 16px;
  font-weight: 700;
}
.workspace-header p {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}
.run-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--accent2);
  padding: 6px 12px;
  background: rgba(0, 212, 255, 0.08);
  border-radius: 20px;
}
.config-alert {
  margin: 0 20px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255, 77, 109, 0.35);
  background: rgba(255, 77, 109, 0.08);
  color: var(--danger);
  font-size: 13px;
}
.config-alert p { margin-top: 6px; color: var(--text); line-height: 1.5; }
.warn-box {
  border-color: rgba(255, 176, 32, 0.35);
  background: rgba(255, 176, 32, 0.08);
  color: var(--warn);
}
.config-alert code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent2);
}

.timeline-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.timeline {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.msg {
  display: flex;
  gap: 12px;
  animation: fadeIn 0.3s ease;
}
.msg-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.msg-avatar.user {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent2);
}
.msg-avatar.agent {
  background: rgba(252, 238, 10, 0.12);
  color: var(--accent);
}
.msg-bubble {
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.65;
  max-width: 85%;
  white-space: pre-wrap;
}
.msg-bubble.user {
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.15);
}
.msg-bubble.agent {
  background: var(--bg-panel);
  border: 1px solid var(--border);
}

.turn-panel {
  flex: 1;
  min-width: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.turn-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid var(--border);
}
.turn-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.turn-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
}
.turn-status.running { color: var(--accent2); }
.turn-status.error { color: var(--danger); }
.turn-status.done { color: var(--ok); }

.steps { padding: 12px 8px 4px; }
.turn-waiting {
  padding: 20px 16px;
  color: var(--muted);
  font-size: 13px;
}

.reply-block {
  border-top: 1px solid var(--border);
  padding: 14px 16px;
  background: rgba(0, 0, 0, 0.15);
}
.reply-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  margin-bottom: 8px;
}
.reply-text {
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent2);
}

.composer {
  display: flex;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  background: var(--bg-elevated);
  align-items: flex-end;
}
.composer textarea {
  flex: 1;
  resize: none;
  min-height: 44px;
}
.composer button {
  height: 44px;
  padding: 0 20px;
}

.workspace-trace {
  background: var(--bg-elevated);
  overflow: hidden;
}

@media (max-width: 1200px) {
  .workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: calc(100vh - 120px);
  }
  .session-panel {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 160px;
  }
  .session-list {
    display: flex;
    flex-direction: row;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 8px;
  }
  .session-item {
    min-width: 140px;
    margin-bottom: 0;
  }
  .workspace-trace {
    border-top: 1px solid var(--border);
    min-height: 280px;
  }
}
</style>
