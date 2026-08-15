---
description: Sincroniza incrementalmente un índice CodeGraph existente y valida su estado final.
agent: code-inspector
subtask: false
---

Sincronizá CodeGraph para el proyecto `$ARGUMENTS`.

Si no se recibió path, usar el repository root actual. Ejecutar únicamente:

```bash
bash ~/.config/opencode/scripts/codegraph_project_sync.sh --project-root "<root>"
```

No inicializar un índice ausente ni ejecutar reindex completo como fallback. Informar resultado y estado final.
