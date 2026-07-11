<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { api } from '../api/client'

const STORAGE_KEY = 'cpmm_collection_state'

const props = defineProps({
  health: { type: Object, required: true },
  installing: { type: Boolean, default: false },
})

const emit = defineEmits(['install-started', 'install-finished', 'refresh-mods'])

const collectionUrl = ref('')
const parsing = ref(false)
const parseError = ref('')
const collection = ref(null)
const queue = shallowRef([])
const stats = ref(null)
const jobId = ref('')
const job = ref(null)
const polling = ref(false)
const revisionChanged = ref(false)
const revisionChecking = ref(false)
const parseStage = ref('')
const queuePageSize = 50
const queueVisibleCount = ref(queuePageSize)
let persistTimer = null
let pollTimer = null
let parseAbort = null
let parseWatchdog = null

const selectedCount = computed(() =>
  queue.value.filter((item) => item.selected && !item.installed).length,
)
const allSelected = computed({
  get() {
    const selectable = queue.value.filter((item) => !item.installed)
    return selectable.length > 0 && selectable.every((item) => item.selected)
  },
  set(value) {
    queue.value.forEach((item) => {
      if (!item.installed) item.selected = value
    })
    onQueueSelectionChange()
  },
})
const isRunning = computed(() => job.value?.state === 'running')
const progress = computed(() => job.value?.progress || null)
const displayedQueue = computed(() => queue.value.slice(0, queueVisibleCount.value))
const hasMoreQueue = computed(() => queueVisibleCount.value < queue.value.length)

function statusLabel(item) {
  if (item.installed && item.status === 'pending') return '已安装·将跳过'
  const map = {
    pending: '待安装',
    running: '安装中',
    success: '完成',
    skipped: '已跳过',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[item.status] || item.status
}

function statusClass(item) {
  if (item.installed && item.status === 'pending') return 'installed'
  return item.status
}

async function applyQueueInChunks(items) {
  const mapped = items.map((item) => ({ ...item }))
  queue.value = []
  queueVisibleCount.value = Math.min(queuePageSize, mapped.length || queuePageSize)
  const chunkSize = 30
  for (let i = 0; i < mapped.length; i += chunkSize) {
    queue.value = queue.value.concat(mapped.slice(i, i + chunkSize))
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
}

async function parseCollection() {
  const url = collectionUrl.value.trim()
  if (!url) return
  if (parseAbort) parseAbort.abort()
  if (parseWatchdog) clearTimeout(parseWatchdog)
  parseAbort = new AbortController()
  parsing.value = true
  parseStage.value = '正在请求 Nexus 收藏夹数据…'
  parseError.value = ''

  parseWatchdog = setTimeout(() => {
    if (!parsing.value) return
    if (parseAbort) parseAbort.abort()
    parsing.value = false
    parseStage.value = ''
    parseError.value =
      '解析超时：未收到后端响应。请确认终端里 python -m cyberpunk_mod_manager 正在运行，并访问 /api/health 检查。'
  }, 50000)

  try {
    stopPolling()
    emit('install-finished')
    jobId.value = ''
    job.value = null
    queue.value = []
    collection.value = null
    stats.value = null
    const data = await api.parseCollection(url, { signal: parseAbort.signal })
    if (parseWatchdog) clearTimeout(parseWatchdog)
    parseWatchdog = null
    collection.value = data.collection
    stats.value = data.stats
    revisionChanged.value = false
    applyRevisionFromParse()
    parsing.value = false
    parseStage.value = '正在渲染安装队列…'
    await nextTick()
    await applyQueueInChunks(data.queue || [])
    schedulePersistState()
  } catch (e) {
    if (parseWatchdog) clearTimeout(parseWatchdog)
    parseWatchdog = null
    if (e?.message === '请求已取消' && !parseError.value) {
      parseError.value = '已取消解析'
    } else if (e?.message && e.message !== '请求已取消') {
      parseError.value = e.message
    }
    collection.value = null
    queue.value = []
    stats.value = null
    schedulePersistState()
  } finally {
    if (parseWatchdog) clearTimeout(parseWatchdog)
    parseWatchdog = null
    parsing.value = false
    parseStage.value = ''
    parseAbort = null
  }
}

function cancelParse() {
  if (parseAbort) parseAbort.abort()
  if (parseWatchdog) clearTimeout(parseWatchdog)
  parseWatchdog = null
  parsing.value = false
  parseStage.value = ''
  parseError.value = '已取消解析'
}

function applyRevisionFromParse() {
  if (!collection.value?.slug) return
  const key = `${STORAGE_KEY}_revision_${collection.value.slug}`
  const stored = sessionStorage.getItem(key)
  const known = stored ? Number(stored) : null
  const current = Number(collection.value.revision_number || 0)
  revisionChanged.value = known !== null && !Number.isNaN(known) && known !== current
  sessionStorage.setItem(key, String(current))
}

function showMoreQueue() {
  queueVisibleCount.value = Math.min(
    queueVisibleCount.value + queuePageSize,
    queue.value.length,
  )
}

function schedulePersistState() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    persistTimer = null
    persistState()
  }, 250)
}

function persistState() {
  try {
    const compactQueue = queue.value.map((item) => ({
      mod_id: item.mod_id,
      name: item.name,
      order: item.order,
      optional: item.optional,
      selected: item.selected,
      installed: item.installed,
      status: item.status,
      message: item.message,
      collection_file_id: item.collection_file_id,
      collection_version_id: item.collection_version_id,
      collection_file_version: item.collection_file_version,
    }))
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        collectionUrl: collectionUrl.value,
        collection: collection.value,
        queue: compactQueue.length > 120 ? [] : compactQueue,
        stats: stats.value,
        jobId: jobId.value,
        job: job.value,
      }),
    )
  } catch {
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }
}

async function restoreState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (data.collectionUrl) collectionUrl.value = data.collectionUrl
    if (data.collection) collection.value = data.collection
    if (data.stats) stats.value = data.stats
    if (Array.isArray(data.queue) && data.queue.length) {
      if (data.queue.length > 120) {
        parseError.value = '队列过大未缓存，请重新点击「解析并生成队列」'
      } else {
        queue.value = data.queue
        queueVisibleCount.value = Math.min(queuePageSize, data.queue.length)
      }
    }
    if (data.jobId) {
      jobId.value = data.jobId
      job.value = data.job || null
      try {
        const latest = await api.getCollectionJob(data.jobId, { timeoutMs: 8000 })
        job.value = latest
        syncQueueFromJob(latest.items || [])
        if (latest.state === 'running') {
          emit('install-started')
          startPolling()
        } else if (latest.state === 'done' || latest.state === 'cancelled') {
          emit('install-finished')
        }
      } catch {
        parseError.value = '安装任务已过期（服务可能已重启），可重新解析收藏夹'
        jobId.value = ''
        job.value = null
      }
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY)
  }
}

function selectedModIds() {
  return queue.value
    .filter((item) => item.selected)
    .map((item) => item.mod_id)
}

function resetQueueForInstall(modIds) {
  const idSet = new Set(modIds)
  queue.value = queue.value.map((item) => {
    if (!idSet.has(item.mod_id)) return item
    if (item.installed) {
      return { ...item, status: 'pending', message: '已安装，将跳过' }
    }
    return { ...item, status: 'pending', message: '' }
  })
}

async function checkRevisionChange() {
  if (!collection.value?.slug) return
  revisionChecking.value = true
  try {
    const stored = sessionStorage.getItem(`${STORAGE_KEY}_revision_${collection.value.slug}`)
    const known = stored ? Number(stored) : null
    const data = await api.checkCollectionRevision(
      collection.value.slug,
      Number.isNaN(known) ? null : known,
      collection.value.domain,
    )
    revisionChanged.value = Boolean(data.changed)
    sessionStorage.setItem(
      `${STORAGE_KEY}_revision_${collection.value.slug}`,
      String(data.revision_number),
    )
  } catch {
    applyRevisionFromParse()
  } finally {
    revisionChecking.value = false
  }
}

async function startInstall() {
  if (!collection.value) return
  const modIds = selectedModIds()
  if (!modIds.length) {
    parseError.value = '请至少选择一个模组'
    return
  }
  parseError.value = ''
  stopPolling()
  emit('install-finished')
  resetQueueForInstall(modIds)
  jobId.value = ''
  job.value = null
  persistState()
  emit('install-started')
  try {
    const data = await api.installCollection({
      slug: collection.value.slug,
      domain: collection.value.domain,
      title: collection.value.title,
      mod_ids: modIds,
      install_dependencies: true,
      skip_installed: true,
    })
    jobId.value = data.job_id
    job.value = data
    persistState()
    startPolling()
  } catch (e) {
    parseError.value = e.message
    emit('install-finished')
  }
}

async function pollJob() {
  if (!jobId.value) return
  try {
    job.value = await api.getCollectionJob(jobId.value)
    syncQueueFromJob(job.value.items || [])
    if (job.value.state === 'done' || job.value.state === 'cancelled') {
      stopPolling()
      emit('install-finished')
      emit('refresh-mods')
    }
    persistState()
  } catch (e) {
    parseError.value = e.message
    stopPolling()
    emit('install-finished')
  }
}

function syncQueueFromJob(jobItems) {
  const byId = Object.fromEntries(jobItems.map((item) => [item.mod_id, item]))
  queue.value = queue.value.map((item) => {
    const latest = byId[item.mod_id]
    if (!latest) return item
    return { ...item, ...latest }
  })
}

function onQueueSelectionChange() {
  queue.value = [...queue.value]
  schedulePersistState()
}

function startPolling() {
  stopPolling()
  polling.value = true
  pollJob()
  pollTimer = setInterval(pollJob, 1500)
}

function stopPolling() {
  polling.value = false
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function cancelInstall() {
  if (!jobId.value) return
  try {
    job.value = await api.cancelCollectionJob(jobId.value)
  } catch (e) {
    parseError.value = e.message
  }
}

onMounted(() => {
  restoreState()
})

watch([collectionUrl, collection, stats, jobId, job], schedulePersistState)

onUnmounted(() => {
  stopPolling()
  if (persistTimer) clearTimeout(persistTimer)
})
</script>

<template>
  <div class="collection-view">
    <header class="view-header">
      <div>
        <h2>收藏夹安装</h2>
        <p>粘贴 Nexus Collection 链接，生成安装队列并批量安装（使用各模组最新版本）</p>
      </div>
    </header>

    <section class="panel url-section">
      <div class="input-wrap">
        <label>收藏夹 URL</label>
        <input
          v-model="collectionUrl"
          type="text"
          placeholder="https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
          :disabled="isRunning"
        />
      </div>
      <div class="btn-row">
        <button
          class="btn-primary"
          :disabled="parsing || isRunning || !collectionUrl.trim() || !health.data_dir_configured"
          @click="parseCollection"
        >
          {{ parsing ? '解析中...' : '解析并生成队列' }}
        </button>
        <button
          v-if="parsing"
          class="btn-ghost"
          @click="cancelParse"
        >
          取消
        </button>
      </div>
      <p v-if="!health.data_dir_configured" class="hint warn">请先在「设置」页配置数据目录</p>
      <p v-if="!health.nexus_configured" class="hint warn">请先在「设置」页配置 Nexus API Key</p>
      <p v-if="!health.nexus_valid && health.nexus_configured" class="hint warn">Nexus API Key 无效，无法解析收藏夹</p>
      <p v-if="parseError" class="hint err">{{ parseError }}</p>
      <p v-else-if="parsing && parseStage" class="hint">{{ parseStage }}</p>
      <p v-else-if="parsing" class="hint">解析中，最长等待约 45 秒…</p>
    </section>

    <section v-if="collection" class="summary panel">
      <div class="summary-top">
        <div>
          <h3>{{ collection.title }}</h3>
          <p class="mono meta">
            {{ collection.slug }} · 修订 #{{ collection.revision_number }} ·
            {{ collection.unique_mod_count }} 个模组（去重后）
          </p>
          <p v-if="revisionChanged" class="hint warn">
            收藏夹修订已更新，建议重新解析队列后再安装。
          </p>
        </div>
        <a class="link" :href="collection.url" target="_blank" rel="noopener">在 Nexus 打开</a>
      </div>
      <div v-if="stats" class="stats-row">
        <span>共 {{ stats.total }}</span>
        <span class="ok">已装 {{ stats.installed }}</span>
        <span class="warn">待装 {{ stats.pending }}</span>
        <span class="muted">可选 {{ stats.optional }}</span>
        <span>已选 {{ selectedCount }}</span>
      </div>
      <div class="btn-row">
        <label class="select-all">
          <input v-model="allSelected" type="checkbox" :disabled="isRunning" />
          全选未安装项
        </label>
        <button
          class="btn-primary"
          :disabled="isRunning || installing || selectedCount === 0"
          @click="startInstall"
        >
          {{ isRunning ? '安装进行中...' : `开始安装 (${selectedCount})` }}
        </button>
        <button v-if="isRunning" class="btn-ghost" @click="cancelInstall">停止后续安装</button>
      </div>
      <div v-if="progress" class="progress-bar-wrap">
        <div
          class="progress-bar"
          :style="{ width: progress.total ? `${(progress.done / progress.total) * 100}%` : '0%' }"
        />
        <span class="progress-text">
          {{ progress.done }}/{{ progress.total }}
          · 成功 {{ progress.success }}
          · 跳过 {{ progress.skipped }}
          · 失败 {{ progress.failed }}
        </span>
      </div>
    </section>

    <section v-if="queue.length" class="queue-section">
      <div class="queue-list">
        <div
          v-for="item in displayedQueue"
          :key="item.mod_id"
          class="queue-item panel"
          :class="statusClass(item)"
        >
          <label class="queue-check">
            <input
              :checked="item.selected"
              type="checkbox"
              :disabled="isRunning || item.installed"
              @change="(e) => { item.selected = e.target.checked; onQueueSelectionChange() }"
            />
          </label>
          <div class="queue-main">
            <div class="queue-title">
              <span class="order mono">#{{ item.order }}</span>
              <span class="mod-id mono">#{{ item.mod_id }}</span>
              <span class="name">{{ item.name || '—' }}</span>
              <span v-if="item.optional" class="tag optional">可选</span>
            </div>
            <p v-if="item.message" class="queue-msg">{{ item.message }}</p>
          </div>
          <span class="status-pill" :class="statusClass(item)">{{ statusLabel(item) }}</span>
        </div>
      </div>
      <div v-if="hasMoreQueue" class="btn-row queue-more">
        <button class="btn-secondary" @click="showMoreQueue">
          显示更多（{{ displayedQueue.length }}/{{ queue.length }}）
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.collection-view {
  padding: 20px 24px 32px;
  max-width: 960px;
}
.view-header { margin-bottom: 20px; }
.view-header h2 { font-size: 18px; font-weight: 700; }
.view-header p { font-size: 13px; color: var(--muted); margin-top: 4px; }
.url-section, .summary { margin-bottom: 16px; padding: 16px; }
.input-wrap label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}
.btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}
.hint { font-size: 12px; margin-top: 10px; }
.hint.warn { color: var(--warn); }
.hint.err { color: var(--danger); }
.summary-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.summary h3 { font-size: 16px; margin-bottom: 4px; }
.meta { font-size: 11px; color: var(--muted); }
.link { font-size: 12px; color: var(--accent2); white-space: nowrap; }
.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin: 12px 0;
  font-size: 12px;
  color: var(--muted);
}
.stats-row .ok { color: var(--ok); }
.stats-row .warn { color: var(--warn); }
.select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  margin-right: auto;
}
.progress-bar-wrap {
  margin-top: 12px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  height: 8px;
  position: relative;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent2), var(--ok));
  transition: width 0.3s ease;
}
.progress-text {
  display: block;
  margin-top: 8px;
  font-size: 11px;
  color: var(--muted);
}
.queue-list { display: flex; flex-direction: column; gap: 8px; }
.queue-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
}
.queue-check { flex: 0 0 auto; }
.queue-main { flex: 1; min-width: 0; }
.queue-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.order { color: var(--muted); font-size: 11px; }
.mod-id { color: var(--accent2); font-size: 12px; }
.name { font-size: 14px; font-weight: 600; }
.tag.optional {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 176, 32, 0.12);
  color: var(--warn);
}
.queue-msg { font-size: 11px; color: var(--muted); margin-top: 4px; }
.status-pill {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 12px;
  white-space: nowrap;
  border: 1px solid var(--border);
  color: var(--muted);
}
.status-pill.running { color: var(--accent2); border-color: rgba(0, 212, 255, 0.3); }
.status-pill.success { color: var(--ok); border-color: rgba(46, 230, 166, 0.3); }
.status-pill.skipped, .status-pill.installed { color: var(--warn); border-color: rgba(255, 176, 32, 0.3); }
.status-pill.failed { color: var(--danger); border-color: rgba(255, 77, 109, 0.3); }
.queue-item.failed { border-color: rgba(255, 77, 109, 0.25); }
.queue-item.running { border-color: rgba(0, 212, 255, 0.25); }
</style>
