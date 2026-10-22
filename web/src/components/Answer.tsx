import { useState } from 'react'
import { imageSrc, type AskOut, type CitationOut } from '../api'
import { formatDuration, STAGES } from '../stages'
import { BidiText, Modal } from './common'
import { BoltIcon, ClockIcon } from './icons'

/** A quiet footer: total time and the slowest stage; "Details" opens a per-stage list. */
function ResponseTime({ res }: { res: AskOut }) {
  const [open, setOpen] = useState(false)
  const total = res.timings?.total ?? res.latency_ms

  if (res.cached || !res.timings || total <= 0) {
    return (
      <div className="timing">
        <div className="timing-row">
          {res.cached ? <BoltIcon width={14} height={14} /> : <ClockIcon width={14} height={14} />}
          <span>{res.cached ? 'Instant · from cache' : formatDuration(total)}</span>
        </div>
      </div>
    )
  }

  // stages run one after another, so each starts where the previous one ended
  let offset = 0
  const stages = STAGES.map((s) => {
    const ms = s.steps.reduce((sum, step) => sum + (res.timings?.[step] ?? 0), 0)
    const start = offset
    offset += ms
    const parts = s.steps
      .filter((step) => res.timings?.[step] !== undefined)
      .map((step) => `${step.replace('_', ' ')} ${formatDuration(res.timings![step])}`)
    return { ...s, ms, start, ran: parts.length > 0, parts }
  })
  const slowest = stages.reduce((a, b) => (b.ms > a.ms ? b : a))
  const pct = (ms: number) => (ms / total) * 100
  const share = (ms: number) => (pct(ms) < 1 ? '<1%' : `${Math.round(pct(ms))}%`)
  const tick = [0.5, 1, 2, 5, 10, 20, 30, 60, 120].find((t) => total / 1000 / t <= 4) ?? 300
  const ticks = Array.from({ length: Math.floor(total / 1000 / tick) + 1 }, (_, i) => i * tick)

  return (
    <div className="timing">
      <div className="timing-row">
        <ClockIcon width={14} height={14} />
        <span className="timing-total">{formatDuration(total)}</span>
        {slowest.ms / total >= 0.5 && <span>· mostly {slowest.short.toLowerCase()}</span>}
        <button className="timing-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? 'Hide details' : 'Details'}
          <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden className={open ? 'flip' : ''}>
            <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {open && (
        <div className="waterfall">
          <ul className="wf-list">
            {stages.map((s) => (
              <li
                key={s.key}
                className={`wf-row ${s.ran ? '' : 'skipped'} ${s === slowest ? 'slowest' : ''}`}
                title={s.ran ? `${s.label}\n${s.parts.join('\n')}` : `${s.label}: did not run`}
              >
                <span className="wf-name">{s.short}</span>
                <span className="wf-track" aria-hidden>
                  {ticks.map((t) => (
                    <i key={t} style={{ left: `${pct(t * 1000)}%` }} />
                  ))}
                  {s.ran && (
                    <span className="wf-bar" style={{ left: `${pct(s.start)}%`, width: `max(${pct(s.ms)}%, 3px)` }} />
                  )}
                </span>
                <span className="wf-ms">{s.ran ? formatDuration(s.ms) : 'skipped'}</span>
                <span className="wf-pct">{s.ran ? share(s.ms) : ''}</span>
              </li>
            ))}
            <li className="wf-axis" aria-hidden>
              <span />
              <span className="wf-track">
                {ticks.map((t) => (
                  <b key={t} style={{ left: `${pct(t * 1000)}%` }}>
                    {t}s
                  </b>
                ))}
              </span>
            </li>
          </ul>
          {slowest.key === 'rank' && pct(slowest.ms) >= 50 && (
            <p className="wf-note">
              Ranking reads each candidate passage closely against your question. It runs on the CPU, so it is the
              slowest step; fewer candidates (<code>CANDIDATE_K</code>) make it faster.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Citation({ c, n }: { c: CitationOut; n: number }) {
  const [open, setOpen] = useState(false)
  const [zoom, setZoom] = useState(false)
  return (
    <div className="citation">
      <button className="citation-thumb" onClick={() => setZoom(true)} title="View page">
        <img src={imageSrc(c.image_url)} alt={`${c.filename} page ${c.page_no}`} loading="lazy" />
      </button>
      <div className="citation-body">
        <div className="citation-head">
          <span className="cite-n">{n}</span>
          <span className="cite-file" title={c.filename}>
            {c.filename}
          </span>
          <span className="cite-page">p. {c.page_no}</span>
          {!c.quote_verified && (
            <span className="warn" title="This quote was not found word-for-word in the passage">
              ⚠ unverified
            </span>
          )}
        </div>
        {c.quote && <BidiText text={c.quote} className="quote" />}
        <button className="link" onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide passage' : 'Show full passage'}
        </button>
        {open && <BidiText text={c.passage} className="passage" />}
      </div>
      {zoom && (
        <Modal onClose={() => setZoom(false)} wide>
          <div className="zoom-head">
            {c.filename} · page {c.page_no}
          </div>
          <img className="zoom-img" src={imageSrc(c.image_url)} alt="" />
        </Modal>
      )}
    </div>
  )
}

export function Answer({ res }: { res: AskOut }) {
  return (
    <div className={`answer-card ${res.found ? '' : 'not-found'}`}>
      <BidiText text={res.answer} className="answer-text" />
      {res.found && !res.grounded && (
        <div className="answer-meta">
          <span className="warn">Some quotes could not be matched to their source — check the pages.</span>
        </div>
      )}
      {res.note && <div className="notice notice-info">{res.note}</div>}
      {res.citations.length > 0 && (
        <div className="citations">
          <div className="citations-title">Sources</div>
          {res.citations.map((c, i) => (
            <Citation key={i} c={c} n={i + 1} />
          ))}
        </div>
      )}
      <ResponseTime res={res} />
    </div>
  )
}
