<script setup>
defineProps({
  health: { type: Object, required: true },
})
defineEmits(['refresh'])
</script>

<template>
  <header class="header">
    <div class="brand">
      <div class="brand-icon">CP77</div>
      <div>
        <h1>Mod Manager</h1>
        <p class="sub">AgentScope 驱动 · 自动下载 · 可逆卸载</p>
      </div>
    </div>
    <div class="actions">
      <div class="health-pill" :class="{ offline: !health.ready }">
        {{ health.label }}
      </div>
      <button class="btn-ghost btn-sm" @click="$emit('refresh')">↻ 刷新</button>
    </div>
  </header>
</template>

<style scoped>
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(12, 12, 24, 0.95), rgba(6, 6, 13, 0.8));
  backdrop-filter: blur(12px);
}
.brand { display: flex; align-items: center; gap: 16px; }
.brand-icon {
  width: 44px;
  height: 44px;
  border: 2px solid var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  clip-path: polygon(10% 0, 100% 0, 100% 70%, 90% 100%, 0 100%, 0 30%);
  background: rgba(252, 238, 10, 0.08);
}
h1 {
  font-family: var(--font-display);
  font-size: 18px;
  letter-spacing: 3px;
  color: var(--accent);
  text-transform: uppercase;
}
.sub { color: var(--muted); font-size: 13px; margin-top: 2px; }
.actions { display: flex; align-items: center; gap: 12px; }
.health-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  background: rgba(46, 230, 166, 0.08);
  border: 1px solid rgba(46, 230, 166, 0.25);
  font-size: 12px;
  color: var(--ok);
  font-weight: 600;
}
.health-pill::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ok);
  animation: pulse 2s infinite;
}
.health-pill.offline {
  background: rgba(255, 59, 92, 0.08);
  border-color: rgba(255, 59, 92, 0.25);
  color: var(--danger);
}
.health-pill.offline::before { background: var(--danger); }

@media (max-width: 600px) {
  .header { flex-wrap: wrap; gap: 12px; padding: 16px; }
}
</style>
