<script setup>
defineProps({
  active: { type: String, default: 'agent' },
  health: { type: Object, required: true },
})
defineEmits(['navigate', 'refresh'])
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="logo">AS</div>
      <div>
        <div class="brand-title">Mod Studio</div>
        <div class="brand-sub">AgentScope</div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <button
        class="nav-item"
        :class="{ active: active === 'agent' }"
        @click="$emit('navigate', 'agent')"
      >
        <span class="nav-icon">◈</span>
        Agent 运行
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'mods' }"
        @click="$emit('navigate', 'mods')"
      >
        <span class="nav-icon">▣</span>
        模组库存
      </button>
    </nav>

    <div class="sidebar-footer">
      <div class="health" :class="{ ok: health.ready }">
        <span class="health-dot" />
        {{ health.label }}
      </div>
      <button class="btn-ghost btn-sm full" @click="$emit('refresh')">刷新数据</button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 50;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 16px;
  border-bottom: 1px solid var(--border);
}
.logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), #d4c800);
  color: #111;
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-title {
  font-weight: 700;
  font-size: 14px;
}
.brand-sub {
  font-size: 11px;
  color: var(--muted);
}
.sidebar-nav {
  flex: 1;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid transparent;
  color: var(--muted);
  text-align: left;
  font-size: 13px;
}
.nav-item:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text);
}
.nav-item.active {
  background: rgba(0, 212, 255, 0.08);
  border-color: rgba(0, 212, 255, 0.2);
  color: var(--accent2);
}
.nav-icon { font-size: 14px; opacity: 0.8; }
.sidebar-footer {
  padding: 14px 12px;
  border-top: 1px solid var(--border);
}
.health {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--danger);
  margin-bottom: 10px;
}
.health.ok { color: var(--ok); }
.health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.full { width: 100%; }

@media (max-width: 900px) {
  .sidebar {
    width: 100%;
    height: auto;
    position: relative;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
  }
  .sidebar-brand { border-bottom: none; flex: 1; }
  .sidebar-nav {
    flex-direction: row;
    flex: none;
    padding: 8px;
  }
  .sidebar-footer {
    display: flex;
    align-items: center;
    gap: 10px;
    border-top: none;
    padding: 8px 12px;
  }
  .health { margin-bottom: 0; }
  .full { width: auto; }
}
</style>
