<script setup>
import { useI18n } from '../i18n'

defineProps({
  visible: { type: Boolean, default: false },
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel'])

const { t } = useI18n()
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="overlay" @click.self="emit('cancel')">
      <div class="dialog">
        <h3 class="dialog-title">{{ t('uninstall.title') }}</h3>
        <p v-if="report" class="dialog-sub">
          {{ report.name }} <span class="mod-id">#{{ report.mod_id }}</span>
        </p>

        <div v-if="report?.safe" class="alert alert--ok">
          {{ t('uninstall.safe') }}
        </div>
        <div v-else class="alert alert--warn">
          <strong>{{ t('uninstall.unsafe') }}</strong>
          <ul>
            <li v-for="(w, i) in report?.warnings || []" :key="i">{{ w }}</li>
          </ul>
        </div>

        <div v-if="report?.blocking_dependents?.length" class="block-list">
          <span class="label">{{ t('uninstall.affected') }}</span>
          <div class="chip-row">
            <span
              v-for="dep in report.blocking_dependents"
              :key="dep.nexus_mod_id"
              class="chip"
            >
              {{ dep.name }} ({{ dep.nexus_mod_id }})
            </span>
          </div>
        </div>

        <div class="actions">
          <button class="btn-ghost" :disabled="loading" @click="emit('cancel')">
            {{ t('uninstall.cancel') }}
          </button>
          <button
            v-if="report?.safe"
            class="btn-primary"
            :disabled="loading"
            @click="emit('confirm', false)"
          >
            {{ loading ? t('uninstall.unloading') : t('uninstall.confirm') }}
          </button>
          <button
            v-else-if="report?.can_uninstall"
            class="btn-danger"
            :disabled="loading"
            @click="emit('confirm', true)"
          >
            {{ loading ? t('uninstall.unloading') : t('uninstall.force') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.dialog {
  width: 100%;
  max-width: 480px;
  padding: 24px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: #0d1117;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.dialog-title {
  margin: 0 0 8px;
  font-size: 18px;
}
.dialog-sub {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 14px;
}
.mod-id {
  font-family: var(--font-display);
  color: var(--accent2);
}
.alert {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 14px;
}
.alert--ok {
  background: rgba(46, 230, 166, 0.08);
  border: 1px solid rgba(46, 230, 166, 0.25);
  color: var(--ok);
}
.alert--warn {
  background: rgba(255, 59, 92, 0.08);
  border: 1px solid rgba(255, 59, 92, 0.25);
  color: var(--danger);
}
.alert ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.block-list { margin-bottom: 18px; }
.label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
  margin-bottom: 8px;
}
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid rgba(252, 238, 10, 0.35);
  color: var(--accent);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
