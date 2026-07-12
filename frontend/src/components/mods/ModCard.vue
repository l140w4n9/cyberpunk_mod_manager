<script setup>
import { useI18n, statusLabel } from '../../i18n'
import DepChipList from './DepChipList.vue'

defineProps({
  mod: { type: Object, required: true },
  showWarning: { type: Boolean, default: false },
  filterMode: { type: String, default: 'installed' },
  installing: { type: Boolean, default: false },
  cleaning: { type: Boolean, default: false },
})

defineEmits(['uninstall', 'install', 'install-with-deps', 'cleanup'])

const { t, locale } = useI18n()

function formatDate(value) {
  if (!value) return '—'
  const loc = locale.value === 'zh' ? 'zh-CN' : 'en-US'
  return new Date(value).toLocaleString(loc)
}

function summaryLabel(source) {
  if (source === 'ai') return t('modCard.summaryAi')
  if (source === 'fallback') return t('modCard.summaryFallback')
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
          <span class="badge" :class="mod.status">{{ statusLabel(mod.status) }}</span>
          <span v-if="showWarning" class="badge warn">{{ t('modCard.depsIncomplete') }}</span>
        </div>
        <p v-if="mod.summary_line" class="summary">
          <span v-if="summaryLabel(mod.summary_source)" class="tag">{{ summaryLabel(mod.summary_source) }}</span>
          {{ mod.summary_line }}
        </p>
      </div>
      <div class="mod-actions">
        <template v-if="filterMode === 'pending'">
          <button
            class="btn-primary btn-sm"
            :disabled="installing"
            @click="$emit('install', mod.nexus_mod_id)"
          >
            {{ installing ? t('modCard.install') + '...' : t('modCard.install') }}
          </button>
          <button
            class="btn-ghost btn-sm"
            :disabled="installing"
            @click="$emit('install-with-deps', mod.nexus_mod_id)"
          >
            {{ t('modCard.withDeps') }}
          </button>
          <button
            class="btn-danger btn-sm"
            :disabled="installing || cleaning"
            @click="$emit('cleanup', mod.nexus_mod_id)"
          >
            {{ cleaning ? t('modCard.cleaning') : t('modCard.cleanup') }}
          </button>
        </template>
        <button
          v-if="filterMode === 'incomplete' || showWarning"
          class="btn-primary btn-sm"
          :disabled="installing"
          @click="$emit('install-with-deps', mod.nexus_mod_id)"
        >
          {{ installing ? t('mods.installing') : t('modCard.repairDeps') }}
        </button>
        <button
          v-if="filterMode === 'installed'"
          class="btn-danger btn-sm"
          :disabled="mod.status !== 'installed' || installing"
          @click="$emit('uninstall', mod.nexus_mod_id)"
        >
          {{ t('modCard.uninstall') }}
        </button>
      </div>
    </div>

    <div class="mod-meta mono">
      <span>v{{ mod.version || '—' }}</span>
      <span>{{ formatDate(mod.installed_at) }}</span>
      <span v-if="mod.dependencies_missing_count" class="miss-count">
        {{ t('modCard.missingDeps', { count: mod.dependencies_missing_count }) }}
      </span>
    </div>

    <div v-if="mod.dependencies?.length" class="deps-section">
      <span class="section-label">{{ t('modCard.prerequisites') }}</span>
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
.mod-title-row h3 { font-size: 15px; font-weight: 600; margin: 0; }
.badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
}
.badge.installed { color: var(--ok); border: 1px solid rgba(46, 230, 166, 0.25); }
.badge.warn { color: var(--warn); border: 1px solid rgba(255, 176, 32, 0.3); }
.summary { font-size: 12px; color: var(--muted); line-height: 1.5; margin: 0; }
.tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(0, 212, 255, 0.1);
  color: var(--accent2);
  margin-right: 6px;
}
.mod-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
  color: var(--muted);
  margin-top: 10px;
}
.miss-count { color: var(--warn); }
.deps-section { margin-top: 12px; }
.section-label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 6px;
}
</style>
