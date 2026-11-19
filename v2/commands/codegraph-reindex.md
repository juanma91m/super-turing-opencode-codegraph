---
description: Reindexa un índice local sólo después de justificarlo y confirmar explícitamente.
agent: master-dev
---
Para $ARGUMENTS, obtener primero status con codegraph-project sobre el root absoluto exacto. Explicar por qué sync no alcanza, efecto de reemplazo del índice regenerable y pedir confirmación explícita. Sólo entonces action reindex con confirmReindex true, conservando permiso nativo. Nunca unlock/uninit, borrar/copiar .codegraph manualmente o hacer fallback al reindex por una consulta pobre. No compartir índices entre worktrees, cambiar watchers para acelerar o modificar código funcional. Si falla/cancela, puede quedar trabajo parcial: informar, sin restauraciones o reintentos ocultos.
