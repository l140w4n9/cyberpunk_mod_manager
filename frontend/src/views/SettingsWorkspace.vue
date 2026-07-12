<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import { i18nState, setLocale, useI18n } from '../i18n'

const emit = defineEmits(['saved'])

const { t } = useI18n()

const form = ref({
  data_dir: '',
  game_path: '',
  game_domain: 'cyberpunk2077',
  nexus_api_key: '',
  openai_api_key: '',
  model_name: 'gpt-4o-mini',
  openai_base_url: 'https://api.openai.com/v1',
  allow_adult_content: false,
  install_plan_mode: 'llm_first',
  ui_locale: 'zh',
})
const configFile = ref('')
const loading = ref(true)
const loadFailed = ref(false)
const saving = ref(false)
const message = ref({ text: '', type: '' })

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
      nexus_api_key: data.nexus_api_key || '',
      openai_api_key: data.openai_api_key || '',
      model_name: data.model_name || 'gpt-4o-mini',
      openai_base_url: data.openai_base_url || 'https://api.openai.com/v1',
      allow_adult_content: Boolean(data.allow_adult_content),
      install_plan_mode: data.install_plan_mode || 'llm_first',
      ui_locale: data.ui_locale || i18nState.locale || 'zh',
    }
    if (data.ui_locale && data.ui_locale !== i18nState.locale) {
      setLocale(data.ui_locale)
    }
    configFile.value = data.config_file || ''
  } catch (e) {
    if (e?.name === 'AbortError') return
    loadFailed.value = true
    message.value = { text: t('settings.loadFailed', { error: e.message }), type: 'err' }
  } finally {
    loading.value = false
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
    message.value = { text: t('settings.saved'), type: 'ok' }
    emit('saved', data)
  } catch (e) {
    message.value = { text: t('settings.saveFailed', { error: e.message }), type: 'err' }
  } finally {
    saving.value = false
  }
}

onMounted(load)
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
        <div class="input-wrap">
          <label>{{ t('settings.apiKey') }}</label>
          <input v-model="form.nexus_api_key" type="password" placeholder="Nexus API Key" />
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
          <input v-model="form.openai_api_key" type="password" placeholder="OpenAI compatible API Key" />
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
