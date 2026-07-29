<script setup lang="ts">
// Quick capture (US1, T044): minimal save / continue / full-edit flow.
// One textarea; "保存" saves and closes, "保存并继续" keeps the dialog open for
// the next note, "保存并编辑" jumps to the full editor.
import { ref } from 'vue'
import { blogCaptureApi, classifyCaptureError } from '@/api/blogCapture'
import CaptureModal from '@/modules/posts/CaptureModal.vue'

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', postId: string): void
  (e: 'saved'): void
}>()

const content = ref('')
const busy = ref(false)
const error = ref('')

async function save(mode: 'close' | 'continue' | 'edit'): Promise<void> {
  if (!content.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await blogCaptureApi.quick({
      content: content.value,
      save_and_continue: mode === 'continue',
    })
    emit('saved')
    if (mode === 'edit') {
      emit('created', res.post.id)
    } else if (mode === 'continue') {
      content.value = ''
    } else {
      emit('close')
    }
  } catch (e) {
    error.value =
      classifyCaptureError(e) === 'invalid_format'
        ? '内容无法保存，请检查后重试。'
        : '保存失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <CaptureModal
    title="快速记录"
    :busy="busy"
    @close="emit('close')"
  >
    <textarea
      v-model="content"
      class="quick-input"
      rows="6"
      placeholder="随手记一笔，稍后再整理…"
      :disabled="busy"
      autofocus
    />
    <p
      v-if="error"
      class="quick-error"
    >
      {{ error }}
    </p>
    <template #footer>
      <button
        type="button"
        class="ghost"
        :disabled="busy || !content.trim()"
        @click="save('continue')"
      >
        保存并继续
      </button>
      <button
        type="button"
        class="ghost"
        :disabled="busy || !content.trim()"
        @click="save('edit')"
      >
        保存并编辑
      </button>
      <button
        type="button"
        class="primary"
        :disabled="busy || !content.trim()"
        @click="save('close')"
      >
        保存
      </button>
    </template>
  </CaptureModal>
</template>

<style scoped>
.quick-input {
  width: 100%;
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.quick-error {
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
  color: var(--color-text);
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
