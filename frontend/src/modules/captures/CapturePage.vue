<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { capturesApi, uploadImageAndCreateCapture, type Capture } from '@/api/captures'
import CaptureCard from '@/modules/captures/CaptureCard.vue'
import ProvenanceField from '@/modules/captures/ProvenanceField.vue'

const captures = ref<Capture[]>([])
const filter = ref<string>('')
const selected = ref<Capture | null>(null)
const uploading = ref(false)

const filters = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'wishlist', label: '想购买' },
  { value: 'owned', label: '家中物品' },
  { value: 'duplicate', label: '可能重复' },
]

async function refresh(): Promise<void> {
  captures.value = (await capturesApi.list(filter.value ? { state: filter.value } : undefined)).items
}

onMounted(refresh)

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    // Save-first: the pending card appears immediately after create resolves.
    const capture = await uploadImageAndCreateCapture(file, null)
    captures.value = [capture, ...captures.value]
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function openDetail(capture: Capture): Promise<void> {
  selected.value = await capturesApi.get(capture.id)
}

const detailFields = computed(() => {
  if (!selected.value) return []
  return [
    { key: 'title', label: '标题' },
    { key: 'brand', label: '品牌' },
    { key: 'model', label: '型号' },
    { key: 'material', label: '材质' },
    { key: 'color', label: '颜色' },
    { key: 'storage_location', label: '存放位置' },
  ]
})

async function convertToTask(): Promise<void> {
  if (!selected.value) return
  await capturesApi.convert(selected.value.id, 'task')
  selected.value = null
}
</script>

<template>
  <main class="captures">
    <header class="head">
      <h1>收藏</h1>
      <label class="add">
        📷 拍照/上传
        <input
          type="file"
          accept="image/*"
          capture="environment"
          @change="onFile"
        >
      </label>
    </header>

    <p
      v-if="uploading"
      class="muted"
      role="status"
    >
      上传中，原图会先保存…
    </p>

    <nav class="filters">
      <button
        v-for="f in filters"
        :key="f.value"
        type="button"
        :class="{ active: filter === f.value }"
        @click="filter = f.value; refresh()"
      >
        {{ f.label }}
      </button>
    </nav>

    <div class="grid">
      <CaptureCard
        v-for="c in captures"
        :key="c.id"
        :capture="c"
        @open="openDetail"
      />
    </div>
    <p
      v-if="captures.length === 0"
      class="muted"
    >
      还没有收藏，拍一张开始吧。
    </p>

    <div
      v-if="selected"
      class="overlay"
      @click.self="selected = null"
    >
      <aside
        class="drawer"
        role="dialog"
        aria-label="收藏详情"
      >
        <h2>收藏详情</h2>
        <p class="hint">
          “你填写”的信息优先，AI 建议单独标注，可编辑或采用。
        </p>
        <ProvenanceField
          v-for="f in detailFields"
          :key="f.key"
          :label="f.label"
          :field="selected.fields[f.key]"
        />
        <p
          v-if="selected.ocr_text"
          class="ocr"
        >
          识别文字：{{ selected.ocr_text }}
        </p>
        <footer>
          <button
            type="button"
            @click="selected = null"
          >
            关闭
          </button>
          <button
            type="button"
            class="primary"
            @click="convertToTask"
          >
            转为待办
          </button>
        </footer>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.captures {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 900px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.add {
  min-height: var(--tap-target);
  display: inline-flex;
  align-items: center;
  padding: 0 var(--space-3);
  background: var(--status-normal);
  color: white;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.add input {
  display: none;
}
.filters {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.filters button {
  min-height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.filters button.active {
  background: var(--color-surface-2);
  color: var(--status-normal);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-2);
}
.muted {
  color: var(--color-text-muted);
}
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: grid;
  place-items: end center;
  z-index: 20;
}
.drawer {
  background: var(--color-surface);
  width: 100%;
  max-width: 480px;
  padding: var(--space-4);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}
.hint {
  color: var(--status-ai);
  font-size: 0.8rem;
}
.ocr {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
footer button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
footer button.primary {
  background: var(--status-normal);
  color: white;
  border: none;
}
</style>
