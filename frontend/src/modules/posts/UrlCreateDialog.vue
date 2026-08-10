<script setup lang="ts">
// URL capture (US1, T043): save a URL + optional note and usage, then let the
// server fetch asynchronously. The record is durable BEFORE extraction, so the
// dialog reports "已保存，正在后台抓取…" and a client-side unsafe-URL guard
// avoids a pointless round-trip.
import { computed, ref } from 'vue'
import {
  blogCaptureApi,
  classifyCaptureError,
  type UrlUsage,
} from '@/api/blogCapture'
import CaptureModal from '@/modules/posts/CaptureModal.vue'

const props = defineProps<{ initialUrl?: string }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', postId: string): void
  (e: 'saved'): void
}>()

const url = ref(props.initialUrl ?? '')
const note = ref('')
const usage = ref<UrlUsage>('triage')
const busy = ref(false)
const error = ref('')
const saved = ref(false)

const usageOptions: Array<{ value: UrlUsage; label: string }> = [
  { value: 'triage', label: '待整理' },
  { value: 'bookmark', label: '书签' },
  { value: 'reading_note', label: '阅读笔记' },
  { value: 'summary_note', label: '摘要笔记' },
  { value: 'technical_material', label: '技术素材' },
  { value: 'travel_material', label: '旅行素材' },
  { value: 'personal_article', label: '个人文章' },
]

const looksValid = computed(() => /^\s*https?:\/\/\S+/i.test(url.value))
const isBilibili = computed(() => {
  try {
    const parsed = new URL(url.value.trim())
    const host = parsed.hostname.toLowerCase().replace(/\.$/, '')
    return (
      (host === 'b23.tv' && parsed.pathname !== '/') ||
      ((host === 'bilibili.com' || host.endsWith('.bilibili.com')) &&
        /^\/video\/BV[a-z0-9]+(?:\/|$)/i.test(parsed.pathname))
    )
  } catch {
    return false
  }
})

async function save(): Promise<void> {
  if (!looksValid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await blogCaptureApi.url({
      url: url.value.trim(),
      note: note.value.trim() || null,
      usage: usage.value,
    })
    emit('saved')
    saved.value = true
    // The source is durable; extraction runs in the background. Give the user a
    // moment to see the confirmation, then open the draft.
    setTimeout(() => emit('created', res.post.id), 700)
  } catch (e) {
    const kind = classifyCaptureError(e)
    error.value =
      kind === 'unsafe_url'
        ? '该链接不被允许（可能是内网地址或非法协议）。'
        : kind === 'invalid_format'
          ? '链接格式不正确。'
          : kind === 'radio_service_unavailable'
            ? 'B站音视频处理服务当前不可用，请稍后重试。'
            : kind === 'bilibili_link_unavailable'
              ? '无法解析该 B 站链接，视频可能已失效、需要登录或存在访问限制。'
              : kind === 'radio_transcription_failed'
                ? '音视频转写失败，请稍后重试。'
          : '保存失败，请稍后重试。'
    busy.value = false
  }
}
</script>

<template>
  <CaptureModal
    title="从网址新建"
    :busy="busy"
    @close="emit('close')"
  >
    <div
      v-if="saved"
      class="url-saved"
    >
      ✓ {{ isBilibili ? '已保存，正在后台处理并转写音视频…' : '已保存，正在后台抓取正文…' }}
    </div>

    <template v-else>
      <label class="field">
        <span>网址</span>
        <input
          v-model="url"
          type="url"
          placeholder="https://…"
          :disabled="busy"
          autofocus
        >
      </label>

      <label class="field">
        <span>备注（可选）</span>
        <textarea
          v-model="note"
          rows="2"
          placeholder="为什么保存它？"
          :disabled="busy"
        />
      </label>

      <label class="field">
        <span>用途</span>
        <select
          v-model="usage"
          :disabled="busy"
        >
          <option
            v-for="o in usageOptions"
            :key="o.value"
            :value="o.value"
          >
            {{ o.label }}
          </option>
        </select>
      </label>

      <p
        v-if="error"
        class="url-error"
      >
        {{ error }}
      </p>
    </template>

    <template #footer>
      <button
        v-if="!saved"
        type="button"
        class="ghost"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        v-if="!saved"
        type="button"
        class="primary"
        :disabled="busy || !looksValid"
        @click="save"
      >
        {{ isBilibili ? '保存并转写' : '保存并抓取' }}
      </button>
    </template>
  </CaptureModal>
</template>

<style scoped>
.field {
  display: block;
  margin-bottom: var(--space-3);
}
.field > span {
  display: block;
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 0.25rem;
}
.field input,
.field textarea,
.field select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.url-saved {
  padding: var(--space-3);
  color: var(--status-done, #16a34a);
  font-weight: 600;
}
.url-error {
  color: var(--status-danger, #dc2626);
  margin: 0;
  font-size: 0.9rem;
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.primary {
  border: none;
  background: var(--status-normal);
  color: #fff;
}
.ghost {
  border: 1px solid var(--color-border);
  background: none;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
