<script setup>
import { computed } from 'vue'
import { filterMods } from '../../utils/mods'
import { useI18n } from '../../i18n'

const props = defineProps({
  active: { type: String, default: 'agent' },
  health: { type: Object, required: true },
  mods: { type: Array, default: () => [] },
})

defineEmits(['navigate', 'refresh'])

const { t, locale, setLocale } = useI18n()

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
        {{ t('nav.agent') }}
      </button>

      <div class="nav-group-label">{{ t('nav.mods') }}</div>
      <button
        class="nav-item"
        :class="{ active: active === 'mods' }"
        @click="$emit('navigate', 'mods')"
      >
        <span class="nav-icon">▣</span>
        {{ t('nav.installed') }}
        <span v-if="installedCount" class="nav-badge ok">{{ installedCount }}</span>
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'mods-pending' }"
        @click="$emit('navigate', 'mods-pending')"
      >
        <span class="nav-icon">○</span>
        {{ t('nav.pending') }}
        <span v-if="pendingCount" class="nav-badge warn">{{ pendingCount }}</span>
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'mods-incomplete' }"
        @click="$emit('navigate', 'mods-incomplete')"
      >
        <span class="nav-icon">⚠</span>
        {{ t('nav.incomplete') }}
        <span v-if="incompleteCount" class="nav-badge danger">{{ incompleteCount }}</span>
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'collections' }"
        @click="$emit('navigate', 'collections')"
      >
        <span class="nav-icon">♥</span>
        {{ t('nav.collections') }}
      </button>
      <button
        class="nav-item"
        :class="{ active: active === 'maintenance' }"
        @click="$emit('navigate', 'maintenance')"
      >
        <span class="nav-icon">✦</span>
        {{ t('nav.maintenance') }}
      </button>

      <div class="nav-group-label">{{ t('nav.system') }}</div>
      <button
        class="nav-item"
        :class="{ active: active === 'settings' }"
        @click="$emit('navigate', 'settings')"
      >
        <span class="nav-icon">⚙</span>
        {{ t('nav.settings') }}
      </button>
      <button class="nav-item nav-item-muted" @click="$emit('refresh')">
        <span class="nav-icon">↻</span>
        {{ t('nav.refresh') }}
      </button>
    </nav>

    <div class="sidebar-footer">
      <div class="lang-switch" role="group" :aria-label="t('lang.label')">
        <button
          type="button"
          class="lang-btn"
          :class="{ active: locale === 'zh' }"
          @click="setLocale('zh')"
        >
          {{ t('lang.zh') }}
        </button>
        <button
          type="button"
          class="lang-btn"
          :class="{ active: locale === 'en' }"
          @click="setLocale('en')"
        >
          {{ t('lang.en') }}
        </button>
      </div>
      <div class="health" :class="{ ok: health.ready }">
        <span class="health-dot" />
        <div class="health-meta">
          <span class="health-text">{{ health.label }}</span>
          <span
            v-if="health.nexus_valid && health.nexus_user?.name"
            class="health-sub"
          >
            {{ health.nexus_user.name }}
            <template v-if="health.nexus_premium"> · Premium</template>
          </span>
          <span v-if="health.nexus_quota_warning" class="health-sub warn">
            {{ health.nexus_quota_warning }}
          </span>
        </div>
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
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.lang-switch {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
}
.lang-btn {
  flex: 1;
  padding: 5px 8px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}
.lang-btn:hover {
  color: var(--text);
}
.lang-btn.active {
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent2);
}
.health {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--danger);
}
.health.ok { color: var(--ok); }
.health-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.health-text {
  line-height: 1.4;
  word-break: break-word;
}
.health-sub {
  font-size: 10px;
  opacity: 0.75;
  line-height: 1.3;
}
.health-sub.warn {
  color: var(--warn, #e6a817);
  opacity: 1;
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
    flex-direction: row;
  }
  .lang-switch { flex: none; }
  .health { margin-bottom: 0; }
}
</style>
