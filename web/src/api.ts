// Typed client for the FastAPI backend (see app/api/schemas.py). All calls go through
// the /api prefix, which the Vite dev server proxies to the backend.

const BASE = '/api'

export type DocStatus = 'uploaded' | 'extracting' | 'indexing' | 'ready' | 'failed'

export interface DocumentOut {
  id: number
  filename: string
  sha256: string
  page_count: number
  pages_done: number
  pages_failed: number
  status: DocStatus
  error: string | null
  uploaded_at: string
  updated_at: string
}

export interface PageOut {
  page_no: number
  method: string
  reason: string | null
  ocr_confidence: number | null
  ocr_status: 'ok' | 'low_quality' | 'failed'
  quality: number | null
  error: string | null
  low_confidence: boolean
  text_chars: number
  image_url: string
}

export interface DocumentDetailOut extends DocumentOut {
  pages: PageOut[]
}

export interface CitationOut {
  document_id: number
  filename: string
  page_no: number
  quote: string
  passage: string
  quote_verified: boolean
  image_url: string
}

export interface AskOut {
  answer: string
  language: string
  found: boolean
  grounded: boolean
  citations: CitationOut[]
  latency_ms: number
  cached: boolean
  note: string | null
  timings: Record<string, number> | null
}

export interface Health {
  status: string
  documents: number
  ready: number
  embedding_model: string
  llm_model: string
  ocr_engine: string
}

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: BodyInit, json = false): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method,
      body,
      headers: json ? { 'Content-Type': 'application/json' } : undefined,
    })
  } catch {
    throw new ApiError('Cannot reach the backend. Is it running on port 8000?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* not JSON */
    }
    throw new ApiError(`${res.status}: ${detail}`)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  health: () => request<Health>('GET', '/health'),
  listDocuments: () => request<DocumentOut[]>('GET', '/documents'),
  getDocument: (id: number) => request<DocumentDetailOut>('GET', `/documents/${id}`),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ document: DocumentOut; duplicate: boolean }>('POST', '/documents', form)
  },
  reprocess: (id: number, full = false) =>
    request<DocumentOut>('POST', `/documents/${id}/reprocess${full ? '?full=true' : ''}`),
  remove: (id: number) => request<void>('DELETE', `/documents/${id}`),
  ask: (question: string, documentIds: number[] | null) =>
    request<AskOut>('POST', '/ask', JSON.stringify({ question, document_ids: documentIds }), true),
}

/** Backend returns paths like /documents/1/pages/2/image; route them through the proxy. */
export const imageSrc = (path: string) => BASE + path
