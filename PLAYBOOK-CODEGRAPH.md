# Playbook: CodeGraph en OpenCode

## Qué resuelve

CodeGraph aporta evidencia estructural vigente del código:

- símbolos y definiciones,
- callers y callees,
- flujos entre archivos,
- blast radius,
- tests potencialmente afectados.

No reemplaza:

- Engram para decisiones durables,
- Qdrant para corpus documental,
- Context7 para APIs externas,
- `grep`/`read` para confirmar texto o una línea exacta,
- Semgrep para políticas estáticas repetibles.

## Cuándo usarlo

Usar `codegraph_explore` primero cuando la pregunta sea estructural:

- “¿cómo fluye X?”,
- “¿quién llama este método?”,
- “¿qué puede romper este cambio?”,
- “¿qué archivos conectan estas capas?”,
- “¿qué tests están relacionados?”.

No usarlo por reflejo para:

- archivos de configuración simples,
- búsquedas literales,
- microcambios ya localizados,
- repos sin índice.

## Contrato de consulta

- Pasar siempre `projectPath` absoluto cuando el MCP no tenga un proyecto por defecto.
- Tratar el source devuelto como ya leído; no reabrir los mismos archivos sin una hipótesis nueva.
- Confirmar con herramientas directas cualquier dato crítico que el grafo no muestre completo.
- Si no hay índice, degradar a `glob`/`grep`/`read`; no inicializarlo autónomamente.

## Lifecycle

- `init`: solo mediante wrapper y con consentimiento del usuario o del flujo de generación ya confirmado.
- `sync`: incremental y no destructivo.
- watcher MCP: mantiene fresco el índice durante la sesión.
- `reindex`: explícito con confirmación.
- `uninit`/`unlock`: operaciones de operador, fuera de la autonomía normal.

## Worktrees

Cada worktree representa contenido distinto y debe tener su propio `.codegraph/`. No copiar bases SQLite ni compartir locks entre roots.

## Roles

- `code-inspector`: consumidor principal.
- `planner`: usa el grafo para alcance y flujos no triviales.
- `reviewer` / `code-reviewer`: lo usa para impacto material, no para inventar findings.
- `master-dev`: lo usa antes de cambios estructurales cuando reduce exploración y riesgo.

## Medición A/B

Para comprobar el beneficio, comparar pares de sesiones nuevas con igual proyecto,
modelo, tarea y criterio de aceptación. Etiquetar una variante `with-codegraph` y la
otra `without-codegraph` mediante `/codegraph-benchmark`.

La métrica principal es la mejora porcentual pareada de tokens totales:

```text
(tokens_sin - tokens_con) / tokens_sin * 100
```

Un valor positivo mejora; uno negativo empeora. Complementar con duración, reducción
de `glob`/`grep`/`read`, bytes de output de búsqueda, tasa de aceptación y retrabajo.
Solo los pares donde ambas variantes fueron aceptadas cuentan para el porcentaje
principal. No usar el error técnico cero como sustituto de calidad funcional.

### Contrato de métricas v2 (sin cambios en el uso del grafo)

- `history --since <ISO-UTC> --until <ISO-UTC>` obtiene agregados retrospectivos
  sin capturas ni hooks; el fin es exclusivo. `--database` permite indicar otra
  base existente, nunca crea una. `--project-root` filtra el root de la familia y
  `--model` exige una etiqueta exacta `provider/model#variant`, sin ocultar modelos
  distintos usados por subagentes.
- La unidad histórica es una familia de sesiones raíz activa en la ventana, no
  una tarea. Los hijos y nietos vinculados por `parent_id` se cuentan una sola vez.
  Trabajo externo/no vinculado permanece desconocido; no se infiere por títulos.
- `capture` exige `--policy-version` declarada y un alcance: `--dedicated-task`
  confirma una tarea por sesión, o `--from-message` + `--to-message` delimitan
  mensajes inclusivos de la principal. En rangos, los descendientes verificables
  se recortan temporalmente: tareas paralelas pueden impedir atribución exacta.
  La confirmación de alcance y equivalencia corresponde al operador.
- `--task-id` por defecto es el pair-id. Usar pair-id único por repetición; varias
  corridas de una variante bajo el mismo par se excluyen, no se elige la mejor.
- La política histórica no se deduce del marker instalado hoy. Solo compara pares
  accepted con proyecto, modelo único, task-kind, task-id, política y tipo de
  alcance coincidentes. Los registros v1 siguen legibles, pero no alimentan el
  porcentaje principal por carecer de alcance/política verificables.
- `--utility` y `--corrections-required` son evaluación explícita. La ausencia de
  evaluación no significa cero correcciones ni mala calidad. La aceptación usa
  solo outcomes evaluados (excluye pending); el reporte muestra la cobertura.
- Los tokens se desglosan en entrada, caché leída/escrita, salida y razonamiento.
  No se suman componentes al total reportado: algunos proveedores incluyen
  razonamiento en salida. Los datos faltantes son null/n/a, no cero ni estimaciones
  por bytes; si una observación falta, el agregado de ese campo queda desconocido.
- Tiempo de asistente acumulado mide trabajo; la unión de intervalos evita sumar
  concurrencia y excluye huecos. Ninguno equivale a tiempo completo de tarea ni
  latencia percibida. La latencia CodeGraph se obtiene de start/end disponibles.
- Bytes son output almacenado, no necesariamente todo el contexto visible al
  modelo. Un estado completed no demuestra éxito semántico. No se reconstruye el
  estado de una llamada en vuelo del pasado: se observa el último estado guardado.
- JSON incluye sumas, medias, medianas/P75/P90 y cobertura; las sumas incompletas
  quedan desconocidas. La distribución de latencia histórica compara medianas de
  llamadas por familia, no una distribución global de llamadas. `report` estratifica por proyecto,
  modelo, tipo de tarea y política. `--output <archivo>` guarda un reporte solo si
  se pide; por defecto history solo imprime. No inicia índices, MCP ni llamadas LLM.
