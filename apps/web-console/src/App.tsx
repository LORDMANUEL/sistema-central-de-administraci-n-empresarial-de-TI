import type { ReactNode } from 'react'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useSession } from './session/SessionContext'
import { LoadingState } from './components/PageState'
import { AppShell } from './layout/AppShell'
import { canNavigate, type ConsoleSection } from './layout/permissions'
import { LoginPage } from './pages/LoginPage'
import { OverviewPage } from './pages/OverviewPage'
import { DevicesPage } from './pages/DevicesPage'
import { DeviceDetailPage } from './pages/DeviceDetailPage'
import { AssetsPage } from './pages/AssetsPage'
import { CommandsPage } from './pages/CommandsPage'
import { EnrollmentPage } from './pages/EnrollmentPage'
import { OrganizationPage } from './pages/OrganizationPage'
import { AuditPage } from './pages/AuditPage'
import { UsersPage } from './pages/UsersPage'

function Protected() {
  const { user, loading } = useSession()
  if (loading) return <LoadingState label="Validando sesión…" />
  return user ? <Outlet /> : <Navigate to="/login" replace />
}

function SectionGuard({ section, children }: { section: ConsoleSection; children: ReactNode }) {
  const { user } = useSession()
  if (!user || !canNavigate(user.role, section)) return <Navigate to="/" replace />
  return <>{children}</>
}

export function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<Protected />}>
      <Route element={<AppShell />}>
        <Route index element={<SectionGuard section="overview"><OverviewPage /></SectionGuard>} />
        <Route path="devices" element={<SectionGuard section="devices"><DevicesPage /></SectionGuard>} />
        <Route path="devices/:deviceId" element={<SectionGuard section="devices"><DeviceDetailPage /></SectionGuard>} />
        <Route path="assets" element={<SectionGuard section="assets"><AssetsPage /></SectionGuard>} />
        <Route path="commands" element={<SectionGuard section="commands"><CommandsPage /></SectionGuard>} />
        <Route path="enrollment" element={<SectionGuard section="enrollment"><EnrollmentPage /></SectionGuard>} />
        <Route path="organization" element={<SectionGuard section="organization"><OrganizationPage /></SectionGuard>} />
        <Route path="audit" element={<SectionGuard section="audit"><AuditPage /></SectionGuard>} />
        <Route path="users" element={<SectionGuard section="users"><UsersPage /></SectionGuard>} />
      </Route>
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}
