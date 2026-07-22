<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from './api/client'
import AppSidebar from './components/layout/AppSidebar.vue'
import AgentWorkspace from './views/AgentWorkspace.vue'
import ModsWorkspace from './views/ModsWorkspace.vue'
import SettingsWorkspace from './views/SettingsWorkspace.vue'
import CollectionWorkspace from './views/CollectionWorkspace.vue'
import MaintenanceWorkspace from './views/MaintenanceWorkspace.vue'
import UninstallDialog from './components/UninstallDialog.vue'
import { installHashListener, readSavedView, writeView } from './utils/navigation'
import { healthLabelFromData, i18nState, t } from './i18n'

const activeView = ref(readSavedView())
const mods = ref([])
const loading = ref(false)
const installing = ref(false)
const cleaning = ref(false)
const health = ref({ ready: false, label: t('health.checking') })
const lastHealthData = ref(null)
const status = ref({ message: '', type: '' })
const uninstallDialog = ref({ visible: false, report: null, modId: null })
const uninstalling = ref(false)

function setStatus(message, type = '') {
  status.value = { message, type }
  if (type) {
    setTimeout(() => {
      if (status.value.message === message) status.value = { message: '', type: '' }
    }, 5000)
  }
}

async function checkHealth() {
  try {
    const data = await api.health()
    const ready = data.data_dir_configured && data.nexus_valid && data.llm_configured
    lastHealthData.value = data
    health.value = {
      ready,
      label: healthLabelFromData(data),
      llm_configured: data.llm_configured,
      data_dir_configured: data.data_dir_configured,
      nexus_configured: data.nexus_configured,
      nexus_valid: data.nexus_valid,
      nexus_premium: data.nexus_premium,
      nexus_user: data.nexus_user || {},
      nexus_quota_warning: data.nexus_rate_limit?.warning || '',
      config_file: data.config_file || '',
    }
  } catch {
    lastHealthData.value = null
    health.value = {
      ready: false,
      label: t('health.connectionFailed'),
      llm_configured: false,
      data_dir_configured: false,
      nexus_configured: false,
      nexus_valid: false,
      config_file: '',
    }
  }
}

async function loadMods() {
  if (!health.value.data_dir_configured) {
    mods.value = []
    return
  }
  loading.value = true
  try {
    mods.value = await api.listMods(false)
  } catch (e) {
    setStatus(t('app.loadModsFailed', { error: e.message }), 'err')
  } finally {
    loading.value = false
  }
}

function navigate(view) {
  activeView.value = view
  writeView(view)
}

const MODS_FILTER = {
  mods: 'installed',
  'mods-pending': 'pending',
  'mods-incomplete': 'incomplete',
}

async function handleCleanupMod(modId) {
  cleaning.value = true
  setStatus(t('app.cleaningMod', { modId }), 'info')
  try {
    const data = await api.deleteMod(modId)
    setStatus(t('app.cleanedMod', { name: data.name || modId }), 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    cleaning.value = false
  }
}

async function handleCleanupAllPending(modIds) {
  cleaning.value = true
  setStatus(t('app.cleaningPending', { count: modIds.length }), 'info')
  try {
    const data = await api.cleanupPendingMods(modIds)
    const failed = data.failed_count || 0
    setStatus(
      failed
        ? t('app.cleanedWithFailed', { ok: data.deleted_count || 0, failed })
        : t('app.cleanedCount', { ok: data.deleted_count || 0 }),
      failed ? 'err' : 'ok',
    )
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    cleaning.value = false
  }
}

async function handleInstall(modId) {
  installing.value = true
  setStatus(t('app.installingMod', { modId }), 'info')
  try {
    const data = await api.installMod(modId)
    if (data.skipped) {
      setStatus(data.message || t('app.modSkipped', { modId }), 'info')
    } else {
      setStatus(t('app.installDone', { name: data.name || modId }), 'ok')
    }
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleInstallWithDeps(modId) {
  installing.value = true
  setStatus(t('app.installingWithDeps', { modId }), 'info')
  try {
    const data = await api.installModWithDeps(modId)
    const repaired = (data.dependencies_installed || []).filter((d) => !d.skipped).length
    const depsFail = (data.dependencies_failed || []).length
    if (data.reason === 'deps_repair' || (data.skipped && (repaired || depsFail))) {
      setStatus(
        data.message ||
          (depsFail
            ? t('app.depsRepairedWithFailed', { repaired, failed: depsFail })
            : t('app.depsRepaired', { repaired })),
        depsFail ? 'err' : 'ok',
      )
    } else if (data.skipped) {
      setStatus(data.message || t('app.modSkipped', { modId }), 'info')
    } else {
      setStatus(
        depsFail
          ? t('app.installWithFilesFailed', { count: data.added_files_count || 0, failed: depsFail })
          : t('app.installWithFiles', { count: data.added_files_count || 0 }),
        depsFail ? 'err' : 'ok',
      )
    }
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleInstallLocal({ modId, archiveName }) {
  installing.value = true
  setStatus(t('app.localInstalling', { modId }), 'info')
  try {
    const data = await api.installLocalMod(modId, archiveName)
    setStatus(t('app.localInstallDone', { count: data.added_files_count }), 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleScanLocalFolder(folderPath, callback) {
  try {
    callback(await api.scanLocalFolder(folderPath))
  } catch (e) {
    setStatus(t('app.scanFailed', { error: e.message }), 'err')
    callback(null)
  }
}

async function handleInstallLocalFolder({ folderPath, modIds }) {
  installing.value = true
  setStatus(t('app.folderInstalling'), 'info')
  try {
    const data = await api.installLocalFolder(folderPath, modIds)
    const failed = (data.failed || []).length
    const ok = (data.succeeded || []).length
    const skipped = (data.skipped || []).length
    const msg = data.message
      || t('app.folderInstallDone', { ok })
        + (skipped ? t('app.folderInstallSkipped', { skipped }) : '')
        + (failed ? t('app.folderInstallFailed', { failed }) : '')
    setStatus(`✓ ${msg}`, failed ? 'err' : 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleCheckDeps(modId, callback) {
  try {
    callback(await api.modDependencies(modId))
  } catch (e) {
    setStatus(t('app.depsCheckFailed', { error: e.message }), 'err')
    callback(null)
  }
}

async function handleUninstall(modId) {
  try {
    const report = await api.uninstallCheck(modId)
    if (!report.can_uninstall) {
      setStatus(report.warnings?.[0] || t('app.cannotUninstall'), 'err')
      return
    }
    uninstallDialog.value = { visible: true, report, modId }
  } catch (e) {
    setStatus(t('app.uninstallCheckFailed', { error: e.message }), 'err')
  }
}

async function confirmUninstall(force) {
  const modId = uninstallDialog.value.modId
  if (!modId) return
  uninstalling.value = true
  try {
    const data = await api.uninstallMod(modId, force)
    uninstallDialog.value = { visible: false, report: null, modId: null }
    setStatus(t('app.uninstalled', { count: data.removed_files_count }), 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    uninstalling.value = false
  }
}

function cancelUninstall() {
  uninstallDialog.value = { visible: false, report: null, modId: null }
}

function onConfigSaved() {
  checkHealth().then(() => loadMods())
}

watch(
  () => i18nState.locale,
  () => {
    if (lastHealthData.value) {
      health.value.label = healthLabelFromData(lastHealthData.value)
    } else if (!health.value.ready) {
      health.value.label = t('health.connectionFailed')
    }
  },
)

let removeHashListener = null

onMounted(async () => {
  writeView(activeView.value)
  removeHashListener = installHashListener((view) => {
    activeView.value = view
  })
  await checkHealth()
  if (!health.value.data_dir_configured && activeView.value === 'agent') {
    activeView.value = 'settings'
    writeView('settings')
  }
  await loadMods()
})

onUnmounted(() => {
  if (removeHashListener) removeHashListener()
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar
      :active="activeView"
      :health="health"
      :mods="mods"
      @navigate="navigate"
      @refresh="loadMods"
    />

    <main class="main-content">
      <AgentWorkspace v-if="activeView === 'agent'" :health="health" @done="loadMods" />
      <SettingsWorkspace
        v-else-if="activeView === 'settings'"
        @saved="onConfigSaved"
      />
      <ModsWorkspace
        v-else-if="MODS_FILTER[activeView]"
        :mods="mods"
        :loading="loading"
        :installing="installing"
        :cleaning="cleaning"
        :status="status"
        :filter-mode="MODS_FILTER[activeView]"
        @install="handleInstall"
        @install-with-deps="handleInstallWithDeps"
        @install-local="handleInstallLocal"
        @scan-local-folder="handleScanLocalFolder"
        @install-local-folder="handleInstallLocalFolder"
        @check-deps="handleCheckDeps"
        @uninstall="handleUninstall"
        @cleanup-mod="handleCleanupMod"
        @cleanup-all-pending="handleCleanupAllPending"
      />
      <CollectionWorkspace
        v-else-if="activeView === 'collections'"
        :health="health"
        :installing="installing"
        @install-started="installing = true"
        @install-finished="installing = false"
        @refresh-mods="loadMods"
      />
      <MaintenanceWorkspace
        v-else-if="activeView === 'maintenance'"
        :health="health"
        :installing="installing"
        @refresh-mods="loadMods"
        @status="setStatus"
        @agent-handoff="navigate('agent')"
      />
      <div v-else class="empty-fallback panel">
        <p>{{ t('app.pageNotFound') }}</p>
        <button class="btn-primary" @click="navigate('agent')">{{ t('app.backToAgent') }}</button>
      </div>
    </main>

    <UninstallDialog
      :visible="uninstallDialog.visible"
      :report="uninstallDialog.report"
      :loading="uninstalling"
      @confirm="confirmUninstall"
      @cancel="cancelUninstall"
    />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg);
}
.main-content {
  flex: 1;
  margin-left: var(--sidebar-width);
  min-width: 0;
  min-height: 100vh;
}
.empty-fallback {
  margin: 24px;
  padding: 24px;
  text-align: center;
  color: var(--muted);
}

@media (max-width: 900px) {
  .app-shell { flex-direction: column; }
  .main-content { margin-left: 0; }
}
</style>
