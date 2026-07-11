<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api/client'

const emit = defineEmits(['saved'])

const form = ref({
  data_dir: '',
  game_path: '',
  nexus_api_key: '',
  openai_api_key: '',
  model_name: 'gpt-4o-mini',
  openai_base_url: 'https://api.openai.com/v1',
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
      nexus_api_key: data.nexus_api_key || '',
      openai_api_key: data.openai_api_key || '',
      model_name: data.model_name || 'gpt-4o-mini',
      openai_base_url: data.openai_base_url || 'https://api.openai.com/v1',
    }
    configFile.value = data.config_file || ''
  } catch (e) {
    if (e?.name === 'AbortError') return
    loadFailed.value = true
    message.value = { text: '加载配置失败: ' + e.message, type: 'err' }
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.data_dir.trim()) {
    message.value = { text: '数据存放目录为必填项', type: 'err' }
    return
  }
  saving.value = true
  message.value = { text: '', type: '' }
  try {
    const data = await api.saveConfig({ ...form.value })
    configFile.value = data.config_file || ''
    message.value = {
      text: '配置已保存。若修改了数据目录，建议重启服务。',
      type: 'ok',
    }
    emit('saved', data)
  } catch (e) {
    message.value = { text: '保存失败: ' + e.message, type: 'err' }
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
        <h2>设置</h2>
        <p>在此配置所有运行参数，保存后写入 config.yaml</p>
      </div>
    </header>

    <div v-if="loading" class="empty-state"><span class="spinner" /> 加载中...</div>

    <div v-else-if="loadFailed" class="empty-state error-panel">
      <p>{{ message.text }}</p>
      <button class="btn-primary" type="button" @click="load">重新加载</button>
    </div>

    <form v-else class="settings-form panel" @submit.prevent="save">
      <section class="form-section">
        <h3>路径</h3>
        <div class="input-wrap required">
          <label>数据存放目录 <span class="req">*</span></label>
          <input
            v-model="form.data_dir"
            type="text"
            placeholder="D:\CyberpunkModManager\data"
            required
          />
          <p class="hint">
            存放数据库、下载缓存、备份（必填，无默认值）。修改后建议重启服务。
          </p>
        </div>
        <div class="input-wrap">
          <label>游戏安装目录</label>
          <input
            v-model="form.game_path"
            type="text"
            placeholder="D:\Steam\steamapps\common\Cyberpunk 2077"
          />
        </div>
      </section>

      <section class="form-section">
        <h3>Nexus Mods</h3>
        <div class="input-wrap">
          <label>API Key</label>
          <input v-model="form.nexus_api_key" type="password" placeholder="Nexus API Key" />
        </div>
      </section>

      <section class="form-section">
        <h3>LLM（Agent）</h3>
        <div class="input-wrap">
          <label>API Key</label>
          <input v-model="form.openai_api_key" type="password" placeholder="OpenAI 兼容 API Key" />
        </div>
        <div class="input-wrap">
          <label>模型名称</label>
          <input v-model="form.model_name" type="text" placeholder="gpt-4o-mini" />
        </div>
        <div class="input-wrap">
          <label>API Base URL</label>
          <input v-model="form.openai_base_url" type="text" placeholder="https://api.openai.com/v1" />
        </div>
      </section>

      <p v-if="configFile" class="config-path mono">配置文件: {{ configFile }}</p>

      <div class="btn-row">
        <button class="btn-primary" type="submit" :disabled="saving">
          {{ saving ? '保存中...' : '保存配置' }}
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
</style>
