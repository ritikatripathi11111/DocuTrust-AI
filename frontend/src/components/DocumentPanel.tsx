import { useRef, useState } from 'react'
import type { DocumentRecord } from '../types'
import { FileTextIcon, UploadIcon } from './Icons'

interface DocumentPanelProps {
  documents: DocumentRecord[]
  onUpload: (file: File) => Promise<void>
  uploading: boolean
  uploadError: string | null
  hasClient: boolean
}

export function DocumentPanel({
  documents,
  onUpload,
  uploading,
  uploadError,
  hasClient,
}: DocumentPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    for (const file of Array.from(files)) {
      await onUpload(file)
    }
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="document-panel">
      <div className="panel-header">
        <div className="panel-title">
          <FileTextIcon size={16} />
          <h2>Document Corpus</h2>
        </div>
        <span className="panel-count">{documents.length} files</span>
      </div>

      <div
        className={`dropzone ${dragOver ? 'drag-over' : ''} ${uploading ? 'uploading' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          handleFiles(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="dropzone-content">
          {uploading ? (
            <>
              <div className="dropzone-spinner" />
              <p>Parsing & embedding document…</p>
            </>
          ) : (
            <>
              <UploadIcon size={28} />
              <p className="dropzone-title">
                {hasClient ? 'Drop multi-page PDFs here' : 'Select a client first'}
              </p>
              <p className="dropzone-hint">
                {hasClient
                  ? 'or click to browse · PDF only'
                  : 'Create or select a client workspace to upload documents'}
              </p>
            </>
          )}
        </div>
      </div>

      {uploadError && <div className="upload-error">{uploadError}</div>}

      <div className="document-list-scroll">
        {documents.length === 0 ? (
          <div className="empty-state">
            <FileTextIcon size={32} />
            <p>No documents yet</p>
            <span>Upload a corporate policy PDF to start querying with CRAG.</span>
          </div>
        ) : (
          <div className="doc-cards">
            {documents.map((doc) => (
              <div key={doc.id} className="doc-card">
                <div className="doc-card-header">
                  <div className="doc-card-icon">
                    <FileTextIcon size={18} />
                  </div>
                  <div className="doc-card-title" title={doc.filename}>
                    {doc.filename}
                  </div>
                </div>
                <div className="doc-card-stats">
                  <div className="stat-pill">
                    <span className="stat-num">{doc.page_count}</span>
                    <span className="stat-lbl">pages</span>
                  </div>
                  <div className="stat-pill">
                    <span className="stat-num">{doc.section_index.length}</span>
                    <span className="stat-lbl">sections</span>
                  </div>
                  <div className="stat-pill">
                    <span className="stat-num">{Math.round(doc.size_bytes / 1024)}</span>
                    <span className="stat-lbl">KB</span>
                  </div>
                </div>
                {doc.section_index.length > 0 && (
                  <div className="doc-sections">
                    {doc.section_index.slice(0, 6).map((s, i) => (
                      <span key={i} className="section-tag" title={s}>
                        {s}
                      </span>
                    ))}
                    {doc.section_index.length > 6 && (
                      <span className="section-tag more">
                        +{doc.section_index.length - 6}
                      </span>
                    )}
                  </div>
                )}
                <div className={`doc-card-status ${doc.status}`}>
                  {doc.status === 'ready' && 'Ready for retrieval'}
                  {doc.status === 'parsing' && 'Parsing…'}
                  {doc.status === 'pending' && 'Pending'}
                  {doc.status.startsWith('failed') && doc.status}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
