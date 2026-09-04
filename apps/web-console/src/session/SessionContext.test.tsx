import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SessionProvider, useSession } from './SessionContext'

function Probe() {
  const session = useSession()
  if (session.loading) return <div>loading</div>
  return <div>{session.user?.email ?? 'anonymous'}</div>
}

it('loads current session through cookie credentials without browser token storage', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ user: { id: 'u1', email: 'admin@example.com', display_name: 'Admin', role: 'platform_admin', is_active: true } }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SessionProvider><Probe /></SessionProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByText('admin@example.com')).toBeInTheDocument())
  expect(fetchMock).toHaveBeenCalledWith('/console/api/session/me', expect.objectContaining({ credentials: 'include' }))
  fetchMock.mockRestore()
})
