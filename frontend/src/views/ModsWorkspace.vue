<script setup>
import { computed, ref } from 'vue'
import ModCard from '../components/mods/ModCard.vue'
import DepChipList from '../components/mods/DepChipList.vue'
import { filterMods } from '../utils/mods'

const props = defineProps({
  mods: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  installing: { type: Boolean, default: false },
  status: { type: Object, default: () => ({ message: '', type: '' }) },
  /** installed | pending | incomplete */
  filterMode: { type: String, default: 'installed' },
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

const PAGE_META = {
  installed: {
    title: '已安装模组',
    desc: '依赖已满足、可正常使用的模组',
    empty: '暂无已安装且依赖完整的模组',
  },
  pending: {
    title: '待安装模组',
    desc: '已入库但尚未安装到游戏的模组',
    empty: '暂无待安装模组',
  },
  incomplete: {
    title: '依赖不全',
    desc: '已安装但缺少必需依赖，可能无法正常使用',
    empty: '暂无依赖不全的模组',
  },
}

const pageMeta = computed(() => PAGE_META[props.filterMode] || PAGE_META.installed)
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
</script>

<template>
  <div class="mods-view">
    <header class="view-header">
      <div>
        <h2>{{ pageMeta.title }}</h2>
        <p>{{ pageMeta.desc }}</p>
      </div>
      <span class="count-badge">{{ filteredMods.length }} 项</span>
    </header>

    <section v-if="filterMode === 'installed'" class="install-section panel">
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
          {{ depsReport.all_satisfied ? '依赖已满足' : `缺失 ${depsReport.missing_count} 项必需依赖` }}
        </span>
        <DepChipList :dependencies="depsReport.dependencies" />
      </div>
    </section>

    <div v-if="loading" class="empty-state"><span class="spinner" /> 加载中...</div>
    <div v-else-if="!filteredMods.length" class="empty-state">{{ pageMeta.empty }}</div>

    <div v-else class="mod-grid">
      <ModCard
        v-for="mod in filteredMods"
        :key="mod.id"
        :mod="mod"
        :show-warning="filterMode === 'incomplete'"
        @uninstall="$emit('uninstall', $event)"
        @install-with-deps="$emit('install-with-deps', $event)"
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
