<script setup lang="ts">
import { ref } from 'vue'
import { voiceApi, type VoiceRecord } from '@/api/voice'
import { isSpeechSupported, useSpeechRecognition } from '@/modules/voice/useSpeechRecognition'
import VoiceRecorder from '@/modules/voice/VoiceRecorder.vue'

const emit = defineEmits<{ (e: 'candidate', record: VoiceRecord): void }>()

const supported = isSpeechSupported()
const { listening, interim, finalText, error, start, stop } = useSpeechRecognition()
const parsing = ref(false)
const parseError = ref('')

async function stopAndParse(): Promise<void> {
  stop()
  const text = (finalText.value + interim.value).trim()
  if (!text) return
  parsing.value = true
  parseError.value = ''
  try {
    // The browser already recognized the speech in real time; the backend parses
    // the text into a structured candidate via the LLM gateway.
    const record = await voiceApi.fromText(text)
    emit('candidate', record)
  } catch {
    parseError.value = '解析失败，请重试或改用录音。'
  } finally {
    parsing.value = false
  }
}
</script>

<template>
  <div class="live-voice">
    <template v-if="supported">
      <button
        v-if="!listening"
        type="button"
        class="mic tappable"
        :disabled="parsing"
        @click="start"
      >
        🎤 {{ parsing ? '解析中…' : '实时语音' }}
      </button>
      <button
        v-else
        type="button"
        class="mic listening tappable"
        @click="stopAndParse"
      >
        ⏹ 停止并识别
      </button>

      <p
        v-if="listening || finalText"
        class="transcript"
        aria-live="polite"
      >
        <span class="final">{{ finalText }}</span>
        <span class="interim">{{ interim }}</span>
        <span
          v-if="listening"
          class="pulse"
          aria-hidden="true"
        />
      </p>

      <p
        v-if="error"
        class="err"
        role="alert"
      >
        {{ error }}
      </p>
      <p
        v-if="parseError"
        class="err"
        role="alert"
      >
        {{ parseError }}
      </p>
    </template>

    <!-- Fallback for browsers without real-time recognition. -->
    <VoiceRecorder
      v-else
      @created="(r) => emit('candidate', r)"
    />
  </div>
</template>

<style scoped>
.live-voice {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
}
.mic {
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
.mic.listening {
  background: var(--status-urgent);
}
.transcript {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  min-width: 200px;
}
.final {
  color: var(--color-text);
}
.interim {
  color: var(--color-text-muted);
}
.pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-left: 6px;
  border-radius: 50%;
  background: var(--status-urgent);
  animation: blink 1s ease-in-out infinite;
}
@keyframes blink {
  50% {
    opacity: 0.2;
  }
}
.err {
  color: var(--status-urgent);
  font-size: 0.85rem;
}
@media (prefers-reduced-motion: reduce) {
  .pulse {
    animation: none;
  }
}
</style>
