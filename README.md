# IT Guardian

Sistema Central de Administración Empresarial de TI, self-hosted y modular.

IT Guardian se construye por capacidades utilizables de punta a punta. Un módulo no se marca terminado solo por tener código: debe tener runtime real, pruebas, seguridad, Docker/instalador cuando aplique, integración y evidencia de CI.

## Estado del proyecto

**Release actual:** `0.7.0`  
**Core certificado:** Identity + Tenant + Asset + Enrollment + PKI + Gateway + Audit + Agent Control + Command + Telemetry + Device Edge + Windows Agent Modern  
**Siguiente gate:** `v0.8.0 — Web Console MVP`  
**Enterprise Stable:** todavía NO; v1.0.0 requiere cerrar los módulos posteriores del roadmap.

### Matriz de avance

| Componente | Estado | Release | Evidencia principal |
|---|---|---:|---|
| Identity Service | ✅ DONE | 0.1.0 | Argon2, JWT Ed25519/JWKS, RBAC |
| Tenant Service | ✅ DONE | 0.2.0 | tenants, sedes, departamentos, membresías |
| Asset Service | ✅ DONE | 0.3.0 | inventario canónico y correlación externa |
| Enrollment + PKI | ✅ DONE | 0.4.0 | token one-time, CSR, certificados, CRL |
| Gateway + Audit | ✅ DONE | 0.5.0 | borde administrativo, audit append-only/hash chain |
| Agent Control + Command + Telemetry | ✅ DONE | 0.6.0 | online/offline, jobs tipados, latest telemetry |
| Device Edge mTLS | ✅ DONE | 0.7.0 | identidad X.509/SPIFFE, CRL, allowlist, non-root |
| Windows Agent Modern | ✅ DONE | 0.7.0 | DPAPI, mTLS, telemetry, commands, spool, updater, MSI |
| Web Console MVP | 🟡 SIGUIENTE | 0.8.0 | administración visual del core |
| Software + Patch + Policy | ⬜ PENDIENTE | 0.9.0 | RMM básico |
| Tickets + Help Client | ⬜ PENDIENTE | 0.10.0 | ITSM inicial |
| Remote Support | ⬜ PENDIENTE | 0.11.0 | soporte remoto |
| Security + Wazuh + USB | ⬜ PENDIENTE | 0.12.0 | postura/endpoint security |
| Linux + macOS Agents | ⬜ PENDIENTE | 0.13.0 | agentes modernos multiplataforma |
| Servers + Zabbix + Printers | ⬜ PENDIENTE | 0.14.0 | infraestructura |
| Backup | ⬜ PENDIENTE | 0.15.0 | backup/restore |
| Network + Wi-Fi + VPN | ⬜ PENDIENTE | 0.16.0 | networking |
| Android/iOS MDM + Location | ⬜ PENDIENTE | 0.17.0 | movilidad |
| DFIR + Vulnerability | ⬜ PENDIENTE | 0.18.0 | respuesta/vulnerabilidades |
| Automation + Reports + Licensing | ⬜ PENDIENTE | 0.19.0 | automatización empresarial |
| RC integral | ⬜ PENDIENTE | 0.20.0-rc | hardening integral |
| Enterprise Stable | ⬜ PENDIENTE | 1.0.0 | producto empresarial completo |

## Arquitectura operativa actual

```text
Administradores / futura Web Console
             |
             v
       Gateway :8080
             |
  +----------+-----------+------------------+
  |          |           |                  |
Identity   Tenant      Asset        Enrollment -> PKI
  |          |           |                  |
  +----------+-----------+-----------> Audit

Windows Agent Modern
        |
        | HTTPS + mTLS (certificado de dispositivo)
        v
 Device Edge :8443
        |
        +----> Agent Control :8007
        +----> Command       :8008
        +----> Telemetry     :8009
```

El Gateway administrativo **no** expone `/api/v1/device/*`. Device Edge es el único borde del plano endpoint y deriva `tenant_id`, `guardian_asset_id`, `device_id` y serial exclusivamente del certificado X.509 validado; los headers `X-Guardian-*` enviados por el cliente se descartan.

## Certificación v0.7.0

El workflow `.github/workflows/windows-agent-ci.yml` certifica:

- `go test -race` + `go vet` del agente;
- rechazo de TLS inseguro y shell remoto arbitrario;
- tests/build de Device Edge y contenedor non-root;
- Windows x64 ejecutado en runner Windows y arm64 compile-gated;
- EXE x64 + EXE arm64 + MSI x64 + `SHA256SUMS.txt`;
- instalación/desinstalación MSI silenciosa real;
- servicio `ITGuardianAgent` bajo `NT AUTHORITY\LocalService`, Auto + `DelayedAutoStart=1`, detenido hasta enrollment;
- template `agent.example.json` válido y sin claves ficticias;
- clean-stack desde volúmenes vacíos;
- enrollment real con CSR/certificado;
- mTLS real contra Device Edge;
- spoofing de identidad bloqueado;
- heartbeat/ONLINE;
- telemetry y lectura `latest`;
- command acquire/running/result y replay idempotente;
- revocación del certificado y bloqueo mediante CRL;
- CA privada del TLS de Device Edge aislada del runtime.

La suite v0.6 también se reejecutó con el stack v0.7 y completó dos clean-stack, protegiendo regresiones del core anterior.

> La matriz física específica por edición/hardware Windows 10/11 es validación de compatibilidad de campo. El gate automatizado ejecuta el agente/MSI en runner Windows x64 y compila arm64; no se afirma hardware físico no probado.

## Servidor — instalación

### Requisitos

- Linux recomendado para producción;
- Windows con Docker Desktop/WSL2 o macOS con Docker Desktop para instalaciones compatibles/laboratorio;
- Docker Engine + Compose v2;
- puertos locales configurables 8001–8009, 8080, 8443 y 8222.

### Arranque

```bash
cp .env.example .env
```

Defina `POSTGRES_PASSWORD`, dos semillas Ed25519 independientes (`IDENTITY_SIGNING_KEY`, `ENROLLMENT_SIGNING_KEY`) y un `DEVICE_PROXY_SHARED_SECRET` aleatorio fuerte.

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

Readiness del plano servidor:

```bash
for p in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8080; do curl -fsS http://127.0.0.1:$p/health/ready; done
```

Device Edge usa mTLS, por lo que su readiness también requiere certificado cliente y no es un endpoint HTTP público anónimo.

## Windows Agent Modern

### Artefactos

El CI de v0.7 produce:

- `itguardian-agent-amd64.exe`;
- `itguardian-agent-arm64.exe`;
- `ITGuardian-Agent-0.7.0-x64.msi`;
- `SHA256SUMS.txt`.

### Instalación x64

1. Instale el MSI. El servicio queda registrado pero detenido hasta completar enrollment.
2. Obtenga únicamente la CA pública del Device Edge, por ejemplo desde el servidor:

```bash
docker compose cp device-edge-service:/tls/server-ca.pem ./device-edge-ca.pem
```

3. Copie `device-edge-ca.pem` a `C:\ProgramData\ITGuardian\Agent\device-edge-ca.pem`.
4. Copie `C:\ProgramData\ITGuardian\Agent\agent.example.json` a `agent.json` y configure la URL real `https://<servidor>:8443`.
5. Cree un enrollment token one-time ligado al activo mediante la API administrativa.
6. Ejecute una sola vez como administrador:

```powershell
& 'C:\Program Files\IT Guardian\itguardian-agent.exe' enroll `
  --gateway https://guardian.example.com `
  --token '<ONE_TIME_TOKEN>' `
  --state 'C:\ProgramData\ITGuardian\Agent\identity.json'
```

7. Inicie el servicio:

```powershell
Start-Service ITGuardianAgent
Get-Service ITGuardianAgent
```

El endpoint genera ECDSA P-256 localmente. La private key no cruza Enrollment/PKI y se persiste protegida por DPAPI LocalMachine.

### Operación

El agente ejecuta:

```text
DPAPI identity -> mTLS Device Edge -> heartbeat -> telemetry -> acquire command
-> running -> WinAPI/SCM typed execution -> idempotent result -> offline spool/retry
```

Comandos permitidos en 0.7:

- `inventory.refresh`;
- `device.reboot`;
- `service.restart`.

No existe `shell.exec`, PowerShell remoto ni command prompt arbitrario.

### Actualización firmada

`agent.json` puede habilitar update únicamente si se configuran los cuatro campos: `update_manifest_url`, `update_public_key`, `update_max_bytes` y `update_health_timeout_seconds`. El manifest debe estar firmado con Ed25519, la URL es HTTPS, el payload se valida por tamaño + SHA-256 y los downgrades se rechazan.

```powershell
& 'C:\Program Files\IT Guardian\itguardian-agent.exe' update `
  --config 'C:\ProgramData\ITGuardian\Agent\agent.json'
```

El helper interno detiene únicamente `ITGuardianAgent`, activa el staged binary y espera un ciclo real exitoso que escriba `update-healthy`; si vence el timeout, restaura el binario previo y reinicia el servicio.

## Seguridad de claves

- Identity y Enrollment usan signers privados separados.
- Root PKI no está disponible al runtime API.
- Device Edge no monta la CA privada de su TLS de servidor.
- El principal endpoint deriva del certificado, nunca de headers elegidos por cliente.
- Private keys de dispositivo permanecen en el endpoint.
- Windows protege la private key con DPAPI LocalMachine.
- El updater acepta solo catálogo/clave Ed25519 pinneados en configuración, no URL/clave arbitrarios por comando.

## Gate Core MVP

- [x] levantar servidor completo hasta v0.7;
- [x] crear/autenticar `platform_admin`;
- [x] crear empresa/sede/departamento/activo;
- [x] emitir token, CSR y certificado;
- [x] instalar/desinstalar Windows Agent vía MSI x64;
- [x] establecer identidad mTLS de dispositivo;
- [x] heartbeat y estado ONLINE;
- [x] pipeline de CPU/RAM/discos y telemetry;
- [x] ejecutar comandos allowlisted sin shell arbitrario;
- [x] recibir resultado idempotente y auditar lifecycle;
- [x] spool/retry offline;
- [x] update firmado + rollback transaccional;
- [ ] administrar todo visualmente desde Web Console v0.8.

El Core MVP aún no se declara producto final hasta cerrar Web Console v0.8 y los gates posteriores del roadmap.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores Huawei específicos usan una matriz de capacidades separada. No se simula paridad donde la plataforma no la permite y esos agentes se desarrollarán en gates posteriores.

Consulte `ROADMAP.md` para el estado canónico y `MASTER.md` para la arquitectura completa.
