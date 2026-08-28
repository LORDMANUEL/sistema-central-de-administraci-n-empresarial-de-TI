import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useSession } from './session/SessionContext'
import { LoadingState } from './components/PageState'
import { AppShell } from './layout/AppShell'
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

function Protected() { const { user, loading } = useSession(); if (loading) return <LoadingState label="Validando sesión…"/>; return user ? <Outlet/> : <Navigate to="/login" replace/> }

export function App(){return <Routes><Route path="/login" element={<LoginPage/>}/><Route element={<Protected/>}><Route element={<AppShell/>}><Route index element={<OverviewPage/>}/><Route path="devices" element={<DevicesPage/>}/><Route path="devices/:deviceId" element={<DeviceDetailPage/>}/><Route path="assets" element={<AssetsPage/>}/><Route path="commands" element={<CommandsPage/>}/><Route path="enrollment" element={<EnrollmentPage/>}/><Route path="organization" element={<OrganizationPage/>}/><Route path="audit" element={<AuditPage/>}/><Route path="users" element={<UsersPage/>}/></Route></Route><Route path="*" element={<Navigate to="/" replace/>}/></Routes>}
