---
name: codegraph-analisis-estructural
description: Usa CodeGraph para analizar callers, flujos, blast radius y tests afectados en repositorios ya indexados; no usar para búsquedas literales ni para inicializar índices autónomamente.
compatibility: opencode
---

# CodeGraph: análisis estructural

## Cuándo cargar esta skill

- antes de modificar símbolos con coupling no obvio,
- al rastrear un flujo entre capas o módulos,
- para identificar callers/callees o blast radius,
- para orientar revisión y selección de tests.

## Elección de evidencia

- Priorizar el grafo si falta una relación estructural, el índice existe y el rol tiene acceso autorizado.
- Para un dato literal o archivo ya localizado sin incertidumbre estructural, preferir lectura directa; existencia o tamaño del índice no obligan a consultarlo.
- Un símbolo localizado puede seguir requiriendo análisis de callers/impacto. Preservar las prioridades de dominio y contratos locales, sin ampliar permisos.

## Flujo

1. Resolver el root Git/worktree real y absoluto del código, no el directorio de su overlay.
2. Consultar `codegraph_explore` con una pregunta corta, símbolos concretos y una frontera de módulo/componente; mapa global solo si es el pedido. Usar únicamente argumentos soportados por el schema anunciado.
3. Pasar `projectPath` absoluto en cada consulta, también desde subdirectorios; no depender del default implícito.
4. Tratar solo el fragmento realmente devuelto como leído, no el archivo entero por ver su nombre.
5. Abrir fuente adicional donde falte evidencia material; no repetir una exploración completa ya cubierta.
6. Contrastar findings materiales con diff, tests o lectura directa.

## Presupuesto de consultas

- CodeGraph debe reemplazar exploración manual, no sumarse a una ronda completa de `grep/read` ya realizada.
- En code review, usar una sola consulta compacta centrada en los símbolos del diff.
- En planning o implementación, usar normalmente hasta tres consultas: mapa inicial, una profundización y una verificación puntual.
- Si la primera respuesta no reduce lecturas o devuelve demasiado contexto, detener el uso del grafo para esa tarea y continuar con lectura directa.
- Las reglas locales del proyecto pueden indicar capas o contratos prioritarios, pero no deben duplicar este procedimiento completo en otra skill.
- Son presupuestos, no cuotas: una consulta suficiente permite terminar. No multiplicarlos por cada root referenciado ni relajar el contrato del review formal.

## Fallback

Si falta índice/tool/acceso, la tool falla, la respuesta es parcial o hay aviso de staleness/degradación:

- explicitarlo,
- usar `glob`/`grep`/`read`,
- sugerir `/codegraph-init <root>` si el usuario quiere habilitarlo,
- no inicializar ni reindexar por cuenta propia.
- una orientación sin `isError` no prueba que hubo evidencia útil del grafo,
- no repetir los mismos argumentos ni usar CLI u otro agente para eludir restricciones,
- no lanzar `status` antes de cada consulta ni reparaciones automáticas; no alterar watcher/autosync configurados.

## Límites

- El grafo puede quedar incompleto por parsing dinámico o código generado.
- No usarlo como prueba única de ausencia de callers.
- No guardar el output crudo del grafo en memoria durable ni Qdrant; persistir solo conclusiones estables y verificadas cuando realmente sean reusables.
- No compartir `.codegraph/` entre worktrees.
- Una reference no crea aristas cross-repo ni autoriza indexar otro checkout; cada consulta debe fijar su root.
- Tamaño, mtime, registro o marcadores de daemon no certifican cobertura, compatibilidad o frescura.
- Configuración externa y relaciones dinámicas/generadas requieren corroboración; no inventar parámetros ni cambiar el motor para acotar una consulta.
