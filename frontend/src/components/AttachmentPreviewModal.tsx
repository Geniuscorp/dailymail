import { useEffect, useState } from 'react'

export interface PreviewableAttachment {
  id: number
  original_filename: string
  mime_type: string
}

interface AttachmentPreviewModalProps {
  attachment: PreviewableAttachment | null
  fetchBlob: (id: number) => Promise<Blob>
  onClose: () => void
}

const PDF_TYPE = 'application/pdf'

function isImageType(mimeType: string): boolean {
  return mimeType.startsWith('image/')
}

// Shared by the mailbox inbox and the admin panel: both need to open a PDF
// or image right on the page instead of a separate browser tab, and both
// authenticate the download differently (mailbox token vs admin token), so
// the actual fetch is passed in rather than hardcoded here.
export default function AttachmentPreviewModal({
  attachment,
  fetchBlob,
  onClose,
}: AttachmentPreviewModalProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!attachment) return
    let objectUrl: string | null = null
    let cancelled = false
    setUrl(null)
    setError(null)
    fetchBlob(attachment.id)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setError('Não foi possível abrir o anexo.')
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [attachment, fetchBlob])

  useEffect(() => {
    if (!attachment) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [attachment, onClose])

  if (!attachment) return null

  const previewable = attachment.mime_type === PDF_TYPE || isImageType(attachment.mime_type)

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70 p-3 sm:p-6" onClick={onClose}>
      <div
        className="flex items-center justify-between gap-3 pb-3"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="min-w-0 truncate text-sm font-medium text-white" title={attachment.original_filename}>
          {attachment.original_filename}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          {url && (
            <a
              href={url}
              download={attachment.original_filename}
              className="rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
            >
              Descarregar
            </a>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            className="rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
          >
            Fechar
          </button>
        </div>
      </div>
      <div
        className="min-h-0 flex-1 overflow-hidden rounded-xl bg-white"
        onClick={(event) => event.stopPropagation()}
      >
        {error && <p className="p-6 text-center text-sm text-red-600">{error}</p>}
        {!error && !url && <p className="p-6 text-center text-sm text-gray-400">A carregar…</p>}
        {!error && url && attachment.mime_type === PDF_TYPE && (
          <iframe title={attachment.original_filename} src={url} className="h-full w-full" />
        )}
        {!error && url && isImageType(attachment.mime_type) && (
          <div className="flex h-full items-center justify-center overflow-auto p-4">
            <img
              src={url}
              alt={attachment.original_filename}
              className="max-h-full max-w-full object-contain"
            />
          </div>
        )}
        {!error && url && !previewable && (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
            <p className="text-sm text-gray-600">Não há pré-visualização para este tipo de ficheiro.</p>
            <a
              href={url}
              download={attachment.original_filename}
              className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
            >
              Descarregar {attachment.original_filename}
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
