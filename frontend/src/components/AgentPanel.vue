<script setup>
import { ref, nextTick } from 'vue'
import { api, TOOL_STATE_LABELS } from '../api/client'
import ToolTrace from './ToolTrace.vue'

const emit = defineEmits(['done'])

const messages = ref([
  {
    role: 'agent',
    text: '你好！给我一个模组 ID，我会自动下载安装并记录卸载方式。',
  },
])
const input = ref('')
const sending = ref(false)
const logRef = ref(null)

function stateLabel(state) {
  return TOOL_STATE_LABELS[state] || state || '执行中'
}

function findTool(tools, id) {
  return tools.find((t) => t.id === id)
}

async function scrollToBottom() {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
}

async function send() {
  const msg = input.value.trim()
  if (!msg || sending.value) return

  messages.value.push({ role: 'user', text: msg })
  input.value = ''
  sending.value = true

  const turn = {
    role: 'turn',
    tools: [],
    reply: '',
    loading: true,
  }
  messages.value.push(turn)
  await scrollToBottom()

  try {
    await api.chatStream(msg, (event, data) => {
      if (event === 'tool_start') {
        turn.tools.push({
          id: data.id,
          name: data.name,
          label: data.label,
          arguments: '',
          result: '',
          state: 'running',
          stateLabel: '执行中',
        })
      } else if (event === 'tool_args') {
        const tool = findTool(turn.tools, data.id)
        if (tool) tool.arguments = data.arguments || ''
      } else if (event === 'tool_result') {
        const tool = findTool(turn.tools, data.id)
        if (tool) {
          tool.result = data.result || ''
          tool.state = data.state || 'done'
          tool.stateLabel = stateLabel(tool.state)
        }
      } else if (event === 'text_delta') {
        turn.reply += data.delta || ''
      } else if (event === 'done') {
        turn.reply = data.reply || turn.reply
        turn.loading = false
        if (data.tool_calls?.length) {
          for (const tc of data.tool_calls) {
            const tool = findTool(turn.tools, tc.id)
            if (tool) {
              tool.arguments = tc.arguments || tool.arguments
              tool.result = tc.result || tool.result
              tool.state = tc.state || tool.state
              tool.stateLabel = stateLabel(tool.state)
            } else {
              turn.tools.push({
                ...tc,
                stateLabel: stateLabel(tc.state),
              })
            }
          }
        }
      } else if (event === 'error') {
        turn.reply = '出错: ' + (data.message || '未知错误')
        turn.loading = false
      }
      scrollToBottom()
    })

    if (turn.loading) turn.loading = false
    if (!turn.reply && !turn.tools.length) {
      turn.reply = '（无回复）'
    }
    emit('done')
  } catch (e) {
    turn.loading = false
    turn.reply = '出错: ' + e.message
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-title">AI 助手</div>
    <div ref="logRef" class="chat-log">
      <template v-for="(msg, i) in messages" :key="i">
        <div v-if="msg.role === 'user'" class="bubble user">
          <div class="bubble-role">你</div>
          {{ msg.text }}
        </div>

        <div v-else-if="msg.role === 'agent'" class="bubble agent">
          <div class="bubble-role">Agent</div>
          {{ msg.text }}
        </div>

        <div v-else-if="msg.role === 'turn'" class="turn-block">
          <ToolTrace :tools="msg.tools" />
          <div v-if="msg.loading && !msg.reply" class="bubble agent loading">
            <div class="bubble-role">Agent</div>
            正在调用工具...
          </div>
          <div v-if="msg.reply" class="bubble agent">
            <div class="bubble-role">Agent</div>
            {{ msg.reply }}
          </div>
        </div>
      </template>
    </div>
    <form class="chat-input" @submit.prevent="send">
      <input v-model="input" placeholder="输入模组 ID 或自然语言..." :disabled="sending" />
      <button class="btn-primary btn-sm" type="submit" :disabled="sending || !input.trim()">
        {{ sending ? '...' : '发送' }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.chat-log {
  height: 420px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-log::-webkit-scrollbar { width: 6px; }
.chat-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

.turn-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-self: stretch;
}

.bubble {
  max-width: 92%;
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  animation: fadeIn 0.3s ease;
}
.bubble.agent {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent2);
}
.bubble.user {
  align-self: flex-end;
  background: rgba(0, 240, 255, 0.08);
  border: 1px solid rgba(0, 240, 255, 0.2);
  border-right: 3px solid var(--accent);
}
.bubble-role {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
  margin-bottom: 6px;
  font-weight: 700;
}
.bubble.user .bubble-role { color: var(--accent); text-align: right; }
.bubble.agent .bubble-role { color: var(--accent2); }
.bubble.loading { color: var(--muted); font-style: italic; }

.chat-input {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}
</style>
