// Answering stages shown while a question runs and in each answer's time breakdown.
import type { AskStep } from './api'

/** User-facing stages; each groups one or more backend steps. */
export const STAGES: { key: string; label: string; short: string; ur: string; steps: AskStep[] }[] = [
  {
    key: 'understand',
    label: 'Understanding your question',
    short: 'Understanding',
    ur: 'سوال سمجھا جا رہا ہے',
    steps: ['embed_query'],
  },
  {
    key: 'search',
    label: 'Searching your documents',
    short: 'Searching',
    ur: 'دستاویزات میں تلاش',
    steps: ['vector_search', 'bm25', 'fetch_chunks'],
  },
  { key: 'rank', label: 'Ranking the best passages', short: 'Ranking', ur: 'بہترین حصوں کا انتخاب', steps: ['rerank'] },
  { key: 'write', label: 'Writing the answer', short: 'Writing', ur: 'جواب لکھا جا رہا ہے', steps: ['llm'] },
]

export interface AskProgress {
  startedAt: number // performance.now() when the question was sent
  steps: { step: AskStep; at: number }[]
  candidates?: number
  sources?: { filename: string; page_no: number }[]
}

/** 0.4s, 12.3s, 1m 05s */
export function formatDuration(ms: number): string {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const s = Math.round(ms / 1000)
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}
