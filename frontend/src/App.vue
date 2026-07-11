<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from './api/client'
import AppSidebar from './components/layout/AppSidebar.vue'
import AgentWorkspace from './views/AgentWorkspace.vue'
import ModsWorkspace from './views/ModsWorkspace.vue'
import SettingsWorkspace from './views/SettingsWorkspace.vue'
import CollectionWorkspace from './views/CollectionWorkspace.vue'
import UninstallDialog from './components/UninstallDialog.vue'
import { installHashListener, readSavedView, writeView } from './utils/navigation'

const activeView = ref(readSavedView())
const mods = ref([])
const loading = ref(false)
const installing = ref(false)
const health = ref({ ready: false, label: '检查中...' })
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
    let label = '系统就绪'
    if (!data.data_dir_configured) label = '数据目录未配置'
    else if (!data.llm_configured) label = 'LLM 未配置'
    else if (!data.nexus_configured) label = 'Nexus Key 未配置'
    else if (!data.nexus_valid) label = 'Nexus Key 无效'
    health.value = {
      ready,
      label,
      llm_configured: data.llm_configured,
      data_dir_configured: data.data_dir_configured,
      nexus_configured: data.nexus_configured,
      nexus_valid: data.nexus_valid,
      config_file: data.config_file || '',
    }
  } catch {
    health.value = {
      ready: false,
      label: '连接失败',
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
    setStatus('加载模组失败: ' + e.message, 'err')
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

async function handleInstall(modId) {
  installing.value = true
  setStatus(`正在安装模组 ${modId}...`, 'info')
  try {
    const data = await api.installMod(modId)
    if (data.skipped) {
      setStatus(data.message || `模组 ${modId} 已安装，已跳过`, 'info')
    } else {
      setStatus(`✓ ${data.name || modId} 安装完成`, 'ok')
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
  setStatus(`正在安装模组 ${modId} 及依赖...`, 'info')
  try {
    const data = await api.installModWithDeps(modId)
    if (data.skipped) {
      setStatus(data.message || `模组 ${modId} 已安装，已跳过`, 'info')
    } else {
      const depsFail = (data.dependencies_failed || []).length
      setStatus(
        `✓ 安装完成，新增 ${data.added_files_count || 0} 文件` +
          (depsFail ? `，${depsFail} 个依赖失败` : ''),
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
  setStatus(`本地安装模组 ${modId}...`, 'info')
  try {
    const data = await api.installLocalMod(modId, archiveName)
    setStatus(`✓ 本地安装完成，${data.added_files_count} 文件`, 'ok')
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
    setStatus('扫描失败: ' + e.message, 'err')
    callback(null)
  }
}

async function handleInstallLocalFolder({ folderPath, modIds }) {
  installing.value = true
  setStatus(`正在从文件夹安装...`, 'info')
  try {
    const data = await api.installLocalFolder(folderPath, modIds)
    const failed = (data.failed || []).length
    const ok = (data.succeeded || []).length
    const skipped = (data.skipped || []).length
    const msg = data.message
      || `文件夹安装完成：新装 ${ok} 个` +
        (skipped ? `，跳过 ${skipped} 个已安装` : '') +
        (failed ? `，${failed} 个失败` : '')
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
    setStatus('依赖检查失败: ' + e.message, 'err')
    callback(null)
  }
}

async function handleUninstall(modId) {
  try {
    const report = await api.uninstallCheck(modId)
    if (!report.can_uninstall) {
      setStatus(report.warnings?.[0] || '无法卸载', 'err')
      return
    }
    uninstallDialog.value = { visible: true, report, modId }
  } catch (e) {
    setStatus('卸载检查失败: ' + e.message, 'err')
  }
}

async function confirmUninstall(force) {
  const modId = uninstallDialog.value.modId
  if (!modId) return
  uninstalling.value = true
  try {
    const data = await api.uninstallMod(modId, force)
    uninstallDialog.value = { visible: false, report: null, modId: null }
    setStatus(`✓ 已卸载 ${data.removed_files_count} 个文件`, 'ok')
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
        :status="status"
        :filter-mode="MODS_FILTER[activeView]"
        @install="handleInstall"
        @install-with-deps="handleInstallWithDeps"
        @install-local="handleInstallLocal"
        @scan-local-folder="handleScanLocalFolder"
        @install-local-folder="handleInstallLocalFolder"
        @check-deps="handleCheckDeps"
        @uninstall="handleUninstall"
      />
      <CollectionWorkspace
        v-else-if="activeView === 'collections'"
        :health="health"
        :installing="installing"
        @install-started="installing = true"
        @install-finished="installing = false"
        @refresh-mods="loadMods"
      />
      <div v-else class="empty-fallback panel">
        <p>页面不存在，请从侧栏重新选择。</p>
        <button class="btn-primary" @click="navigate('agent')">返回 Agent</button>
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
