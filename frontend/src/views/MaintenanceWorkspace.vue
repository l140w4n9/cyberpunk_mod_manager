<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import {
  buildMaintenanceHandoffMessage,
  hasMaintenanceHandoffData,
  queueAgentHandoff,
} from '../utils/agentHandoff'

const STORAGE_KEY = 'cpmm_maintenance_state'

const props = defineProps({
  health: { type: Object, required: true },
  installing: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh-mods', 'status', 'agent-handoff'])

const auditing = ref(false)
const checkingUpdates = ref(false)
const autoFix = ref(false)
const report = ref(null)
const updatesResult = ref(null)
const error = ref('')
const jobId = ref('')
const job = ref(null)
const lastUpdated = ref('')
let pollTimer = null

const issueSummary = computed(() => report.value?.issues || null)
const healthy = computed(() => report.value?.healthy === true)
const llmReport = computed(() => report.value?.llm_report || null)
const autoFixResult = computed(() => report.value?.auto_fix || null)
const isRunning = computed(() => job.value?.state === 'running')
const progress = computed(() => job.value?.progress || null)
const progressPercent = computed(() => {
  const p = progress.value
  if (!p) return 0
  if (typeof p.percent === 'number') return Math.min(100, Math.max(0, p.percent))
  if (p.total && p.current) return Math.round((p.current / p.total) * 100)
  const phaseMap = { scan: 15, updates: 45, llm: 80, fix: 92, done: 100, pending: 5 }
  return phaseMap[p.phase] ?? 10
})

const canAgentHandoff = computed(
  () =>
    !isRunning.value &&
    props.health.llm_configured &&
    hasMaintenanceHandoffData({
      report: report.value,
      updatesResult: updatesResult.value,
    }),
)

function handoffToAgent() {
  const message = buildMaintenanceHandoffMessage({
    report: report.value,
    updatesResult: updatesResult.value,
  })
  if (!message) {
    setError('没有可交给 Agent 处理的审查数据')
    return
  }
  queueAgentHandoff({
    title: '健康审查处理',
    message,
    source: 'maintenance',
  })
  emit('agent-handoff')
  emit('status', '已交给 Agent，正在跳转…', 'info')
}

function setError(message) {
  error.value = message
  emit('status', message, 'err')
}

function applyAuditResult(result) {
  report.value = result
  updatesResult.value = {
    update_count: result?.issues?.update_count ?? 0,
    updates: result?.updates || [],
  }
  lastUpdated.value = new Date().toLocaleString()
}

function applyUpdatesResult(result) {
  updatesResult.value = result
  lastUpdated.value = new Date().toLocaleString()
}

function persistState() {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        autoFix: autoFix.value,
        report: report.value,
        updatesResult: updatesResult.value,
        jobId: jobId.value,
        job: job.value,
        lastUpdated: lastUpdated.value,
        error: error.value,
      }),
    )
  } catch {
    /* sessionStorage 可能已满，忽略 */
  }
}

function handleJobFinished(latest) {
  if (latest.kind === 'audit' && latest.result) {
    applyAuditResult(latest.result)
    emit(
      'status',
      latest.result.healthy ? '审查完成：未发现明显问题' : '审查完成，发现需处理项',
      latest.result.healthy ? 'ok' : 'info',
    )
    emit('refresh-mods')
  } else if (latest.kind === 'updates' && latest.result) {
    applyUpdatesResult(latest.result)
    emit('status', `检查完成：${latest.result.update_count || 0} 个模组有更新`, 'info')
  }
}

async function pollJob() {
  if (!jobId.value) return
  try {
    const latest = await api.getAuditJob(jobId.value)
    job.value = latest
    persistState()
    if (latest.state === 'running') return
    stopPolling()
    auditing.value = false
    checkingUpdates.value = false
    if (latest.state === 'done') {
      error.value = ''
      handleJobFinished(latest)
    } else if (latest.state === 'failed') {
      setError(latest.error || latest.progress?.message || '任务失败')
    }
    persistState()
  } catch (e) {
    stopPolling()
    auditing.value = false
    checkingUpdates.value = false
    setError('获取任务进度失败: ' + e.message)
    persistState()
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollJob, 1200)
  pollJob()
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function clearResultState() {
  report.value = null
  updatesResult.value = null
  lastUpdated.value = ''
  error.value = ''
}

async function runAudit() {
  if (!props.health.data_dir_configured) {
    setError('请先配置数据目录')
    return
  }
  stopPolling()
  clearResultState()
  persistState()
  auditing.value = true
  checkingUpdates.value = false
  try {
    const started = await api.startAuditJob(autoFix.value)
    jobId.value = started.job_id
    job.value = started
    persistState()
    startPolling()
  } catch (e) {
    auditing.value = false
    setError('启动审查失败: ' + e.message)
    persistState()
  }
}

async function runCheckUpdates() {
  if (!props.health.data_dir_configured) {
    setError('请先配置数据目录')
    return
  }
  stopPolling()
  clearResultState()
  persistState()
  checkingUpdates.value = true
  auditing.value = false
  try {
    const started = await api.startCheckUpdatesJob()
    jobId.value = started.job_id
    job.value = started
    persistState()
    startPolling()
  } catch (e) {
    checkingUpdates.value = false
    setError('启动更新检查失败: ' + e.message)
    persistState()
  }
}

async function restoreState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (typeof data.autoFix === 'boolean') autoFix.value = data.autoFix
    if (data.report) report.value = data.report
    if (data.updatesResult) updatesResult.value = data.updatesResult
    if (data.lastUpdated) lastUpdated.value = data.lastUpdated
    if (data.error) error.value = data.error
    if (data.job) job.value = data.job
    if (!data.jobId) return

    jobId.value = data.jobId
    try {
      const latest = await api.getAuditJob(data.jobId)
      job.value = latest
      if (latest.state === 'running') {
        if (latest.kind === 'audit') auditing.value = true
        if (latest.kind === 'updates') checkingUpdates.value = true
        startPolling()
      } else if (latest.state === 'done') {
        if (!data.report && latest.kind === 'audit') applyAuditResult(latest.result)
        else if (!data.updatesResult && latest.kind === 'updates') applyUpdatesResult(latest.result)
        else if (latest.kind === 'audit' && latest.result) applyAuditResult(latest.result)
        else if (latest.kind === 'updates' && latest.result) applyUpdatesResult(latest.result)
      } else if (latest.state === 'failed') {
        setError(latest.error || '任务失败')
      }
      persistState()
    } catch {
      /* 服务重启后 job 丢失，保留已缓存的 report */
    }
  } catch {
    /* ignore corrupt storage */
  }
}

function actionLabel(action) {
  const map = {
    install_deps: '补全依赖',
    reinstall: '重新安装',
    install_pending: '安装待装模组',
    manual: '手动处理',
  }
  return map[action] || action
}

watch(autoFix, persistState)

onMounted(() => {
  restoreState()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="maintenance panel">
    <header class="page-header">
      <div>
        <h2>健康审查</h2>
        <p>一键检查依赖不全、待安装、更新与安装记录问题，并由 LLM 给出修复建议。</p>
        <p v-if="lastUpdated" class="last-updated">上次完成：{{ lastUpdated }}</p>
      </div>
    </header>

    <section class="actions panel-inner">
      <label class="auto-fix">
        <input v-model="autoFix" type="checkbox" :disabled="isRunning" />
        审查后自动修复（补全依赖 + 重装有更新的模组）
      </label>
      <div class="btn-row">
        <button
          class="btn-primary"
          :disabled="auditing || checkingUpdates || installing || !health.data_dir_configured"
          @click="runAudit"
        >
          {{ auditing ? '审查中…' : '一键审查' }}
        </button>
        <button
          class="btn-secondary"
          :disabled="auditing || checkingUpdates || installing || !health.data_dir_configured"
          @click="runCheckUpdates"
        >
          {{ checkingUpdates ? '检查中…' : '仅检查更新' }}
        </button>
      </div>

      <div v-if="isRunning && progress" class="progress-section">
        <div class="progress-header">
          <span class="progress-phase">{{ progress.phase_label || '处理中' }}</span>
          <span class="progress-percent">{{ progressPercent }}%</span>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar" :style="{ width: `${progressPercent}%` }" />
        </div>
        <p class="progress-message">{{ progress.message }}</p>
        <p v-if="progress.total" class="progress-count">
          {{ progress.current || 0 }} / {{ progress.total }}
        </p>
      </div>

      <p v-if="error" class="error-text">{{ error }}</p>
      <div v-if="canAgentHandoff" class="handoff-row">
        <button class="btn-primary" :disabled="installing" @click="handoffToAgent">
          交给 Agent 处理
        </button>
        <span class="handoff-hint">将审查结果发给 Agent，自动调用工具修复依赖、安装与更新</span>
      </div>
      <p v-else-if="!isRunning && report && !health.llm_configured" class="hint warn">
        未配置 LLM，无法使用 Agent 自动处理。请先在设置中配置 API Key。
      </p>
    </section>

    <section v-if="issueSummary" class="summary panel-inner" :class="{ ok: healthy }">
      <h3>{{ healthy ? '✓ 安装状态良好' : '发现以下问题' }}</h3>
      <ul class="issue-grid">
        <li><span>待安装</span><strong>{{ issueSummary.pending_count }}</strong></li>
        <li><span>依赖不全</span><strong>{{ issueSummary.incomplete_count }}</strong></li>
        <li><span>有更新</span><strong>{{ issueSummary.update_count }}</strong></li>
        <li><span>无卸载记录</span><strong>{{ issueSummary.no_uninstall_plan_count }}</strong></li>
        <li><span>已下载未装</span><strong>{{ issueSummary.downloaded_not_installed_count }}</strong></li>
        <li><span>已禁用</span><strong>{{ issueSummary.disabled_installed_count }}</strong></li>
      </ul>
    </section>

    <section v-if="llmReport" class="llm panel-inner">
      <h3>AI 审查结论</h3>
      <p class="llm-summary">{{ llmReport.summary }}</p>
      <p v-if="llmReport.error" class="llm-error">LLM 未生效：{{ llmReport.error }}</p>
      <p v-if="llmReport.llm_fallback && !llmReport.error" class="muted">
        大模型未返回有效 JSON，已使用规则引擎建议。
      </p>
      <ul v-if="llmReport.risks?.length" class="risk-list">
        <li v-for="(risk, i) in llmReport.risks" :key="i">{{ risk }}</li>
      </ul>
      <div v-if="llmReport.recommendations?.length" class="rec-list">
        <div v-for="(rec, i) in llmReport.recommendations" :key="i" class="rec-item">
          <span class="rec-action">{{ actionLabel(rec.action) }}</span>
          <span class="rec-mod">#{{ rec.mod_id }}</span>
          <span class="rec-reason">{{ rec.reason }}</span>
        </div>
      </div>
      <p class="muted">来源：{{ llmReport.source === 'ai' ? '大模型' : '规则引擎' }}</p>
    </section>

    <section v-if="updatesResult?.updates?.length" class="updates panel-inner">
      <h3>可用更新（{{ updatesResult.update_count || updatesResult.updates.length }}）</h3>
      <div v-for="item in updatesResult.updates" :key="item.mod_id" class="update-row">
        <strong>{{ item.name }}</strong>
        <span class="muted">#{{ item.mod_id }}</span>
        <span v-if="item.installed_version">{{ item.installed_version }} → {{ item.latest_version }}</span>
        <span v-for="(reason, i) in item.reasons" :key="i" class="reason">{{ reason }}</span>
      </div>
    </section>

    <section v-if="report?.incomplete?.length" class="detail panel-inner">
      <h3>依赖不全模组</h3>
      <div v-for="mod in report.incomplete" :key="mod.nexus_mod_id" class="mod-row">
        <span>{{ mod.name }}</span>
        <span class="muted">缺 {{ mod.dependencies_missing_count }} 个依赖</span>
      </div>
    </section>

    <section v-if="report?.pending?.length" class="detail panel-inner">
      <h3>待安装模组</h3>
      <div v-for="mod in report.pending" :key="mod.nexus_mod_id" class="mod-row">
        <span>{{ mod.name }}</span>
        <span class="muted">{{ mod.status }}</span>
      </div>
    </section>

    <section v-if="autoFixResult" class="fix panel-inner">
      <h3>自动修复结果</h3>
      <p>成功 {{ autoFixResult.fixed?.length || 0 }} 项，失败 {{ autoFixResult.failed?.length || 0 }} 项</p>
      <div v-for="item in autoFixResult.failed || []" :key="item.mod_id + item.action" class="mod-row err">
        #{{ item.mod_id }} {{ item.action }}：{{ item.result?.error || '失败' }}
      </div>
    </section>
  </div>
</template>

<style scoped>
.maintenance {
  margin: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-header h2 {
  margin: 0 0 6px;
  font-family: var(--font-display);
}
.page-header p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.last-updated {
  margin-top: 6px !important;
  font-size: 12px !important;
}
.panel-inner {
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(0, 0, 0, 0.15);
}
.actions .btn-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.auto-fix {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
}
.progress-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}
.progress-phase {
  color: var(--accent2);
  font-weight: 600;
}
.progress-percent {
  color: var(--muted);
  font-family: var(--font-mono, monospace);
}
.progress-bar-wrap {
  background: rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  height: 8px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent2), var(--ok));
  transition: width 0.35s ease;
}
.progress-message {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text);
  line-height: 1.4;
}
.progress-count {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--muted);
}
.handoff-row {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.handoff-hint {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.4;
}
.hint.warn {
  margin-top: 10px;
  font-size: 12px;
  color: var(--warn);
}
.error-text {
  color: var(--danger);
  font-size: 13px;
  margin: 10px 0 0;
}
.summary.ok {
  border-color: rgba(46, 230, 166, 0.3);
}
.summary h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.issue-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}
.issue-grid li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.issue-grid strong {
  font-size: 20px;
  color: var(--text);
}
.llm-summary {
  margin: 0 0 10px;
  line-height: 1.5;
}
.llm-error {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--warn);
  line-height: 1.4;
  word-break: break-word;
}
.risk-list {
  margin: 0 0 12px;
  padding-left: 18px;
  color: var(--warn);
  font-size: 13px;
}
.rec-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rec-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
}
.rec-action {
  color: var(--accent2);
  font-weight: 600;
}
.rec-mod {
  color: var(--muted);
}
.update-row,
.mod-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.update-row:last-child,
.mod-row:last-child {
  border-bottom: none;
}
.reason {
  font-size: 12px;
  color: var(--warn);
}
.mod-row.err {
  color: var(--danger);
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
</style>
