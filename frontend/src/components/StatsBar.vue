<script setup>
import { computed } from 'vue'

const props = defineProps({
  mods: { type: Array, default: () => [] },
})

const stats = computed(() => {
  const result = { total: props.mods.length, installed: 0, downloaded: 0, pending: 0, other: 0 }
  for (const m of props.mods) {
    if (m.status === 'installed') result.installed++
    else if (m.status === 'downloaded') result.downloaded++
    else if (m.status === 'not_installed') result.pending++
    else result.other++
  }
  return result
})
</script>

<template>
  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-label">模组总数</div>
      <div class="stat-value accent">{{ stats.total }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">已安装</div>
      <div class="stat-value">{{ stats.installed }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">已下载</div>
      <div class="stat-value ok">{{ stats.downloaded }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">待处理</div>
      <div class="stat-value">{{ stats.pending }}</div>
    </div>
  </div>
</template>

<style scoped>
.stats-bar {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 20px 32px 0;
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
}
.stat-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  transition: border-color 0.2s, transform 0.2s;
}
.stat-card:hover {
  border-color: var(--panel-border);
  transform: translateY(-2px);
}
.stat-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--muted);
  font-weight: 600;
}
.stat-value {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  margin-top: 4px;
  color: var(--accent2);
}
.stat-value.accent { color: var(--accent); }
.stat-value.ok { color: var(--ok); }

@media (max-width: 1100px) {
  .stats-bar { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 600px) {
  .stats-bar { padding: 16px 16px 0; }
}
</style>
