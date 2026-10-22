import { useCallback, useEffect, useState } from 'react'
import { api, type DocumentOut, type Health } from './api'
import { ChatPanel } from './components/ChatPanel'
import { DocumentDetail } from './components/DocumentDetail'
import { ChatIcon, LayersIcon } from './components/icons'
import { Library } from './components/Library'
import { NavRail } from './components/NavRail'
import type { LibraryFilter } from './library'

export default function App() {
  const [docs, setDocs] = useState<DocumentOut[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [filter, setFilter] = useState<LibraryFilter>('all')
  const [detailId, setDetailId] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ msg: string; kind: 'error' | 'info' } | null>(null)
  const [navOpen, setNavOpen] = useState(false)
  const [mobileView, setMobileView] = useState<'library' | 'chat'>('chat')

  const refresh = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([api.listDocuments(), api.health()])
      setDocs(d)
      setHealth(h)
      setOffline(false)
      // drop selections for documents that are gone or no longer ready
      setSelected((s) => s.filter((id) => d.some((x) => x.id === id && x.status === 'ready')))
    } catch {
      setOffline(true)
    }
  }, [])

  // Poll quickly while something is processing, slowly otherwise
  const busy = docs.some((d) => d.status !== 'ready' && d.status !== 'failed')
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, busy ? 2500 : 15000)
    return () => clearInterval(t)
  }, [refresh, busy])

  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 6000)
    return () => clearTimeout(t)
  }, [notice])

  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const showNotice = (msg: string, kind: 'error' | 'info' = 'error') => setNotice({ msg, kind })

  return (
    <div className={`app ${navOpen ? 'nav-open' : ''} view-${mobileView}`}>
      <NavRail
        docs={docs}
        health={health}
        offline={offline}
        filter={filter}
        onFilter={(f) => {
          setFilter(f)
          setNavOpen(false)
          setMobileView('library')
        }}
        selected={selected}
        onToggle={toggle}
        onClearSelection={() => setSelected([])}
      />
      <div className="scrim" onClick={() => setNavOpen(false)} />

      <Library
        docs={docs}
        filter={filter}
        selected={selected}
        onToggle={toggle}
        onSelect={setSelected}
        onChanged={refresh}
        onOpen={setDetailId}
        onNotice={showNotice}
        onMenu={() => setNavOpen(true)}
      />

      <ChatPanel
        docs={docs}
        health={health}
        offline={offline}
        selected={selected}
        onClearSelection={() => setSelected([])}
        onNotice={showNotice}
      />

      <nav className="view-tabs" aria-label="Switch view">
        <button className={mobileView === 'library' ? 'active' : ''} onClick={() => setMobileView('library')}>
          <LayersIcon /> Documents
        </button>
        <button className={mobileView === 'chat' ? 'active' : ''} onClick={() => setMobileView('chat')}>
          <ChatIcon /> Assistant
        </button>
      </nav>

      {notice && <div className={`toast notice notice-${notice.kind}`}>{notice.msg}</div>}

      {detailId !== null && (
        <DocumentDetail id={detailId} onClose={() => setDetailId(null)} onChanged={refresh} />
      )}
    </div>
  )
}
