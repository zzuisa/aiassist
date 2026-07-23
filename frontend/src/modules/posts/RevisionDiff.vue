<script setup lang="ts">
import { computed } from 'vue'

// Renders a unified diff with add/remove line coloring. Apply/ignore/regenerate
// are explicit; AI text is never auto-applied to the draft.
const props = defineProps<{ unifiedDiff: string }>()
defineEmits<{ (e: 'apply'): void; (e: 'ignore'): void; (e: 'regenerate'): void }>()

interface Line {
  text: string
  kind: 'add' | 'remove' | 'context' | 'meta'
}

const lines = computed<Line[]>(() =>
  props.unifiedDiff.split('\n').map((text) => {
    if (text.startsWith('+++') || text.startsWith('---') || text.startsWith('@@'))
      return { text, kind: 'meta' }
    if (text.startsWith('+')) return { text, kind: 'add' }
    if (text.startsWith('-')) return { text, kind: 'remove' }
    return { text, kind: 'context' }
  }),
)
</script>

<template>
  <div class="diff">
    <pre><code><span
      v-for="(line, i) in lines"
      :key="i"
      class="line"
      :class="line.kind"
    >{{ line.text }}
</span></code></pre>
    <div class="actions">
      <button
        type="button"
        class="apply"
        @click="$emit('apply')"
      >
        应用
      </button>
      <button
        type="button"
        @click="$emit('ignore')"
      >
        忽略
      </button>
      <button
        type="button"
        @click="$emit('regenerate')"
      >
        重新生成
      </button>
    </div>
  </div>
</template>

<style scoped>
.diff {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
pre {
  margin: 0;
  padding: var(--space-2);
  overflow-x: auto;
  font-size: 0.8rem;
}
.line {
  display: block;
}
.line.add {
  background: color-mix(in srgb, var(--status-done) 15%, transparent);
}
.line.remove {
  background: color-mix(in srgb, var(--status-urgent) 15%, transparent);
}
.line.meta {
  color: var(--color-text-muted);
}
.actions {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2);
  border-top: 1px solid var(--color-border);
}
button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
button.apply {
  background: var(--status-ai);
  color: white;
  border: none;
}
</style>
