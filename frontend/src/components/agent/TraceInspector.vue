<script setup>
import { computed } from 'vue'
import { formatJson } from '../../utils/agent'

const props = defineProps({
  tool: { type: Object, default: null },
  turn: { type: Object, default: null },
})

const duration = computed(() => {
  if (!props.turn?.startedAt) return null
  const end = props.turn.endedAt || Date.now()
  const sec = ((end - props.turn.startedAt) / 1000).toFixed(1)
  return `${sec}s`
})
</script>

<template>
  <div class="inspector">
    <div class="inspector-head">
      <h3>运行追踪</h3>
      <span v-if="duration" class="duration mono">{{ duration }}</span>
    </div>

    <div v-if="!tool && !turn" class="inspector-empty">
      选择时间线中的工具步骤查看详情
    </div>

    <template v-else-if="tool">
      <div class="meta-card">
        <div class="meta-row">
          <span class="meta-label">工具</span>
          <span>{{ tool.label }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">函数</span>
          <span class="mono">{{ tool.name }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">状态</span>
          <span class="meta-state" :class="tool.state">{{ tool.stateLabel }}</span>
        </div>
      </div>

      <div v-if="tool.arguments" class="code-block">
        <div class="code-label">调用参数</div>
        <pre class="mono">{{ formatJson(tool.arguments) }}</pre>
      </div>

      <div v-if="tool.result" class="code-block">
        <div class="code-label">返回结果</div>
        <pre class="mono">{{ formatJson(tool.result) }}</pre>
      </div>
      <div v-else-if="tool.state === 'running'" class="inspector-loading">
        <span class="spinner" /> 等待工具返回...
      </div>
    </template>

    <template v-else-if="turn">
      <div class="meta-card">
        <div class="meta-row">
          <span class="meta-label">本轮状态</span>
          <span>{{ turn.status === 'running' ? '运行中' : turn.status === 'error' ? '失败' : '完成' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">工具调用</span>
          <span>{{ turn.tools.length }} 次</span>
        </div>
      </div>
      <p class="hint">点击左侧时间线中的步骤查看详细参数与结果。</p>
    </template>
  </div>
</template>

<style scoped>
.inspector {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.inspector-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
}
.inspector-head h3 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.duration {
  font-size: 11px;
  color: var(--accent2);
}
.inspector-empty,
.hint {
  padding: 24px 18px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}
.inspector-loading {
  padding: 16px 18px;
  color: var(--muted);
  font-size: 13px;
}
.meta-card {
  margin: 14px 18px 0;
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.meta-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  padding: 4px 0;
}
.meta-label {
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.meta-state.running { color: var(--accent2); }
.meta-state.error,
.meta-state.ERROR { color: var(--danger); }
.code-block {
  margin: 12px 18px 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.code-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  margin-bottom: 6px;
}
.code-block pre {
  flex: 1;
  overflow: auto;
  padding: 12px;
  background: #0c0c14;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 280px;
}
</style>
