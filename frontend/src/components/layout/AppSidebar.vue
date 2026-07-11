<script setup>
import { computed } from 'vue'
import { filterMods } from '../../utils/mods'

const props = defineProps({
  active: { type: String, default: 'agent' },
  health: { type: Object, required: true },
  mods: { type: Array, default: () => [] },
})

defineEmits(['navigate', 'refresh'])

const pendingCount = computed(() => filterMods(props.mods, 'pending').length)
const installedCount = computed(() => filterMods(props.mods, 'installed').length)
const incompleteCount = computed(() => filterMods(props.mods, 'incomplete').length)
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

      <div class="nav-group-label">模组管理</div>
      <button
        class="nav-item"
        :class="{ active: active === 'mods' }"
        @click="$emit('navigate', 'mods')"
      >
        <span class="nav-icon">▣</span>
        已安装
        <span v-if="installedCount" class="nav-badge ok">{{ installedCount }}</span>
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'mods-pending' }"
        @click="$emit('navigate', 'mods-pending')"
      >
        <span class="nav-icon">○</span>
        待安装
        <span v-if="pendingCount" class="nav-badge warn">{{ pendingCount }}</span>
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'mods-incomplete' }"
        @click="$emit('navigate', 'mods-incomplete')"
      >
        <span class="nav-icon">⚠</span>
        依赖不全
        <span v-if="incompleteCount" class="nav-badge danger">{{ incompleteCount }}</span>
      </button>

      <div class="nav-group-label">系统</div>
      <button
        class="nav-item"
        :class="{ active: active === 'settings' }"
        @click="$emit('navigate', 'settings')"
      >
        <span class="nav-icon">⚙</span>
        设置
      </button>
      <button class="nav-item nav-item-muted" @click="$emit('refresh')">
        <span class="nav-icon">↻</span>
        刷新数据
      </button>
    </nav>

    <div class="sidebar-footer">
      <div class="health" :class="{ ok: health.ready }">
        <span class="health-dot" />
        <span class="health-text">{{ health.label }}</span>
      </div>
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
.nav-group-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  padding: 10px 12px 4px;
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
.nav-badge {
  margin-left: auto;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
}
.nav-badge.warn {
  background: rgba(255, 176, 32, 0.15);
  color: var(--warn);
}
.nav-badge.ok {
  background: rgba(46, 230, 166, 0.12);
  color: var(--ok);
}
.nav-badge.danger {
  background: rgba(255, 77, 109, 0.15);
  color: var(--danger);
}
.nav-item-muted {
  color: var(--muted);
}
.nav-item-muted:hover {
  color: var(--text);
}
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
}
.health.ok { color: var(--ok); }
.health-text {
  line-height: 1.4;
  word-break: break-word;
}
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
    flex-wrap: wrap;
  }
  .nav-group-label { display: none; }
  .sidebar-footer {
    display: flex;
    align-items: center;
    gap: 10px;
    border-top: none;
    padding: 8px 12px;
  }
  .health { margin-bottom: 0; }
}
</style>
