export type EditorMode = 'source' | 'rich' | 'split' | 'preview'
export type PersistedEditorMode = 'markdown' | 'rich' | 'split'

/** Translate the API's historical `markdown` name to the source editor UI. */
export function editorModeFromApi(mode: string | null | undefined): EditorMode {
  if (mode === 'rich' || mode === 'split') return mode
  return 'source'
}

/** Preview is transient; every editable mode has an explicit API value. */
export function editorModeToApi(mode: Exclude<EditorMode, 'preview'>): PersistedEditorMode {
  return mode === 'source' ? 'markdown' : mode
}
