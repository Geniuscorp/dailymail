import { API_BASE_URL } from '../services/api'

export default function InfoSidebar() {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Sobre a conta</h2>
        <ul className="mt-2.5 space-y-2 text-sm text-gray-600">
          <li className="flex gap-2">
            <span className="text-indigo-500">•</span>
            As mensagens ficam guardadas 30 dias.
          </li>
          <li className="flex gap-2">
            <span className="text-indigo-500">•</span>
            O endereço em si nunca expira, só o conteúdo.
          </li>
          <li className="flex gap-2">
            <span className="text-indigo-500">•</span>
            Novas mensagens aparecem sozinhas, sem precisar de atualizar.
          </li>
        </ul>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Para programadores</h2>
        <p className="mt-2 text-sm text-gray-600">
          Cria contas, lê mensagens e descarrega anexos diretamente pela API REST.
        </p>
        <a
          href={`${API_BASE_URL}/docs`}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          Abrir documentação da API
          <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden="true">
            <path
              d="M7 17L17 7M17 7H9M17 7v8"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </a>
      </div>
    </div>
  )
}
