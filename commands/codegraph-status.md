---
description: Muestra el estado real del índice CodeGraph de un repositorio sin modificarlo.
agent: code-inspector
subtask: false
---

Revisá el estado CodeGraph del proyecto `$ARGUMENTS`.

Si no se recibió path, usar el repository root actual. Ejecutar únicamente:

```bash
bash ~/.config/opencode/scripts/codegraph_project_status.sh --project-root "<root>"
```

Informar si el índice existe, versión que lo construyó, archivos/nodos/aristas, cambios pendientes y si CodeGraph recomienda reindex.
