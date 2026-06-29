import { useState } from 'react'
import type { Client, DocumentRecord } from '../types'
import {
  BookOpenIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DatabaseIcon,
  FileTextIcon,
  PlusIcon,
  ShieldCheckIcon,
  TrashIcon,
  XIcon,
} from './Icons'

interface SidebarProps {
  clients: Client[]
  activeClientId: string | null
  onSelectClient: (id: string) => void
  onCreateClient: (name: string, industry: string, region: string) => Promise<void>
  documents: DocumentRecord[]
  activeDocumentIds: string[]
  onToggleDocument: (id: string) => void
  onDeleteDocument: (id: string) => void
  traceCount: number
}

const NAME_MAX = 200
const INDUSTRY_MAX = 120
const REGION_MAX = 120

export function Sidebar(props: SidebarProps) {
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newIndustry, setNewIndustry] = useState('')
  const [newRegion, setNewRegion] = useState('')
  const [docsOpen, setDocsOpen] = useState(true)
  const [creating, setCreating] = useState(false)
  const [errors, setErrors] = useState<{ name?: string; industry?: string; region?: string }>({})

  const activeClient = props.clients.find((c) => c.id === props.activeClientId)

  function validate(): boolean {
    const next: typeof errors = {}
    const name = newName.trim()
    if (!name) {
      next.name = 'Name is required'
    } else if (name.length > NAME_MAX) {
      next.name = `Name must be ${NAME_MAX} characters or fewer`
    }
    const industry = newIndustry.trim()
    if (industry.length > INDUSTRY_MAX) {
      next.industry = `Industry must be ${INDUSTRY_MAX} characters or fewer`
    }
    const region = newRegion.trim()
    if (region.length > REGION_MAX) {
      next.region = `Region must be ${REGION_MAX} characters or fewer`
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  function resetForm() {
    setNewName('')
    setNewIndustry('')
    setNewRegion('')
    setErrors({})
  }

  async function handleCreate() {
    if (creating) return
    if (!validate()) return
    setCreating(true)
    try {
      await props.onCreateClient(newName.trim(), newIndustry.trim(), newRegion.trim())
      resetForm()
      setShowCreate(false)
    } catch {
      // error toast is surfaced by the parent; keep the modal open so the
      // user can fix the inputs and retry
    } finally {
      setCreating(false)
    }
  }

  function openModal() {
    resetForm()
    setShowCreate(true)
  }

  function closeModal() {
    if (creating) return
    setShowCreate(false)
    resetForm()
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">
          <ShieldCheckIcon size={22} />
          <div className="logo-text">
            <span className="logo-title">DocuTrust</span>
            <span className="logo-subtitle">CRAG Platform</span>
          </div>
        </div>
      </div>

      <div className="sidebar-section">
        <div className="section-label">
          <DatabaseIcon size={13} />
          <span>Client Workspace</span>
        </div>
        <div className="client-list">
          {props.clients.length === 0 && (
            <div className="empty-hint">No clients yet. Create one to begin.</div>
          )}
          {props.clients.map((c) => (
            <button
              key={c.id}
              className={`client-item ${c.id === props.activeClientId ? 'active' : ''}`}
              onClick={() => props.onSelectClient(c.id)}
            >
              <div className="client-avatar">{c.name.charAt(0).toUpperCase()}</div>
              <div className="client-info">
                <div className="client-name">{c.name}</div>
                <div className="client-meta">
                  {c.industry || '—'} · {c.region || 'Global'}
                </div>
              </div>
            </button>
          ))}
        </div>
        <button className="add-client-btn" onClick={openModal}>
          <PlusIcon size={14} />
          <span>New Client</span>
        </button>
      </div>

      {activeClient && (
        <div className="sidebar-section">
          <button
            className="section-label clickable"
            onClick={() => setDocsOpen((v) => !v)}
          >
            {docsOpen ? <ChevronDownIcon size={13} /> : <ChevronRightIcon size={13} />}
            <BookOpenIcon size={13} />
            <span>Documents ({props.documents.length})</span>
          </button>
          {docsOpen && (
            <div className="document-list">
              {props.documents.length === 0 && (
                <div className="empty-hint">Upload a PDF to populate the corpus.</div>
              )}
              {props.documents.map((doc) => {
                const active = props.activeDocumentIds.includes(doc.id)
                return (
                  <div
                    key={doc.id}
                    className={`document-item ${active ? 'active' : ''}`}
                  >
                    <label className="doc-check">
                      <input
                        type="checkbox"
                        checked={active}
                        onChange={() => props.onToggleDocument(doc.id)}
                      />
                      <span className="checkmark" />
                    </label>
                    <div className="doc-info">
                      <div className="doc-name">
                        <FileTextIcon size={13} />
                        <span title={doc.filename}>{doc.filename}</span>
                      </div>
                      <div className="doc-meta">
                        {doc.page_count}p · {doc.section_index.length} sections ·{' '}
                        <span className={`doc-status ${doc.status}`}>{doc.status}</span>
                      </div>
                    </div>
                    <button
                      className="doc-delete"
                      title="Delete document"
                      onClick={() => props.onDeleteDocument(doc.id)}
                    >
                      <TrashIcon size={13} />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="sidebar-footer">
        <div className="footer-stat">
          <span className="stat-label">Traces logged</span>
          <span className="stat-value">{props.traceCount}</span>
        </div>
      </div>

      {showCreate && (
        <div className="modal-backdrop" onClick={closeModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>New Client Profile</h3>
              <button className="modal-close" onClick={closeModal} disabled={creating}>
                <XIcon size={18} />
              </button>
            </div>
            <div className="modal-body">
              <label>
                <span>Name</span>
                <input
                  placeholder="e.g. Acme Corp"
                  value={newName}
                  onChange={(e) => {
                    setNewName(e.target.value)
                    if (errors.name) setErrors((p) => ({ ...p, name: undefined }))
                  }}
                  disabled={creating}
                  maxLength={NAME_MAX}
                  autoFocus
                />
                {errors.name && <span className="field-error">{errors.name}</span>}
              </label>
              <label>
                <span>Industry</span>
                <input
                  placeholder="e.g. Technology"
                  value={newIndustry}
                  onChange={(e) => {
                    setNewIndustry(e.target.value)
                    if (errors.industry) setErrors((p) => ({ ...p, industry: undefined }))
                  }}
                  disabled={creating}
                  maxLength={INDUSTRY_MAX}
                />
                {errors.industry && <span className="field-error">{errors.industry}</span>}
              </label>
              <label>
                <span>Region</span>
                <input
                  placeholder="e.g. North America"
                  value={newRegion}
                  onChange={(e) => {
                    setNewRegion(e.target.value)
                    if (errors.region) setErrors((p) => ({ ...p, region: undefined }))
                  }}
                  disabled={creating}
                  maxLength={REGION_MAX}
                />
                {errors.region && <span className="field-error">{errors.region}</span>}
              </label>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={closeModal} disabled={creating}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleCreate}
                disabled={creating || !newName.trim()}
              >
                {creating && <span className="btn-spinner dark" />}
                <span>{creating ? 'Creating…' : 'Create Client'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
