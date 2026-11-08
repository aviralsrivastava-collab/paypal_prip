# PRIP Infrastructure Module

## Ownership
- Local developer runtime configurations, Dockerfiles, docker-compose definitions, and proxy setups.
- Environment provisioning and port mappings (FastAPI backend on `:8000`, React frontend on `:3000`).
- CORS allowlist definitions and security header policies for local testing.

## Boundary Rules
- Must not contain live secrets, credentials, or private keys.
- Sandbox and Live deployment targets must remain strictly isolated.
