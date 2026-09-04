import { createContext, useContext, type PropsWithChildren } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, setCsrfToken } from '../api/client'
import type { User } from '../api/types'

interface SessionResponse { user: User; csrf_token?: string }
interface SessionValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  bootstrap: (email: string, displayName: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient()
  const session = useQuery({
    queryKey: ['session'],
    queryFn: async () => {
      const data = await api.get<SessionResponse>('/session/me')
      setCsrfToken(data.csrf_token)
      return data
    },
    retry: false,
    staleTime: 30_000,
  })
  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) => api.post<SessionResponse>('/session/login', { email, password }),
    onSuccess: (data) => { setCsrfToken(data.csrf_token); queryClient.setQueryData(['session'], data) },
  })
  const bootstrapMutation = useMutation({
    mutationFn: ({ email, displayName, password }: { email: string; displayName: string; password: string }) => api.post<SessionResponse>('/session/bootstrap', { email, display_name: displayName, password }),
    onSuccess: (data) => { setCsrfToken(data.csrf_token); queryClient.setQueryData(['session'], data) },
  })
  const logoutMutation = useMutation({
    mutationFn: () => api.post<void>('/session/logout'),
    onSettled: () => { setCsrfToken(null); queryClient.setQueryData(['session'], null) },
  })

  const user = session.data?.user ?? null
  return (
    <SessionContext.Provider value={{
      user,
      loading: session.isLoading,
      login: async (email, password) => { await loginMutation.mutateAsync({ email, password }) },
      bootstrap: async (email, displayName, password) => { await bootstrapMutation.mutateAsync({ email, displayName, password }) },
      logout: async () => { await logoutMutation.mutateAsync() },
    }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used within SessionProvider')
  return value
}

export function isSessionError(error: unknown) {
  return error instanceof ApiError && error.status === 401
}
