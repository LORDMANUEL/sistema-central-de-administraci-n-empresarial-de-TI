export function LoadingState({ label = 'Cargando…' }: { label?: string }) {
  return <div className="page-state"><span className="spinner" />{label}</div>
}

export function ErrorState({ message = 'No se pudo cargar la información.' }: { message?: string }) {
  return <div className="page-state page-state--error">{message}</div>
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="empty-state"><strong>{title}</strong><span>{body}</span></div>
}
