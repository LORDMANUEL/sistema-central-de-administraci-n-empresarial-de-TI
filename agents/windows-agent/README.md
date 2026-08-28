# IT Guardian Windows Agent 0.7.0

Windows Agent Modern es un servicio no interactivo para endpoints administrados. Se enrola una vez por Gateway, genera la private key localmente, la protege con DPAPI LocalMachine y después se comunica con Device Edge únicamente por mTLS.

## Target v0.7

- Windows 10/11 moderno x64.
- arm64 compile-gated en CI.
- Windows 7/8/8.1 pertenece a la matriz Legacy y no comparte el gate moderno.
- No existe shell remoto arbitrario.

## Directorio de datos

`C:\ProgramData\ITGuardian\Agent`

- `agent.example.json`: template válido instalado por MSI.
- `agent.json`: configuración runtime no-secret.
- `device-edge-ca.pem`: CA pública del HTTPS de Device Edge.
- `identity.json`: IDs, certificado/chain, session ID y private key protegida por DPAPI.
- `spool\`: cola offline acotada.
- `update-healthy`: health marker del updater.

El enrollment token one-time nunca se escribe en `agent.json` ni `identity.json`.

## Instalación

1. Instale `ITGuardian-Agent-0.7.0-x64.msi`.
2. Copie la CA pública de Device Edge a `device-edge-ca.pem`.
3. Copie `agent.example.json` a `agent.json` y cambie `device_edge_url`.
4. Cree un enrollment token para el activo.
5. Ejecute:

```powershell
& 'C:\Program Files\IT Guardian\itguardian-agent.exe' enroll `
  --gateway https://guardian.example.com `
  --token '<ONE_TIME_TOKEN>' `
  --state 'C:\ProgramData\ITGuardian\Agent\identity.json'
```

6. Inicie el servicio:

```powershell
Start-Service ITGuardianAgent
```

El MSI registra `ITGuardianAgent` como LocalService, Auto + delayed-auto, pero lo deja detenido para evitar arrancar un endpoint no enrolado.

## Runtime

```text
DPAPI identity
  -> mTLS Device Edge
  -> heartbeat/capabilities
  -> CPU/RAM/disk telemetry
  -> acquire typed command
  -> running
  -> WinAPI/SCM execution
  -> idempotent terminal result
  -> offline spool/retry
```

Comandos 0.7: `inventory.refresh`, `device.reboot`, `service.restart`.

## Offline

- 64 MiB máximo.
- 10,000 items máximo.
- Resultados terminales tienen prioridad sobre telemetry.
- IDs estables impiden mutación del payload bajo retry.
- Backoff exponencial con jitter: 1 s hasta 5 min.
- Un comando no se reejecuta solo porque falló el upload de su resultado.

## Updates firmados

Updates están deshabilitados por defecto. Para habilitarlos, `agent.json` debe incluir los cuatro campos:

```json
{
  "update_manifest_url": "https://updates.example.com/itguardian/manifest.json",
  "update_public_key": "<BASE64_ED25519_PUBLIC_KEY>",
  "update_max_bytes": 67108864,
  "update_health_timeout_seconds": 120
}
```

La clave pública debe ser una Ed25519 válida de 32 bytes codificada en base64. La URL debe ser HTTPS.

```powershell
& 'C:\Program Files\IT Guardian\itguardian-agent.exe' update `
  --config 'C:\ProgramData\ITGuardian\Agent\agent.json'
```

Flujo:

1. descarga manifest acotado;
2. verifica firma Ed25519 y SemVer anti-downgrade;
3. descarga payload acotado;
4. verifica tamaño y SHA-256 streaming;
5. publica staged binary atómicamente;
6. lanza una copia fija del propio agente como helper interno;
7. helper espera salida del padre, detiene únicamente `ITGuardianAgent`, activa staged y reinicia;
8. el nuevo proceso debe completar un ciclo real y escribir `update-healthy`;
9. health válido elimina previous; timeout restaura previous y reinicia.

No se acepta URL/clave arbitraria en `update` y `apply-update` es una operación interna validada contra la ruta fija del helper.

## Verificación

CI v0.7 ejecuta:

- `go test -race ./...` y `go vet ./...`;
- scans contra `InsecureSkipVerify` y shell remoto en command executor;
- tests Windows, build x64 y compile arm64;
- WiX MSI x64;
- instalación/desinstalación MSI real;
- verificación LocalService, Auto, delayed-auto y servicio detenido antes de enrollment;
- hashes SHA-256;
- clean-stack mTLS del servidor/Device Edge.

La matriz física por edición/hardware Windows 10/11 es validación de campo adicional; no se presenta el runner hospedado como hardware físico probado.
