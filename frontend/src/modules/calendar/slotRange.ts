// Compute a padded visible hour range so empty early/late hours collapse and the
// day's events show without wasted whitespace. Falls back to a sensible daytime
// window when there are no timed events.

export interface SlotRange {
  min: string // 'HH:00:00'
  max: string // 'HH:00:00'
}

const DEFAULT_MIN_HOUR = 7
const DEFAULT_MAX_HOUR = 22
const PAD_HOURS = 1

function hourOf(iso: string | null | undefined): number | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.getHours()
}

export function computeSlotRange(
  events: Array<{ start_at?: string | null; due_at?: string | null }>,
): SlotRange {
  let minHour = Number.POSITIVE_INFINITY
  let maxHour = Number.NEGATIVE_INFINITY

  for (const e of events) {
    const start = hourOf(e.start_at)
    if (start !== null) {
      minHour = Math.min(minHour, start)
      maxHour = Math.max(maxHour, start + 1)
    }
    const end = hourOf(e.due_at)
    if (end !== null) {
      // Round the end hour up so a 09:30 end still shows the 10:00 line.
      const endHour = new Date(e.due_at as string).getMinutes() > 0 ? end + 1 : end
      maxHour = Math.max(maxHour, endHour)
    }
  }

  if (!Number.isFinite(minHour) || !Number.isFinite(maxHour)) {
    return { min: pad(DEFAULT_MIN_HOUR), max: pad(DEFAULT_MAX_HOUR) }
  }

  const min = Math.max(0, Math.floor(minHour) - PAD_HOURS)
  const max = Math.min(24, Math.ceil(maxHour) + PAD_HOURS)
  return { min: pad(min), max: pad(max === 24 ? 24 : max) }
}

function pad(hour: number): string {
  if (hour >= 24) return '24:00:00'
  return `${String(hour).padStart(2, '0')}:00:00`
}
