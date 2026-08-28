# IT Guardian v0.7.0 — Windows Agent Modern + Device Edge mTLS

## Estado y objetivo

`main` v0.6.0 ya certifica Identity, Tenant, Asset, Enrollment/PKI, Gateway/Audit y el plano operativo Agent Control + Command + Telemetry. v0.7.0 debe convertir ese core en un producto que administre un endpoint Windows real sin degradar el modelo de seguridad.

La entrega se considera terminada únicamente cuando un Windows Agent real pueda enrolarse, conservar su identidad criptográfica, autenticarse por mTLS, reportar heartbeat/telemetry, recibir y ejecutar únicamente comandos tipados permitidos, tolerar desconexiones y recuperarse de una actualización fallida.

## Decisión arquitectónica

v0.7.0 se divide en dos componentes que forman una sola capacidad:

1. **Device Edge mTLS**: borde de confianza para tráfico `/api/v1/device/*`. Valida el certificado cliente, deriva la identidad del URI SAN SPIFFE emitido por PKI, elimina cualquier header de identidad aportado por el cliente e inyecta el principal normalizado que los servicios v0.6 ya consumen.
2. **Windows Agent Modern**: binario Go instalado como servicio Windows no interactivo. Genera su propia private key, se enrola mediante el Gateway, guarda credenciales localmente, establece mTLS con Device Edge y opera contra Agent Control/Command/Telemetry.

El Gateway administrativo sigue siendo el borde bearer/JWT. Device Edge no sustituye Gateway y no expone APIs administrativas.

## Límites de seguridad

- El agente nunca envía `X-Guardian-Tenant-ID`, `X-Guardian-Asset-ID`, `X-Guardian-Device-ID`, `X-Guardian-Certificate-Serial` ni `X-Guardian-Proxy-Token`.
- Device Edge descarta cualquier `X-Guardian-*`, `Forwarded`, `X-Forwarded-*`, `Host` y headers hop-by-hop recibidos antes de construir la petición upstream.
- La identidad se obtiene de exactamente un URI SAN con formato `spiffe://guardian/tenant/{tenant_id}/asset/{asset_id}/device/{device_id}` y del serial X.509 validado.
- Device Edge solo monta CA/cadena pública para trust y su propio TLS server key/certificate. Nunca recibe Root/Intermediate private keys de PKI.
- El agente genera ECDSA P-256 localmente. La private key no sale del endpoint.
- En Windows, la private key se persiste cifrada mediante DPAPI LocalMachine y el directorio de estado se restringe al servicio/administradores.
- No existe shell remoto arbitrario. v0.7 ejecuta solo `inventory.refresh`, `device.reboot` y `service.restart` con los esquemas ya definidos en Command Service.
- `service.restart` usa Windows Service Control Manager; no construye `cmd.exe`, PowerShell ni una línea de shell a partir de datos remotos.
- TLS server verification nunca puede desactivarse por configuración de producción.

## Device Edge

### Interfaz northbound

Escucha HTTPS, por defecto `:8443`, con `ClientAuth = RequireAndVerifyClientCert`.

Allowlist exacta:

- `POST /api/v1/device/heartbeat` -> Agent Control `:8007`.
- `POST /api/v1/device/commands/acquire` -> Command `:8008`.
- `POST /api/v1/device/commands/{uuid}/running` -> Command `:8008`.
- `POST /api/v1/device/commands/{uuid}/result` -> Command `:8008`.
- `POST /api/v1/device/telemetry` -> Telemetry `:8009`.
- `GET /health/live` y `GET /health/ready` son locales al edge.

Cualquier otra ruta devuelve 404 y nunca selecciona upstream desde input del cliente.

### Principal normalizado

Después de validar la cadena cliente, Device Edge extrae:

- `tenant_id` UUID;
- `guardian_asset_id` UUID;
- `device_id` UUID;
- `certificate_serial` hexadecimal canónico.

Solo entonces inyecta al upstream:

- `X-Guardian-Proxy-Token` desde secreto local del edge;
- `X-Guardian-Tenant-ID`;
- `X-Guardian-Asset-ID`;
- `X-Guardian-Device-ID`;
- `X-Guardian-Certificate-Serial`.

### Revocación

Device Edge carga una CRL PEM firmada por la CA de dispositivos. Al iniciar valida firma/issuer contra la cadena confiable configurada. Un serial presente en CRL se rechaza antes del proxy. La CRL se relee periódicamente sin detener conexiones sanas; si una recarga falla, se conserva la última CRL válida y se expone estado degradado en readiness.

## Windows Agent

### Estructura de ejecución

Un solo `itguardian-agent.exe` soporta:

- `enroll --token <one-time-token>`: bootstrap interactivo/automatizable que genera clave/CSR y obtiene certificado.
- `run`: modo foreground para pruebas y soporte.
- ejecución sin argumentos bajo Windows Service Control Manager.
- `version`: imprime versión y commit cuando están embebidos por CI.

La configuración no secreta se guarda en `%ProgramData%\ITGuardian\Agent\config.json`. Estado y spool viven bajo el mismo árbol con ACL restringida.

### Enrollment

1. Rechaza re-enrollment destructivo si ya existe identidad válida salvo `--rotate` explícito.
2. Genera ECDSA P-256 y CSR con CN igual al hostname.
3. Envía a Gateway `POST /api/v1/enrollments` con token, platform=`windows`, hostname, agent_version y CSR.
4. Verifica que el certificado devuelto corresponda a la private key generada.
5. Verifica el URI SAN y que `device_id`, `tenant_id`, `asset_id` coincidan con el JSON de respuesta.
6. Persiste certificado/cadena y private key cifrada; elimina cualquier token temporal.
7. Persiste `device_id`, `tenant_id`, `asset_id`, serial/fingerprint y un `session_id` estable.

### Heartbeat y capabilities

Envía el contrato v0.6 con:

- `agent_version`;
- `platform=windows`;
- `platform_version`;
- `session_id` persistente;
- `capability_version=1`;
- capacidades: `heartbeat.v1`, `telemetry.v1`, `inventory.v1`, `command.inventory_refresh.v1`, `command.device_reboot.v1`, `command.service_restart.v1`, `spool.v1`, `update.v1`.

Respeta los intervalos devueltos por Agent Control dentro de límites locales seguros.

### Telemetry e inventario base

Telemetry produce únicamente métricas admitidas por v0.6:

- `cpu.utilization_pct`;
- `memory.total_bytes`;
- `memory.used_bytes`;
- `disk.total_bytes{volume}`;
- `disk.free_bytes{volume}`;
- `network.rx_bytes_total` y `network.tx_bytes_total` cuando Windows expone contadores válidos.

El inventario base se serializa localmente y `inventory.refresh` fuerza recolección inmediata. v0.7 no agrega todavía un Software Service; el inventario de SO/hardware se refleja en heartbeat/telemetry y queda preparado para v0.9 sin inventar endpoints nuevos.

### Command lifecycle

Para cada comando adquirido:

1. Valida tipo y argumentos localmente contra la misma allowlist de v0.6.
2. Envía `running` con execution token.
3. Ejecuta sin shell arbitrario.
4. Devuelve exactamente un resultado terminal lógico con `result_sequence=1`.
5. Si la red falla, el resultado se persiste en spool y se reintenta idempotentemente con el mismo command/execution token/payload.

Implementación:

- `inventory.refresh`: recolecta heartbeat/telemetry inmediatamente y termina succeeded si la recolección local es válida.
- `device.reboot`: acepta solo `delay_seconds` 0..3600 y usa API Windows de shutdown/reboot; en pruebas el executor se sustituye por interfaz, nunca reinicia el runner CI.
- `service.restart`: valida `service_name` y usa SCM Stop/Start con timeout acotado.

### Offline spool y backoff

Spool persistente, bounded y crash-safe:

- resultados de comando no confirmados;
- batches de telemetry no confirmados.

Cada item tiene UUID/digest estable. Se escribe archivo temporal + fsync + rename atómico. Límite inicial 64 MiB y 10,000 items; al alcanzar límite se preservan primero resultados de comando y se descarta telemetry más antigua con métrica/log explícito.

Retry: exponencial con jitter, base 1 s, cap 5 min. Un éxito resetea el backoff.

### Actualización y rollback

El updater usa un manifest JSON canónico firmado con Ed25519 y una public key fija/configurada en instalación. El manifest contiene versión, URL, SHA-256 y tamaño. Flujo:

1. verifica firma Ed25519;
2. rechaza downgrade salvo rollback explícito;
3. descarga a staging con límite de tamaño;
4. valida SHA-256 antes de ejecutar;
5. conserva el binario anterior;
6. instala la versión nueva mediante helper separado;
7. exige health marker del agente nuevo;
8. si no aparece en ventana definida, restaura el binario anterior y reinicia servicio.

CI prueba firma válida, firma inválida, hash inválido y rollback simulado. La clave privada de release no vive en el repositorio.

## Instalación Windows

CI produce:

- `itguardian-agent-windows-amd64.exe`;
- `itguardian-agent-windows-arm64.exe` si todos los paquetes Windows compilan para arm64;
- MSI x64 mediante WiX para instalación de servicio bajo `NT AUTHORITY\LocalService`;
- `SHA256SUMS.txt` para cada artefacto.

El MSI crea `%ProgramData%\ITGuardian\Agent`, aplica permisos restrictivos, instala el servicio con startup automático retrasado y no incorpora enrollment tokens ni secretos de servidor.

## CI y gates

Workflow `windows-agent-ci.yml` debe ejecutar:

- tests puros Go en Linux cuando no dependan de Windows;
- `GOOS=windows GOARCH=amd64 go test`/compile de paquetes Windows mediante separación por build tags;
- build amd64/arm64;
- tests del Device Edge, incluyendo spoofing, SAN inválido, certificado no confiable, revocado y route allowlist;
- test de enrollment con PKI/certificado real en el clean-stack;
- Device Edge mTLS -> heartbeat -> ONLINE;
- telemetry -> latest;
- command -> Windows agent foreground/simulator-compatible executor -> running/result;
- caída temporal del upstream/red -> spool -> recuperación;
- update verifier + rollback simulado;
- secret scan básico;
- hashes reproducibles sobre el SHA candidato.

## Definition of Done v0.7

Se marca DONE solo si sobre un mismo SHA candidato:

- todos los CI v0.1–v0.6 siguen verdes;
- Device Edge construye non-root y valida mTLS/CRL;
- ningún header de identidad del cliente puede suplantar el certificado;
- un agente Windows se enrola con key local y certificado real;
- heartbeat muestra ONLINE;
- telemetry CPU/RAM/disco llega al core;
- los tres comandos tipados completan lifecycle sin shell arbitrario;
- spool resiste reinicio/desconexión y drena idempotentemente;
- updater rechaza paquetes no firmados/corruptos y rollback está probado;
- EXE/MSI versionados + SHA-256 salen de CI;
- pruebas Windows 10/11 quedan representadas en runner Windows y matriz documentada;
- `README.md`, `ROADMAP.md`, `MASTER.md`, `CHANGELOG.md` y `VERSION` se promueven a 0.7.0 únicamente después de la certificación.

Windows 7/8/8.1 permanece como matriz legacy separada y no degrada el agente moderno.