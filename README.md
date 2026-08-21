# IT Guardian

Sistema central de administración empresarial de TI.

> Estado: bootstrap inicial. El desarrollo funcional se realiza por versiones y microservicios aislados antes de promoverse a `main`.

## Objetivo

Unificar administración de endpoints, servidores, móviles, impresoras, red, seguridad, soporte remoto, backups, VPN, Wi-Fi, políticas, inventario, tickets, auditoría y automatización en una sola experiencia web/desktop.

## Arquitectura

IT Guardian se construye como una plataforma de microservicios desde v0.1.0. Cada servicio tiene API, almacenamiento de dominio, pruebas, health/readiness, Dockerfile y documentación propios.

Consulte `MASTER.md` y `docs/` en las ramas de desarrollo para la especificación completa.
