---
description: Inicializa o adopta explícitamente un índice CodeGraph en el root exacto.
agent: master-dev
---
Sólo por el pedido explícito actual, usá codegraph-project action init con projectRoot absoluto Git/worktree exacto de $ARGUMENTS. Si falta root resolvé el del repo actual por metadata, no infieras otro proyecto. El runtime no cambia el path ni adopta symlinks/subdirectorios. Conservar permiso nativo; si existe índice compatible lo adopta sin indexar de nuevo. Si falta runtime, hay mismatch, índice incompleto o recomienda reindex, informar y detenerse: nada de install/unlock/uninit/reindex de fallback, ni crear codegraph.json. El índice es local al worktree, no compartido. No modificar código funcional ni persistir outputs privados en memoria/corpus.
