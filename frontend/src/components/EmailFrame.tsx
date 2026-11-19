import { useCallback, useEffect, useRef, useState } from 'react'

// Defence in depth for untrusted HTML: it is sanitised on the server, the frame
// has no `allow-scripts` (nothing can run), and this CSP blocks every network
// request. `allow-same-origin` is therefore safe here: with scripts off it only
// lets the page measure the content so the frame can be sized to fit it.
const HTML_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
const BASE_STYLE =
  'html{-webkit-text-size-adjust:100%}' +
  'body{font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:0;padding:16px;color:#111;background:#fff;overflow-wrap:break-word}' +
  'img{max-width:100%;height:auto}a{color:#4f46e5}'
// Below this, shrinking to fit makes text unreadable: scroll sideways instead.
const MIN_SCALE = 0.35

function buildSrcDoc(html: string): string {
  return (
    `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${HTML_CSP}">` +
    `<base target="_blank"><style>${BASE_STYLE}</style></head><body>${html}</body></html>`
  )
}

interface Layout {
  width: number
  height: number
  scale: number
}

/**
 * Renders an email at its natural size with no scrollbar of its own: the frame is
 * as tall as the message, and a message wider than the page (a typical 600-700px
 * table layout on a phone) is scaled down to fit rather than overflowing.
 */
export default function EmailFrame({ html }: { html: string }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<HTMLIFrameElement>(null)
  const [layout, setLayout] = useState<Layout>({ width: 0, height: 320, scale: 1 })

  const measure = useCallback(() => {
    const box = boxRef.current
    const frame = frameRef.current
    const doc = frame?.contentDocument
    const root = doc?.documentElement
    if (!box || !frame || !doc || !root) return
    const available = box.clientWidth
    if (available === 0) return

    // Lay the message out at the page width first to learn how wide it really wants to be.
    frame.style.width = `${available}px`
    const needed = Math.max(root.scrollWidth, doc.body?.scrollWidth ?? 0, available)
    frame.style.width = `${needed}px`
    // Collapse first: scrollHeight never reports less than the frame's current height.
    frame.style.height = '0px'
    const height = Math.ceil(root.scrollHeight)
    const scale = Math.max(MIN_SCALE, Math.min(1, available / needed))

    setLayout((current) =>
      Math.abs(current.width - needed) < 1 && Math.abs(current.height - height) < 1 && current.scale === scale
        ? current
        : { width: needed, height, scale },
    )
    frame.style.height = `${height}px`
  }, [])

  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const observer = new ResizeObserver(() => measure())
    observer.observe(box)
    return () => observer.disconnect()
  }, [measure])

  function handleLoad() {
    measure()
    // Late layout changes: web fonts swapping in, embedded images decoding.
    void frameRef.current?.contentDocument?.fonts?.ready.then(measure)
    window.setTimeout(measure, 300)
  }

  return (
    <div ref={boxRef} className="overflow-x-auto bg-white">
      <div style={{ width: layout.width * layout.scale || '100%', height: layout.height * layout.scale }}>
        <iframe
          ref={frameRef}
          title="Conteúdo da mensagem"
          sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
          srcDoc={buildSrcDoc(html)}
          onLoad={handleLoad}
          scrolling="no"
          style={{
            display: 'block',
            border: 0,
            width: layout.width || '100%',
            height: layout.height,
            transform: `scale(${layout.scale})`,
            transformOrigin: '0 0',
          }}
        />
      </div>
    </div>
  )
}
