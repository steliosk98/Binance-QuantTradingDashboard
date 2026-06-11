import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type GeneralSettings } from '../api/client'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: api.settings,
  })
  const keysQuery = useQuery({
    queryKey: ['api-keys'],
    queryFn: api.apiKeysStatus,
  })

  const [edited, setEdited] = useState<GeneralSettings | null>(null)
  const [watchlistEdit, setWatchlistEdit] = useState<string | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  // Render from server data until the user edits — no effects needed.
  const form = edited ?? settingsQuery.data ?? null
  const watchlistText =
    watchlistEdit ?? settingsQuery.data?.watchlist.join(', ') ?? ''
  const setForm = setEdited
  const setWatchlistText = setWatchlistEdit

  const saveGeneral = async () => {
    if (!form) return
    setMessage(null)
    try {
      await api.saveSettings({
        ...form,
        watchlist: watchlistText
          .split(',')
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
      })
      setMessage('Settings saved.')
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (e) {
      setMessage(String(e))
    }
  }

  const saveKeys = async () => {
    setMessage(null)
    try {
      await api.saveApiKeys(apiKey, apiSecret)
      setApiKey('')
      setApiSecret('')
      setMessage(
        'API keys stored (encrypted). They will never be displayed again.',
      )
      void queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      void queryClient.invalidateQueries({ queryKey: ['portfolio-status'] })
    } catch (e) {
      setMessage(String(e))
    }
  }

  const removeKeys = async () => {
    await api.deleteApiKeys()
    setMessage('API keys removed.')
    void queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    void queryClient.invalidateQueries({ queryKey: ['portfolio-status'] })
  }

  return (
    <div className="grid max-w-3xl gap-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="rounded border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium uppercase text-zinc-400">
          General
        </h2>
        {form && (
          <div className="grid gap-3">
            <label className="text-sm">
              <div className="text-xs text-zinc-500">
                Watchlist (comma-separated)
              </div>
              <textarea
                aria-label="Watchlist"
                value={watchlistText}
                onChange={(e) => setWatchlistText(e.target.value)}
                rows={2}
                className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
              />
            </label>
            <div className="flex gap-3">
              {(
                [
                  ['fee_bps', 'Taker fee (bps)'],
                  ['slippage_bps', 'Slippage (bps)'],
                  ['whale_threshold_usd', 'Whale threshold (USD)'],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="text-sm">
                  <div className="text-xs text-zinc-500">{label}</div>
                  <input
                    type="number"
                    aria-label={label}
                    value={form[key]}
                    onChange={(e) =>
                      setForm({ ...form, [key]: Number(e.target.value) })
                    }
                    className="w-36 rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
                  />
                </label>
              ))}
            </div>
            <button
              onClick={() => void saveGeneral()}
              className="w-fit rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
            >
              Save settings
            </button>
          </div>
        )}
      </section>

      <section className="rounded border border-zinc-800 p-4">
        <h2 className="mb-1 text-sm font-medium uppercase text-zinc-400">
          Binance API keys (read-only)
        </h2>
        <p className="mb-3 text-xs text-zinc-500">
          Used only for the read-only Portfolio view. Stored encrypted at rest;
          never returned to the browser after saving. Use keys WITHOUT trade
          permissions.
        </p>
        <p className="mb-3 text-sm" data-testid="keys-status">
          Status:{' '}
          {keysQuery.data?.configured ? (
            <span className="text-emerald-400">configured</span>
          ) : (
            <span className="text-zinc-500">not configured</span>
          )}
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <div className="text-xs text-zinc-500">API key</div>
            <input
              aria-label="API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-64 rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
            />
          </label>
          <label className="text-sm">
            <div className="text-xs text-zinc-500">API secret</div>
            <input
              type="password"
              aria-label="API secret"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              className="w-64 rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
            />
          </label>
          <button
            onClick={() => void saveKeys()}
            disabled={apiKey.length < 10 || apiSecret.length < 10}
            className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            Save keys
          </button>
          {keysQuery.data?.configured && (
            <button
              onClick={() => void removeKeys()}
              className="rounded bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-500"
            >
              Remove keys
            </button>
          )}
        </div>
      </section>

      {message && <p className="text-sm text-zinc-300">{message}</p>}
    </div>
  )
}
