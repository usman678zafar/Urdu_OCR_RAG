import type { ReactNode } from 'react'
import type { DocumentOut, Health } from '../api'
import { displayName, FILTERS, type LibraryFilter } from '../library'
import {
  AlertIcon,
  CheckCircleIcon,
  GeminiMark,
  LayersIcon,
  LoaderIcon,
  Logo,
  PagesIcon,
  ScanIcon,
  SparkIcon,
  TesseractMark,
} from './icons'

const FILTER_ICON: Record<LibraryFilter, ReactNode> = {
  all: <LayersIcon />,
  ready: <CheckCircleIcon />,
  processing: <LoaderIcon />,
  attention: <AlertIcon />,
}

interface Props {
  docs: DocumentOut[]
  health: Health | null
  offline: boolean
  filter: LibraryFilter
  onFilter: (f: LibraryFilter) => void
  selected: number[]
  onToggle: (id: number) => void
  onClearSelection: () => void
}

export function NavRail({ docs, health, offline, filter, onFilter, selected, onToggle, onClearSelection }: Props) {
  const scoped = docs.filter((d) => selected.includes(d.id))
  const pages = docs.filter((d) => d.status === 'ready').reduce((n, d) => n + d.page_count, 0)

  return (
    <aside className="nav pane">
      <div className="brand">
        <Logo size={36} />
        <span className="brand-name">Harf</span>
      </div>

      <div className="nav-section">
        <div className="nav-heading">Library</div>
        {FILTERS.map((f) => {
          const n = docs.filter(f.match).length
          if (f.key !== 'all' && f.key !== 'ready' && n === 0) return null
          return (
            <button
              key={f.key}
              className={`nav-item ${filter === f.key ? 'active' : ''} ${f.key === 'attention' ? 'nav-warn' : ''}`}
              onClick={() => onFilter(f.key)}
            >
              {FILTER_ICON[f.key]}
              <span>{f.label}</span>
              <span className="nav-count">{n}</span>
            </button>
          )
        })}
      </div>

      <div className="nav-section">
        <div className="nav-heading">
          Search scope
          {scoped.length > 0 && (
            <button className="link" onClick={onClearSelection}>
              Reset
            </button>
          )}
        </div>
        {scoped.length === 0 ? (
          <div className="scope-all">
            <span className="scope-dot" aria-hidden />
            All ready documents
          </div>
        ) : (
          <ul className="scope-list">
            {scoped.map((d) => (
              <li key={d.id} title={d.filename}>
                <span className="scope-dot" aria-hidden />
                <span className="scope-name">{displayName(d.filename)}</span>
                <button className="icon-btn" onClick={() => onToggle(d.id)} aria-label={`Remove ${d.filename}`}>
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="nav-hint">Tick documents in the list to narrow what questions search.</div>
      </div>

      <div className="nav-foot">
        <div className="nav-heading">System</div>
        {offline && (
          <div className="sys-row sys-bad">
            <span className="sys-dot" aria-hidden />
            Backend offline
          </div>
        )}
        {health && !offline && (
          <ul className="sys-list">
            <li title="Model that writes the answers">
              <span className="sys-icon sys-logo">
                {health.llm_model.toLowerCase().includes('gemini') ? <GeminiMark /> : <SparkIcon />}
              </span>
              <span className="sys-text">
                <span className="sys-label">Model</span>
                <span className="sys-value">{health.llm_model}</span>
              </span>
            </li>
            <li title="Engine that reads scanned pages">
              <span className="sys-icon sys-logo">
                {health.ocr_engine === 'tesseract' ? (
                  <TesseractMark />
                ) : health.ocr_engine === 'gemini' ? (
                  <GeminiMark />
                ) : (
                  <ScanIcon />
                )}
              </span>
              <span className="sys-text">
                <span className="sys-label">OCR</span>
                <span className="sys-value">{health.ocr_engine}</span>
              </span>
            </li>
            <li title="Pages searchable right now">
              <span className="sys-icon">
                <PagesIcon />
              </span>
              <span className="sys-text">
                <span className="sys-label">Indexed</span>
                <span className="sys-value">{pages.toLocaleString()} pages</span>
              </span>
            </li>
          </ul>
        )}
      </div>
    </aside>
  )
}
