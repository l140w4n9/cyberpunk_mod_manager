<script setup>

import { ref } from 'vue'

import { STATUS_LABELS } from '../api/client'



defineProps({

  mods: { type: Array, default: () => [] },

  loading: { type: Boolean, default: false },

  installing: { type: Boolean, default: false },

  status: { type: Object, default: () => ({ message: '', type: '' }) },

})



const emit = defineEmits(['install', 'install-with-deps', 'install-local', 'uninstall', 'check-deps'])

const modIdInput = ref('')

const archiveNameInput = ref('')

const depsReport = ref(null)

const checkingDeps = ref(false)



function formatDate(value) {

  return value ? new Date(value).toLocaleString('zh-CN') : '—'

}



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



async function checkDeps() {

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

  <section class="panel">

    <div class="panel-title">模组库存</div>



    <form class="install-box" @submit.prevent="submitInstall(false)">

      <div class="input-wrap">

        <label>Nexus Mod ID</label>

        <input v-model="modIdInput" type="number" placeholder="例如 27967" />

      </div>

      <div class="input-wrap">

        <label>本地压缩包（Premium 手动下载）</label>

        <input v-model="archiveNameInput" type="text" placeholder="如 27967_0-Engine.zip" />

      </div>

      <div class="btn-row">

        <button class="btn-primary" type="submit" :disabled="installing || !modIdInput.trim()">

          {{ installing ? '安装中...' : '安装模组' }}

        </button>

        <button

          class="btn-secondary"

          type="button"

          :disabled="installing || !modIdInput.trim()"

          @click="submitInstall(true)"

        >

          安装含依赖

        </button>

        <button

          class="btn-secondary"

          type="button"

          :disabled="installing || !modIdInput.trim() || !archiveNameInput.trim()"

          @click="submitLocalInstall"

        >

          本地安装

        </button>

        <button

          class="btn-ghost"

          type="button"

          :disabled="checkingDeps || !modIdInput.trim()"

          @click="checkDeps"

        >

          {{ checkingDeps ? '检查中...' : '检查依赖' }}

        </button>

      </div>

    </form>



    <div v-if="depsReport" class="deps-panel">

      <div class="deps-title">

        依赖检查 — Mod {{ depsReport.mod_id }}

        <span class="deps-badge" :class="depsReport.all_satisfied ? 'ok' : 'warn'">

          {{ depsReport.all_satisfied ? '全部满足' : `缺失 ${depsReport.missing_count}` }}

        </span>

      </div>

      <ul class="deps-list">

        <li v-for="dep in depsReport.dependencies" :key="dep.nexus_mod_id">

          <span class="dep-id">{{ dep.nexus_mod_id }}</span>

          <span class="dep-name">{{ dep.name || '未知' }}</span>

          <span class="badge small" :class="dep.installed ? 'installed' : 'not_installed'">

            {{ dep.installed ? '已安装' : '未安装' }}

          </span>

        </li>

      </ul>

    </div>



    <div class="table-wrap">

      <table>

        <thead>

          <tr>

            <th>ID</th>

            <th>名称</th>

            <th>版本</th>

            <th>状态</th>

            <th>安装时间</th>

            <th>操作</th>

          </tr>

        </thead>

        <tbody>

          <tr v-if="loading">

            <td colspan="6" class="empty"><span class="spinner" />加载中...</td>

          </tr>

          <tr v-else-if="!mods.length">

            <td colspan="6" class="empty">

              <div class="empty-icon">◇</div>

              暂无模组

              <small>输入模组 ID 开始安装</small>

            </td>

          </tr>

          <tr v-for="mod in mods" :key="mod.id">

            <td><span class="mod-id">{{ mod.nexus_mod_id }}</span></td>

            <td>

              <div class="mod-name">{{ mod.name || '—' }}</div>

              <a

                v-if="mod.mod_page_url"

                class="mod-link"

                :href="mod.mod_page_url"

                target="_blank"

                rel="noopener noreferrer"

              >Nexus 主页 →</a>

            </td>

            <td>{{ mod.version || '—' }}</td>

            <td>

              <span class="badge" :class="mod.status">

                {{ STATUS_LABELS[mod.status] || mod.status }}

              </span>

            </td>

            <td class="time">{{ formatDate(mod.installed_at) }}</td>

            <td>

              <button

                class="btn-danger"

                :disabled="mod.status !== 'installed'"

                @click="$emit('uninstall', mod.nexus_mod_id)"

              >卸载</button>

            </td>

          </tr>

        </tbody>

      </table>

    </div>



    <div v-if="status.message" class="status-line" :class="status.type">

      {{ status.message }}

    </div>

  </section>

</template>



<style scoped>

.install-box {

  display: flex;

  flex-wrap: wrap;

  gap: 12px;

  margin-bottom: 20px;

  padding: 16px;

  background: rgba(0, 0, 0, 0.3);

  border: 1px dashed rgba(0, 240, 255, 0.2);

  border-radius: var(--radius-sm);

}

.install-box .input-wrap { flex: 1 1 200px; }

.btn-row {

  display: flex;

  flex-wrap: wrap;

  gap: 8px;

  align-items: flex-end;

  width: 100%;

}

.btn-secondary {

  padding: 10px 16px;

  border-radius: var(--radius-sm);

  border: 1px solid rgba(0, 240, 255, 0.35);

  background: rgba(0, 240, 255, 0.08);

  color: var(--accent2);

  cursor: pointer;

}

.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {

  padding: 10px 16px;

  border-radius: var(--radius-sm);

  border: 1px solid var(--border);

  background: transparent;

  color: var(--muted);

  cursor: pointer;

}

.deps-panel {

  margin-bottom: 16px;

  padding: 14px 16px;

  border: 1px solid var(--border);

  border-radius: var(--radius-sm);

  background: rgba(0, 0, 0, 0.25);

}

.deps-title {

  display: flex;

  align-items: center;

  gap: 10px;

  font-size: 13px;

  margin-bottom: 10px;

}

.deps-badge.ok { color: var(--ok); }

.deps-badge.warn { color: var(--accent); }

.deps-list { list-style: none; margin: 0; padding: 0; }

.deps-list li {

  display: flex;

  align-items: center;

  gap: 10px;

  padding: 6px 0;

  font-size: 13px;

  border-bottom: 1px solid rgba(255, 255, 255, 0.05);

}

.dep-id {

  font-family: var(--font-display);

  color: var(--accent2);

  min-width: 48px;

}

.dep-name { flex: 1; }

.badge.small { font-size: 11px; padding: 2px 8px; }

.table-wrap {

  overflow-x: auto;

  border-radius: var(--radius-sm);

  border: 1px solid var(--border);

}

table { width: 100%; border-collapse: collapse; }

th {

  text-align: left;

  color: var(--muted);

  font-size: 10px;

  text-transform: uppercase;

  letter-spacing: 1.5px;

  padding: 14px 16px;

  background: rgba(0, 0, 0, 0.35);

  border-bottom: 1px solid var(--border);

}

td {

  padding: 14px 16px;

  border-bottom: 1px solid var(--border);

  font-size: 14px;

  vertical-align: middle;

}

tbody tr:hover td { background: rgba(0, 240, 255, 0.04); }

.mod-id {

  font-family: var(--font-display);

  color: var(--accent2);

}

.mod-name { font-weight: 600; }

.mod-link {

  color: var(--accent2);

  font-size: 12px;

  text-decoration: none;

  opacity: 0.85;

}

.mod-link:hover { text-decoration: underline; opacity: 1; }

.time { color: var(--muted); font-size: 13px; }

.empty {

  text-align: center;

  padding: 48px 20px;

  color: var(--muted);

}

.empty small { display: block; margin-top: 8px; }

.empty-icon { font-size: 28px; margin-bottom: 8px; opacity: 0.4; }

.status-line {

  margin-top: 16px;

  padding: 12px 16px;

  border-radius: var(--radius-sm);

  font-size: 13px;

}

.status-line.info {

  background: rgba(0, 240, 255, 0.08);

  border: 1px solid rgba(0, 240, 255, 0.2);

  color: var(--accent2);

}

.status-line.ok {

  background: rgba(46, 230, 166, 0.08);

  border: 1px solid rgba(46, 230, 166, 0.2);

  color: var(--ok);

}

.status-line.err {

  background: rgba(255, 59, 92, 0.08);

  border: 1px solid rgba(255, 59, 92, 0.2);

  color: var(--danger);

}



@media (max-width: 600px) {

  .install-box { flex-direction: column; }

}

</style>

