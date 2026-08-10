<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  taskNotesApi,
  uploadNoteImage,
  type NoteAsset,
  type TaskNote,
} from '@/api/taskNotes'
import NoteAttachmentViewer from '@/modules/calendar/NoteAttachmentViewer.vue'

const props = defineProps<{ taskId: string; title: string }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

const content = ref('')
const version = ref<number>(0)
const assets = ref<NoteAsset[]>([])
const previews = ref<Record<string, string>>({})
const savingText = ref(false)
const viewerIndex = ref<number | null>(null)

function openViewer(a: NoteAsset): void {
  if (a.processing_status === 'failed') return
  const i = assets.value.findIndex((x) => x.id === a.id)
  if (i >= 0) viewerIndex.value = i
}
const textError = ref('')

interface Batch {
  file: File
  status: 'uploading' | 'attaching' | 'done' | 'failed'
  error?: string
}
const batch = ref<Batch[]>([])

async function load(): Promise<void> {
  const note: TaskNote = await taskNotesApi.get(props.taskId)
  content.value = note.content
  version.value = note.version
  assets.value = note.assets
  loadPreviews()
}

function isImage(a: NoteAsset): boolean {
  return a.media_type.startsWith('image/')
}
function fileIcon(a: NoteAsset): string {
  if (a.media_type === 'application/pdf') return '📄'
  if (a.media_type.startsWith('text/')) return '📃'
  if (a.media_type === 'application/zip') return '🗜️'
  if (a.media_type.includes('sheet') || a.media_type.includes('excel')) return '📊'
  if (a.media_type.includes('word') || a.media_type.includes('document')) return '📝'
  if (a.media_type.includes('presentation') || a.media_type.includes('powerpoint')) return '📑'
  return '📎'
}
function loadPreviews(): void {
  // The access endpoint streams the bytes with cookie auth, so its URL works
  // directly as an <img> src (images) or a file link (other types).
  for (const a of assets.value) {
    if (a.processing_status !== 'failed') {
      previews.value[a.id] = `/api/v1/tasks/${props.taskId}/note/assets/${a.id}/access`
    }
  }
}

onMounted(load)

async function saveText(): Promise<void> {
  savingText.value = true
  textError.value = ''
  try {
    const note = await taskNotesApi.save(props.taskId, content.value, version.value || undefined)
    version.value = note.version
    emit('saved')
  } catch {
    textError.value = '保存失败，请重试。'
  } finally {
    savingText.value = false
  }
}

async function onFiles(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = '' // allow re-selecting the same files
  if (!files.length) return
  const items: Batch[] = files.map((file) => ({ file, status: 'uploading' }))
  batch.value = items
  await runBatch(items)
}

async function runBatch(items: Batch[]): Promise<void> {
  // Upload each file; keep per-file status so one failure doesn't block others.
  const uploaded: { item: Batch; uploadId: string }[] = []
  await Promise.all(
    items.map(async (item) => {
      try {
        const id = await uploadNoteImage(item.file)
        item.status = 'attaching'
        uploaded.push({ item, uploadId: id })
      } catch {
        item.status = 'failed'
        item.error = '上传失败'
      }
    }),
  )
  if (uploaded.length) {
    try {
      const { results } = await taskNotesApi.attach(
        props.taskId,
        uploaded.map((u) => u.uploadId),
      )
      const byId = new Map(results.map((r) => [r.upload_id, r]))
      for (const u of uploaded) {
        const r = byId.get(u.uploadId)
        if (r && r.status === 'attached') u.item.status = 'done'
        else {
          u.item.status = 'failed'
          u.item.error = r?.error ?? '关联失败'
        }
      }
      await load()
      emit('saved')
    } catch {
      for (const u of uploaded) {
        u.item.status = 'failed'
        u.item.error = '关联失败'
      }
    }
  }
}

async function retry(item: Batch): Promise<void> {
  item.status = 'uploading'
  item.error = undefined
  await runBatch([item])
}
</script>

<template>
  <div
    class="editor"
    role="dialog"
    aria-label="事件备注"
    @click.stop
  >
    <header>
      <strong>备注 · {{ title }}</strong>
      <button
        class="x"
        aria-label="关闭"
        @click="emit('close')"
      >
        ✕
      </button>
    </header>

    <textarea
      v-model="content"
      class="text"
      rows="4"
      maxlength="20000"
      placeholder="写点什么…"
    />
    <div class="row">
      <button
        class="primary"
        :disabled="savingText"
        @click="saveText"
      >
        {{ savingText ? '保存中…' : '保存备注' }}
      </button>
      <label class="file">
        + 添加图片
        <input
          type="file"
          accept="image/*,application/pdf,text/plain,text/markdown,text/csv,application/json,application/zip,.doc,.docx,.xls,.xlsx,.ppt,.pptx"
          multiple
          hidden
          @change="onFiles"
        >
      </label>
    </div>
    <p
      v-if="textError"
      class="err"
      role="alert"
    >
      {{ textError }}
    </p>

    <ul
      v-if="batch.length"
      class="batch"
    >
      <li
        v-for="(b, i) in batch"
        :key="i"
        :class="b.status"
      >
        <span class="name">{{ b.file.name }}</span>
        <span class="st">
          {{ b.status === 'done' ? '✓ 已保存'
            : b.status === 'failed' ? '✕ ' + (b.error ?? '失败')
              : '上传中…' }}
        </span>
        <button
          v-if="b.status === 'failed'"
          class="retry"
          @click="retry(b)"
        >
          重试
        </button>
      </li>
    </ul>

    <div
      v-if="assets.length"
      class="gallery"
    >
      <button
        v-for="a in assets"
        :key="a.id"
        type="button"
        class="thumb"
        :class="{ file: !isImage(a) }"
        :title="a.filename"
        @click="openViewer(a)"
      >
        <img
          v-if="isImage(a) && previews[a.id]"
          :src="previews[a.id]"
          :alt="a.filename"
        >
        <template v-else>
          <span class="ph">{{ a.processing_status === 'failed' ? '⚠️' : fileIcon(a) }}</span>
          <span class="fname">{{ a.filename }}</span>
        </template>
      </button>
    </div>

    <NoteAttachmentViewer
      v-if="viewerIndex !== null"
      :assets="assets"
      :task-id="taskId"
      :start-index="viewerIndex"
      @close="viewerIndex = null"
    />
  </div>
</template>

<style scoped>
.editor {
  width: min(420px, 94vw);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.x {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--color-text-muted);
  min-width: 32px;
  min-height: 32px;
}
.text {
  width: 100%;
  resize: vertical;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}
.row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.primary,
.file {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.file {
  background: var(--color-surface);
  color: var(--color-text);
}
.err {
  color: var(--status-urgent);
  font-size: 0.85rem;
  margin: 0;
}
.batch {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.batch li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.8rem;
}
.batch .name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.batch li.failed .st {
  color: var(--status-urgent);
}
.batch li.done .st {
  color: var(--status-done);
}
.retry {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  padding: 2px 8px;
}
.gallery {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.thumb {
  border: none;
  cursor: pointer;
  padding: 0;
  width: 72px;
  height: 72px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-surface-2);
  display: grid;
  place-items: center;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ph {
  font-size: 1.4rem;
}
.thumb.file {
  width: auto;
  min-width: 96px;
  max-width: 160px;
  height: auto;
  padding: var(--space-2);
  flex-direction: column;
  gap: 4px;
  text-decoration: none;
  color: var(--color-text);
}
.thumb {
  text-decoration: none;
}
.fname {
  font-size: 0.68rem;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
