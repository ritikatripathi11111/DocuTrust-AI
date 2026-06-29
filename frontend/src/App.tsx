import { useCallback, useEffect, useState } from 'react'
import { AgentLogPanel } from './components/AgentLogPanel'
import { AnswerPanel } from './components/AnswerPanel'
import { DocumentPanel } from './components/DocumentPanel'
import { Sidebar } from './components/Sidebar'
import { ToastProvider, useToast } from './components/Toast'
import {
  createClient,
  listClients,
  listDocuments,
  listTraces,
  runQuery,
  uploadDocument,
  deleteDocument,
} from './lib/api'
import type {
  AgentStep,
  Client,
  DocumentRecord,
  QueryResponse,
} from './types'

function AppInner() {
  const toast = useToast()
  const [clients, setClients] = useState<Client[]>([])
  const [activeClientId, setActiveClientId] = useState<string | null>(null)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [activeDocumentIds, setActiveDocumentIds] = useState<string[]>([])
  const [traceCount, setTraceCount] = useState(0)

  const [query, setQuery] = useState('')
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const loadClients = useCallback(async () => {
    try {
      const data = await listClients()
      setClients(data)
      if (data.length > 0 && !activeClientId) {
        setActiveClientId(data[0].id)
      }
    } catch (err) {
      console.error('failed to load clients', err)
      toast.show('error', 'Failed to load clients', err instanceof Error ? err.message : undefined)
    }
  }, [activeClientId, toast])

  const loadDocuments = useCallback(async (clientId: string) => {
    try {
      const data = await listDocuments(clientId)
      setDocuments(data)
      // Auto-select all ready documents for querying
      setActiveDocumentIds(data.filter((d) => d.status === 'ready').map((d) => d.id))
    } catch (err) {
      console.error('failed to load documents', err)
      setDocuments([])
    }
  }, [])

  const loadTraceCount = useCallback(async (clientId: string) => {
    try {
      const traces = await listTraces(clientId)
      setTraceCount(traces.length)
    } catch (err) {
      console.error('failed to load traces', err)
    }
  }, [])

  useEffect(() => {
    loadClients()
  }, [loadClients])

  useEffect(() => {
    if (activeClientId) {
      loadDocuments(activeClientId)
      loadTraceCount(activeClientId)
    } else {
      setDocuments([])
      setActiveDocumentIds([])
      setTraceCount(0)
    }
  }, [activeClientId, loadDocuments, loadTraceCount])

  const handleCreateClient = useCallback(
    async (name: string, industry: string, region: string) => {
      try {
        const client = await createClient({ name, industry, region })
        // Refresh the client list from the backend so the new record is
        // authoritative, then select it.
        await loadClients()
        setActiveClientId(client.id)
        toast.show('success', 'Client created', `${client.name} is now your active workspace.`)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to create client'
        toast.show('error', 'Failed to create client', message)
        throw err
      }
    },
    [loadClients, toast],
  )

  const handleUpload = useCallback(
    async (file: File) => {
      if (!activeClientId) return
      setUploading(true)
      setUploadError(null)
      try {
        await uploadDocument(activeClientId, file)
        await loadDocuments(activeClientId)
        toast.show('success', 'Document uploaded', `${file.name} is ready for retrieval.`)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed'
        setUploadError(message)
        toast.show('error', 'Upload failed', message)
      } finally {
        setUploading(false)
      }
    },
    [activeClientId, loadDocuments, toast],
  )

  const handleDeleteDocument = useCallback(
    async (id: string) => {
      try {
        await deleteDocument(id)
        if (activeClientId) await loadDocuments(activeClientId)
        toast.show('success', 'Document deleted')
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to delete document'
        toast.show('error', 'Failed to delete document', message)
      }
    },
    [activeClientId, loadDocuments, toast],
  )

  const handleToggleDocument = useCallback((id: string) => {
    setActiveDocumentIds((prev) =>
      prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id],
    )
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!activeClientId || !query.trim() || running) return
    setRunning(true)
    setError(null)
    setResult(null)
    setSteps([])
    try {
      const response = await runQuery({
        client_id: activeClientId,
        query: query.trim(),
        document_ids: activeDocumentIds.length > 0 ? activeDocumentIds : undefined,
      })
      setSteps(response.steps)
      setResult(response)
      loadTraceCount(activeClientId)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Query failed'
      setError(message)
      toast.show('error', 'Query failed', message)
    } finally {
      setRunning(false)
    }
  }, [activeClientId, query, running, activeDocumentIds, loadTraceCount, toast])

  const hasDocuments = documents.some((d) => d.status === 'ready')

  return (
    <div className="app">
      <Sidebar
        clients={clients}
        activeClientId={activeClientId}
        onSelectClient={setActiveClientId}
        onCreateClient={handleCreateClient}
        documents={documents}
        activeDocumentIds={activeDocumentIds}
        onToggleDocument={handleToggleDocument}
        onDeleteDocument={handleDeleteDocument}
        traceCount={traceCount}
      />
      <main className="main">
        <DocumentPanel
          documents={documents}
          onUpload={handleUpload}
          uploading={uploading}
          uploadError={uploadError}
          hasClient={!!activeClientId}
        />
        <AgentLogPanel steps={steps} running={running} hasQuery={!!query.trim() || running} />
        <AnswerPanel
          query={query}
          onQueryChange={setQuery}
          onSubmit={handleSubmit}
          running={running}
          result={result}
          error={error}
          hasClient={!!activeClientId}
          hasDocuments={hasDocuments}
        />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  )
}
