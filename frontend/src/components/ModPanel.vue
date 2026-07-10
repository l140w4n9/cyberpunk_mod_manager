<script setup>
import { ref } from 'vue'
import { STATUS_LABELS } from '../api/client'

defineProps({
  mods: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  installing: { type: Boolean, default: false },
  status: { type: Object, default: () => ({ message: '', type: '' }) },
})

const emit = defineEmits([
  'install',
  'install-with-deps',
  'install-local',
  'uninstall',
  'check-deps',
])

const modIdInput = ref('')
const archiveNameInput = ref('')
const depsReport = ref(null)
const checkingDeps = ref(false)
const expandedId = ref(null)

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

function summaryLabel(source) {
  if (source === 'ai') return 'AI 摘要'
  if (source === 'fallback') return '简介'
  return ''
}

function toggleExpand(nexusModId) {
  expandedId.value = expandedId.value === nexusModId ? null : nexusModId
}

function submitInstall(withDeps = false) {
  const id = modIdInput.value.trim()
  if (!id) return
  emit(withDeps ? 'install-with-deps' : 'install', parseInt(id, 10))
}

function submitLocalInstall() {
  const id = modIdInput.value.trim()
  const archive = archiveNameInput.value.trim()
  if (!id || !archive) return
  emit('install-local', { modId: parseInt(id, 10), archiveName: archive })
}

function checkDeps() {
  const id = modIdInput.value.trim()
  if (!id) return
  checkingDeps.value = true
  depsReport.value = null
  emit('check-deps', parseInt(id, 10), (report) => {
    depsReport.value = report
    checkingDeps.value = false
  })
}
</script>

<template>
  <section class="panel">
    <div class="panel-title">模组库存</div>

    <form class="install-box" @submit.prevent="submitInstall(false)">
      <div class="input-wrap">
        <label>Nexus Mod ID</label>
        <input v-model="modIdInput" type="number" placeholder="例如 27967" />
      </div>
      <div class="input-wrap">
        <label>本地压缩包（Premium 手动下载）</label>
        <input v-model="archiveNameInput" type="text" placeholder="如 27967_0-Engine.zip" />
      </div>
      <div class="btn-row">
        <button class="btn-primary" type="submit" :disabled="installing || !modIdInput.trim()">
          {{ installing ? '安装中...' : '安装模组' }}
        </button>
        <button
          class="btn-secondary"
          type="button"
          :disabled="installing || !modIdInput.trim()"
          @click="submitInstall(true)"
        >
          安装含依赖
        </button>
        <button
          class="btn-secondary"
          type="button"
          :disabled="installing || !modIdInput.trim() || !archiveNameInput.trim()"
          @click="submitLocalInstall"
        >
          本地安装
        </button>
        <button
          class="btn-ghost"
          type="button"
          :disabled="checkingDeps || !modIdInput.trim()"
          @click="checkDeps"
        >
          {{ checkingDeps ? '检查中...' : '检查依赖' }}
        </button>
      </div>
    </form>

    <div v-if="depsReport" class="deps-panel">
      <div class="deps-title">
        依赖检查 — Mod {{ depsReport.mod_id }}
        <span class="deps-badge" :class="depsReport.all_satisfied ? 'ok' : 'warn'">
          {{ depsReport.all_satisfied ? '全部满足' : `缺失 ${depsReport.missing_count}` }}
        </span>
      </div>
      <ul class="deps-list">
        <li v-for="dep in depsReport.dependencies" :key="dep.nexus_mod_id">
          <span class="dep-id">{{ dep.nexus_mod_id }}</span>
          <span class="dep-name">{{ dep.name || '未知' }}</span>
          <span class="badge small" :class="dep.installed ? 'installed' : 'not_installed'">
            {{ dep.installed ? '已安装' : '未安装' }}
          </span>
        </li>
      </ul>
    </div>

    <div v-if="loading" class="mod-list-empty"><span class="spinner" />加载中...</div>
    <div v-else-if="!mods.length" class="mod-list-empty">
      <div class="empty-icon">◇</div>
      暂无模组
      <small>输入模组 ID 开始安装</small>
    </div>

    <div v-else class="mod-list">
      <article
        v-for="mod in mods"
        :key="mod.id"
        class="mod-card"
        :class="{ expanded: expandedId === mod.nexus_mod_id }"
      >
        <header class="mod-card__head">
          <div class="mod-card__main">
            <div class="mod-card__title-row">
              <span class="mod-id">{{ mod.nexus_mod_id }}</span>
              <h3 class="mod-name">{{ mod.name || '—' }}</h3>
              <span class="badge" :class="mod.status">
                {{ STATUS_LABELS[mod.status] || mod.status }}
              </span>
            </div>
            <p v-if="mod.summary_line" class="mod-summary">
              <span v-if="summaryLabel(mod.summary_source)" class="summary-tag">
                {{ summaryLabel(mod.summary_source) }}
              </span>
              {{ mod.summary_line }}
            </p>
            <a
              v-if="mod.mod_page_url"
              class="mod-link"
              :href="mod.mod_page_url"
              target="_blank"
              rel="noopener noreferrer"
            >Nexus 主页 →</a>
          </div>
          <div class="mod-card__meta">
            <span class="version">v{{ mod.version || '—' }}</span>
            <span class="time">{{ formatDate(mod.installed_at) }}</span>
            <button
              class="btn-danger"
              :disabled="mod.status !== 'installed'"
              @click="$emit('uninstall', mod.nexus_mod_id)"
            >卸载</button>
          </div>
        </header>

        <div class="mod-card__deps">
          <div class="deps-block">
            <span class="deps-label">前置依赖</span>
            <span
              v-if="mod.dependencies?.length"
              class="deps-count"
              :class="mod.dependencies_satisfied ? 'ok' : 'warn'"
            >
              {{ mod.dependencies_satisfied ? '已满足' : `缺 ${mod.dependencies_missing_count}` }}
            </span>
            <span v-else class="deps-count muted">无记录</span>
          </div>
          <div v-if="mod.dependencies?.length" class="chip-row">
            <span
              v-for="dep in mod.dependencies"
              :key="dep.nexus_mod_id"
              class="chip"
              :class="dep.installed ? 'chip--ok' : 'chip--miss'"
              :title="`${dep.name} (${dep.nexus_mod_id})`"
            >
              {{ dep.name || dep.nexus_mod_id }}
              <em>{{ dep.installed ? '✓' : '✕' }}</em>
            </span>
          </div>

          <div v-if="mod.dependents?.length" class="deps-block dependents">
            <span class="deps-label">被依赖</span>
            <button class="link-btn" @click="toggleExpand(mod.nexus_mod_id)">
              {{ expandedId === mod.nexus_mod_id ? '收起' : `查看 ${mod.dependents.length} 项` }}
            </button>
          </div>
          <div
            v-if="expandedId === mod.nexus_mod_id && mod.dependents?.length"
            class="chip-row"
          >
            <span
              v-for="dep in mod.dependents"
              :key="dep.nexus_mod_id"
              class="chip"
              :class="dep.installed ? 'chip--warn' : 'chip--idle'"
            >
              {{ dep.name || dep.nexus_mod_id }}
              <em>{{ dep.installed ? '已装' : '未装' }}</em>
            </span>
          </div>
        </div>
      </article>
    </div>

    <div v-if="status.message" class="status-line" :class="status.type">
      {{ status.message }}
    </div>
  </section>
</template>

<style scoped>
.install-box {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px dashed rgba(0, 240, 255, 0.2);
  border-radius: var(--radius-sm);
}
.install-box .input-wrap { flex: 1 1 200px; }
.btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-end;
  width: 100%;
}
.btn-secondary {
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(0, 240, 255, 0.35);
  background: rgba(0, 240, 255, 0.08);
  color: var(--accent2);
  cursor: pointer;
}
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost {
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.deps-panel {
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.25);
}
.deps-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  margin-bottom: 10px;
}
.deps-badge.ok { color: var(--ok); }
.deps-badge.warn { color: var(--accent); }
.deps-list { list-style: none; margin: 0; padding: 0; }
.deps-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.dep-id {
  font-family: var(--font-display);
  color: var(--accent2);
  min-width: 48px;
}
.dep-name { flex: 1; }
.badge.small { font-size: 11px; padding: 2px 8px; }

.mod-list { display: flex; flex-direction: column; gap: 12px; }
.mod-list-empty {
  text-align: center;
  padding: 48px 20px;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.mod-list-empty small { display: block; margin-top: 8px; }
.empty-icon { font-size: 28px; margin-bottom: 8px; opacity: 0.4; }

.mod-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.28);
  overflow: hidden;
}
.mod-card__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.mod-card__title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}
.mod-id {
  font-family: var(--font-display);
  color: var(--accent2);
  font-size: 13px;
}
.mod-name {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.mod-summary {
  margin: 0 0 6px;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
}
.summary-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  letter-spacing: 0.5px;
  color: var(--accent);
  border: 1px solid rgba(252, 238, 10, 0.35);
  background: rgba(252, 238, 10, 0.08);
}
.mod-link {
  color: var(--accent2);
  font-size: 12px;
  text-decoration: none;
}
.mod-card__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}
.version, .time {
  font-size: 12px;
  color: var(--muted);
}
.mod-card__deps {
  padding: 12px 16px 14px;
}
.deps-block {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.deps-block.dependents { margin-top: 10px; margin-bottom: 0; }
.deps-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--muted);
}
.deps-count { font-size: 12px; }
.deps-count.ok { color: var(--ok); }
.deps-count.warn { color: var(--accent); }
.deps-count.muted { color: var(--muted); }
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.35);
}
.chip em {
  font-style: normal;
  font-size: 10px;
  opacity: 0.85;
}
.chip--ok { border-color: rgba(46, 230, 166, 0.35); color: var(--ok); }
.chip--miss { border-color: rgba(255, 59, 92, 0.35); color: var(--danger); }
.chip--warn { border-color: rgba(252, 238, 10, 0.35); color: var(--accent); }
.chip--idle { color: var(--muted); }
.link-btn {
  background: none;
  border: none;
  color: var(--accent2);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.status-line {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.status-line.info {
  background: rgba(0, 240, 255, 0.08);
  border: 1px solid rgba(0, 240, 255, 0.2);
  color: var(--accent2);
}
.status-line.ok {
  background: rgba(46, 230, 166, 0.08);
  border: 1px solid rgba(46, 230, 166, 0.2);
  color: var(--ok);
}
.status-line.err {
  background: rgba(255, 59, 92, 0.08);
  border: 1px solid rgba(255, 59, 92, 0.2);
  color: var(--danger);
}

@media (max-width: 700px) {
  .mod-card__head { flex-direction: column; }
  .mod-card__meta { align-items: flex-start; flex-direction: row; flex-wrap: wrap; }
}
@media (max-width: 600px) {
  .install-box { flex-direction: column; }
}
</style>
