import { Activity, Building2, ClipboardList, Command, Cpu, LogOut, PackageSearch, ScrollText, ShieldCheck, Users } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../session/SessionContext'
import { useTenantScope } from '../scope/TenantScopeContext'
import { canNavigate, type ConsoleSection } from './permissions'

const navigation = [
  ['/', 'Overview', Activity, 'overview'],
  ['/devices', 'Dispositivos', Cpu, 'devices'],
  ['/assets', 'Activos', PackageSearch, 'assets'],
  ['/commands', 'Comandos', Command, 'commands'],
  ['/enrollment', 'Enrollment', ShieldCheck, 'enrollment'],
  ['/organization', 'Organización', Building2, 'organization'],
  ['/audit', 'Auditoría', ScrollText, 'audit'],
  ['/users', 'Usuarios', Users, 'users'],
] as const satisfies ReadonlyArray<readonly [string, string, typeof Activity, ConsoleSection]>

const titles: Record<string, string> = {
  '/': 'Overview', '/devices': 'Dispositivos', '/assets': 'Activos', '/commands': 'Comandos', '/enrollment': 'Enrollment', '/organization': 'Organización', '/audit': 'Auditoría', '/users': 'Usuarios',
}

export function AppShell() {
  const { user, logout } = useSession()
  const scope = useTenantScope()
  const location = useLocation()
  const base = `/${location.pathname.split('/')[1]}`
  const title = location.pathname === '/' ? 'Overview' : titles[base] ?? 'IT Guardian'
  const role = user?.role ?? 'viewer'
  const visibleNavigation = navigation.filter(([, , , section]) => canNavigate(role, section))

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><ShieldCheck size={20} /></div><div><strong>IT Guardian</strong><span>Central</span></div></div>
        <nav>
          {visibleNavigation.map(([path, label, Icon]) => (
            <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}><Icon size={18} /><span>{label}</span></NavLink>
          ))}
        </nav>
        <div className="sidebar-foot"><ClipboardList size={16} /><span>Core v0.8 certificado</span></div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div><h1>{title}</h1><p>Administración central de endpoints</p></div>
          <div className="topbar-actions">
            {user && <div className="scope-selectors" aria-label="Alcance administrativo">
              <label>
                <span>Empresa</span>
                <select aria-label="Seleccionar empresa" value={scope.tenantId} disabled={scope.loading || scope.tenants.length === 0} onChange={(event) => scope.setTenantId(event.target.value)}>
                  {scope.tenants.length === 0 && <option value="">Sin empresas</option>}
                  {scope.tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
                </select>
              </label>
              <label>
                <span>Sede</span>
                <select aria-label="Seleccionar sede" value={scope.siteId} disabled={!scope.tenantId || scope.loading} onChange={(event) => scope.setSiteId(event.target.value)}>
                  <option value="">Todas las sedes</option>
                  {scope.sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}
                </select>
              </label>
            </div>}
            <div className="user-menu"><div><strong>{user?.display_name}</strong><span>{user?.role.replaceAll('_', ' ')}</span></div><button className="icon-button" onClick={() => void logout()} aria-label="Cerrar sesión"><LogOut size={18} /></button></div>
          </div>
        </header>
        {scope.error && <div className="scope-error" role="alert">No se pudo cargar el alcance: {scope.error.message}</div>}
        <div className="content"><Outlet /></div>
      </main>
    </div>
  )
}
