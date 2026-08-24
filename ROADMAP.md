# IT Guardian — Roadmap de producto

Este roadmap reemplaza el avance por cantidad de microservicios con una regla más estricta: **cada versión debe agregar una capacidad utilizable de punta a punta**.

## Camino crítico Core MVP

`Identity -> Tenant -> Asset -> Enrollment/PKI -> Gateway/Audit -> Agent Control/Command/Telemetry -> Windows Agent -> Web Console`

No se inicia una línea posterior mientras la versión anterior no cumpla su Definition of Done y su prueba de integración.

## Versiones

| Versión | Entrega | Criterio funcional |
|---|---|---|
| v0.1.0 | Foundation + Identity | login, bootstrap, tokens Ed25519/JWKS, RBAC y CI reproducible |
| v0.2.0 | Tenant | empresas, membresías, sedes y departamentos con aislamiento por tenant |
| v0.3.0 | Asset Service | crear/listar/consultar activos canónicos y correlacionar IDs externos |
| v0.4.0 | Enrollment + PKI | alta de dispositivo, certificado, rotación y revocación |
| v0.5.0 | Gateway + Audit | entrada HTTP única, contexto tenant y auditoría central |
| v0.6.0 | Agent Control + Command + Telemetry | heartbeat, capacidades, trabajos remotos y resultados |
| v0.7.0 | Windows Agent Modern | primer endpoint Windows administrable y actualizable |
| v0.8.0 | Web Console MVP | login -> empresa -> sede -> activo -> estado -> comando -> auditoría |
| v0.9.0 | Software + Patch + Policy | inventario y operaciones RMM básicas |
| v0.10.0 | Tickets + Help Client | service desk conectado con activos |
| v0.11.0 | Remote Support | Tactical/Mesh detrás de adaptador propio |
| v0.12.0 | Security + Wazuh + USB | alertas, postura y controles endpoint |
| v0.13.0 | Linux + macOS Agents | endpoints modernos multiplataforma |
| v0.14.0 | Servers + Zabbix + Printers | infraestructura y periféricos |
| v0.15.0 | Backup | backup, restore y verificación |
| v0.16.0 | Network + Wi-Fi + VPN | red empresarial y acceso |
| v0.17.0 | Android/iOS MDM + Location | movilidad administrada y ubicación auditable |
| v0.18.0 | DFIR + Vulnerability | Velociraptor/OpenVAS |
| v0.19.0 | Automation + Reports + Licensing | automatización y operación empresarial |
| v0.20.0-rc | Release Candidate | instalador, upgrade/rollback, hardening, E2E |
| v1.0.0 | Enterprise Stable | instalación limpia y upgrade soportado con todos los gates verdes |

## Definition of Done obligatoria por microservicio

Un servicio se considera DONE únicamente cuando tiene:

1. API `/api/v1` con contrato estable y errores normalizados.
2. Autenticación/autorización explícita.
3. Base de datos propia del dominio; ningún otro servicio la escribe.
4. Migraciones Alembic con `upgrade -> downgrade -> upgrade`.
5. `/health/live`, `/health/ready`, métricas Prometheus y logs JSON con `request_id`.
6. Dockerfile no-root y arranque mediante Compose.
7. Tests unitarios y de integración verdes.
8. Eventos persistidos mediante transactional outbox cuando existe publicación asíncrona.
9. CI que compile, pruebe, construya la imagen y valide Compose.
10. Documentación operativa y notas de seguridad.
11. Prueba de integración con el servicio anterior del camino crítico.
12. Cero endpoints de producción vacíos, mocks permanentes o estados falsos.

## Gate Core MVP

El Core MVP solo se declara funcional cuando una instalación limpia pueda ejecutar esta secuencia sin intervención manual sobre bases de datos:

1. iniciar Docker Compose;
2. crear `platform_admin`;
3. autenticar;
4. crear empresa y sede;
5. crear activo;
6. emitir/usar enrollment;
7. instalar agente Windows;
8. recibir heartbeat e inventario;
9. ejecutar un comando autorizado;
10. recibir el resultado;
11. consultar el audit trail desde la consola web.

## Compatibilidad legacy

Windows 7/8/8.1, macOS Lion–10.12, KaiOS, Symbian y adaptadores especiales de Huawei se implementarán con matriz de capacidades separada. No bloquean el Core MVP ni `v1.0.0` del núcleo moderno salvo cuando una capacidad figure expresamente como requisito de release.

## Estado actual

- Identity Service: implementado y validado por CI en su rama.
- Tenant Service: implementado y validado por CI en su rama.
- Asset Service: **en desarrollo en `feature/v0.2.0-asset`; pasa a ser el siguiente gate obligatorio**.
- Los módulos posteriores quedan congelados hasta cerrar Asset y sus pruebas de integración.
