<script setup>
import { computed, ref } from 'vue'
import ModCard from '../components/mods/ModCard.vue'
import DepChipList from '../components/mods/DepChipList.vue'
import { filterMods } from '../utils/mods'
import { useI18n } from '../i18n'

const props = defineProps({
  mods: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  installing: { type: Boolean, default: false },
  status: { type: Object, default: () => ({ message: '', type: '' }) },
  cleaning: { type: Boolean, default: false },
  /** installed | pending | incomplete */
  filterMode: { type: String, default: 'installed' },
})

const emit = defineEmits([
  'install',
  'install-with-deps',
  'install-local',
  'install-local-folder',
  'scan-local-folder',
  'uninstall',
  'check-deps',
  'cleanup-mod',
  'cleanup-all-pending',
])

const { t } = useI18n()

const modIdInput = ref('')
const archiveNameInput = ref('')
const folderPathInput = ref('')
const folderScan = ref(null)
const scanningFolder = ref(false)
const depsReport = ref(null)
const checkingDeps = ref(false)

const pageMeta = computed(() => ({
  title: t(`mods.${props.filterMode}.title`),
  desc: t(`mods.${props.filterMode}.desc`),
  empty: t(`mods.${props.filterMode}.empty`),
}))
const filteredMods = computed(() => filterMods(props.mods, props.filterMode))

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

function scanFolder() {
  const folder = folderPathInput.value.trim()
  if (!folder) return
  scanningFolder.value = true
  folderScan.value = null
  emit('scan-local-folder', folder, (result) => {
    folderScan.value = result
    scanningFolder.value = false
  })
}

function installFromFolder() {
  const folder = folderPathInput.value.trim()
  if (!folder) return
  const id = modIdInput.value.trim()
  const modIds = id ? [parseInt(id, 10)] : null

  if (folderScan.value?.is_downloads_dir && !modIds) {
    window.alert(t('mods.noDownloadsBatch'))
    return
  }

  const pending = folderScan.value?.pending_count
  if (!modIds && pending != null && pending > 0) {
    const skip = folderScan.value?.installed_count || 0
    const msg = t('mods.confirmFolderInstall', {
      pending,
      skip: skip ? t('mods.confirmFolderSkip', { skip }) : '',
    })
    if (!window.confirm(msg)) return
  }

  emit('install-local-folder', { folderPath: folder, modIds })
}

function cleanupMod(modId) {
  const mod = filteredMods.value.find((m) => m.nexus_mod_id === modId)
  const label = mod?.name ? `${mod.name} (#${modId})` : `#${modId}`
  if (!window.confirm(t('mods.confirmCleanup', { label }))) return
  emit('cleanup-mod', modId)
}

function cleanupAllPending() {
  const count = filteredMods.value.length
  if (!count) return
  if (!window.confirm(t('mods.confirmCleanupAll', { count }))) return
  emit('cleanup-all-pending', filteredMods.value.map((m) => m.nexus_mod_id))
}
</script>

<template>
  <div class="mods-view">
    <header class="view-header">
      <div>
        <h2>{{ pageMeta.title }}</h2>
        <p>{{ pageMeta.desc }}</p>
      </div>
      <span class="count-badge">{{ t('mods.items', { count: filteredMods.length }) }}</span>
    </header>

    <section v-if="filterMode === 'installed'" class="install-section panel">
      <div class="install-grid">
        <div class="input-wrap">
          <label>{{ t('mods.modId') }}</label>
          <input v-model="modIdInput" type="number" placeholder="27967" />
        </div>
        <div class="input-wrap">
          <label>{{ t('mods.localArchive') }}</label>
          <input v-model="archiveNameInput" type="text" placeholder="27967_xxx.zip" />
        </div>
      </div>
      <div class="btn-row">
        <button class="btn-primary" :disabled="installing || !modIdInput.trim()" @click="submitInstall(false)">
          {{ installing ? t('mods.installing') : t('mods.install') }}
        </button>
        <button class="btn-ghost" :disabled="installing || !modIdInput.trim()" @click="submitInstall(true)">
          {{ t('mods.withDeps') }}
        </button>
        <button
          class="btn-ghost"
          :disabled="installing || !modIdInput.trim() || !archiveNameInput.trim()"
          @click="submitLocalInstall"
        >
          {{ t('mods.localInstall') }}
        </button>
        <button class="btn-ghost" :disabled="checkingDeps || !modIdInput.trim()" @click="checkDeps">
          {{ checkingDeps ? t('mods.checking') : t('mods.checkDeps') }}
        </button>
      </div>

      <div v-if="depsReport" class="deps-report">
        <span :class="depsReport.all_satisfied ? 'ok' : 'warn'">
          {{
            depsReport.all_satisfied
              ? t('mods.depsOk')
              : t('mods.depsMissing', { count: depsReport.missing_count })
          }}
        </span>
        <DepChipList :dependencies="depsReport.dependencies" />
      </div>

      <div class="folder-section">
        <div class="section-divider">{{ t('mods.folderBatch') }}</div>
        <div class="input-wrap">
          <label>{{ t('mods.localFolder') }}</label>
          <input
            v-model="folderPathInput"
            type="text"
            :placeholder="t('mods.folderPlaceholder')"
          />
          <p class="input-hint">{{ t('mods.folderHint') }}</p>
        </div>
        <div class="btn-row">
          <button class="btn-ghost" :disabled="scanningFolder || !folderPathInput.trim()" @click="scanFolder">
            {{ scanningFolder ? t('mods.scanning') : t('mods.scanFolder') }}
          </button>
          <button
            class="btn-primary"
            :disabled="installing || !folderPathInput.trim()"
            @click="installFromFolder"
          >
            {{
              installing
                ? t('mods.installing')
                : modIdInput.trim()
                  ? t('mods.folderInstallOne')
                  : t('mods.folderInstallAll')
            }}
          </button>
        </div>
        <div v-if="folderScan" class="scan-result">
          <span class="scan-summary">
            {{ t('mods.detected', { count: folderScan.detected_count }) }} ·
            <span class="ok-text">{{ t('mods.installedCount', { count: folderScan.installed_count || 0 }) }}</span> ·
            <span class="pending-text">{{ t('mods.pendingCount', { count: folderScan.pending_count || 0 }) }}</span>
            <template v-if="folderScan.is_downloads_dir"> · {{ t('mods.downloadsDir') }}</template>
          </span>
          <div v-if="folderScan.detected?.length" class="chip-row mono">
            <span
              v-for="item in folderScan.detected"
              :key="item.mod_id"
              class="chip"
              :class="item.installed ? 'installed' : 'pending'"
            >
              #{{ item.mod_id }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <div v-if="loading" class="empty-state"><span class="spinner" /> {{ t('mods.loading') }}</div>
    <div v-else-if="!filteredMods.length" class="empty-state">{{ pageMeta.empty }}</div>

    <section v-else-if="filterMode === 'pending'" class="pending-toolbar panel">
      <p class="toolbar-hint">{{ t('mods.pendingToolbar') }}</p>
      <button
        class="btn-danger"
        :disabled="installing || cleaning"
        @click="cleanupAllPending"
      >
        {{
          cleaning
            ? t('mods.cleaning')
            : t('mods.cleanupAll', { count: filteredMods.length })
        }}
      </button>
    </section>

    <div v-if="!loading && filteredMods.length" class="mod-grid">
      <ModCard
        v-for="mod in filteredMods"
        :key="mod.id"
        :mod="mod"
        :filter-mode="filterMode"
        :show-warning="filterMode === 'incomplete'"
        :installing="installing"
        :cleaning="cleaning"
        @install="$emit('install', $event)"
        @uninstall="$emit('uninstall', $event)"
        @install-with-deps="$emit('install-with-deps', $event)"
        @cleanup="cleanupMod"
      />
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
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
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
.count-badge {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
  white-space: nowrap;
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
.folder-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.section-divider {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent2);
  margin-bottom: 12px;
}
.input-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 6px;
}
.scan-result { margin-top: 12px; }
.scan-summary { font-size: 12px; color: var(--muted); }
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
.chip.installed {
  border-color: rgba(46, 230, 166, 0.3);
  color: var(--ok);
}
.chip.pending {
  border-color: rgba(255, 176, 32, 0.35);
  color: var(--warn);
}
.ok-text { color: var(--ok); }
.pending-text { color: var(--warn); }
.pending-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px 16px;
}
.toolbar-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  max-width: 520px;
  line-height: 1.4;
}

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
