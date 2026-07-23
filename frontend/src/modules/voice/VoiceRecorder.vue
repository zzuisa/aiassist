<script setup lang="ts">
import { ref } from 'vue'
import { getCsrfToken } from '@/api/client'
import { voiceApi, uploadAudioBytes, type VoiceRecord } from '@/api/voice'

const emit = defineEmits<{ (e: 'created', record: VoiceRecord): void }>()

type Phase = 'idle' | 'recording' | 'uploading' | 'error'
const phase = ref<Phase>('idle')
const errorMsg = ref('')

let mediaRecorder: MediaRecorder | null = null
let chunks: BlobPart[] = []

async function start(): Promise<void> {
  errorMsg.value = ''
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data)
    mediaRecorder.onstop = () => void finalize(stream)
    mediaRecorder.start()
    phase.value = 'recording'
  } catch {
    phase.value = 'error'
    errorMsg.value = '无法访问麦克风，请检查权限。'
  }
}

function stop(): void {
  mediaRecorder?.stop()
}

async function finalize(stream: MediaStream): Promise<void> {
  phase.value = 'uploading'
  stream.getTracks().forEach((t) => t.stop())
  try {
    const blob = new Blob(chunks, { type: 'audio/webm' })
    const session = await voiceApi.createUpload('recording.webm', 'audio/webm', blob.size)
    await uploadAudioBytes(session.id, blob, getCsrfToken())
    await voiceApi.completeUpload(session.id)
    const record = await voiceApi.create(session.id)
    emit('created', record) // record is durable even if processing later fails
    phase.value = 'idle'
  } catch {
    phase.value = 'error'
    errorMsg.value = '上传失败，请重试。'
  }
}
</script>

<template>
  <div class="recorder">
    <button
      v-if="phase === 'idle' || phase === 'error'"
      type="button"
      class="record"
      @click="start"
    >
      🎙️ 开始录音
    </button>
    <button
      v-else-if="phase === 'recording'"
      type="button"
      class="stop"
      @click="stop"
    >
      ⏹ 停止
    </button>
    <span
      v-else
      class="status"
    >上传中…</span>
    <p
      v-if="errorMsg"
      class="error"
      role="alert"
    >
      {{ errorMsg }}
    </p>
  </div>
</template>

<style scoped>
.recorder {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
}
button {
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: white;
}
.record {
  background: var(--status-normal);
}
.stop {
  background: var(--status-urgent);
}
.error {
  color: var(--status-urgent);
}
</style>
