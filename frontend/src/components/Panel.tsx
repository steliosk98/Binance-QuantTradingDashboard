import type { ReactNode } from 'react'

/** Terminal panel: uppercase mono microlabel header, optional status dot. */
export default function Panel({
  title,
  status,
  right,
  children,
  className = '',
  testId,
}: {
  title: string
  status?: 'live' | 'idle' | 'warn'
  right?: ReactNode
  children: ReactNode
  className?: string
  testId?: string
}) {
  return (
    <section
      data-testid={testId}
      className={`panel-rise relative rounded-sm border border-zinc-800 bg-zinc-900/80 ${className}`}
    >
      <header className="flex items-center gap-2 border-b border-zinc-800 px-3 py-1.5">
        {status && (
          <span
            aria-label={status}
            className={`h-1.5 w-1.5 rounded-full ${
              status === 'live'
                ? 'animate-pulse-dot bg-emerald-400'
                : status === 'warn'
                  ? 'bg-amber-400'
                  : 'bg-zinc-600'
            }`}
          />
        )}
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
          {title}
        </h2>
        {right && <div className="ml-auto">{right}</div>}
      </header>
      {children}
    </section>
  )
}
