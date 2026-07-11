<script setup>
import { ref, nextTick, onMounted } from 'vue'
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
import ToolStep from '../components/agent/ToolStep.vue'
import TraceInspector from '../components/agent/TraceInspector.vue'

const emit = defineEmits(['done'])

const props = defineProps({
  health: {
    type: Object,
    default: () => ({ ready: false, label: '检查中...', llm_configured: false, config_file: '' }),
  },
})

const WELCOME = {
  id: 'welcome',
  role: 'assistant',
  content:
    '你好！我是模组管理 Agent。给我一个 Nexus 模组 ID 或自然语言指令，我会展示完整的工具调用过程并自动安装。',
}

const sessions = ref([])
const activeSessionId = ref(null)
const messages = ref([WELCOME])
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
  messages.value = data.messages?.length ? data.messages : [WELCOME]
  selectedTool.value = null
  selectedTurn.value = null
  await scrollToBottom()
}

async function ensureSession() {
  if (activeSessionId.value) return activeSessionId.value
  const data = await api.createSession()
  activeSessionId.value = data.id
  setActiveSessionId(data.id)
  messages.value = data.messages?.length ? data.messages : [WELCOME]
  await refreshSessions()
  return data.id
}

async function startNewSession() {
  const data = await api.createSession()
  activeSessionId.value = data.id
  setActiveSessionId(data.id)
  messages.value = data.messages?.length ? data.messages : [WELCOME]
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
    turn.reply = '出错: ' + (data.message || '未知错误')
    turn.status = 'error'
    turn.loading = false
    turn.endedAt = Date.now()
  }
}

async function send() {
  const msg = input.value.trim()
  if (!msg || sending.value) return
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
        'LLM 未配置，无法运行 Agent。请编辑 config.yaml 填入 openai_api_key 后重启服务。',
    })
    input.value = ''
    return
  }

  const sessionId = await ensureSession()

  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content: msg })
  input.value = ''
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
    if (!turn.reply && !turn.tools.length) turn.reply = '（无回复）'
    await persistMessages()
    emit('done')
  } catch (e) {
    turn.loading = false
    turn.status = 'error'
    turn.reply = '出错: ' + e.message
    turn.endedAt = Date.now()
    await persistMessages()
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

onMounted(async () => {
  sessionsLoading.value = true
  try {
    await refreshSessions()
    const savedId = getActiveSessionId()
    if (savedId && sessions.value.some((s) => s.id === savedId)) {
      await loadSession(savedId)
    } else if (sessions.value.length) {
      await loadSession(sessions.value[0].id)
    } else {
      await startNewSession()
    }
  } catch {
    messages.value = [WELCOME]
  } finally {
    sessionsLoading.value = false
  }
})
</script>

<template>
  <div class="workspace">
    <aside class="session-panel">
      <div class="session-header">
        <span class="session-title">会话</span>
        <button class="btn-ghost btn-sm" type="button" @click="startNewSession">+ 新建</button>
      </div>
      <div v-if="sessionsLoading" class="session-empty">加载中...</div>
      <div v-else-if="!sessions.length" class="session-empty">暂无会话</div>
      <ul v-else class="session-list">
        <li
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === activeSessionId }"
          @click="switchSession(s.id)"
        >
          <div class="session-item-top">
            <span class="session-name">{{ s.title || '新会话' }}</span>
            <button
              class="session-del"
              type="button"
              title="删除会话"
              @click.stop="removeSession(s.id)"
            >
              ×
            </button>
          </div>
          <div class="session-preview">{{ s.preview || '（空）' }}</div>
          <div class="session-time mono">{{ formatSessionTime(s.updated_at) }}</div>
        </li>
      </ul>
    </aside>

    <div class="workspace-main">
      <header class="workspace-header">
        <div>
          <h2>Agent 运行</h2>
          <p>实时展示 LLM 推理与工具调用全过程</p>
        </div>
        <div v-if="sending" class="run-badge">
          <span class="spinner" /> 运行中
        </div>
      </header>

      <div v-if="!health.llm_configured" class="config-alert">
        <strong>LLM 未配置</strong>
        <p>
          请在 <code>cyberpunk_mod_manager/config.yaml</code> 中设置
          <code>openai_api_key</code>，或设置环境变量 <code>OPENAI_API_KEY</code>。
        </p>
        <p v-if="health.config_file" class="mono">当前配置: {{ health.config_file || '（未找到配置文件）' }}</p>
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
                  <span class="turn-label">Agent 执行流程</span>
                  <span class="turn-status" :class="msg.status">
                    {{
                      msg.status === 'running'
                        ? msg.phase === 'reply'
                          ? '生成回复'
                          : '调用工具'
                        : msg.status === 'error'
                          ? '失败'
                          : '完成'
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
                  <span class="spinner" /> 等待 Agent 决策...
                </div>

                <div v-if="msg.reply" class="reply-block">
                  <div class="reply-label">最终回复</div>
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
          placeholder="输入模组 ID（如 27967）或：帮我安装 0-Engine 及依赖..."
          :disabled="sending"
          @keydown.enter.exact.prevent="send"
        />
        <button class="btn-primary" type="submit" :disabled="sending || !input.trim()">
          {{ sending ? '运行中' : '发送' }}
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
