import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { AlertCircleIcon, CheckCircleIcon, XIcon } from './Icons'

type ToastVariant = 'success' | 'error' | 'info'

interface Toast {
  id: number
  variant: ToastVariant
  title: string
  message?: string
}

interface ToastContextValue {
  show: (variant: ToastVariant, title: string, message?: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return ctx
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const show = useCallback(
    (variant: ToastVariant, title: string, message?: string) => {
      const id = Date.now() + Math.random()
      setToasts((prev) => [...prev, { id, variant, title, message }])
    },
    [],
  )

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div className="toast-container">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setLeaving(true)
      setTimeout(onDismiss, 250)
    }, 4000)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <div className={`toast toast-${toast.variant} ${leaving ? 'leaving' : ''}`}>
      <div className="toast-icon">
        {toast.variant === 'success' && <CheckCircleIcon size={18} />}
        {toast.variant === 'error' && <AlertCircleIcon size={18} />}
      </div>
      <div className="toast-content">
        <div className="toast-title">{toast.title}</div>
        {toast.message && <div className="toast-message">{toast.message}</div>}
      </div>
      <button className="toast-close" onClick={onDismiss} aria-label="Dismiss">
        <XIcon size={14} />
      </button>
    </div>
  )
}
