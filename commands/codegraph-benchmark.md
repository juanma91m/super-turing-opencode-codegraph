---
description: Captura y compara métricas A/B de sesiones con y sin CodeGraph, sin persistir prompts ni outputs crudos.
agent: code-inspector
subtask: false
---

Operá el benchmark CodeGraph solicitado en `$ARGUMENTS` mediante:

```bash
bash ~/.config/opencode/scripts/codegraph_metrics.sh <capture|report> <argumentos>
```

Para capturar una corrida exigir siempre:

- `--session <id>` explícito,
- `--variant with-codegraph|without-codegraph`,
- `--pair-id <id-compartido-por-ambas-variantes>`,
- `--project <proyecto>`,
- `--task-kind <tipo-de-tarea>`,
- `--outcome accepted|partial|reworked|incorrect|pending`.

No inventar ni inferir el session ID. Si falta, pedirlo o indicar que puede obtenerse con `/sessions-list`.
Capturar desde una sesión operadora distinta de la sesión medida para no contaminar sus tokens y tools con el propio benchmark.

Para informar resultados ejecutar `report`. Explicar que un porcentaje positivo representa mejora con CodeGraph y que solo los pares comparables con ambos resultados `accepted` alimentan el porcentaje principal.
