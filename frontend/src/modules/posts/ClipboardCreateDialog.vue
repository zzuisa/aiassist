<script setup lang="ts">
// Clipboard capture (US1, T042): read the clipboard, detect its format, show a
// preview, and save the original before any AI. Handles permission denial, an
// image-only clipboard (partial), and a URL-only clipboard (offer URL capture).
import { computed, onMounted, ref } from 'vue'
import {
  blogCaptureApi,
  classifyCaptureError,
  type DetectedFormat,
} from '@/api/blogCapture'
import CaptureModal from '@/modules/posts/CaptureModal.vue'

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', postId: string): void
  (e: 'switch-url', url: string): void
  (e: 'saved'): void
}>()

type Phase = 'reading' | 'denied' | 'empty' | 'ready' | 'image-only'
const phase = ref<Phase>('reading')
const raw = ref('')
const detected = ref<DetectedFormat>('plain')
const busy = ref(false)
const error = ref('')

const isUrlOnly = computed(
  () => detected.value === 'url' && /^\s*https?:\/\/\S+\s*$/i.test(raw.value),
)

function detectFormat(text: string, hasHtml: boolean): DetectedFormat {
  if (/^\s*https?:\/\/\S+\s*$/i.test(text)) return 'url'
  if (hasHtml) return 'html'
  if (/^\s*(#{1,6}\s|[-*]\s|```)/m.test(text)) return 'markdown'
  if (/[;{}]\s*$|^\s{2,}\S/m.test(text)) return 'code'
  return 'plain'
}

async function readClipboard(): Promise<void> {
  phase.value = 'reading'
  const clip = navigator.clipboard
  try {
    if (!clip) {
      phase.value = 'denied'
      return
    }
    // Prefer the rich read() API so we can detect HTML; fall back to text.
    if (typeof clip.read === 'function') {
      const items = await clip.read()
      let text = ''
      let html = ''
      let sawImage = false
      for (const item of items) {
        if (item.types.includes('text/html')) html = await (await item.getType('text/html')).text()
        if (item.types.includes('text/plain'))
          text = await (await item.getType('text/plain')).text()
        if (item.types.some((t) => t.startsWith('image/'))) sawImage = true
      }
      if (!text && !html && sawImage) {
        phase.value = 'image-only'
        return
      }
      raw.value = html || text
      detected.value = detectFormat(text || html, Boolean(html))
    } else {
      raw.value = await clip.readText()
      detected.value = detectFormat(raw.value, false)
    }
    phase.value = raw.value.trim() ? 'ready' : 'empty'
  } catch {
    phase.value = 'denied'
  }
}

onMounted(readClipboard)

async function save(): Promise<void> {
  if (!raw.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await blogCaptureApi.clipboard({
      raw_content: raw.value,
      detected_format: detected.value,
    })
    emit('saved')
    emit('created', res.post.id)
  } catch (e) {
    const kind = classifyCaptureError(e)
    error.value =
      kind === 'too_large'
        ? '内容过大，无法保存。'
        : kind === 'invalid_format'
          ? '内容格式无法识别，请重试。'
          : '保存失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <CaptureModal
    title="从剪贴板新建"
    :busy="busy"
    @close="emit('close')"
  >
    <p
      v-if="phase === 'reading'"
      class="muted"
    >
      正在读取剪贴板…
    </p>

    <div v-else-if="phase === 'denied'">
      <p class="muted">
        无法读取剪贴板。请授予权限，或直接粘贴内容：
      </p>
      <textarea
        v-model="raw"
        class="clip-input"
        rows="6"
        placeholder="在此粘贴 (Ctrl/Cmd + V)"
        @input="detected = detectFormat(raw, /</.test(raw))"
      />
    </div>

    <p
      v-else-if="phase === 'empty'"
      class="muted"
    >
      剪贴板是空的。
    </p>

    <p
      v-else-if="phase === 'image-only'"
      class="muted"
    >
      剪贴板里只有图片，暂不支持图片直接新建，请改用文字或链接。
    </p>

    <div v-else>
      <div class="clip-meta">
        <span class="badge">识别格式：{{ detected }}</span>
        <button
          v-if="isUrlOnly"
          type="button"
          class="link"
          @click="emit('switch-url', raw.trim())"
        >
          这是链接，改为抓取网页 →
        </button>
      </div>
      <pre class="clip-preview">{{ raw }}</pre>
    </div>

    <p
      v-if="error"
      class="clip-error"
    >
      {{ error }}
    </p>

    <template #footer>
      <button
        type="button"
        class="ghost"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        type="button"
        class="primary"
        :disabled="busy || phase === 'reading' || phase === 'empty' || phase === 'image-only' || !raw.trim()"
        @click="save"
      >
        保存原文
      </button>
    </template>
  </CaptureModal>
</template>

<style scoped>
.muted {
  color: var(--color-text-muted);
}
.clip-input {
  width: 100%;
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.clip-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.badge {
  font-size: 0.8rem;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #4f46e5);
}
.clip-preview {
  max-height: 240px;
  overflow: auto;
  padding: var(--space-3);
  background: var(--color-surface-muted, #f8fafc);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.link {
  border: none;
  background: none;
  color: var(--color-accent, #4f46e5);
  cursor: pointer;
  font-size: 0.85rem;
}
.clip-error {
  color: var(--status-danger, #dc2626);
  margin: var(--space-2) 0 0;
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
