# Playbook: CodeGraph en OpenCode

## Qué resuelve

CodeGraph aporta evidencia estructural del índice consultado; su vigencia y
cobertura deben corroborarse cuando afecten la conclusión:

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

Un símbolo ya localizado puede necesitar análisis estructural si aún hay
incertidumbre sobre callers o impacto. El tamaño/presencia del índice no decide
por sí solo el routing. Conservar las prioridades de dominio del proyecto y la
autoridad del rol; no ampliar tools ni permisos para seguir este procedimiento.

## Contrato de consulta

- Pasar `projectPath` absoluto en cada consulta: root Git/worktree real del código,
  incluso desde subdirectorios, no su overlay ni un default implícito. Una reference
  hermana no crea aristas cross-repo ni autoriza indexar otro checkout.
- Empezar por una pregunta corta sobre símbolos y una frontera de módulo/componente.
  El mapa global sigue permitido cuando es el pedido, no como estación previa a todo
  cambio. No inventar parámetros ni cambiar el motor para acotar la respuesta.
- Tratar solo el fragmento realmente recibido como leído, no el archivo entero por
  su nombre. Abrir la fuente donde falte evidencia material sin repetir todo el recorrido.
- Confirmar con herramientas directas cualquier dato crítico que el grafo no muestre completo.
- Preservar una consulta compacta del diff en review formal y normalmente hasta tres
  en planning/implementación. No son cuotas obligatorias ni se multiplican por roots;
  la skill del review formal conserva sus restricciones adicionales.
- Ante falta de índice/tool/acceso, respuesta parcial o aviso de staleness/degradación,
  declarar el límite y degradar a `glob`/`grep`/`read`; no inicializar ni reindexar por
  cuenta propia. Una orientación sin `isError` no demuestra que hubo grafo útil.
- No repetir argumentos ni usar CLI/otro agente para eludir restricciones. No añadir
  `status` antes de cada consulta, reparaciones o cambios de watcher/autosync.
- Tamaño, mtime, registro o marcadores no certifican salud del índice; configuración
  externa y relaciones dinámicas/generadas necesitan corroboración. No usar ausencia
  de aristas como prueba única de ausencia de impacto.

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
