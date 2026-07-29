// Thin wrapper over the browser's real-time SpeechRecognition (Web Speech API).
// It exposes interim + final transcripts reactively so the UI can show words as
// they are spoken. Recognition runs entirely in the browser (like typing); the
// final text is then sent to the backend, which parses it via the LLM gateway.
import { ref } from 'vue'

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }>
}

function getRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function isSpeechSupported(): boolean {
  return getRecognitionCtor() !== null
}

export function useSpeechRecognition(lang = 'zh-CN') {
  const listening = ref(false)
  const interim = ref('')
  const finalText = ref('')
  const error = ref('')
  let recognition: SpeechRecognitionLike | null = null
  // `stopping` distinguishes a user-initiated stop from Chrome silently ending
  // the session after a pause. Without this, long Chinese sentences with natural
  // pauses get truncated because continuous mode dies mid-utterance.
  let stopping = false

  function build(Ctor: new () => SpeechRecognitionLike): SpeechRecognitionLike {
    const rec = new Ctor()
    rec.lang = lang
    rec.continuous = true
    rec.interimResults = true
    // A few candidates let the engine pick a better final for zh-CN homophones.
    rec.maxAlternatives = 3
    rec.onresult = (event) => {
      let interimBuf = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i]
        if (res.isFinal) finalText.value += res[0].transcript
        else interimBuf += res[0].transcript
      }
      interim.value = interimBuf
    }
    rec.onerror = (e) => {
      // `no-speech`/`aborted` are transient during pauses; onend will restart.
      if (e.error === 'no-speech' || e.error === 'aborted') return
      error.value = e.error === 'not-allowed' ? '麦克风权限被拒绝。' : '识别出错，请重试。'
      stopping = true
      listening.value = false
    }
    rec.onend = () => {
      // Auto-restart unless the user asked to stop, so pauses don't end the session.
      if (stopping) {
        listening.value = false
        return
      }
      // Fold any trailing interim into final so nothing is lost across restarts.
      if (interim.value) {
        finalText.value += interim.value
        interim.value = ''
      }
      try {
        rec.start()
      } catch {
        listening.value = false
      }
    }
    return rec
  }

  function start(): void {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      error.value = '当前浏览器不支持实时语音识别。'
      return
    }
    error.value = ''
    interim.value = ''
    finalText.value = ''
    stopping = false
    recognition = build(Ctor)
    recognition.start()
    listening.value = true
  }

  function stop(): void {
    stopping = true
    recognition?.stop()
    listening.value = false
  }

  return { listening, interim, finalText, error, start, stop }
}
