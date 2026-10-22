// Library filters shared by the navigation and the document table.
import type { DocumentOut } from './api'

export type LibraryFilter = 'all' | 'ready' | 'processing' | 'attention'

export const FILTERS: { key: LibraryFilter; label: string; match: (d: DocumentOut) => boolean }[] = [
  { key: 'all', label: 'All documents', match: () => true },
  { key: 'ready', label: 'Ready', match: (d) => d.status === 'ready' },
  { key: 'processing', label: 'Processing', match: (d) => d.status !== 'ready' && d.status !== 'failed' },
  { key: 'attention', label: 'Needs attention', match: (d) => d.status === 'failed' || !!d.error },
]

/** "Roshan_Tameerat_Handbook.pdf" -> "Roshan Tameerat Handbook" */
export const displayName = (filename: string) => filename.replace(/\.pdf$/i, '').replace(/_+/g, ' ')
