<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { api } from '../api/client'
import { isRequestCancelled, useI18n } from '../i18n'

const STORAGE_KEY = 'cpmm_collection_state'

const { t } = useI18n()

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
  if (item.installed && item.status === 'pending') return t('collections.statusInstalledSkip')
  const map = {
    pending: t('collections.statusPending'),
    running: t('collections.statusRunning'),
    success: t('collections.statusSuccess'),
    skipped: t('collections.statusSkipped'),
    failed: t('collections.statusFailed'),
    cancelled: t('collections.statusCancelled'),
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
  parseStage.value = t('collections.parseStageRequest')
  parseError.value = ''

  parseWatchdog = setTimeout(() => {
    if (!parsing.value) return
    if (parseAbort) parseAbort.abort()
    parsing.value = false
    parseStage.value = ''
    parseError.value = t('collections.parseTimeout')
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
    parseStage.value = t('collections.parseStageRender')
    await nextTick()
    await applyQueueInChunks(data.queue || [])
    schedulePersistState()
  } catch (e) {
    if (parseWatchdog) clearTimeout(parseWatchdog)
    parseWatchdog = null
    if (isRequestCancelled(e) && !parseError.value) {
      parseError.value = t('collections.parseCancelled')
    } else if (e?.message && !isRequestCancelled(e)) {
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
  parseError.value = t('collections.parseCancelled')
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
        parseError.value = t('collections.queueTooLarge')
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
        parseError.value = t('collections.jobExpired')
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
    .filter((item) => item.selected && !item.installed)
    .map((item) => item.mod_id)
}

function recomputeStats() {
  if (!stats.value) return
  const total = queue.value.length
  const installed = queue.value.filter((item) => item.installed).length
  const pending = queue.value.filter((item) => item.selected && !item.installed).length
  const optional = queue.value.filter((item) => item.optional).length
  const selected = queue.value.filter((item) => item.selected && !item.installed).length
  stats.value = { ...stats.value, total, installed, pending, optional, selected }
}

function applyInstallStatusRows(rows) {
  if (!Array.isArray(rows) || !rows.length) return
  const byId = Object.fromEntries(rows.map((row) => [row.mod_id, row]))
  queue.value = queue.value.map((item) => {
    const row = byId[item.mod_id]
    if (!row) return item
    const installed = Boolean(row.installed)
    if (!installed) {
      return { ...item, installed: false }
    }
    return {
      ...item,
      installed: true,
      selected: false,
      status: item.status === 'pending' ? 'skipped' : item.status,
      message: item.message || t('maintenance.installedSkipMsg'),
    }
  })
  recomputeStats()
  schedulePersistState()
}

function resetQueueForInstall(modIds) {
  const idSet = new Set(modIds)
  queue.value = queue.value.map((item) => {
    if (!idSet.has(item.mod_id)) return item
    if (item.installed) return item
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
  try {
    const statusData = await api.collectionQueueStatus(queue.value.map((item) => item.mod_id))
    applyInstallStatusRows(statusData.mods || [])
  } catch {
    /* 状态刷新失败时仍尝试安装，后端会跳过已装项 */
  }
  const modIds = selectedModIds()
  if (!modIds.length) {
    parseError.value = t('collections.noPending')
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
    const merged = { ...item, ...latest }
    if (latest.status === 'success' || latest.installed) {
      merged.installed = true
      merged.selected = false
    }
    if (latest.status === 'skipped' && latest.message?.includes('已安装')) {
      merged.installed = true
      merged.selected = false
    }
    return merged
  })
  recomputeStats()
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
        <h2>{{ t('collections.title') }}</h2>
        <p>{{ t('collections.subtitle') }}</p>
      </div>
    </header>

    <section class="panel url-section">
      <div class="input-wrap">
        <label>{{ t('collections.urlLabel') }}</label>
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
          {{ parsing ? t('collections.parsing') : t('collections.parse') }}
        </button>
        <button
          v-if="parsing"
          class="btn-ghost"
          @click="cancelParse"
        >
          {{ t('collections.cancel') }}
        </button>
      </div>
      <p v-if="!health.data_dir_configured" class="hint warn">{{ t('collections.configureDataDir') }}</p>
      <p v-if="!health.nexus_configured" class="hint warn">{{ t('collections.configureNexus') }}</p>
      <p v-if="!health.nexus_valid && health.nexus_configured" class="hint warn">{{ t('collections.invalidNexus') }}</p>
      <p v-if="parseError" class="hint err">{{ parseError }}</p>
      <p v-else-if="parsing && parseStage" class="hint">{{ parseStage }}</p>
      <p v-else-if="parsing" class="hint">{{ t('collections.parsingWait') }}</p>
    </section>

    <section v-if="collection" class="summary panel">
      <div class="summary-top">
        <div>
          <h3>{{ collection.title }}</h3>
          <p class="mono meta">
            {{ collection.slug }} · #{{ collection.revision_number }} ·
            {{ t('collections.modsDeduped', { count: collection.unique_mod_count }) }}
          </p>
          <p v-if="revisionChanged" class="hint warn">
            {{ t('collections.revisionUpdated') }}
          </p>
        </div>
        <a class="link" :href="collection.url" target="_blank" rel="noopener">{{ t('collections.openNexus') }}</a>
      </div>
      <div v-if="stats" class="stats-row">
        <span>{{ t('collections.total', { count: stats.total }) }}</span>
        <span class="ok">{{ t('collections.installed', { count: stats.installed }) }}</span>
        <span class="warn">{{ t('collections.pending', { count: stats.pending }) }}</span>
        <span class="muted">{{ t('collections.optional', { count: stats.optional }) }}</span>
        <span>{{ t('collections.selected', { count: selectedCount }) }}</span>
      </div>
      <div class="btn-row">
        <label class="select-all">
          <input v-model="allSelected" type="checkbox" :disabled="isRunning" />
          {{ t('collections.selectUninstalled') }}
        </label>
        <button
          class="btn-primary"
          :disabled="isRunning || installing || selectedCount === 0"
          @click="startInstall"
        >
          {{ isRunning ? t('collections.installing') : t('collections.startInstall', { count: selectedCount }) }}
        </button>
        <button v-if="isRunning" class="btn-ghost" @click="cancelInstall">{{ t('collections.stopInstall') }}</button>
      </div>
      <div v-if="progress" class="progress-bar-wrap">
        <div
          class="progress-bar"
          :style="{ width: progress.total ? `${(progress.done / progress.total) * 100}%` : '0%' }"
        />
        <span class="progress-text">
          {{ t('collections.progress', {
            done: progress.done,
            total: progress.total,
            success: progress.success,
            skipped: progress.skipped,
            failed: progress.failed,
          }) }}
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
              <span v-if="item.optional" class="tag optional">{{ t('collections.optionalTag') }}</span>
            </div>
            <p v-if="item.message" class="queue-msg">{{ item.message }}</p>
          </div>
          <span class="status-pill" :class="statusClass(item)">{{ statusLabel(item) }}</span>
        </div>
      </div>
      <div v-if="hasMoreQueue" class="btn-row queue-more">
        <button class="btn-secondary" @click="showMoreQueue">
          {{ t('collections.showMore', { shown: displayedQueue.length, total: queue.length }) }}
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
