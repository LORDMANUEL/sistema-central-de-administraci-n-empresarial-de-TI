# Identity Asymmetric JWT/JWKS Design

**Date:** 2026-08-21  
**Status:** Approved as required microservice hardening

## Problem

The v0.1.0 Identity baseline initially used HS256. Sharing that secret with Tenant, Asset and future services would allow every verifier to mint valid Guardian tokens, violating service isolation.

## Decision

Identity exclusively owns a 32-byte Ed25519 private seed supplied as URL-safe base64 in `IDENTITY_SIGNING_KEY`. It signs access and refresh JWTs with EdDSA and a `kid`. It exposes only the derived public Ed25519 key through `GET /.well-known/jwks.json`.

Tokens include `iss=urn:it-guardian:identity`, `aud=it-guardian-services`, `sub`, `role`, `type`, `iat`, `exp`, and `jti`. Identity validates all mandatory claims and the expected token type.

## Rotation boundary

The first release publishes one active key. `kid` and the JWKS array make multi-key overlap/rotation possible later without changing consumers. Downstream services must never receive `IDENTITY_SIGNING_KEY`.

## Operational rule

Development has a deterministic seed for local execution only. Production configuration rejects it. Operators generate 32 random bytes, encode them as base64url without padding, and store the result in the deployment secret store.
