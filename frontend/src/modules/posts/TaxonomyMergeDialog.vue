<script setup lang="ts">
import { computed, ref } from 'vue'
import { taxonomyApi, type TaxonomyItem } from '@/api/blogTaxonomy'

const props = defineProps<{ kind: TaxonomyItem['kind']; source: TaxonomyItem; items: TaxonomyItem[] }>()
const emit = defineEmits<{ close: []; merged: [] }>()
const targetId = ref('')
const busy = ref(false)
const status = ref('')
const error = ref('')
const targets = computed(() => props.items.filter((item) => item.id !== props.source.id && item.enabled))
async function merge(): Promise<void> {
  if (!targetId.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await taxonomyApi.merge(props.kind, props.source.id, targetId.value)
    status.value = 'job_type' in result ? '已提交后台合并，可在任务中心查看' : '合并完成'
    emit('merged')
  } catch {
    error.value = '合并失败，请检查层级关系或稍后重试。'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div
    class="backdrop"
    @click.self="emit('close')"
  >
    <section
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-label="合并组织项"
    >
      <h2>合并“{{ source.name }}”</h2><p class="impact">
        将迁移 {{ source.usage_count }} 篇文章的关联，源项完成后停用；历史记录保留。
      </p><label>合并到<select v-model="targetId"><option value="">请选择目标</option><option
        v-for="item in targets"
        :key="item.id"
        :value="item.id"
      >{{ item.name }}</option></select></label><p
        v-if="status"
        role="status"
      >
        {{ status }}
      </p><p
        v-if="error"
        class="error"
        role="alert"
      >
        {{ error }}
      </p><footer>
        <button @click="emit('close')">
          取消
        </button><button
          class="danger"
          :disabled="!targetId || busy"
          @click="merge"
        >
          {{ busy ? '处理中…' : '确认合并' }}
        </button>
      </footer>
    </section>
  </div>
</template>
<style scoped>.backdrop{position:fixed;inset:0;z-index:45;background:#0007;display:grid;place-items:center}.dialog{width:min(460px,calc(100% - 24px));padding:var(--space-4);border-radius:var(--radius-lg);background:var(--color-surface)}select{display:block;width:100%;margin-top:var(--space-2);padding:var(--space-2);background:inherit;color:inherit}.impact{color:var(--color-text-muted)}.error{color:var(--status-urgent)}footer{display:flex;justify-content:flex-end;align-items:center;gap:var(--space-2);margin-top:var(--space-4)}button{min-height:var(--tap-target);padding:0 var(--space-3)}.danger{background:var(--status-urgent);color:#fff;border:0}</style>
