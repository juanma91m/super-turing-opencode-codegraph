# Changelog

## [Unreleased]

## [0.1.0-alpha.2] - 2026-09-11

### Added

- `scripts/preflight.sh` valida Python, Git, Node y npm antes de que la distribución modifique el target,
- benchmark A/B machine-local para comparar sesiones equivalentes con y sin CodeGraph,
- métricas de tokens totales, duración, llamadas y bytes de búsqueda manual/estructural,
- control de calidad por outcome y exclusión de pares no comparables,
- comando `/codegraph-benchmark` y reporte agregado con mejora porcentual pareada.

### Changed

- La skill global absorbe las heurísticas reutilizables descubiertas en overlays AUNE: presupuesto por fase, CodeGraph como reemplazo de exploración y corte temprano cuando no reduce lecturas.
- Las variantes locales deberían conservar solo lentes de dominio, no copiar el procedimiento global.

## [0.1.0-alpha.1] - 2026-08-15

### Added

- addon global independiente para CodeGraph,
- pin reproducible de `@colbymchenry/codegraph@1.5.0`,
- MCP global limitado a `codegraph_explore`,
- telemetría y update checks deshabilitados,
- bootstrap adoptivo de índices por repository root,
- wrappers de `init`, `status`, `sync` y reindex explícito,
- inventario machine-local de proyectos indexados,
- lifecycle de instalación, diagnóstico y desinstalación no destructiva,
- documentación operativa, skill y commands para OpenCode.
