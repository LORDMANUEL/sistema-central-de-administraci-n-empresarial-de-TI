# Identity Asymmetric JWT/JWKS Hardening Implementation Plan

**Goal:** Make Identity the only service capable of minting Guardian tokens while allowing every downstream microservice to verify them using public key material.

**Spec:** `docs/superpowers/specs/2026-08-21-identity-jwks-design.md`

- [x] Write failing tests for JWKS, Ed25519 header metadata, issuer/audience, production default-key rejection and malformed seed rejection.
- [x] Observe RED: JWKS returned 404 and signing-key validation was absent.
- [x] Add Ed25519 `TokenService` and public JWK serialization.
- [x] Add `kid`, `iss`, `aud` and mandatory claim verification.
- [x] Expose `/.well-known/jwks.json`.
- [x] Change deployment configuration from shared JWT secret to private signing seed.
- [x] Add `cryptography` dependency.
- [x] Run focused tests GREEN.
- [x] Run full suite GREEN: 22 passed.
- [x] Update README, environment template, Compose and changelog.
