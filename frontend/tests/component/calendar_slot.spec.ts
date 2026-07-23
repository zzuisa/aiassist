import { describe, expect, it } from 'vitest'
import { computeSlotRange } from '@/modules/calendar/slotRange'

describe('computeSlotRange (collapse empty hours)', () => {
  it('falls back to a daytime window when there are no timed events', () => {
    expect(computeSlotRange([])).toEqual({ min: '07:00:00', max: '22:00:00' })
  })

  it('collapses to a padded range around the events', () => {
    const range = computeSlotRange([
      { start_at: '2026-07-24T10:00:00', due_at: '2026-07-24T11:00:00' },
      { start_at: '2026-07-24T14:00:00', due_at: '2026-07-24T15:00:00' },
    ])
    // 1h padding: min 09:00, max 16:00 — empty early/late hours are hidden.
    expect(range.min).toBe('09:00:00')
    expect(range.max).toBe('16:00:00')
  })

  it('rounds a non-hour end time up so its line is visible', () => {
    const range = computeSlotRange([
      { start_at: '2026-07-24T09:00:00', due_at: '2026-07-24T09:30:00' },
    ])
    // end 09:30 rounds to 10:00, then +1h padding = 11:00.
    expect(range.max).toBe('11:00:00')
  })

  it('never produces a range outside 00:00–24:00', () => {
    const range = computeSlotRange([
      { start_at: '2026-07-24T00:00:00', due_at: '2026-07-24T23:30:00' },
    ])
    expect(range.min).toBe('00:00:00')
    expect(range.max).toBe('24:00:00')
  })
})
