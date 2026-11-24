import { useEffect, useRef, useState } from 'react'
// Vite resolves this to the final built asset URL; pdf.js runs its actual
// parsing/rendering work in this worker, off the main thread.
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// pdf.js is ~1MB; most visits never open a PDF, so it's loaded on first use
// instead of bloating every page's initial bundle.
let pdfjsLibPromise: Promise<typeof import('pdfjs-dist')> | null = null
function loadPdfjs() {
  if (!pdfjsLibPromise) {
    pdfjsLibPromise = import('pdfjs-dist').then((mod) => {
      mod.GlobalWorkerOptions.workerSrc = pdfWorkerUrl
      return mod
    })
  }
  return pdfjsLibPromise
}

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

// Renders every page onto its own <canvas> via pdf.js instead of handing the
// PDF to the browser's native viewer (an <iframe src="blob:...">): mobile
// Chrome has no inline PDF viewer to embed that way and just downloads the
// file instead, silently leaving the modal blank. Canvas rendering works
// identically on desktop and mobile since nothing depends on a native
// plugin or viewer.
function PdfPages({ data, filename }: { data: ArrayBuffer; filename: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    if (containerRef.current) containerRef.current.innerHTML = ''

    ;(async () => {
      try {
        // getDocument() transfers (detaches) the buffer it's given, so a
        // copy is passed instead of `data` itself - otherwise a second run
        // of this effect (React StrictMode in dev) would crash on an
        // already-detached ArrayBuffer.
        const pdfjsLib = await loadPdfjs()
        const pdf = await pdfjsLib.getDocument({ data: data.slice(0) }).promise
        const pixelRatio = window.devicePixelRatio || 1
        for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
          if (cancelled) return
          const page = await pdf.getPage(pageNumber)
          const viewport = page.getViewport({ scale: 1.3 * pixelRatio })
          const canvas = document.createElement('canvas')
          canvas.width = Math.ceil(viewport.width)
          canvas.height = Math.ceil(viewport.height)
          canvas.style.width = `${Math.ceil(viewport.width / pixelRatio)}px`
          canvas.style.height = `${Math.ceil(viewport.height / pixelRatio)}px`
          canvas.className = 'mx-auto mb-3 block max-w-full rounded shadow'
          const context = canvas.getContext('2d')
          if (!context) continue
          await page.render({ canvasContext: context, viewport }).promise
          if (cancelled) return
          containerRef.current?.appendChild(canvas)
          setLoading(false)
        }
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [data])

  return (
    <div className="h-full overflow-auto bg-gray-100 p-3">
      {loading && <p className="p-6 text-center text-sm text-gray-400">A carregar…</p>}
      {error && <p className="p-6 text-center text-sm text-red-600">Não foi possível mostrar "{filename}".</p>}
      <div ref={containerRef} />
    </div>
  )
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
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
  const [pdfData, setPdfData] = useState<ArrayBuffer | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!attachment) return
    let objectUrl: string | null = null
    let cancelled = false
    setDownloadUrl(null)
    setPdfData(null)
    setError(null)
    fetchBlob(attachment.id)
      .then(async (blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setDownloadUrl(objectUrl)
        if (attachment.mime_type === PDF_TYPE) {
          const buffer = await blob.arrayBuffer()
          if (!cancelled) setPdfData(buffer)
        }
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
        className="flex items-center justify-between gap-3 pb-3 pr-14"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="min-w-0 truncate text-sm font-medium text-white" title={attachment.original_filename}>
          {attachment.original_filename}
        </p>
        {downloadUrl && (
          <a
            href={downloadUrl}
            download={attachment.original_filename}
            className="shrink-0 rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
          >
            Descarregar
          </a>
        )}
      </div>

      {/* Always in the same corner regardless of what the toolbar above
          shows (pdf.js's own canvas has none, but a future viewer might),
          and large enough to be a clear, easy tap target on a phone. */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Fechar"
        className="absolute right-3 top-3 flex h-10 w-10 items-center justify-center rounded-full bg-white/15 text-xl leading-none text-white transition-colors hover:bg-white/25 sm:right-6 sm:top-6"
      >
        ✕
      </button>

      <div
        className="min-h-0 flex-1 overflow-hidden rounded-xl bg-white"
        onClick={(event) => event.stopPropagation()}
      >
        {error && <p className="p-6 text-center text-sm text-red-600">{error}</p>}
        {!error && attachment.mime_type === PDF_TYPE && pdfData && (
          <PdfPages data={pdfData} filename={attachment.original_filename} />
        )}
        {!error && attachment.mime_type === PDF_TYPE && !pdfData && (
          <p className="p-6 text-center text-sm text-gray-400">A carregar…</p>
        )}
        {!error && downloadUrl && isImageType(attachment.mime_type) && (
          <div className="flex h-full items-center justify-center overflow-auto p-4">
            <img
              src={downloadUrl}
              alt={attachment.original_filename}
              className="max-h-full max-w-full object-contain"
            />
          </div>
        )}
        {!error && downloadUrl && !previewable && (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
            <p className="text-sm text-gray-600">Não há pré-visualização para este tipo de ficheiro.</p>
            <a
              href={downloadUrl}
              download={attachment.original_filename}
              className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
            >
              Descarregar {attachment.original_filename}
            </a>
          </div>
        )}
        {!error && !downloadUrl && !pdfData && attachment.mime_type !== PDF_TYPE && (
          <p className="p-6 text-center text-sm text-gray-400">A carregar…</p>
        )}
      </div>
    </div>
  )
}
