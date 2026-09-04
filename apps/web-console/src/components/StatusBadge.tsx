export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase()
  const tone = ['online', 'active', 'succeeded', 'valid', 'enrolled'].includes(normalized)
    ? 'success'
    : ['offline', 'failed', 'revoked', 'suspended', 'invalid'].includes(normalized)
      ? 'danger'
      : ['queued', 'leased', 'running', 'reserved', 'pending'].includes(normalized)
        ? 'warning'
        : 'neutral'
  return <span className={`status status--${tone}`}>{value.toUpperCase()}</span>
}
