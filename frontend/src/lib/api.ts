import type {
  Client,
  ClientCreate,
  DocumentChunk,
  DocumentRecord,
  QueryRequest,
  QueryResponse,
  TraceRecord,
} from '../types'

const API_BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        // FastAPI 422 validation errors: [{msg, loc, ...}, ...]
        detail = body.detail
          .map((e: { msg?: string; loc?: unknown[] }) => e?.msg || 'invalid value')
          .join('; ')
      } else if (body.message) {
        detail = body.message
      }
    } catch {
      // ignore json parse errors
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

// --- Clients ---

export async function listClients(): Promise<Client[]> {
  return request<Client[]>('/clients')
}

export async function createClient(payload: ClientCreate): Promise<Client> {
  return request<Client>('/clients', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// --- Documents ---

export async function listDocuments(clientId: string): Promise<DocumentRecord[]> {
  return request<DocumentRecord[]>(`/documents?client_id=${encodeURIComponent(clientId)}`)
}

export async function uploadDocument(clientId: string, file: File): Promise<DocumentRecord> {
  const form = new FormData()
  form.append('client_id', clientId)
  form.append('file', file)
  const response = await fetch(`${API_BASE}/documents`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return response.json()
}

export async function deleteDocument(documentId: string): Promise<void> {
  await request<{ status: string }>(`/documents/${documentId}`, { method: 'DELETE' })
}

export async function listChunks(documentId: string): Promise<DocumentChunk[]> {
  return request<DocumentChunk[]>(`/documents/${documentId}/chunks`)
}

// --- Query / CRAG ---

export async function runQuery(payload: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function listTraces(clientId: string, limit = 50): Promise<TraceRecord[]> {
  return request<TraceRecord[]>(`/query/traces/${clientId}?limit=${limit}`)
}

export async function getTrace(traceId: string): Promise<TraceRecord> {
  return request<TraceRecord>(`/query/trace/${traceId}`)
}
