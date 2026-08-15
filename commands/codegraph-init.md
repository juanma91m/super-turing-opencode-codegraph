---
description: Inicializa o adopta de forma segura el índice CodeGraph machine-local de un repositorio.
agent: build
subtask: false
---

Inicializá CodeGraph para el proyecto `$ARGUMENTS`.

Reglas:
- si no se recibió path, usar el repository root actual,
- ejecutar únicamente `bash ~/.config/opencode/scripts/codegraph_project_init.sh --project-root "<root>"`,
- no crear `codegraph.json` salvo que exista una necesidad de configuración confirmada,
- si ya existe un índice compatible, adoptarlo sin reindexar,
- si el wrapper informa incompatibilidad o recomienda reindex, detenerse y explicarlo,
- devolver el resumen de `codegraph status` sin modificar código funcional.
