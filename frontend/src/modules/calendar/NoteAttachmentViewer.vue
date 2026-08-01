<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import type { NoteAsset } from '@/api/taskNotes'

const props = defineProps<{ assets: NoteAsset[]; taskId: string; startIndex: number }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const index = ref(props.startIndex)
const textBody = ref('')
const textLoading = ref(false)

const current = computed(() => props.assets[index.value])
const url = computed(
  () => `/api/v1/tasks/${props.taskId}/note/assets/${current.value.id}/access`,
)
const kind = computed<'image' | 'pdf' | 'text' | 'other'>(() => {
  const mt = current.value?.media_type ?? ''
  if (mt.startsWith('image/')) return 'image'
  if (mt === 'application/pdf') return 'pdf'
  if (mt.startsWith('text/') || mt === 'application/json') return 'text'
  return 'other'
})
const counter = computed(() => `${index.value + 1} / ${props.assets.length}`)

function go(delta: number): void {
  const n = props.assets.length
  index.value = (index.value + delta + n) % n
}

async function loadText(): Promise<void> {
  if (kind.value !== 'text') return
  textLoading.value = true
  textBody.value = ''
  try {
    const resp = await fetch(url.value, { credentials: 'same-origin' })
    textBody.value = (await resp.text()).slice(0, 20000)
  } catch {
    textBody.value = '（无法加载预览）'
  } finally {
    textLoading.value = false
  }
}
watch(index, loadText)
onMounted(loadText)

// Keyboard
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowRight') go(1)
  else if (e.key === 'ArrowLeft') go(-1)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// Touch / pointer gestures: horizontal swipe navigates, downward swipe closes.
const dragX = ref(0)
const dragY = ref(0)
const dragging = ref(false)
let startX = 0
let startY = 0
function onDown(e: PointerEvent): void {
  startX = e.clientX
  startY = e.clientY
  dragging.value = true
}
function onMove(e: PointerEvent): void {
  if (!dragging.value) return
  dragX.value = e.clientX - startX
  dragY.value = e.clientY - startY
}
function onUp(): void {
  if (!dragging.value) return
  dragging.value = false
  const dx = dragX.value
  const dy = dragY.value
  dragX.value = 0
  dragY.value = 0
  if (dy > 90 && Math.abs(dy) > Math.abs(dx)) {
    emit('close')
    return
  }
  if (props.assets.length > 1 && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
    go(dx < 0 ? 1 : -1)
  }
}
const stageStyle = computed(() =>
  dragging.value
    ? { transform: `translate(${dragX.value}px, ${Math.max(0, dragY.value)}px)` }
    : {},
)
</script>

<template>
  <div
    class="viewer"
    role="dialog"
    aria-modal="true"
    aria-label="附件预览"
    @click.self="emit('close')"
  >
    <button
      class="close"
      aria-label="关闭"
      @click="emit('close')"
    >
      ✕
    </button>
    <span
      v-if="assets.length > 1"
      class="counter"
    >{{ counter }}</span>

    <button
      v-if="assets.length > 1"
      class="nav prev"
      aria-label="上一个"
      @click.stop="go(-1)"
    >
      ‹
    </button>

    <div
      class="stage"
      :class="{ dragging }"
      :style="stageStyle"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
      @pointercancel="onUp"
    >
      <img
        v-if="kind === 'image'"
        :src="url"
        :alt="current.filename"
        draggable="false"
      >
      <iframe
        v-else-if="kind === 'pdf'"
        :src="url"
        :title="current.filename"
        class="pdf"
      />
      <pre
        v-else-if="kind === 'text'"
        class="text"
      >{{ textLoading ? '加载中…' : textBody }}</pre>
      <div
        v-else
        class="other"
      >
        <span class="big">📎</span>
        <span class="fn">{{ current.filename }}</span>
        <a
          class="dl"
          :href="url"
          :download="current.filename"
        >下载文件</a>
      </div>
    </div>

    <button
      v-if="assets.length > 1"
      class="nav next"
      aria-label="下一个"
      @click.stop="go(1)"
    >
      ›
    </button>

    <p class="hint">
      下滑关闭 · 左右滑动切换
    </p>
  </div>
</template>

<style scoped>
.viewer {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(0, 0, 0, 0.86);
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: 1fr auto;
  align-items: center;
  justify-items: center;
  animation: fade 0.2s ease;
  touch-action: none;
  user-select: none;
}
@keyframes fade {
  from {
    opacity: 0;
  }
}
.stage {
  grid-column: 2;
  grid-row: 1;
  max-width: 96vw;
  max-height: 82vh;
  display: grid;
  place-items: center;
  animation: pop 0.24s cubic-bezier(0.34, 1.4, 0.64, 1);
  will-change: transform;
}
.stage.dragging {
  animation: none;
}
@keyframes pop {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
}
.stage img {
  max-width: 96vw;
  max-height: 82vh;
  object-fit: contain;
  border-radius: var(--radius-sm);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
}
.pdf {
  width: 92vw;
  height: 82vh;
  border: none;
  background: #fff;
  border-radius: var(--radius-sm);
}
.text {
  max-width: 92vw;
  max-height: 82vh;
  overflow: auto;
  margin: 0;
  padding: var(--space-3);
  background: var(--color-surface);
  color: var(--color-text);
  border-radius: var(--radius-sm);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.85rem;
}
.other {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  color: #fff;
}
.other .big {
  font-size: 3rem;
}
.dl {
  padding: 0 var(--space-4);
  min-height: var(--tap-target);
  display: inline-flex;
  align-items: center;
  background: var(--status-normal);
  color: #fff;
  border-radius: var(--radius-sm);
  text-decoration: none;
}
.close {
  grid-column: 3;
  grid-row: 1;
  align-self: start;
  justify-self: end;
  margin: var(--space-3);
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 1.1rem;
  cursor: pointer;
  z-index: 2;
}
.counter {
  grid-column: 2;
  grid-row: 1;
  align-self: start;
  margin-top: var(--space-3);
  color: rgba(255, 255, 255, 0.85);
  font-variant-numeric: tabular-nums;
  z-index: 2;
}
.nav {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 1.6rem;
  line-height: 1;
  cursor: pointer;
  align-self: center;
}
.nav.prev {
  grid-column: 1;
  grid-row: 1;
  margin-left: var(--space-2);
}
.nav.next {
  grid-column: 3;
  grid-row: 1;
  margin-right: var(--space-2);
}
.hint {
  grid-column: 1 / -1;
  grid-row: 2;
  margin: 0 0 calc(var(--safe-bottom, 0px) + var(--space-3));
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.75rem;
}
@media (min-width: 721px) {
  .hint {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .viewer,
  .stage {
    animation: none;
  }
}
</style>
