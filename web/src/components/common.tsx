import { useEffect, type ReactNode } from 'react'
import type { DocStatus } from '../api'

/** One paragraph per line with dir="auto", so Urdu and English lines each lay out correctly. */
export function BidiText({ text, className = '' }: { text: string; className?: string }) {
  const paras = text.split('\n').filter((p) => p.trim())
  return (
    <div className={`bidi ${className}`}>
      {(paras.length ? paras : ['']).map((p, i) => (
        <p key={i} dir="auto">
          {p}
        </p>
      ))}
    </div>
  )
}

const STATUS_LABEL: Record<DocStatus, string> = {
  uploaded: 'Queued',
  extracting: 'Reading pages',
  indexing: 'Indexing',
  ready: 'Ready',
  failed: 'Failed',
}

export function StatusBadge({ status }: { status: DocStatus }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status] ?? status}</span>
}

export function Modal({ onClose, children, wide }: { onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`} onClick={(e) => e.stopPropagation()} role="dialog">
        <button className="icon-btn modal-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
        {children}
      </div>
    </div>
  )
}

export function Spinner() {
  return <span className="spinner" aria-hidden />
}
