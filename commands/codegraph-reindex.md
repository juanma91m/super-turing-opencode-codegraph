---
description: Regenera explícitamente el índice CodeGraph de un repositorio después de confirmación.
agent: build
subtask: false
---

Prepará el reindex de CodeGraph para `$ARGUMENTS`.

Esta operación reemplaza un índice regenerable existente. Antes de ejecutarla:

1. mostrar el estado actual,
2. explicar por qué hace falta reindex y no alcanza `sync`,
3. pedir confirmación explícita,
4. recién entonces ejecutar:

```bash
bash ~/.config/opencode/scripts/codegraph_project_reindex.sh --project-root "<root>" --confirm-reindex
```

No ejecutar `uninit`, `unlock` ni borrar `.codegraph/` manualmente.
