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

## Fallback

Si no hay índice o la tool falla:

- explicitarlo,
- usar `glob`/`grep`/`read`,
- sugerir `/codegraph-init <root>` si el usuario quiere habilitarlo,
- no inicializar ni reindexar por cuenta propia.

## Límites

- El grafo puede quedar incompleto por parsing dinámico o código generado.
- No usarlo como prueba única de ausencia de callers.
- No guardar el grafo en memoria durable ni Qdrant.
- No compartir `.codegraph/` entre worktrees.
