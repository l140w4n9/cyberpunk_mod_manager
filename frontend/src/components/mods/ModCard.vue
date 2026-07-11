<script setup>
import { STATUS_LABELS } from '../../api/client'
import DepChipList from './DepChipList.vue'

defineProps({
  mod: { type: Object, required: true },
  showWarning: { type: Boolean, default: false },
})

defineEmits(['uninstall', 'install-with-deps'])

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

function summaryLabel(source) {
  if (source === 'ai') return 'AI'
  if (source === 'fallback') return '简介'
  return ''
}
</script>

<template>
  <article class="mod-card panel">
    <div class="mod-top">
      <div>
        <div class="mod-title-row">
          <span class="mod-id mono">#{{ mod.nexus_mod_id }}</span>
          <h3>{{ mod.name || '—' }}</h3>
          <span class="badge" :class="mod.status">{{ STATUS_LABELS[mod.status] || mod.status }}</span>
          <span v-if="showWarning" class="badge warn">依赖不全</span>
        </div>
        <p v-if="mod.summary_line" class="summary">
          <span v-if="summaryLabel(mod.summary_source)" class="tag">{{ summaryLabel(mod.summary_source) }}</span>
          {{ mod.summary_line }}
        </p>
      </div>
      <div class="mod-actions">
        <button
          v-if="showWarning"
          class="btn-primary btn-sm"
          @click="$emit('install-with-deps', mod.nexus_mod_id)"
        >
          补装依赖
        </button>
        <button
          class="btn-danger btn-sm"
          :disabled="mod.status !== 'installed'"
          @click="$emit('uninstall', mod.nexus_mod_id)"
        >
          卸载
        </button>
      </div>
    </div>

    <div class="mod-meta mono">
      <span>v{{ mod.version || '—' }}</span>
      <span>{{ formatDate(mod.installed_at) }}</span>
      <span v-if="mod.dependencies_missing_count" class="miss-count">
        缺失 {{ mod.dependencies_missing_count }} 项必需依赖
      </span>
    </div>

    <div v-if="mod.dependencies?.length" class="deps-section">
      <span class="section-label">前置依赖</span>
      <DepChipList :dependencies="mod.dependencies" />
    </div>
  </article>
</template>

<style scoped>
.mod-card { padding: 16px; }
.mod-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.mod-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}
.mod-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}
.mod-id { color: var(--accent2); font-size: 12px; }
.mod-title-row h3 { font-size: 15px; }
.badge.warn {
  background: rgba(255, 176, 32, 0.12);
  color: var(--warn);
  border: 1px solid rgba(255, 176, 32, 0.3);
}
.summary {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
}
.tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  background: rgba(252, 238, 10, 0.1);
  color: var(--accent);
}
.mod-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--muted);
}
.miss-count { color: var(--danger); }
.deps-section { margin-top: 12px; }
.section-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
</style>
