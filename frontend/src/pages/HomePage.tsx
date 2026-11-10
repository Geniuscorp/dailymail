import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Emails temporários</h1>
      <p className="text-gray-600">Consulte a sua caixa com o endereço e a senha definidos na criação.</p>
      <Link
        to="/login"
        className="inline-block rounded-md bg-gray-900 px-4 py-2 text-white hover:bg-gray-700"
      >
        Consultar caixa
      </Link>
    </section>
  )
}
