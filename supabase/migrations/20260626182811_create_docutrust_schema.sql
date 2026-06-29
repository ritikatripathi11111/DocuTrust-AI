/*
# DocuTrust CRAG Platform Schema

## Overview
Creates the full data model for the DocuTrust Corrective RAG platform: client profiles,
uploaded documents, structural chunks with vector embeddings, and dynamic interaction
trace logs that record every step of the multi-agent evaluation pipeline.

## 1. New Tables

- `clients` — Individual client profiles (tenants). Each client has a name, an industry
  label, and a workspace region. Documents and traces are scoped to a client.
  Columns: `id` (uuid PK), `name` (text), `industry` (text), `region` (text),
  `created_at` (timestamptz).

- `documents` — Uploaded PDF metadata. Stores the original filename, MIME type, byte
  size, page count, parsed status, and a structural indexing list (ordered list of
  section headings) used to support semantic searching and chunk reassembly.
  Columns: `id` (uuid PK), `client_id` (uuid FK -> clients), `filename` (text),
  `mime_type` (text), `size_bytes` (bigint), `page_count` (int), `status` (text),
  `section_index` (jsonb), `created_at` (timestamptz).

- `document_chunks` — Structural chunks of a document with text content and a vector
  embedding for semantic retrieval. The `chunk_index` preserves document order,
  `page_number` ties the chunk to its source page, and `section` records the heading
  the chunk falls under. `embedding` is a vector(1536) for similarity search.
  Columns: `id` (uuid PK), `document_id` (uuid FK -> documents), `chunk_index` (int),
  `page_number` (int), `section` (text), `content` (text), `token_count` (int),
  `embedding` (vector(1536)), `created_at` (timestamptz).

- `interaction_traces` — Dynamic interaction trace logs. Each row is one step of the
  CRAG pipeline (retrieve, grade, rewrite, web_search, generate, validate) with the
  agent name, step type, input/output payloads, relevance scores, decision labels,
  latency, and a status. The `query` column records the user question that triggered
  the trace and `answer` holds the final validated answer when the trace completes.
  Columns: `id` (uuid PK), `client_id` (uuid FK -> clients), `query` (text),
  `answer` (text), `citations` (jsonb), `steps` (jsonb), `status` (text),
  `created_at` (timestamptz), `completed_at` (timestamptz).

## 2. Indexes

- `document_chunks.document_id` — fast chunk lookup per document.
- `document_chunks.embedding` — HNSW vector index for fast cosine similarity search.
- `documents.client_id` — fast document listing per client.
- `interaction_traces.client_id` — fast trace listing per client.
- `interaction_traces.created_at` — chronological trace browsing.

## 3. Security (RLS)

This is a single-tenant demo with no sign-in screen, so all policies use
`TO anon, authenticated` with `USING (true)` / `WITH CHECK (true)` because the data
is intentionally shared across the workspace. RLS is enabled on every table so the
tables are not accidentally exposed without a policy.

## 4. Important Notes

1. The `vector` extension is created in the `extensions` schema (already installed);
   we enable it on the public schema with `CREATE EXTENSION IF NOT EXISTS vector`.
2. The embedding dimension is 1536 to match a standard text-embedding model output.
   The grader/retriever services treat the column as opaque and only require that
   inserted vectors match the dimension.
3. All tables use `gen_random_uuid()` for primary keys so inserts can omit the id.
4. `created_at` defaults to `now()` on every table for chronological ordering.
*/

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS clients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  industry text,
  region text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  filename text NOT NULL,
  mime_type text NOT NULL DEFAULT 'application/pdf',
  size_bytes bigint NOT NULL DEFAULT 0,
  page_count integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'pending',
  section_index jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  page_number integer NOT NULL DEFAULT 1,
  section text,
  content text NOT NULL,
  token_count integer NOT NULL DEFAULT 0,
  embedding vector(1536),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interaction_traces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  query text NOT NULL,
  answer text,
  citations jsonb NOT NULL DEFAULT '[]'::jsonb,
  steps jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'running',
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_documents_client_id ON documents(client_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_interaction_traces_client_id ON interaction_traces(client_id);
CREATE INDEX IF NOT EXISTS idx_interaction_traces_created_at ON interaction_traces(created_at DESC);

-- HNSW vector index for semantic similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
  ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- Enable RLS on every table
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE interaction_traces ENABLE ROW LEVEL SECURITY;

-- clients: single-tenant shared workspace, anon + authenticated CRUD
DROP POLICY IF EXISTS "anon_select_clients" ON clients;
CREATE POLICY "anon_select_clients" ON clients FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_clients" ON clients;
CREATE POLICY "anon_insert_clients" ON clients FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_clients" ON clients;
CREATE POLICY "anon_update_clients" ON clients FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_clients" ON clients;
CREATE POLICY "anon_delete_clients" ON clients FOR DELETE
  TO anon, authenticated USING (true);

-- documents
DROP POLICY IF EXISTS "anon_select_documents" ON documents;
CREATE POLICY "anon_select_documents" ON documents FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_documents" ON documents;
CREATE POLICY "anon_insert_documents" ON documents FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_documents" ON documents;
CREATE POLICY "anon_update_documents" ON documents FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_documents" ON documents;
CREATE POLICY "anon_delete_documents" ON documents FOR DELETE
  TO anon, authenticated USING (true);

-- document_chunks
DROP POLICY IF EXISTS "anon_select_document_chunks" ON document_chunks;
CREATE POLICY "anon_select_document_chunks" ON document_chunks FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_document_chunks" ON document_chunks;
CREATE POLICY "anon_insert_document_chunks" ON document_chunks FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_document_chunks" ON document_chunks;
CREATE POLICY "anon_update_document_chunks" ON document_chunks FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_document_chunks" ON document_chunks;
CREATE POLICY "anon_delete_document_chunks" ON document_chunks FOR DELETE
  TO anon, authenticated USING (true);

-- interaction_traces
DROP POLICY IF EXISTS "anon_select_interaction_traces" ON interaction_traces;
CREATE POLICY "anon_select_interaction_traces" ON interaction_traces FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_interaction_traces" ON interaction_traces;
CREATE POLICY "anon_insert_interaction_traces" ON interaction_traces FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_interaction_traces" ON interaction_traces;
CREATE POLICY "anon_update_interaction_traces" ON interaction_traces FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_interaction_traces" ON interaction_traces;
CREATE POLICY "anon_delete_interaction_traces" ON interaction_traces FOR DELETE
  TO anon, authenticated USING (true);
