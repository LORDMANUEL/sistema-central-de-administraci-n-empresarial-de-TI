import { useState, type FormEvent } from 'react'
import { ShieldCheck } from 'lucide-react'
import { Navigate } from 'react-router-dom'
import { useSession } from '../session/SessionContext'

export function LoginPage() {
  const { user, login, bootstrap } = useSession()
  const [mode, setMode] = useState<'login' | 'bootstrap'>('login')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (user) return <Navigate to="/" replace />

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (mode === 'bootstrap') await bootstrap(email, displayName, password)
      else await login(email, password)
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo completar la autenticación') } finally { setBusy(false) }
  }

  return <div className="login-page"><div className="login-panel"><div className="login-brand"><div className="brand-mark brand-mark--large"><ShieldCheck size={28} /></div><div><strong>IT Guardian</strong><span>Endpoint Operations</span></div></div><div className="login-copy"><h1>{mode === 'bootstrap' ? 'Configura el primer administrador.' : 'Control central, sin perder trazabilidad.'}</h1><p>{mode === 'bootstrap' ? 'Este flujo funciona una sola vez en una instalación nueva y crea la cuenta platform_admin inicial.' : 'Accede a dispositivos, telemetría, comandos autorizados y auditoría desde una sola consola.'}</p></div><form onSubmit={submit} className="login-form">{mode === 'bootstrap' && <label>Nombre del administrador<input required maxLength={120} autoComplete="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></label>}<label>Correo electrónico<input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>Contraseña<input type="password" required minLength={mode === 'bootstrap' ? 12 : 1} autoComplete={mode === 'bootstrap' ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} /></label>{error && <p className="form-error">{error}</p>}<button className="button button--primary button--full" disabled={busy}>{busy ? 'Procesando…' : mode === 'bootstrap' ? 'Crear administrador' : 'Iniciar sesión'}</button></form><button className="login-mode" type="button" onClick={() => { setMode(mode === 'login' ? 'bootstrap' : 'login'); setError('') }}>{mode === 'login' ? '¿Instalación nueva? Configurar primer administrador' : 'Volver al inicio de sesión'}</button><p className="security-note">La sesión de Guardian permanece protegida en el servidor; el navegador no almacena los tokens de acceso.</p></div><div className="login-visual"><div className="signal-grid" /><div className="login-visual-copy"><span>OPERATIONS CORE</span><strong>Identidad · Activos · mTLS · Telemetría · Auditoría</strong><p>El plano administrativo se mantiene separado del plano seguro de dispositivos.</p></div></div></div>
}
