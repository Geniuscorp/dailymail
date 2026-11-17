import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { DownloadStalledError, fetchAttachment } from '../services/api'
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

function describeError(error: unknown, action: string): string {
  if (error instanceof DownloadStalledError) {
    return `A transferência ficou parada. Verifica a ligação e tenta ${action} outra vez.`
  }
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    if (status === 429) return 'Demasiados pedidos. Tenta novamente daqui a pouco.'
    if (status === 403) return 'O acesso foi bloqueado pela rede ou pelo servidor (403).'
    if (status === 404) return 'O anexo já não existe.'
    if (status === 503) return 'O armazenamento de anexos está indisponível. Tenta mais tarde.'
    if (status) return `O servidor respondeu com o erro ${status}.`
    return 'Sem ligação ao servidor. Verifica a rede e tenta outra vez.'
  }
  return `Não foi possível ${action} o anexo.`
}

function ImagePreview({ attachment }: { attachment: AttachmentSummary }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    fetchAttachment(attachment.id)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [attachment.id])

  if (failed) return <p className="text-xs text-gray-400">Pré-visualização indisponível.</p>
  if (!url) return null
  return <img src={url} alt={attachment.original_filename} className="max-h-72 w-auto rounded border border-gray-200" />
}

export default function AttachmentList({ attachments }: { attachments: AttachmentSummary[] }) {
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  if (attachments.length === 0) return null

  function beginTransfer(attachment: AttachmentSummary) {
    setError(null)
    setProgress(null)
    setBusyId(attachment.id)
    const controller = new AbortController()
    abortRef.current = controller
    return {
      signal: controller.signal,
      onProgress: (loaded: number, total: number | null) =>
        setProgress(total ? Math.min(100, Math.round((loaded / total) * 100)) : null),
    }
  }

  function endTransfer() {
    abortRef.current = null
    setBusyId(null)
    setProgress(null)
  }

  function cancelTransfer() {
    abortRef.current?.abort()
  }

  async function download(attachment: AttachmentSummary) {
    const transfer = beginTransfer(attachment)
    try {
      const blob = await fetchAttachment(attachment.id, transfer)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = attachment.original_filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      if (!transfer.signal.aborted || err instanceof DownloadStalledError) {
        setError(describeError(err, 'transferir'))
      }
    } finally {
      endTransfer()
    }
  }

  async function openPdf(attachment: AttachmentSummary) {
    const transfer = beginTransfer(attachment)
    const tab = window.open('about:blank', '_blank')
    try {
      const blob = await fetchAttachment(attachment.id, transfer)
      const url = URL.createObjectURL(new Blob([blob], { type: PDF_TYPE }))
      if (tab) {
        tab.opener = null
        tab.location.href = url
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      tab?.close()
      if (!transfer.signal.aborted || err instanceof DownloadStalledError) {
        setError(describeError(err, 'abrir'))
      }
    } finally {
      endTransfer()
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
      <ul className="divide-y divide-gray-100 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
        {attachments.map((attachment) => (
          <li key={attachment.id} className="space-y-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-gray-900">{attachment.original_filename}</p>
                <p className="text-xs text-gray-400">{formatSize(attachment.file_size)}</p>
              </div>
              <div className="flex gap-2">
                {attachment.mime_type === PDF_TYPE && (
                  <button
                    type="button"
                    disabled={busyId !== null}
                    onClick={() => void openPdf(attachment)}
                    className="rounded-lg border border-gray-200 px-3 py-1 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
                  >
                    Abrir
                  </button>
                )}
                <button
                  type="button"
                  disabled={busyId !== null}
                  onClick={() => void download(attachment)}
                  className="rounded-lg border border-gray-200 px-3 py-1 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
                >
                  {busyId === attachment.id ? (progress !== null ? `A transferir… ${progress}%` : 'A transferir…') : 'Descarregar'}
                </button>
                {busyId === attachment.id && (
                  <button
                    type="button"
                    onClick={cancelTransfer}
                    className="rounded-lg px-3 py-1 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900"
                  >
                    Cancelar
                  </button>
                )}
              </div>
            </div>
            {isImage(attachment) && <ImagePreview attachment={attachment} />}
          </li>
        ))}
      </ul>
    </section>
  )
}
