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
