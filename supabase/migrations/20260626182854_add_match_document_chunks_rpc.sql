/*
# Add vector similarity search RPC

## Overview
Adds a Postgres function `match_document_chunks` that performs cosine similarity
search over the `document_chunks.embedding` column. The retriever agent calls
this RPC to fetch the top-k most semantically similar chunks for a query embedding,
optionally filtered to a specific client's documents.

## 1. New Functions

- `match_document_chunks(query_embedding vector, match_count int DEFAULT 6,
  filter_client_id uuid DEFAULT NULL, filter_document_ids uuid[] DEFAULT NULL)`
  Returns the top-k chunks ranked by cosine similarity (1 - distance), joined with
  their parent document's filename and client_id so the retriever has everything
  it needs in one round trip.

  Columns returned: id, document_id, client_id, filename, chunk_index, page_number,
  section, content, token_count, score (similarity in [0,1]).

## 2. Security

The function is `SECURITY DEFINER` so it can read across documents owned by
different clients in this single-tenant demo. It is exposed via PostgREST as an
RPC callable by the anon role (RLS on `document_chunks` already permits anon
SELECT, so this is consistent with the existing policy).

## 3. Important Notes

1. The function uses the `<=>` cosine distance operator from the `vector` extension.
2. `score = 1 - (embedding <=> query_embedding)` so higher is more similar.
3. NULL filter arguments are ignored; passing `filter_document_ids` restricts the
   search to a subset of the client's documents (used when the user scopes a query
   to specific uploaded PDFs).
*/

CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding vector(1536),
  match_count integer DEFAULT 6,
  filter_client_id uuid DEFAULT NULL,
  filter_document_ids uuid[] DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  document_id uuid,
  client_id uuid,
  filename text,
  chunk_index integer,
  page_number integer,
  section text,
  content text,
  token_count integer,
  score float
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT
    dc.id,
    dc.document_id,
    d.client_id,
    d.filename,
    dc.chunk_index,
    dc.page_number,
    dc.section,
    dc.content,
    dc.token_count,
    (1 - (dc.embedding <=> query_embedding))::float AS score
  FROM document_chunks dc
  JOIN documents d ON d.id = dc.document_id
  WHERE dc.embedding IS NOT NULL
    AND (filter_client_id IS NULL OR d.client_id = filter_client_id)
    AND (
      filter_document_ids IS NULL
      OR d.id = ANY(filter_document_ids)
    )
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count
$$;
