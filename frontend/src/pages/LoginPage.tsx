import { useState } from 'react'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'

export default function LoginPage() {
  const setToken = useAuthStore((s) => s.setToken)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { token } = await api.login(password)
      setToken(token)
    } catch {
      setError('Invalid password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form
        onSubmit={(e) => void submit(e)}
        className="w-80 rounded border border-zinc-800 bg-zinc-900 p-6"
      >
        <h1 className="mb-4 text-xl font-bold text-emerald-400">CryptoQuant</h1>
        <label className="text-sm">
          <div className="mb-1 text-xs text-zinc-500">Password</div>
          <input
            type="password"
            aria-label="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-3 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2"
            autoFocus
          />
        </label>
        <button
          type="submit"
          disabled={busy || !password}
          className="w-full rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        {error && (
          <p className="mt-3 text-sm text-red-400" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  )
}
