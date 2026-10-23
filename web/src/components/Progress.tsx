import { useEffect, useState } from 'react'
import { formatDuration, STAGES, type AskProgress } from '../stages'

function useNow(intervalMs = 100) {
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    const t = setInterval(() => setNow(performance.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}

type StageState = { status: 'pending' | 'active' | 'done' | 'skipped'; start?: number; end?: number }

function stageStates(p: AskProgress): StageState[] {
  const starts = STAGES.map((s) => {
    const times = p.steps.filter((x) => s.steps.includes(x.step)).map((x) => x.at)
    return times.length ? Math.min(...times) : undefined
  })
  const lastStarted = starts.reduce<number>((acc, t, i) => (t !== undefined ? i : acc), -1)
  return STAGES.map((_, i) => {
    const start = starts[i]
    if (i > lastStarted) {
      // before the first event arrives, show the first stage as running
      return lastStarted === -1 && i === 0 ? { status: 'active', start: p.startedAt } : { status: 'pending' }
    }
    if (start === undefined) return { status: 'skipped' } // e.g. reranker turned off
    const next = starts.slice(i + 1).find((t) => t !== undefined)
    return next === undefined ? { status: 'active', start } : { status: 'done', start, end: next }
  })
}

const HINTS: Record<string, (p: AskProgress) => string> = {
  understand: () => 'Turning your question into a search vector…',
  search: () => 'Matching by meaning and by exact words…',
  rank: (p) =>
    p.candidates ? `Reading ${p.candidates} candidate passages closely…` : 'Reading candidate passages closely…',
  write: (p) =>
    p.sources?.length
      ? `Composing an answer from ${p.sources.length} passage${p.sources.length > 1 ? 's' : ''}, with citations…`
      : 'Composing an answer with citations…',
}

export function AskProgressCard({ progress, onStop }: { progress: AskProgress; onStop: () => void }) {
  const now = useNow()
  const states = stageStates(progress)
  const visible = STAGES.map((s, i) => ({ ...s, ...states[i] })).filter((s) => s.status !== 'skipped')
  const activeIdx = visible.findIndex((s) => s.status === 'active')
  const active = visible[activeIdx]
  const elapsed = now - progress.startedAt

  // within a stage the bar eases toward the next one but never reaches it
  const inStage = active?.start !== undefined ? (now - active.start) / 1000 : 0
  const fraction = 1 - Math.exp(-inStage / 6)
  const percent = Math.min(97, ((Math.max(activeIdx, 0) + 0.9 * fraction) / visible.length) * 100)

  return (
    <div className="ask-progress" role="status" aria-live="polite">
      <div className="ask-bar">
        <div className="ask-fill" style={{ width: `${percent}%` }} />
      </div>

      <div className="ask-head">
        <span className="pulse" aria-hidden />
        <div className="ask-title">
          <div>{active?.label ?? 'Working…'}</div>
          {active && (
            <div className="ask-title-ur" dir="rtl">
              {active.ur}
            </div>
          )}
        </div>
        <span className="ask-timer" title="Time since you asked">
          {formatDuration(elapsed)}
        </span>
        <button type="button" className="btn btn-ghost ask-stop" onClick={onStop}>
          Stop
        </button>
      </div>

      <ol className="stages">
        {visible.map((s) => (
          <li key={s.key} className={`stage stage-${s.status}`}>
            <span className="stage-icon" aria-hidden>
              {s.status === 'done' ? '✓' : ''}
            </span>
            <span className="stage-label">{s.label}</span>
            <span className="stage-time">
              {s.status === 'done' && s.start !== undefined && s.end !== undefined && formatDuration(s.end - s.start)}
              {s.status === 'active' && s.start !== undefined && formatDuration(Math.max(0, now - s.start))}
            </span>
            {s.status === 'active' && <div className="stage-hint">{HINTS[s.key]?.(progress)}</div>}
          </li>
        ))}
      </ol>

      {progress.sources && progress.sources.length > 0 && (
        <div className="found-pages">
          <span className="found-label">Found in</span>
          {progress.sources.map((s, i) => (
            <span
              key={`${s.filename}-${s.page_no}`}
              className="found-chip"
              style={{ animationDelay: `${i * 70}ms` }}
              title={s.filename}
            >
              p. {s.page_no}
            </span>
          ))}
        </div>
      )}

      {active?.key === 'write' && (
        <div className="skeleton" dir="rtl" aria-hidden>
          <span style={{ width: '92%' }} />
          <span style={{ width: '78%' }} />
          <span style={{ width: '85%' }} />
          <span style={{ width: '40%' }} />
        </div>
      )}
    </div>
  )
}
