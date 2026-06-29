import { useEffect, useRef, useState } from 'react'
import type { AgentStep } from '../types'
import {
  ActivityIcon,
  CheckCircleIcon,
  CpuIcon,
  GlobeIcon,
  LayersIcon,
  QuoteIcon,
  RefreshCwIcon,
  SearchIcon,
  SparklesIcon,
  XCircleIcon,
} from './Icons'

interface AgentLogPanelProps {
  steps: AgentStep[]
  running: boolean
  hasQuery: boolean
}

const AGENT_META: Record<
  string,
  { icon: typeof SearchIcon; label: string; color: string }
> = {
  retriever: { icon: SearchIcon, label: 'Retriever Agent', color: 'var(--color-primary)' },
  grader: { icon: CpuIcon, label: 'Relevance Grader', color: 'var(--color-info)' },
  query_rewriter: { icon: RefreshCwIcon, label: 'Query Rewriter', color: 'var(--color-warning)' },
  web_search: { icon: GlobeIcon, label: 'Web Search Fallback', color: 'var(--color-accent)' },
  generator: { icon: SparklesIcon, label: 'Generator + Citation Validator', color: 'var(--color-primary)' },
}

export function AgentLogPanel({ steps, running, hasQuery }: AgentLogPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [steps])

  return (
    <div className="agent-log-panel">
      <div className="panel-header">
        <div className="panel-title">
          <ActivityIcon size={16} />
          <h2>Agent Evaluation Pipeline</h2>
        </div>
        {running && (
          <div className="running-badge">
            <span className="running-dot" />
            <span>Processing</span>
          </div>
        )}
      </div>

      <div className="agent-log-scroll" ref={scrollRef}>
        {!hasQuery && (
          <div className="empty-state">
            <LayersIcon size={32} />
            <p>Pipeline idle</p>
            <span>Submit a query to watch the CRAG agents evaluate in real time.</span>
          </div>
        )}

        {hasQuery && steps.length === 0 && (
          <div className="pipeline-skeleton">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton-step" style={{ animationDelay: `${i * 120}ms` }}>
                <div className="skeleton-icon" />
                <div className="skeleton-lines">
                  <div className="skeleton-line w-60" />
                  <div className="skeleton-line w-40" />
                </div>
              </div>
            ))}
          </div>
        )}

        {steps.length > 0 && (
          <div className="pipeline-flow">
            {steps.map((step, idx) => {
              const meta = AGENT_META[step.agent] || {
                icon: CpuIcon,
                label: step.agent,
                color: 'var(--color-text-muted)',
              }
              const Icon = meta.icon
              const isLast = idx === steps.length - 1
              return (
                <div key={idx} className="pipeline-step" style={{ animationDelay: `${idx * 60}ms` }}>
                  <div className="step-connector">
                    <div
                      className="step-node"
                      style={{ borderColor: meta.color, color: meta.color }}
                    >
                      <Icon size={16} />
                    </div>
                    {!isLast && <div className="step-line" />}
                  </div>
                  <div className="step-body">
                    <div className="step-header">
                      <span className="step-agent">{meta.label}</span>
                      <span className="step-name">{step.step}</span>
                      <span className={`step-status ${step.status}`}>
                        {step.status === 'completed' && <CheckCircleIcon size={13} />}
                        {step.status === 'failed' && <XCircleIcon size={13} />}
                        {step.status === 'running' && <span className="step-spinner" />}
                        <span>{step.status}</span>
                      </span>
                      {step.duration_ms != null && (
                        <span className="step-duration">{step.duration_ms}ms</span>
                      )}
                    </div>
                    {step.detail && <div className="step-detail">{step.detail}</div>}
                    {step.decision && (
                      <div className="step-decision">
                        <span className="decision-label">decision</span>
                        <span className="decision-value">{step.decision}</span>
                      </div>
                    )}
                    {step.output != null && (
                      <StepOutput agent={step.agent} output={step.output} />
                    )}
                  </div>
                </div>
              )
            })}
            {running && (
              <div className="pipeline-step pending">
                <div className="step-connector">
                  <div className="step-node pending">
                    <span className="step-spinner" />
                  </div>
                </div>
                <div className="step-body">
                  <div className="step-header">
                    <span className="step-agent">Next agent</span>
                    <span className="step-name">awaiting</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StepOutput({ agent, output }: { agent: string; output: unknown }) {
  const [expanded, setExpanded] = useState(false)
  if (!output || typeof output !== 'object') return null

  let summary: { label: string; value: string }[] = []
  const o = output as Record<string, unknown>

  if (agent === 'retriever') {
    summary = [
      { label: 'chunks', value: String(o.count ?? '') },
      { label: 'top score', value: (o.top_score as number)?.toFixed(3) ?? '' },
    ]
  } else if (agent === 'grader') {
    summary = [
      { label: 'relevant', value: String(o.relevant_count ?? 0) },
      { label: 'web search', value: o.needs_web_search ? 'required' : 'skipped' },
    ]
  } else if (agent === 'query_rewriter') {
    summary = [{ label: 'rewritten', value: (o.rewritten_query as string) || '' }]
  } else if (agent === 'web_search') {
    summary = [{ label: 'results', value: String(o.count ?? 0) }]
  } else if (agent === 'generator') {
    summary = [
      { label: 'answer', value: `${o.answer_length ?? 0} chars` },
      { label: 'citations', value: String(o.citations ?? 0) },
      { label: 'validation', value: (o.validation as string) || '' },
    ]
  }

  const graded = o.graded as Array<{ score: number; label: string }> | undefined
  const results = o.results as Array<{ title: string; score: number }> | undefined

  return (
    <div className="step-output">
      {summary.length > 0 && (
        <div className="output-summary">
          {summary.map((s) => (
            <div key={s.label} className="output-chip">
              <span className="chip-label">{s.label}</span>
              <span className="chip-value" title={s.value}>
                {s.value || '—'}
              </span>
            </div>
          ))}
        </div>
      )}
      {graded && graded.length > 0 && (
        <div className="graded-list">
          {graded.map((g, i) => (
            <div key={i} className={`graded-row ${g.label}`}>
              <span className="graded-score">{g.score.toFixed(3)}</span>
              <div className="graded-bar">
                <div
                  className="graded-fill"
                  style={{ width: `${Math.round(g.score * 100)}%` }}
                />
              </div>
              <span className="graded-label">{g.label}</span>
            </div>
          ))}
        </div>
      )}
      {results && results.length > 0 && (
        <div className="web-results">
          {results.map((r, i) => (
            <div key={i} className="web-result-row">
              <QuoteIcon size={12} />
              <span className="web-title" title={r.title}>
                {r.title}
              </span>
              <span className="web-score">{r.score.toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
      <button className="expand-toggle" onClick={() => setExpanded(!expanded)}>
        {expanded ? 'hide raw' : 'raw output'}
      </button>
      {expanded && (
        <pre className="raw-output">{JSON.stringify(output, null, 2)}</pre>
      )}
    </div>
  )
}
