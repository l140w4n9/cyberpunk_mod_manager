<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import { i18nState, setLocale, useI18n } from '../i18n'

const emit = defineEmits(['saved'])

const { t } = useI18n()

const form = ref({
  data_dir: '',
  game_path: '',
  game_domain: 'cyberpunk2077',
  openai_api_key: '',
  model_name: 'gpt-4o-mini',
  openai_base_url: 'https://api.openai.com/v1',
  allow_adult_content: false,
  install_plan_mode: 'llm_first',
  ui_locale: 'zh',
})
const nexusStatus = ref({ connected: false, username: '', auth_method: '' })
const openaiConfigured = ref(false)
const configFile = ref('')
const loading = ref(true)
const loadFailed = ref(false)
const saving = ref(false)
const nexusConnecting = ref(false)
const nexusDisconnecting = ref(false)
const message = ref({ text: '', type: '' })

function onOAuthMessage(event) {
  if (event.origin !== window.location.origin) return
  const payload = event.data || {}
  if (payload.type === 'nexus-oauth-complete') {
    nexusConnecting.value = false
    nexusStatus.value = {
      connected: true,
      username: payload.username || '',
      auth_method: 'oauth',
    }
    message.value = { text: t('settings.nexusConnected', { user: payload.username || '' }), type: 'ok' }
    emit('saved', { nexus_connected: true })
  } else if (payload.type === 'nexus-oauth-error') {
    nexusConnecting.value = false
    message.value = { text: t('settings.nexusConnectFailed', { error: payload.error || '' }), type: 'err' }
  }
}

async function refreshNexusStatus() {
  try {
    const status = await api.nexusAuthStatus()
    nexusStatus.value = {
      connected: Boolean(status.connected),
      username: status.username || '',
      auth_method: status.auth_method || '',
    }
  } catch {
    /* ignore */
  }
}

async function load() {
  loading.value = true
  loadFailed.value = false
  message.value = { text: '', type: '' }
  try {
    const data = await api.getConfig(3)
    form.value = {
      data_dir: data.data_dir || '',
      game_path: data.game_path || '',
      game_domain: data.game_domain || 'cyberpunk2077',
      openai_api_key: '',
      model_name: data.model_name || 'gpt-4o-mini',
      openai_base_url: data.openai_base_url || 'https://api.openai.com/v1',
      allow_adult_content: Boolean(data.allow_adult_content),
      install_plan_mode: data.install_plan_mode || 'llm_first',
      ui_locale: data.ui_locale || i18nState.locale || 'zh',
    }
    nexusStatus.value = data.nexus || { connected: false, username: '', auth_method: '' }
    openaiConfigured.value = Boolean(data.openai_configured)
    if (data.ui_locale && data.ui_locale !== i18nState.locale) {
      setLocale(data.ui_locale)
    }
    configFile.value = data.config_file || ''
    await refreshNexusStatus()
  } catch (e) {
    if (e?.name === 'AbortError') return
    loadFailed.value = true
    message.value = { text: t('settings.loadFailed', { error: e.message }), type: 'err' }
  } finally {
    loading.value = false
  }
}

async function connectNexus() {
  nexusConnecting.value = true
  message.value = { text: '', type: '' }
  try {
    const { authorize_url: authorizeUrl } = await api.startNexusAuth()
    const popup = window.open(authorizeUrl, 'nexus-oauth', 'width=520,height=720')
    if (!popup) {
      throw new Error(t('settings.nexusPopupBlocked'))
    }
  } catch (e) {
    nexusConnecting.value = false
    message.value = { text: t('settings.nexusConnectFailed', { error: e.message }), type: 'err' }
  }
}

async function disconnectNexus() {
  nexusDisconnecting.value = true
  try {
    await api.disconnectNexus()
    nexusStatus.value = { connected: false, username: '', auth_method: '' }
    message.value = { text: t('settings.nexusDisconnected'), type: 'ok' }
    emit('saved', { nexus_connected: false })
  } catch (e) {
    message.value = { text: t('settings.nexusDisconnectFailed', { error: e.message }), type: 'err' }
  } finally {
    nexusDisconnecting.value = false
  }
}

async function save() {
  if (!form.value.data_dir.trim()) {
    message.value = { text: t('settings.dataDirRequired'), type: 'err' }
    return
  }
  saving.value = true
  message.value = { text: '', type: '' }
  try {
    const data = await api.saveConfig({ ...form.value, ui_locale: i18nState.locale })
    configFile.value = data.config_file || ''
    nexusStatus.value = data.nexus || nexusStatus.value
    openaiConfigured.value = Boolean(data.openai_configured)
    form.value.openai_api_key = ''
    message.value = { text: t('settings.saved'), type: 'ok' }
    emit('saved', data)
  } catch (e) {
    message.value = { text: t('settings.saveFailed', { error: e.message }), type: 'err' }
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  window.addEventListener('message', onOAuthMessage)
  load()
})

onUnmounted(() => {
  window.removeEventListener('message', onOAuthMessage)
})
</script>

<template>
  <div class="settings-view">
    <header class="view-header">
      <div>
        <h2>{{ t('settings.title') }}</h2>
        <p>{{ t('settings.subtitle') }}</p>
      </div>
    </header>

    <div v-if="loading" class="empty-state"><span class="spinner" /> {{ t('settings.loading') }}</div>

    <div v-else-if="loadFailed" class="empty-state error-panel">
      <p>{{ message.text }}</p>
      <button class="btn-primary" type="button" @click="load">{{ t('settings.reload') }}</button>
    </div>

    <form v-else class="settings-form panel" @submit.prevent="save">
      <section class="form-section">
        <h3>{{ t('settings.paths') }}</h3>
        <div class="input-wrap required">
          <label>{{ t('settings.dataDir') }} <span class="req">*</span></label>
          <input
            v-model="form.data_dir"
            type="text"
            placeholder="D:\CyberpunkModManager\data"
            required
          />
          <p class="hint">{{ t('settings.dataDirHint') }}</p>
        </div>
        <div class="input-wrap">
          <label>{{ t('settings.gamePath') }}</label>
          <input
            v-model="form.game_path"
            type="text"
            placeholder="D:\Steam\steamapps\common\Cyberpunk 2077"
          />
        </div>
        <div class="input-wrap">
          <label>{{ t('settings.gameDomain') }}</label>
          <input
            v-model="form.game_domain"
            type="text"
            placeholder="cyberpunk2077"
          />
          <p class="hint">{{ t('settings.gameDomainHint') }}</p>
        </div>
      </section>

      <section class="form-section">
        <h3>{{ t('settings.nexus') }}</h3>
        <div class="nexus-auth-row">
          <div class="nexus-status">
            <span v-if="nexusStatus.connected" class="status-ok">
              {{ t('settings.nexusConnectedAs', { user: nexusStatus.username || 'Nexus' }) }}
            </span>
            <span v-else class="status-muted">{{ t('settings.nexusNotConnected') }}</span>
          </div>
          <div class="btn-row">
            <button
              v-if="!nexusStatus.connected"
              class="btn-primary"
              type="button"
              :disabled="nexusConnecting"
              @click="connectNexus"
            >
              {{ nexusConnecting ? t('settings.nexusConnecting') : t('settings.nexusConnect') }}
            </button>
            <button
              v-else
              class="btn-secondary"
              type="button"
              :disabled="nexusDisconnecting"
              @click="disconnectNexus"
            >
              {{ nexusDisconnecting ? t('settings.nexusDisconnecting') : t('settings.nexusDisconnect') }}
            </button>
          </div>
        </div>
        <label class="checkbox-row">
          <input v-model="form.allow_adult_content" type="checkbox" />
          {{ t('settings.allowAdult') }}
        </label>
      </section>

      <section class="form-section">
        <h3>{{ t('settings.llm') }}</h3>
        <div class="input-wrap">
          <label>{{ t('settings.apiKey') }}</label>
          <input
            v-model="form.openai_api_key"
            type="password"
            :placeholder="openaiConfigured ? t('settings.apiKeyConfigured') : 'OpenAI compatible API Key'"
          />
        </div>
        <div class="input-wrap">
          <label>{{ t('settings.modelName') }}</label>
          <input v-model="form.model_name" type="text" placeholder="gpt-4o-mini" />
        </div>
        <div class="input-wrap">
          <label>{{ t('settings.apiBase') }}</label>
          <input v-model="form.openai_base_url" type="text" placeholder="https://api.openai.com/v1" />
        </div>
        <div class="input-wrap">
          <label>{{ t('settings.installPlanMode') }}</label>
          <select v-model="form.install_plan_mode">
            <option value="llm_first">{{ t('settings.planLlmFirst') }}</option>
            <option value="hybrid">{{ t('settings.planHybrid') }}</option>
            <option value="rules_only">{{ t('settings.planRulesOnly') }}</option>
          </select>
          <p class="hint">{{ t('settings.planHint') }}</p>
        </div>
      </section>

      <p v-if="configFile" class="config-path mono">{{ t('settings.configFile', { path: configFile }) }}</p>

      <div class="btn-row">
        <button class="btn-primary" type="submit" :disabled="saving">
          {{ saving ? t('settings.saving') : t('settings.save') }}
        </button>
      </div>

      <div v-if="message.text" class="form-msg" :class="message.type">{{ message.text }}</div>
    </form>
  </div>
</template>

<style scoped>
.settings-view {
  padding: 20px 24px 32px;
  max-width: 720px;
}
.view-header { margin-bottom: 20px; }
.view-header h2 { font-size: 18px; font-weight: 700; }
.view-header p { font-size: 13px; color: var(--muted); margin-top: 4px; }
.settings-form { padding: 20px; }
.form-section { margin-bottom: 24px; }
.form-section h3 {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent2);
  margin-bottom: 14px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.input-wrap { margin-bottom: 14px; }
.input-wrap label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}
.req { color: var(--danger); }
.hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 6px;
  line-height: 1.5;
}
.nexus-auth-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0;
}
.nexus-status { font-size: 13px; }
.status-ok { color: var(--ok); }
.status-muted { color: var(--muted); }
.config-path {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 14px;
  word-break: break-all;
}
.btn-row { display: flex; gap: 8px; }
.form-msg {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.form-msg.ok {
  background: rgba(46, 230, 166, 0.1);
  border: 1px solid rgba(46, 230, 166, 0.3);
  color: var(--ok);
}
.form-msg.err {
  background: rgba(255, 77, 109, 0.1);
  border: 1px solid rgba(255, 77, 109, 0.3);
  color: var(--danger);
}
.empty-state {
  text-align: center;
  padding: 60px;
  color: var(--muted);
}
.error-panel p {
  color: var(--danger);
  margin-bottom: 16px;
  line-height: 1.6;
}
.checkbox-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
  margin-top: 10px;
  line-height: 1.5;
}
</style>
