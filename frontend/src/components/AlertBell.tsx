import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTopic } from '../ws/hooks'

interface AlertMsg {
  rule_name: string
  message: string
  ts: number
}

/** Command-bar bell: live unread count + recent alerts dropdown. */
export default function AlertBell() {
  const [recent, setRecent] = useState<AlertMsg[]>([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)

  useTopic('alerts', (data) => {
    const msg = data as AlertMsg
    setRecent((prev) => [msg, ...prev].slice(0, 12))
    setUnread((n) => n + 1)
  })

  return (
    <div className="relative">
      <button
        onClick={() => {
          setOpen((v) => !v)
          setUnread(0)
        }}
        aria-label={`alerts (${unread} unread)`}
        data-testid="alert-bell"
        className="relative cursor-pointer rounded-sm p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-amber-400"
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {unread > 0 && (
          <span
            data-testid="alert-unread"
            className="absolute -top-1 -right-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-amber-500 px-0.5 font-mono text-[8px] font-bold text-zinc-950"
          >
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-sm border border-zinc-700 bg-zinc-900 shadow-xl shadow-black/50">
          <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5">
            <span className="font-mono text-[10px] tracking-[0.14em] text-zinc-500 uppercase">
              Alerts
            </span>
            <Link
              to="/alerts"
              onClick={() => setOpen(false)}
              className="font-mono text-[10px] text-amber-400 uppercase hover:underline"
            >
              Manage →
            </Link>
          </div>
          <div className="max-h-72 overflow-y-auto font-mono text-[11px]">
            {recent.length === 0 && (
              <p className="px-3 py-3 text-zinc-600">No alerts this session.</p>
            )}
            {recent.map((a, i) => (
              <div
                key={i}
                className="border-t border-zinc-800/60 px-3 py-1.5 first:border-t-0"
              >
                <div className="text-zinc-100">{a.message}</div>
                <div className="text-[10px] text-zinc-600">
                  {a.rule_name} · {new Date(a.ts).toISOString().slice(11, 19)}{' '}
                  UTC
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
