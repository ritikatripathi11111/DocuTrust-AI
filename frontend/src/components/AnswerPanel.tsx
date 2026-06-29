import { useState } from 'react'
import type { Citation, QueryResponse } from '../types'
import {
  AlertCircleIcon,
  CheckCircleIcon,
  QuoteIcon,
  SendIcon,
  SparklesIcon,
} from './Icons'

interface AnswerPanelProps {
  query: string
  onQueryChange: (q: string) => void
  onSubmit: () => void
  running: boolean
  result: QueryResponse | null
  error: string | null
  hasClient: boolean
  hasDocuments: boolean
}

export function AnswerPanel({
  query,
  onQueryChange,
  onSubmit,
  running,
  result,
  error,
  hasClient,
  hasDocuments,
}: AnswerPanelProps) {
  const canSubmit = hasClient && hasDocuments && query.trim().length > 0 && !running
  const [copied, setCopied] = useState(false)

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSubmit) onSubmit()
    }
  }

  return (
    <div className="answer-panel">
      <div className="panel-header">
        <div className="panel-title">
          <SparklesIcon size={16} />
          <h2>Validated Answer</h2>
        </div>
        {result && result.status === 'completed' && (
          <div className="validated-badge">
            <CheckCircleIcon size={13} />
            <span>Citations validated</span>
          </div>
        )}
      </div>

      <div className="query-input-wrap">
        <textarea
          className="query-input"
          placeholder={
            hasClient && hasDocuments
              ? 'Ask a question about the uploaded policy documents…'
              : hasClient
                ? 'Upload a document to enable querying.'
                : 'Select or create a client workspace to begin.'
          }
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          disabled={!hasClient || !hasDocuments}
        />
        <button
          className="query-submit"
          onClick={onSubmit}
          disabled={!canSubmit}
          title="Run CRAG pipeline (Enter)"
        >
          {running ? <span className="btn-spinner" /> : <SendIcon size={15} />}
          <span>{running ? 'Processing' : 'Run Pipeline'}</span>
        </button>
      </div>

      <div className="answer-scroll">
        {error && (
          <div className="answer-error">
            <AlertCircleIcon size={18} />
            <div>
              <strong>Query failed</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        {!error && !result && !running && (
          <div className="empty-state">
            <SparklesIcon size={32} />
            <p>No answer yet</p>
            <span>
              The validated answer with strict citations will appear here after the
              CRAG pipeline completes.
            </span>
          </div>
        )}

        {running && !result && (
          <div className="answer-skeleton">
            <div className="skeleton-line w-80" />
            <div className="skeleton-line w-100" />
            <div className="skeleton-line w-90" />
            <div className="skeleton-line w-60" />
          </div>
        )}

        {result && (
          <div className="answer-content">
            <div className="answer-toolbar">
              <button
                className="copy-btn"
                onClick={() => {
                  navigator.clipboard.writeText(result!.answer)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
              }}
              >
               {copied ? "✓ Copied" : "📋 Copy"}
              </button>

              <button
                className="copy-btn"
                onClick={() => downloadAnswer(result!.answer)}
              >
                ⬇ Download
              </button>

              <button
                className="copy-btn"
                onClick={() => onQueryChange("")}
              >
                🗑 Clear
              </button>
            </div>
            <div className="answer-text">
              <RenderAnswer text={result.answer} />
            </div>

            {result.citations.length > 0 && (
              <div className="citations-section">
                <div className="citations-header">
                  <QuoteIcon size={14} />
                  <h3>Citations ({result.citations.length})</h3>
                </div>
                <div className="citations-list">
                  {result.citations.map((c, i) => (
                    <CitationCard key={i} citation={c} index={i + 1} />
                  ))}
                </div>
              </div>
            )}

            <div className="answer-meta">
              <span className="meta-item">
                <span className="meta-label">Pipeline</span>
                <span className="meta-value">{result.steps.length} steps</span>
              </span>
              <span className="meta-item">
                <span className="meta-label">Status</span>
                <span className={`meta-value status-${result.status}`}>{result.status}</span>
              </span>
              {result.completed_at && (
                <span className="meta-item">
                  <span className="meta-label">Completed</span>
                  <span className="meta-value">
                    {new Date(result.completed_at).toLocaleTimeString()}
                  </span>
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function RenderAnswer({ text }: { text: string }) {
  
  if (!text) return <p className="answer-empty">No answer produced.</p>
  // Split by citation markers [n] and render with styled citation chips
  const parts = text.split(/(\[\d+\])/g)
  return (
    <p className="answer-paragraph">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/)
        if (match) {
          return (
            <span key={i} className="inline-citation">
              [{match[1]}]
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </p>
  )
}
function downloadAnswer(text: string) {
  const blob = new Blob([text], { type: "text/plain" })
  const url = URL.createObjectURL(blob)

  const a = document.createElement("a")
  a.href = url
  a.download = "validated_answer.txt"
  a.click()

  URL.revokeObjectURL(url)
}

function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const isWeb = citation.chunk_id.startsWith('web:')
  return (
    <div className={`citation-card ${isWeb ? 'web' : 'doc'}`}>
      <div className="citation-header" onClick={() => setExpanded(!expanded)}>
        <span className="citation-index">{index}</span>
        <div className="citation-title" title={citation.filename}>
          {isWeb ? <SendIcon size={12} /> : <QuoteIcon size={12} />}
          <span>{citation.filename}</span>
        </div>
        <span className="citation-score" title="Relevance score">
          {citation.score.toFixed(3)}
        </span>
      </div>
      <div className="citation-meta">
        {isWeb ? (
          <span className="citation-source web">Web fallback</span>
        ) : (
          <>
            <span className="citation-source">Page {citation.page_number}</span>
            {citation.section && (
              <span className="citation-source">· {citation.section}</span>
            )}
          </>
        )}
      </div>
      {expanded && (
        <div className="citation-snippet">
          <QuoteIcon size={12} />
          <p>{citation.snippet}</p>
        </div>
      )}
      {!expanded && (
        <button className="citation-expand" onClick={() => setExpanded(true)}>
          view snippet
        </button>
      )}
    </div>
  )
}
