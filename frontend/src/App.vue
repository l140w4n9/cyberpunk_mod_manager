<script setup>
import { ref, onMounted } from 'vue'
import { api } from './api/client'
import AppHeader from './components/AppHeader.vue'
import StatsBar from './components/StatsBar.vue'
import ModPanel from './components/ModPanel.vue'
import AgentPanel from './components/AgentPanel.vue'
import UninstallPlanPanel from './components/UninstallPlanPanel.vue'

const mods = ref([])
const loading = ref(false)
const installing = ref(false)
const health = ref({ ready: false, label: '检查中...' })
const status = ref({ message: '', type: '' })

function setStatus(message, type = '') {
  status.value = { message, type }
}

async function checkHealth() {
  try {
    const data = await api.health()
    const ready = data.nexus_valid && data.llm_configured
    let label = '系统就绪'
    if (!data.llm_configured) label = 'LLM 未配置'
    else if (!data.nexus_configured) label = 'Nexus Key 未配置'
    else if (!data.nexus_valid) label = 'Nexus Key 无效'
    health.value = { ready, label }
  } catch {
    health.value = { ready: false, label: '连接失败' }
  }
}

async function loadMods() {
  loading.value = true
  try {
    mods.value = await api.listMods()
  } catch (e) {
    setStatus('加载模组失败: ' + e.message, 'err')
  } finally {
    loading.value = false
  }
}

async function handleInstall(modId) {
  installing.value = true
  setStatus(`正在安装模组 ${modId}...`, 'info')
  try {
    const data = await api.installMod(modId)
    const name = data.name || `模组 ${modId}`
    setStatus(`✓ ${name} 安装完成，新增 ${data.added_files_count} 个文件`, 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleInstallWithDeps(modId) {
  installing.value = true
  setStatus(`正在安装模组 ${modId} 及前置依赖...`, 'info')
  try {
    const data = await api.installModWithDeps(modId)
    const depsOk = (data.dependencies_installed || []).length
    const depsFail = (data.dependencies_failed || []).length
    const name = data.name || `模组 ${modId}`
    let msg = `✓ ${name} 安装完成，新增 ${data.added_files_count} 个文件`
    if (depsOk || depsFail) {
      msg += `；依赖成功 ${depsOk}，失败 ${depsFail}`
    }
    setStatus(msg, depsFail ? 'err' : 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleInstallLocal({ modId, archiveName }) {
  installing.value = true
  setStatus(`正在从本地包安装模组 ${modId}...`, 'info')
  try {
    const data = await api.installLocalMod(modId, archiveName)
    setStatus(`✓ 本地安装完成，新增 ${data.added_files_count} 个文件`, 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  } finally {
    installing.value = false
  }
}

async function handleCheckDeps(modId, callback) {
  try {
    const report = await api.modDependencies(modId)
    callback(report)
  } catch (e) {
    setStatus('✕ 依赖检查失败: ' + e.message, 'err')
    callback(null)
  }
}

async function handleUninstall(modId) {
  if (!confirm(`确定卸载模组 ${modId}？`)) return
  setStatus(`正在卸载模组 ${modId}...`, 'info')
  try {
    const data = await api.uninstallMod(modId)
    setStatus(`✓ 已删除 ${data.removed_files_count} 个文件，恢复 ${data.restored_backups} 个备份`, 'ok')
    await loadMods()
  } catch (e) {
    setStatus('✕ ' + e.message, 'err')
  }
}

onMounted(async () => {
  await Promise.all([checkHealth(), loadMods()])
})
</script>

<template>
  <div class="app">
    <div class="bg-grid" />
    <div class="bg-glow bg-glow--yellow" />
    <div class="bg-glow bg-glow--cyan" />

    <AppHeader :health="health" @refresh="loadMods" />
    <StatsBar :mods="mods" />

    <main class="container">
      <ModPanel
        :mods="mods"
        :loading="loading"
        :installing="installing"
        :status="status"
        @install="handleInstall"
        @install-with-deps="handleInstallWithDeps"
        @install-local="handleInstallLocal"
        @check-deps="handleCheckDeps"
        @uninstall="handleUninstall"
      />
      <aside class="sidebar">
        <AgentPanel @done="loadMods" />
        <UninstallPlanPanel />
      </aside>
    </main>
  </div>
</template>

<style scoped>
.app { position: relative; min-height: 100vh; display: flex; flex-direction: column; }

.bg-grid {
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 240, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.03) 1px, transparent 1px);
  background-size: 48px 48px;
  pointer-events: none;
  z-index: 0;
}
.bg-glow {
  position: fixed;
  width: 600px;
  height: 600px;
  border-radius: 50%;
  filter: blur(120px);
  opacity: 0.15;
  pointer-events: none;
  z-index: 0;
}
.bg-glow--yellow { top: -200px; right: -100px; background: var(--accent); }
.bg-glow--cyan { bottom: -200px; left: -100px; background: var(--accent2); }

.container {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 20px;
  padding: 20px 32px 32px;
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
  flex: 1;
}
.sidebar { display: flex; flex-direction: column; gap: 20px; }

@media (max-width: 1100px) {
  .container { grid-template-columns: 1fr; }
  .sidebar { order: -1; }
}
@media (max-width: 600px) {
  .container { padding: 16px; }
}
</style>
