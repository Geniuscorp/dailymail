import { useEffect, useState } from 'react'
import { fetchAttachment } from '../services/api'
import type { AttachmentSummary } from '../types'

const PDF_TYPE = 'application/pdf'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImage(attachment: AttachmentSummary): boolean {
  return attachment.mime_type.startsWith('image/')
}

function ImagePreview({ attachment }: { attachment: AttachmentSummary }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    fetchAttachment(attachment.id)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [attachment.id])

  if (!url) return null
  return <img src={url} alt={attachment.original_filename} className="max-h-72 w-auto rounded border border-gray-200" />
}

export default function AttachmentList({ attachments }: { attachments: AttachmentSummary[] }) {
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  if (attachments.length === 0) return null

  async function download(attachment: AttachmentSummary) {
    setError(null)
    setBusyId(attachment.id)
    try {
      const blob = await fetchAttachment(attachment.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = attachment.original_filename
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      setError('Não foi possível transferir o anexo.')
    } finally {
      setBusyId(null)
    }
  }

  async function openPdf(attachment: AttachmentSummary) {
    setError(null)
    setBusyId(attachment.id)
    const tab = window.open('about:blank', '_blank')
    try {
      const blob = await fetchAttachment(attachment.id)
      const url = URL.createObjectURL(new Blob([blob], { type: PDF_TYPE }))
      if (tab) {
        tab.opener = null
        tab.location.href = url
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      tab?.close()
      setError('Não foi possível abrir o anexo.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium text-gray-700">Anexos ({attachments.length})</h2>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <ul className="divide-y divide-gray-200 rounded-md border border-gray-200 bg-white">
        {attachments.map((attachment) => (
          <li key={attachment.id} className="space-y-2 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm text-gray-900">{attachment.original_filename}</p>
                <p className="text-xs text-gray-500">{formatSize(attachment.file_size)}</p>
              </div>
              <div className="flex gap-2">
                {attachment.mime_type === PDF_TYPE && (
                  <button
                    type="button"
                    disabled={busyId !== null}
                    onClick={() => void openPdf(attachment)}
                    className="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50"
                  >
                    Abrir
                  </button>
                )}
                <button
                  type="button"
                  disabled={busyId !== null}
                  onClick={() => void download(attachment)}
                  className="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50"
                >
                  Descarregar
                </button>
              </div>
            </div>
            {isImage(attachment) && <ImagePreview attachment={attachment} />}
          </li>
        ))}
      </ul>
    </section>
  )
}
