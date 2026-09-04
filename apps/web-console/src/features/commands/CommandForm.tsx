import { useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { Command, Device } from '../../api/types'
import { buildCommandPayload, type CommandType } from '../../lib/guardian'

export function CommandForm({ device }: { device: Device }) {
  const queryClient = useQueryClient()
  const [type, setType] = useState<CommandType>('inventory.refresh')
  const [delay, setDelay] = useState(0)
  const [serviceName, setServiceName] = useState('')
  const [validation, setValidation] = useState('')
  const mutation = useMutation({
    mutationFn: (payload: ReturnType<typeof buildCommandPayload>) => api.post<Command>('/commands', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['commands'] })
      setValidation('')
    },
  })

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      const payload = buildCommandPayload({ device, type, delaySeconds: delay, serviceName })
      await mutation.mutateAsync(payload)
    } catch (error) {
      setValidation(error instanceof Error ? error.message : 'Comando inválido')
    }
  }

  return (
    <form className="command-form" onSubmit={submit}>
      <label>Acción<select value={type} onChange={(event) => setType(event.target.value as CommandType)}>
        <option value="inventory.refresh">Actualizar inventario</option>
        <option value="device.reboot">Reiniciar dispositivo</option>
        <option value="service.restart">Reiniciar servicio</option>
      </select></label>
      {type === 'device.reboot' && <label>Retraso (segundos)<input type="number" min={0} max={3600} value={delay} onChange={(event) => setDelay(Number(event.target.value))} /></label>}
      {type === 'service.restart' && <label>Nombre del servicio<input value={serviceName} maxLength={128} onChange={(event) => setServiceName(event.target.value)} placeholder="Spooler" /></label>}
      <button className="button button--primary" disabled={mutation.isPending}>{mutation.isPending ? 'Enviando…' : 'Ejecutar comando'}</button>
      {(validation || mutation.error) && <p className="form-error">{validation || (mutation.error as Error).message}</p>}
      {mutation.isSuccess && <p className="form-success">Comando creado: {mutation.data.command_id.slice(0, 8)}…</p>}
    </form>
  )
}
