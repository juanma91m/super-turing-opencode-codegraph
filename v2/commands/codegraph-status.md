---
description: Consulta estado del índice CodeGraph explícito mediante la tool nativa acotada.
agent: code-inspector
---
Usá codegraph-project action status con projectRoot absoluto Git/worktree exacto de $ARGUMENTS o del repo actual verificado. Reportar existencia/versión/conteos/pending y recomendación de reindex que el backend realmente exponga. Campos faltantes son no disponibles, no cero. No invocar init/sync/reindex, shell/CLI alternativos o reparar para obtener status. Status puede abrir SQLite/locks/migraciones normales de upstream: no prometer cero escrituras físicas. Ante falta de runtime/acceso, degradar e informar; no usar status por reflejo antes de cada explore.
