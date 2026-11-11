# IT Guardian — plan de cierre verificable (2026)

## Alcance y definición de terminado

La rama `feature/p0-debian-cli-console-hardening` es una entrega incremental; NO representa una versión empresarial terminada ni una certificación SOC 2/ISO 27001. El core v0.8 sigue siendo la base de seguridad.

| Gate | Alcance | Evidencia obligatoria | Bloqueante de salida |
| --- | --- | --- | --- |
| P0-A / 0.8.1 | Debian CLI + paquete, adaptaciones responsive de consola, matriz de seguridad | Build .deb, tests CLI, Vitest, TypeScript, Playwright, CI verde | Sin builds o agente real verificado no se declara lista para producción |
| P0-B / 0.8.2 | Instalador asistido y operaciones con backup/restore PostgreSQL, rollback seguro, gestor de secretos | Instalar/actualizar/reparar y restaurar en Debian 12/13 y Ubuntu; restore test; hardening host | Recuperación de datos reproducible |
| 0.9.0 | Software Inventory + Patch + Policy | Windows API real, pruebas E2E, targeting/RBAC, consentimiento de acciones | No se ejecutan comandos arbitrarios |
| 0.10.0 | Tickets/help-client | flujo de ticket con E2E, adjuntos privados, roles | evidencia de aislamiento multiempresa |
| 0.11.0 | Remote Support propio | video/captura, control autorizado, auditoría, consentimiento, interrupción, latencia y pruebas de fuga de sesión | no expuesto en Internet sin autenticación |
| 0.12–0.14 | Seguridad endpoint, agentes Linux/macOS, servidores/impresoras | matrices por SO y equipos físicos | pruebas de privilegios mínimos |
| 0.15–0.19 | Backup/restauración, networking, MDM, vulnerabilidad, automatización | pruebas de recuperación, integración y evaluación de riesgos | métricas y alertas reales |
| 0.20-RC / 1.0 | release integral | CI sobre SHA, SBOM, SAST/deps, pentest, backup drill, políticas y manuales | aprobación formal de salida |

## Orden de ejecución P0

1. Congelar contratos de Identity, Enrollment, PKI y Device Edge; no modificar rutas ni permisos para el rediseño.
2. Ejecutar todas las suites existentes en un SHA fijo y guardar logs/artefactos.
3. Construir `it-guardian_0.8.1_all.deb` y probar en VM Debian limpia.
4. Instalar Windows Agent MSI en un Windows 11 real de laboratorio, validar enrollment, heartbeat, telemetry, offline/retry, revocación y comando permitido.
5. Validar responsive 360/390/768/1440px y navegación teclado, lector de pantalla, prefers-reduced-motion.
6. Restaurar base de datos en laboratorio antes de autorizar despliegue productivo.
7. Revisar secretos, superficie de red, permisos Docker y cambios de infraestructura.
8. Obtener revisión independiente y CI verde para merge.

## Contrato Debian

- Paquete fuente + CLI bajo `/usr/bin/it-guardian`, payload `/usr/share/it-guardian/source.tar.gz`.
- `sudo it-guardian doctor` comprueba prerrequisitos; `install` despliega en `/opt/it-guardian` después de validar Compose.
- `/etc/it-guardian/guardian.env` debe existir con root:root, modo 0600 y valores únicos, nunca lo reemplaza el actualizador.
- `up`, `down`, `status`, `verify`, `logs` se limitan al proyecto Compose `it-guardian`.
- `backup-config` NO es respaldo de PostgreSQL y jamás debe presentarse como tal.
- No se ejecuta `docker system prune`, no se borran volúmenes con `down`, no se cambia firewall, DNS, DHCP, Exim/Postfix ni servicios ajenos.
- Dependencias Docker Engine y Compose se instalan por procedimiento de plataforma, con pinning de versiones y revisión del administrador; el instalador no tiene permiso de cambiar host arbitrariamente.

## Criterios para decir “funcional”

Funcional laboratorio: E2E integral de servidor + consola + un agente Windows nativo, instalador .deb, HTTPS público válido, backups restaurables, revocación verificada y observabilidad.

Funcional producción: además hardening de host, almacenamiento cifrado, recuperación probada, control de cambios, operación monitoreada, documentación y validación de responsabilidad compartida.

No usar cifras de avance porcentual si no existe evidencia trazable por gate.
