import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <section className="flex flex-col items-center py-12 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600 shadow-lg shadow-indigo-200">
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="3" className="fill-white/20" />
          <path
            d="M5 8l6.3 4.2a2 2 0 0 0 2.2 0L20 8"
            stroke="white"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <h1 className="mt-6 text-3xl font-bold tracking-tight text-gray-900">Emails temporários</h1>
      <p className="mt-3 max-w-sm text-gray-500">
        Cria um endereço com uma senha e recebe mensagens ao instante — sem precisar de confirmar nada.
      </p>

      <div className="mt-8 flex w-full max-w-xs flex-col gap-3">
        <Link
          to="/create"
          className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
        >
          Criar conta
        </Link>
        <Link
          to="/login"
          className="rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50"
        >
          Consultar caixa existente
        </Link>
      </div>
    </section>
  )
}
