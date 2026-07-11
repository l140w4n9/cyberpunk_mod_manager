<script setup>
import { computed, ref } from 'vue'
import { depChipClass, depTypeLabel, DEPS_PREVIEW_COUNT } from '../../utils/mods'

const props = defineProps({
  dependencies: { type: Array, default: () => [] },
  previewCount: { type: Number, default: DEPS_PREVIEW_COUNT },
})

const expanded = ref(false)

const total = computed(() => props.dependencies.length)
const needsCollapse = computed(() => total.value > props.previewCount)
const visibleDeps = computed(() => {
  if (!needsCollapse.value || expanded.value) return props.dependencies
  return props.dependencies.slice(0, props.previewCount)
})
const hiddenCount = computed(() => Math.max(0, total.value - props.previewCount))

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div v-if="dependencies.length" class="dep-list">
    <div class="chip-row">
      <span
        v-for="dep in visibleDeps"
        :key="dep.nexus_mod_id"
        class="chip mono"
        :class="depChipClass(dep)"
        :title="depTypeLabel(dep)"
      >
        <span v-if="!dep.installed" class="chip-tag">{{ depTypeLabel(dep) }}</span>
        #{{ dep.nexus_mod_id }}
      </span>
    </div>
    <button
      v-if="needsCollapse"
      type="button"
      class="expand-btn"
      @click="toggle"
    >
      {{ expanded ? '收起' : `展开剩余 ${hiddenCount} 项` }}
      <span class="expand-meta">（共 {{ total }} 项）</span>
    </button>
  </div>
</template>

<style scoped>
.dep-list { margin-top: 8px; }
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.2);
}
.chip.ok { border-color: rgba(46, 230, 166, 0.3); color: var(--ok); }
.chip.miss { border-color: rgba(255, 77, 109, 0.3); color: var(--danger); }
.chip.warn { border-color: rgba(255, 176, 32, 0.35); color: var(--warn); }
.chip-tag {
  font-size: 10px;
  opacity: 0.85;
  margin-right: 4px;
}
.expand-btn {
  margin-top: 8px;
  padding: 0;
  background: none;
  border: none;
  color: var(--accent2);
  font-size: 12px;
  cursor: pointer;
}
.expand-btn:hover { text-decoration: underline; }
.expand-meta {
  color: var(--muted);
  font-size: 11px;
}
</style>
