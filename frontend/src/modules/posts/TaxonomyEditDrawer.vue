<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { TaxonomyCreate, TaxonomyItem } from '@/api/blogTaxonomy'

const props = defineProps<{
  item: TaxonomyItem | null
  kind: TaxonomyItem['kind']
  categories: TaxonomyItem[]
}>()
const emit = defineEmits<{ close: []; save: [value: TaxonomyCreate] }>()
const kindLabel = computed(() => props.kind === 'category' ? '分类' : props.kind === 'tag' ? '标签' : '关键词')
const form = reactive({ name: '', description: '', parent_id: '', aliases: '', color: '', enabled: true, stop_word: false })

watch(() => props.item, (item) => {
  form.name = item?.name ?? ''
  form.description = item?.description ?? ''
  form.parent_id = item?.parent_id ?? ''
  form.aliases = item?.aliases.join('，') ?? ''
  form.color = item?.color ?? ''
  form.enabled = item?.enabled ?? true
  form.stop_word = item?.stop_word ?? false
}, { immediate: true })

function submit(): void {
  emit('save', {
    name: form.name.trim(), description: form.description.trim() || null,
    parent_id: props.kind === 'category' ? form.parent_id || null : null,
    aliases: props.kind === 'category' ? [] : form.aliases.split(/[，,]/).map((v) => v.trim()).filter(Boolean),
    color: props.kind === 'tag' ? form.color.trim() || null : null,
    enabled: form.enabled, stop_word: props.kind === 'keyword' && form.stop_word,
  })
}
</script>

<template>
  <div
    class="backdrop"
    role="presentation"
    @click.self="emit('close')"
  >
    <section
      class="drawer"
      role="dialog"
      aria-modal="true"
      aria-label="编辑组织项"
    >
      <header><h2>{{ item ? '编辑' : '新建' }}{{ kindLabel }}</h2></header>
      <label>名称<input
        v-model="form.name"
        :aria-label="`${kindLabel}名称`"
      ></label>
      <label>说明<textarea
        v-model="form.description"
        rows="3"
      /></label>
      <label v-if="kind === 'category'">父分类<select
        v-model="form.parent_id"
        aria-label="父分类"
      ><option value="">顶层分类</option><option
        v-for="category in categories.filter((c) => c.id !== item?.id)"
        :key="category.id"
        :value="category.id"
      >{{ category.name }}</option></select></label>
      <label v-if="kind !== 'category'">{{ kind === 'tag' ? '别名' : '同义词' }}<input
        v-model="form.aliases"
        placeholder="用逗号分隔"
      ></label>
      <label v-if="kind === 'tag'">颜色<input
        v-model="form.color"
        placeholder="blue"
      ></label>
      <label class="check"><input
        v-model="form.enabled"
        type="checkbox"
      >启用</label>
      <label
        v-if="kind === 'keyword'"
        class="check"
      ><input
        v-model="form.stop_word"
        type="checkbox"
      >停用词（不参与词云和自动提取）</label>
      <footer>
        <button
          type="button"
          @click="emit('close')"
        >
          取消
        </button><button
          class="primary"
          type="button"
          :disabled="!form.name.trim()"
          @click="submit"
        >
          保存
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.backdrop{position:fixed;inset:0;z-index:40;background:#0007;display:flex;justify-content:flex-end}.drawer{width:min(420px,100%);height:100%;padding:var(--space-4);background:var(--color-surface);overflow:auto}.drawer label{display:block;margin:var(--space-3) 0}.drawer input,.drawer textarea,.drawer select{display:block;width:100%;margin-top:var(--space-1);padding:var(--space-2);border:1px solid var(--color-border);background:inherit;color:inherit}.check{display:flex!important;gap:var(--space-2)}.check input{width:auto}.drawer footer{display:flex;justify-content:flex-end;gap:var(--space-2)}button{min-height:var(--tap-target);padding:0 var(--space-3)}.primary{background:var(--status-normal);color:#fff;border:0}
</style>
