import { Activity, Building2, ClipboardList, Command, Cpu, LogOut, PackageSearch, ScrollText, ShieldCheck, Users } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../session/SessionContext'

const navigation = [
  ['/', 'Overview', Activity],
  ['/devices', 'Dispositivos', Cpu],
  ['/assets', 'Activos', PackageSearch],
  ['/commands', 'Comandos', Command],
  ['/enrollment', 'Enrollment', ShieldCheck],
  ['/organization', 'Organización', Building2],
  ['/audit', 'Auditoría', ScrollText],
  ['/users', 'Usuarios', Users],
] as const

const titles: Record<string, string> = {
  '/': 'Overview', '/devices': 'Dispositivos', '/assets': 'Activos', '/commands': 'Comandos', '/enrollment': 'Enrollment', '/organization': 'Organización', '/audit': 'Auditoría', '/users': 'Usuarios',
}

export function AppShell() {
  const { user, logout } = useSession()
  const location = useLocation()
  const base = `/${location.pathname.split('/')[1]}`
  const title = location.pathname === '/' ? 'Overview' : titles[base] ?? 'IT Guardian'
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><ShieldCheck size={20} /></div><div><strong>IT Guardian</strong><span>Central</span></div></div>
        <nav>
          {navigation.map(([path, label, Icon]) => (
            <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}><Icon size={18} /><span>{label}</span></NavLink>
          ))}
        </nav>
        <div className="sidebar-foot"><ClipboardList size={16} /><span>Core v0.7 certificado</span></div>
      </aside>
      <main className="main-area">
        <header className="topbar"><div><h1>{title}</h1><p>Administración central de endpoints</p></div><div className="user-menu"><div><strong>{user?.display_name}</strong><span>{user?.role.replaceAll('_', ' ')}</span></div><button className="icon-button" onClick={() => void logout()} aria-label="Cerrar sesión"><LogOut size={18} /></button></div></header>
        <div className="content"><Outlet /></div>
      </main>
    </div>
  )
}
