export interface Client {
  id: string
  name: string
  industry: string | null
  region: string | null
  created_at: string
}

export interface ClientCreate {
  name: string
  industry?: string
  region?: string
}

export interface DocumentRecord {
  id: string
  client_id: string
  filename: string
  mime_type: string
  size_bytes: number
  page_count: number
  status: string
  section_index: string[]
  created_at: string
}

export interface DocumentChunk {
  id: string
  document_id: string
  chunk_index: number
  page_number: number
  section: string | null
  content: string
  token_count: number
}

export interface Citation {
  chunk_id: string
  document_id: string
  filename: string
  page_number: number
  section: string | null
  snippet: string
  score: number
}

export interface AgentStep {
  agent: string
  step: string
  status: 'running' | 'completed' | 'failed'
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  input: unknown
  output: unknown
  decision: string | null
  detail: string | null
}

export interface QueryResponse {
  trace_id: string
  client_id: string
  query: string
  answer: string
  citations: Citation[]
  steps: AgentStep[]
  status: string
  created_at: string
  completed_at: string | null
}

export interface TraceRecord {
  id: string
  client_id: string
  query: string
  answer: string | null
  citations: Citation[]
  steps: AgentStep[]
  status: string
  created_at: string
  completed_at: string | null
}

export interface QueryRequest {
  client_id: string
  query: string
  document_ids?: string[]
}
