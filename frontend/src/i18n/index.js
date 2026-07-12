import { computed, reactive } from 'vue'
import en from './locales/en'
import zh from './locales/zh'

const STORAGE_KEY = 'cpmm_locale'

const messages = { zh, en }

function detectDefaultLocale() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'zh' || stored === 'en') return stored
  } catch {
    /* ignore */
  }
  const lang = (navigator.language || 'zh').toLowerCase()
  return lang.startsWith('zh') ? 'zh' : 'en'
}

export const i18nState = reactive({
  locale: detectDefaultLocale(),
})

function resolve(obj, path) {
  return path.split('.').reduce((acc, key) => (acc && acc[key] != null ? acc[key] : undefined), obj)
}

export function t(key, params) {
  const pack = messages[i18nState.locale] || messages.zh
  let text = resolve(pack, key)
  if (text == null) {
    text = resolve(messages.zh, key)
  }
  if (text == null) return key
  if (typeof text !== 'string') return key
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (_, name) => {
    const value = params[name]
    return value == null ? `{${name}}` : String(value)
  })
}

export function setLocale(locale) {
  if (locale !== 'zh' && locale !== 'en') return
  i18nState.locale = locale
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    /* ignore */
  }
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
  syncLocaleToBackend(locale)
}

export function getRequestLocale() {
  return i18nState.locale
}

export async function syncLocaleToBackend(locale = i18nState.locale) {
  try {
    await fetch('/api/config/locale', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Locale': locale,
        'Accept-Language': locale === 'en' ? 'en-US' : 'zh-CN',
      },
      body: JSON.stringify({ ui_locale: locale }),
    })
  } catch {
    /* 后端未启动时忽略 */
  }
}

export function useI18n() {
  const locale = computed(() => i18nState.locale)
  return {
    locale,
    t,
    setLocale,
  }
}

export function statusLabel(status) {
  return t(`status.${status}`) || status
}

export function toolStateLabel(state) {
  return t(`toolState.${state}`) || state
}

export const REQUEST_CANCELLED = 'REQUEST_CANCELLED'

export function isRequestCancelled(error) {
  return error?.code === REQUEST_CANCELLED || error?.name === 'AbortError'
}

export function healthLabelFromData(data) {
  if (!data) return t('health.connectionFailed')
  if (!data.data_dir_configured) return t('health.noDataDir')
  if (!data.llm_configured) return t('health.noLlm')
  if (!data.nexus_configured) return t('health.noNexusKey')
  if (!data.nexus_valid) return t('health.invalidNexusKey')
  return t('health.ready')
}

setLocale(i18nState.locale)
