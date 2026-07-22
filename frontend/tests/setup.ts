// Global test setup for Vitest component/unit tests.
import { afterEach, vi } from 'vitest'

// jsdom does not implement EventSource; provide a controllable stub.
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  readyState = 0
  onopen: ((ev: Event) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  private listeners = new Map<string, Set<(ev: MessageEvent) => void>>()

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: (ev: MessageEvent) => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(cb)
  }

  removeEventListener(type: string, cb: (ev: MessageEvent) => void): void {
    this.listeners.get(type)?.delete(cb)
  }

  emit(type: string, data: unknown, lastEventId = ''): void {
    const ev = new MessageEvent(type, { data: JSON.stringify(data), lastEventId })
    this.listeners.get(type)?.forEach((cb) => cb(ev))
    if (type === 'message') this.onmessage?.(ev)
  }

  close(): void {
    this.readyState = 2
  }
}

;(globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource

if (!('matchMedia' in globalThis)) {
  ;(globalThis as unknown as { matchMedia: unknown }).matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })
}

afterEach(() => {
  MockEventSource.instances = []
})

export { MockEventSource }
