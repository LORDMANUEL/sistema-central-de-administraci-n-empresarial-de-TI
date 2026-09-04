import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TenantScopeProvider, useTenantScope } from './TenantScopeContext'

vi.mock('../session/SessionContext', () => ({
  useSession: () => ({ user: { id: 'u1', role: 'platform_admin' }, loading: false }),
}))

function Probe() {
  const scope = useTenantScope()
  return <div>
    <span data-testid="tenant">{scope.tenantId}</span>
    <span data-testid="site">{scope.siteId}</span>
    <select aria-label="tenant" value={scope.tenantId} onChange={(e) => scope.setTenantId(e.target.value)}>
      {scope.tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
    </select>
    <select aria-label="site" value={scope.siteId} onChange={(e) => scope.setSiteId(e.target.value)}>
      <option value="">Todas</option>
      {scope.sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}
    </select>
  </div>
}

it('selects first accessible tenant and resets site when tenant changes without browser persistence', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input); calls.push(url)
    if (url.endsWith('/console/api/tenants')) return new Response(JSON.stringify([
      { id: 't1', name: 'Tenant One', slug: 'one', status: 'active', timezone: 'UTC', locale: 'es', created_at: '', updated_at: '' },
      { id: 't2', name: 'Tenant Two', slug: 'two', status: 'active', timezone: 'UTC', locale: 'es', created_at: '', updated_at: '' },
    ]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (url.endsWith('/console/api/tenants/t1/sites')) return new Response(JSON.stringify([{ id: 's1', tenant_id: 't1', code: 'S1', name: 'Site One', status: 'active', timezone: null, country_code: null, region: null, city: null, address_line1: null }]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (url.endsWith('/console/api/tenants/t2/sites')) return new Response(JSON.stringify([{ id: 's2', tenant_id: 't2', code: 'S2', name: 'Site Two', status: 'active', timezone: null, country_code: null, region: null, city: null, address_line1: null }]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    throw new Error(`unexpected fetch ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><TenantScopeProvider><Probe /></TenantScopeProvider></QueryClientProvider>)
  await waitFor(() => expect(screen.getByTestId('tenant')).toHaveTextContent('t1'))
  await waitFor(() => expect(screen.getByRole('option', { name: 'Site One' })).toBeInTheDocument())
  fireEvent.change(screen.getByLabelText('site'), { target: { value: 's1' } })
  expect(screen.getByTestId('site')).toHaveTextContent('s1')
  fireEvent.change(screen.getByLabelText('tenant'), { target: { value: 't2' } })
  await waitFor(() => expect(screen.getByTestId('site')).toHaveTextContent(''))
  await waitFor(() => expect(screen.getByRole('option', { name: 'Site Two' })).toBeInTheDocument())
  expect(calls).toContain('/console/api/tenants/t2/sites')
  expect(localStorage.length).toBe(0)
  expect(sessionStorage.length).toBe(0)
  vi.restoreAllMocks()
})
