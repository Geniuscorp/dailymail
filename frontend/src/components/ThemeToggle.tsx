import { useEffect, useState } from 'react'
import { applyPreference, readPreference, savePreference, type ThemePreference } from '../utils/theme'

const NEXT: Record<ThemePreference, ThemePreference> = { system: 'light', light: 'dark', dark: 'system' }
const LABEL: Record<ThemePreference, string> = { system: 'Automático', light: 'Claro', dark: 'Escuro' }

function Icon({ preference }: { preference: ThemePreference }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true" {...common}>
      {preference === 'light' && (
        <>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
        </>
      )}
      {preference === 'dark' && <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />}
      {preference === 'system' && (
        <>
          <rect x="3" y="4" width="18" height="12" rx="2" />
          <path d="M8 20h8M12 16v4" />
        </>
      )}
    </svg>
  )
}

/** Cycles automatic (follows the system) -> light -> dark. */
export default function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>(readPreference)

  useEffect(() => {
    applyPreference(preference)
    if (preference !== 'system' || !window.matchMedia) return
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyPreference('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [preference])

  function change() {
    const next = NEXT[preference]
    savePreference(next)
    setPreference(next)
  }

  return (
    <button
      type="button"
      onClick={change}
      title={`Tema: ${LABEL[preference]} (clica para mudar)`}
      aria-label={`Tema: ${LABEL[preference]}. Clica para mudar.`}
      className="rounded-lg p-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
    >
      <Icon preference={preference} />
    </button>
  )
}
