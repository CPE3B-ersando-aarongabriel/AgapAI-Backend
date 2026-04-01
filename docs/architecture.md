# Architecture Notes

## Layers

- API layer: request/response handling only.
- Service layer: orchestration and business logic.
- Repository layer: direct MongoDB operations.
- Utilities: shared helper logic and formatting.

## Future Auth Hook

Authentication/authorization is intentionally omitted for current device-first phase.
Add auth middleware/dependencies later under `app/dependencies` and route guards in `app/api`.
