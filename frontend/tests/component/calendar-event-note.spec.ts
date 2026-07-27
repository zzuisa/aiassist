import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CalendarEventNoteEditor from '@/modules/calendar/CalendarEventNoteEditor.vue'
import * as noteApi from '@/api/taskNotes'

function stubNote(assets: noteApi.NoteAsset[] = []) {
  vi.spyOn(noteApi.taskNotesApi, 'get').mockResolvedValue({
    content: '旧备注',
    version: 2,
    assets,
  })
}

describe('CalendarEventNoteEditor (US2)', () => {
  it('loads and shows the existing note text', async () => {
    stubNote()
    const w = mount(CalendarEventNoteEditor, { props: { taskId: 't1', title: '开会' } })
    await flushPromises()
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('旧备注')
  })

  it('saves note text with the current version', async () => {
    stubNote()
    const save = vi
      .spyOn(noteApi.taskNotesApi, 'save')
      .mockResolvedValue({ content: 'x', version: 3, assets: [] })
    const w = mount(CalendarEventNoteEditor, { props: { taskId: 't1', title: '开会' } })
    await flushPromises()
    await w.get('textarea').setValue('买灯泡')
    await w.get('button.primary').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('t1', '买灯泡', 2)
    expect(w.emitted('saved')).toBeTruthy()
  })
})
