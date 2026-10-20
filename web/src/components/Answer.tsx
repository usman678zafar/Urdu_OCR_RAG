import { useState } from 'react'
import { imageSrc, type AskOut, type CitationOut } from '../api'
import { BidiText, Modal } from './common'

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
      <div className="answer-meta">
        <span>{(res.latency_ms / 1000).toFixed(1)}s</span>
        {res.cached && <span className="chip">cached</span>}
        {res.found && !res.grounded && (
          <span className="warn">Some quotes could not be matched to their source — check the pages.</span>
        )}
      </div>
      {res.note && <div className="notice notice-info">{res.note}</div>}
      {res.citations.length > 0 && (
        <div className="citations">
          <div className="citations-title">Sources</div>
          {res.citations.map((c, i) => (
            <Citation key={i} c={c} n={i + 1} />
          ))}
        </div>
      )}
    </div>
  )
}
