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

## Flujo

1. Resolver el repository root absoluto.
2. Consultar `codegraph_explore` con una pregunta corta y símbolos concretos.
3. Pasar `projectPath` siempre que no haya default inequívoco.
4. Tratar el source devuelto como leído.
5. Abrir archivos adicionales solo para confirmar una hipótesis no cubierta.
6. Contrastar findings materiales con diff, tests o lectura directa.

## Presupuesto de consultas

- CodeGraph debe reemplazar exploración manual, no sumarse a una ronda completa de `grep/read` ya realizada.
- En code review, usar una sola consulta compacta centrada en los símbolos del diff.
- En planning o implementación, usar normalmente hasta tres consultas: mapa inicial, una profundización y una verificación puntual.
- Si la primera respuesta no reduce lecturas o devuelve demasiado contexto, detener el uso del grafo para esa tarea y continuar con lectura directa.
- Las reglas locales del proyecto pueden indicar capas o contratos prioritarios, pero no deben duplicar este procedimiento completo en otra skill.

## Fallback

Si no hay índice o la tool falla:

- explicitarlo,
- usar `glob`/`grep`/`read`,
- sugerir `/codegraph-init <root>` si el usuario quiere habilitarlo,
- no inicializar ni reindexar por cuenta propia.

## Límites

- El grafo puede quedar incompleto por parsing dinámico o código generado.
- No usarlo como prueba única de ausencia de callers.
- No guardar el output crudo del grafo en memoria durable ni Qdrant; persistir solo conclusiones estables y verificadas cuando realmente sean reusables.
- No compartir `.codegraph/` entre worktrees.
