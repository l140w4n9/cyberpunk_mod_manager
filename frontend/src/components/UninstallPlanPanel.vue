<script setup>
import { ref } from 'vue'
import { api } from '../api/client'

const modId = ref('')
const plan = ref(null)
const loading = ref(false)
const error = ref('')

async function loadPlan() {
  const id = modId.value.trim()
  if (!id) return
  loading.value = true
  error.value = ''
  plan.value = null
  try {
    plan.value = await api.uninstallPlan(parseInt(id, 10))
  } catch {
    error.value = '该模组无卸载记录'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-title">卸载计划</div>
    <div class="input-wrap" style="margin-bottom: 12px">
      <label>查看模组</label>
      <input v-model="modId" type="number" placeholder="输入模组 ID" />
    </div>
    <button class="btn-ghost full" :disabled="loading || !modId.trim()" @click="loadPlan">
      {{ loading ? '加载中...' : '查看卸载计划' }}
    </button>
    <div class="plan-box">
      <div v-if="loading" class="plan-empty"><span class="spinner" />加载中...</div>
      <div v-else-if="error" class="plan-empty">{{ error }}</div>
      <div v-else-if="!plan" class="plan-empty">选择模组查看卸载计划</div>
      <template v-else>
        <strong>新增文件 ({{ plan.added_files.length }})</strong>
        <ul>
          <li v-for="f in plan.added_files" :key="f">{{ f }}</li>
          <li v-if="!plan.added_files.length">无</li>
        </ul>
        <strong>创建目录 ({{ plan.created_dirs.length }})</strong>
        <ul>
          <li v-for="d in plan.created_dirs" :key="d">{{ d }}</li>
          <li v-if="!plan.created_dirs.length">无</li>
        </ul>
        <strong>备份文件 ({{ plan.backed_up_files.length }})</strong>
        <ul>
          <li v-for="b in plan.backed_up_files" :key="b.path">{{ b.path }}</li>
          <li v-if="!plan.backed_up_files.length">无</li>
        </ul>
      </template>
    </div>
  </section>
</template>

<style scoped>
.full { width: 100%; margin-bottom: 14px; }
.plan-box {
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px;
  font-size: 13px;
  max-height: 220px;
  overflow-y: auto;
}
.plan-box strong {
  display: block;
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin: 12px 0 6px;
}
.plan-box strong:first-child { margin-top: 0; }
.plan-box ul { list-style: none; }
.plan-box li {
  color: var(--muted);
  padding: 4px 0 4px 16px;
  position: relative;
  font-family: Consolas, monospace;
  font-size: 12px;
}
.plan-box li::before {
  content: "›";
  position: absolute;
  left: 0;
  color: var(--accent2);
}
.plan-empty { color: var(--muted); text-align: center; padding: 24px; }
</style>
