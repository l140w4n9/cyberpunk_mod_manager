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
  if (source === 'ai') return 'AI'
  if (source === 'fallback') return '简介'
  return ''
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
  <div class="mods-view">
    <header class="view-header">
      <div>
        <h2>模组库存</h2>
        <p>管理已安装模组、依赖关系与安全卸载</p>
      </div>
    </header>

    <section class="install-section panel">
      <div class="install-grid">
        <div class="input-wrap">
          <label>Nexus Mod ID</label>
          <input v-model="modIdInput" type="number" placeholder="27967" />
        </div>
        <div class="input-wrap">
          <label>本地压缩包</label>
          <input v-model="archiveNameInput" type="text" placeholder="27967_xxx.zip" />
        </div>
      </div>
      <div class="btn-row">
        <button class="btn-primary" :disabled="installing || !modIdInput.trim()" @click="submitInstall(false)">
          {{ installing ? '安装中...' : '安装' }}
        </button>
        <button class="btn-ghost" :disabled="installing || !modIdInput.trim()" @click="submitInstall(true)">
          含依赖安装
        </button>
        <button
          class="btn-ghost"
          :disabled="installing || !modIdInput.trim() || !archiveNameInput.trim()"
          @click="submitLocalInstall"
        >
          本地安装
        </button>
        <button class="btn-ghost" :disabled="checkingDeps || !modIdInput.trim()" @click="checkDeps">
          {{ checkingDeps ? '检查中...' : '检查依赖' }}
        </button>
      </div>

      <div v-if="depsReport" class="deps-report">
        <span :class="depsReport.all_satisfied ? 'ok' : 'warn'">
          {{ depsReport.all_satisfied ? '依赖已满足' : `缺失 ${depsReport.missing_count} 项` }}
        </span>
        <div class="chip-row">
          <span
            v-for="dep in depsReport.dependencies"
            :key="dep.nexus_mod_id"
            class="chip"
            :class="dep.installed ? 'ok' : 'miss'"
          >
            {{ dep.name || dep.nexus_mod_id }}
          </span>
        </div>
      </div>
    </section>

    <div v-if="loading" class="empty-state"><span class="spinner" /> 加载中...</div>
    <div v-else-if="!mods.length" class="empty-state">暂无模组</div>

    <div v-else class="mod-grid">
      <article v-for="mod in mods" :key="mod.id" class="mod-card panel">
        <div class="mod-top">
          <div>
            <div class="mod-title-row">
              <span class="mod-id mono">#{{ mod.nexus_mod_id }}</span>
              <h3>{{ mod.name || '—' }}</h3>
              <span class="badge" :class="mod.status">{{ STATUS_LABELS[mod.status] || mod.status }}</span>
            </div>
            <p v-if="mod.summary_line" class="summary">
              <span v-if="summaryLabel(mod.summary_source)" class="tag">{{ summaryLabel(mod.summary_source) }}</span>
              {{ mod.summary_line }}
            </p>
          </div>
          <button
            class="btn-danger btn-sm"
            :disabled="mod.status !== 'installed'"
            @click="$emit('uninstall', mod.nexus_mod_id)"
          >
            卸载
          </button>
        </div>

        <div class="mod-meta mono">
          <span>v{{ mod.version || '—' }}</span>
          <span>{{ formatDate(mod.installed_at) }}</span>
        </div>

        <div v-if="mod.dependencies?.length" class="deps-section">
          <span class="section-label">前置依赖</span>
          <div class="chip-row">
            <span
              v-for="dep in mod.dependencies"
              :key="dep.nexus_mod_id"
              class="chip"
              :class="dep.installed ? 'ok' : 'miss'"
            >
              {{ dep.name || dep.nexus_mod_id }}
            </span>
          </div>
        </div>
      </article>
    </div>

    <div v-if="status.message" class="toast" :class="status.type">{{ status.message }}</div>
  </div>
</template>

<style scoped>
.mods-view {
  padding: 20px 24px 32px;
  max-width: 1100px;
}
.view-header {
  margin-bottom: 20px;
}
.view-header h2 {
  font-size: 18px;
  font-weight: 700;
}
.view-header p {
  font-size: 13px;
  color: var(--muted);
  margin-top: 4px;
}
.install-section { margin-bottom: 20px; }
.install-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.btn-row { display: flex; flex-wrap: wrap; gap: 8px; }
.deps-report {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.deps-report .ok { color: var(--ok); font-size: 13px; font-weight: 600; }
.deps-report .warn { color: var(--warn); font-size: 13px; font-weight: 600; }
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
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

.empty-state {
  text-align: center;
  padding: 60px;
  color: var(--muted);
}
.mod-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.mod-card { padding: 16px; }
.mod-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
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
  gap: 16px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--muted);
}
.deps-section { margin-top: 12px; }
.section-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 12px 18px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  max-width: 400px;
  z-index: 200;
  box-shadow: var(--shadow);
}
.toast.info { background: #1a2430; border: 1px solid rgba(0, 212, 255, 0.3); color: var(--accent2); }
.toast.ok { background: #142820; border: 1px solid rgba(46, 230, 166, 0.3); color: var(--ok); }
.toast.err { background: #281820; border: 1px solid rgba(255, 77, 109, 0.3); color: var(--danger); }

@media (max-width: 700px) {
  .install-grid { grid-template-columns: 1fr; }
  .mods-view { padding: 16px; }
}
</style>
