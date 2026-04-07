import { NavLink, Outlet } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Workspace' },
  { to: '/settings', label: 'Settings' },
  { to: '/sessions', label: 'Sessions' },
] as const

export function Layout() {
  return (
    <div className="flex h-screen bg-base">
      <nav className="w-56 flex-shrink-0 bg-surface border-r border-border-subtle flex flex-col">
        <div className="p-6 pb-4">
          <h1 className="text-xl font-bold text-brand">Clef</h1>
          <p className="text-xs text-muted mt-1">AI Music Composition</p>
        </div>
        <ul className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ to, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `block px-3 py-2 rounded-lg text-sm font-bold transition-colors duration-150 ${
                    isActive
                      ? 'bg-surface-mid text-white'
                      : 'text-silver hover:text-white hover:bg-surface-hover'
                  }`
                }
              >
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
