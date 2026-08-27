# Agent Control Service

IT Guardian v0.6 endpoint liveness plane. Owns device heartbeat, capability snapshots and online/offline state. Device-facing calls require a trusted endpoint-authentication proxy token and certificate-derived identity headers; Gateway never exposes these routes as bearer-admin endpoints.
