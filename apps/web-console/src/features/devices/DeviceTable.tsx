import { Link } from 'react-router-dom'
import type { Device } from '../../api/types'
import { relativeTime } from '../../lib/guardian'
import { StatusBadge } from '../../components/StatusBadge'

function shortId(value: string) { return value.length > 12 ? `${value.slice(0, 8)}…` : value }

export function DeviceTable({ devices }: { devices: Device[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Dispositivo</th><th>Estado</th><th>Plataforma</th><th>Agente</th><th>Última conexión</th></tr></thead>
        <tbody>
          {devices.map((device) => (
            <tr key={device.device_id}>
              <td><Link className="primary-link" to={`/devices/${device.device_id}`}>{shortId(device.device_id)}</Link><small>Activo {shortId(device.guardian_asset_id)}</small></td>
              <td><StatusBadge value={device.state} /></td>
              <td>{device.platform === 'windows' ? 'Windows' : device.platform} {device.platform_version}</td>
              <td>{device.agent_version}</td>
              <td title={new Date(device.last_seen_at).toLocaleString()}>{relativeTime(device.last_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
