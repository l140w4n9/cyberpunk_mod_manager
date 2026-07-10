<script setup>
defineProps({
  tools: { type: Array, default: () => [] },
})
</script>

<template>
  <div v-if="tools.length" class="tool-traces">
    <div v-for="tool in tools" :key="tool.id" class="tool-card" :class="tool.state">
      <div class="tool-head">
        <span class="tool-icon">⚙</span>
        <div class="tool-meta">
          <span class="tool-name">{{ tool.label || tool.name }}</span>
          <span class="tool-fn">{{ tool.name }}</span>
        </div>
        <span class="tool-state" :class="tool.state">{{ tool.stateLabel }}</span>
      </div>
      <details v-if="tool.arguments" class="tool-detail" open>
        <summary>调用参数</summary>
        <pre>{{ tool.arguments }}</pre>
      </details>
      <details v-if="tool.result" class="tool-detail" open>
        <summary>返回结果</summary>
        <pre>{{ tool.result }}</pre>
      </details>
    </div>
  </div>
</template>

<style scoped>
.tool-traces {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 4px 0;
}
.tool-card {
  background: rgba(252, 238, 10, 0.04);
  border: 1px solid rgba(252, 238, 10, 0.15);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  font-size: 12px;
  animation: fadeIn 0.25s ease;
}
.tool-card.error,
.tool-card.interrupted {
  border-color: rgba(255, 59, 92, 0.3);
  background: rgba(255, 59, 92, 0.06);
}
.tool-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.tool-icon {
  color: var(--accent);
  font-size: 14px;
}
.tool-meta { flex: 1; min-width: 0; }
.tool-name {
  display: block;
  font-weight: 700;
  color: var(--accent);
  font-size: 13px;
}
.tool-fn {
  display: block;
  color: var(--muted);
  font-family: Consolas, monospace;
  font-size: 11px;
}
.tool-state {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 3px 8px;
  border-radius: 12px;
  background: rgba(0, 240, 255, 0.1);
  color: var(--accent2);
  font-weight: 700;
}
.tool-state.running {
  animation: pulse 1.5s infinite;
}
.tool-state.error,
.tool-state.interrupted {
  background: rgba(255, 59, 92, 0.15);
  color: var(--danger);
}
.tool-detail {
  margin-top: 8px;
}
.tool-detail summary {
  cursor: pointer;
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}
.tool-detail pre {
  background: rgba(0, 0, 0, 0.35);
  border-radius: 6px;
  padding: 8px 10px;
  overflow-x: auto;
  color: var(--text);
  font-family: Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 160px;
  overflow-y: auto;
}
</style>
