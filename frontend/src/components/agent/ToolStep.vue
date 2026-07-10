<script setup>
import { formatJson, summarizeToolResult } from '../../utils/agent'

const props = defineProps({
  tool: { type: Object, required: true },
  index: { type: Number, default: 0 },
  active: { type: Boolean, default: false },
  isLast: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])
</script>

<template>
  <div
    class="step"
    :class="[tool.state, { active, 'step--last': isLast }]"
    @click="emit('select', tool)"
  >
    <div class="step-rail">
      <div class="step-dot" :class="tool.state">
        <span v-if="tool.state === 'running'" class="spinner spinner--sm" />
        <span v-else-if="tool.state === 'SUCCESS' || tool.state === 'success' || tool.state === 'done'">✓</span>
        <span v-else-if="tool.state === 'ERROR' || tool.state === 'error'">✕</span>
        <span v-else>{{ index + 1 }}</span>
      </div>
      <div v-if="!isLast" class="step-line" />
    </div>

    <div class="step-body">
      <div class="step-head">
        <div>
          <div class="step-title">{{ tool.label }}</div>
          <div class="step-fn mono">{{ tool.name }}</div>
        </div>
        <span class="step-state" :class="tool.state">{{ tool.stateLabel }}</span>
      </div>

      <div v-if="tool.arguments" class="step-preview mono">
        <span class="preview-label">参数</span>
        {{ formatJson(tool.arguments).slice(0, 120) }}{{ tool.arguments.length > 120 ? '…' : '' }}
      </div>

      <div v-if="tool.result" class="step-result">
        {{ summarizeToolResult(tool.result) }}
      </div>
      <div v-else-if="tool.state === 'running'" class="step-running">
        正在执行...
      </div>
    </div>
  </div>
</template>

<style scoped>
.step {
  display: flex;
  gap: 14px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
  animation: fadeIn 0.25s ease;
}
.step:hover { background: rgba(255, 255, 255, 0.03); }
.step.active { background: rgba(0, 212, 255, 0.06); }

.step-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 28px;
  flex-shrink: 0;
}
.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  background: var(--bg-elevated);
  color: var(--muted);
}
.step-dot.running {
  border-color: var(--accent2);
  color: var(--accent2);
}
.step-dot.success,
.step-dot.SUCCESS,
.step-dot.done {
  border-color: var(--ok);
  color: var(--ok);
  background: rgba(46, 230, 166, 0.1);
}
.step-dot.error,
.step-dot.ERROR {
  border-color: var(--danger);
  color: var(--danger);
  background: rgba(255, 77, 109, 0.1);
}
.step-line {
  flex: 1;
  width: 2px;
  min-height: 16px;
  background: var(--border);
  margin: 4px 0;
}
.spinner--sm {
  width: 12px;
  height: 12px;
  border-width: 2px;
  margin: 0;
}

.step-body { flex: 1; min-width: 0; padding-bottom: 12px; }
.step-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}
.step-title {
  font-weight: 600;
  font-size: 13px;
}
.step-fn {
  color: var(--muted);
  margin-top: 2px;
}
.step-state {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
  flex-shrink: 0;
}
.step-state.running { color: var(--accent2); animation: pulse 1.5s infinite; }
.step-state.error,
.step-state.ERROR { color: var(--danger); }

.step-preview {
  margin-top: 8px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.25);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preview-label {
  color: var(--accent2);
  margin-right: 6px;
  font-weight: 600;
}
.step-result {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ok);
}
.step-running {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}
</style>
