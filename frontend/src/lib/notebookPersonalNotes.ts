export type NotebookPersonalNotesSource = 'manual' | 'capture' | 'migration';

export type NotebookPersonalNotesState = {
  markdown: string;
  updatedAt: string | null;
  wordCount: number;
  captureCount: number;
  manualSaveCount: number;
  lastUpdatedSource: NotebookPersonalNotesSource | null;
  version: number;
};

const PERSONAL_NOTES_KEY = 'personal_notes';

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function countWords(markdown: string) {
  return markdown.trim() ? markdown.trim().split(/\s+/).length : 0;
}

export function readNotebookPersonalNotes(settings: Record<string, unknown> | null | undefined): NotebookPersonalNotesState {
  const record = asRecord(settings);
  const noteValue = record?.[PERSONAL_NOTES_KEY];

  if (typeof noteValue === 'string') {
    return {
      markdown: noteValue,
      updatedAt: null,
      wordCount: countWords(noteValue),
      captureCount: 0,
      manualSaveCount: noteValue.trim() ? 1 : 0,
      lastUpdatedSource: null,
      version: 1,
    };
  }

  const noteRecord = asRecord(noteValue);
  const markdown = asString(noteRecord?.markdown) || '';
  const updatedAt = asString(noteRecord?.updated_at);
  const captureCount = asNumber(noteRecord?.capture_count) ?? 0;
  const manualSaveCount = asNumber(noteRecord?.manual_save_count) ?? 0;
  const version = asNumber(noteRecord?.version) ?? 1;
  const lastUpdatedSource = noteRecord?.last_updated_source;

  return {
    markdown,
    updatedAt,
    wordCount: asNumber(noteRecord?.word_count) ?? countWords(markdown),
    captureCount,
    manualSaveCount,
    lastUpdatedSource:
      lastUpdatedSource === 'manual' || lastUpdatedSource === 'capture' || lastUpdatedSource === 'migration'
        ? lastUpdatedSource
        : null,
    version,
  };
}

export function buildNotebookSettingsWithPersonalNotes(
  settings: Record<string, unknown> | null | undefined,
  markdown: string,
  source: NotebookPersonalNotesSource,
): Record<string, unknown> {
  const nextSettings = { ...(settings || {}) };
  const existing = readNotebookPersonalNotes(settings);
  const normalizedMarkdown = markdown.trimEnd();

  nextSettings[PERSONAL_NOTES_KEY] = {
    markdown: normalizedMarkdown,
    updated_at: new Date().toISOString(),
    word_count: countWords(normalizedMarkdown),
    capture_count: existing.captureCount + (source === 'capture' ? 1 : 0),
    manual_save_count: existing.manualSaveCount + (source === 'manual' ? 1 : 0),
    last_updated_source: source,
    version: Math.max(1, existing.version),
  };

  return nextSettings;
}
