---
description: Reporta telemetría histórica o compara tareas A/B de CodeGraph sin persistir contenido crudo.
agent: code-inspector
subtask: false
---

Operá el benchmark CodeGraph solicitado en `$ARGUMENTS` mediante:

```bash
bash ~/.config/opencode/scripts/codegraph_metrics.sh <history|capture|report> <argumentos>
```

Antes de lanzar sesiones, exigir una decisión concreta que el resultado pueda
cambiar, criterio de calidad/parada, presupuesto y autorización. Empezar con
un par exploratorio (dos sesiones) de un caso; ampliar solo si queda una duda
decisoria. Es descriptivo: no extrapolar resultados a otros proyectos ni medir
por obligación. Conservar contexto inicial comparable y no pasar respuestas o
hallazgos persistidos de una variante al control.

Se compara con/sin grafo, no un antes/después de políticas. Ambos registros deben
declarar la misma `--policy-version`: no falsear etiquetas ni pedir que se acepten
políticas distintas para obtener un porcentaje. No forzar grafo en una tarea literal.
Si el rol no puede ejecutar el wrapper, pedir un operador compatible; no ampliar
permisos ni delegar como bypass. No inicializar/sincronizar/reindexar para preparar
el experimento por reflejo.

Para capturar una corrida exigir siempre:

- `--session <id>` explícito,
- `--variant with-codegraph|without-codegraph`,
- `--pair-id <id-compartido-por-ambas-variantes>`,
- `--project <proyecto>`,
- `--task-kind <tipo-de-tarea>`,
- `--policy-version <etiqueta-de-la-política-realmente-usada>`,
- `--dedicated-task` para una sesión que corresponde a una sola tarea, o ambos `--from-message <id>` y `--to-message <id>` (inclusivos),
- `--outcome accepted|partial|reworked|incorrect|pending`.

Opcionales de evaluación explícita: `--utility yes|partial|no|not-evaluated|not-applicable` y `--corrections-required <n>`. No inferir utilidad, calidad, correcciones ni política histórica. `--task-id` por defecto es el pair-id; usar pair-id único para cada repetición A/B.

Para telemetría sin capturas previas usar `history --since <fecha-UTC-inclusiva> --until <fecha-UTC-exclusiva>`, opcionalmente `--project-root <root>` y `--model <provider/model#variant>`. Lee SQLite en modo read-only y agrupa familias de sesiones por proyecto/modelo; no equivale a tareas ni calcula ahorro causal.

No inventar ni inferir el session ID. Si falta, pedirlo o indicar que puede obtenerse con `/sessions-list`.
Capturar desde una sesión operadora distinta de la sesión medida para no contaminar sus tokens y tools con el propio benchmark.

Para informar resultados ejecutar `report`. Explicar que un porcentaje positivo representa mejora con CodeGraph y que solo los pares comparables con ambos resultados `accepted` alimentan el porcentaje principal.
Datos no disponibles se muestran como n/a, no cero. Sesiones hijas se suman una sola vez por parent_id; trabajo externo o no vinculado queda desconocido. No cambiar reglas de consulta, límites, índices ni permisos al operar estas métricas.

Interpretar la columna de referencia como heurística: la captura actual usa
1 llamada para review, 3 en otros tipos y 10 KiB de salida, no límites del motor
o de la política vigente. Los flags son los guardados al capturar, no una nueva
evaluación de la política. JSON conserva sus claves/valores legacy por compatibilidad.
La búsqueda observada cubre CodeGraph y glob/grep/read, no todas las lecturas por
Bash, wrappers u otras tools. Informar calidad/correcciones y outcomes/exclusiones,
no solo el porcentaje de pares accepted, sin cambiar los cálculos para mejorar cifras.
