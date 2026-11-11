import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Emails temporários</h1>
      <p className="text-gray-600">Cria um endereço com uma senha, ou consulta uma caixa que já tenhas.</p>
      <div className="flex flex-wrap gap-3">
        <Link
          to="/create"
          className="inline-block rounded-md bg-gray-900 px-4 py-2 text-white hover:bg-gray-700"
        >
          Criar conta
        </Link>
        <Link
          to="/login"
          className="inline-block rounded-md border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
        >
          Consultar caixa
        </Link>
      </div>
    </section>
  )
}
