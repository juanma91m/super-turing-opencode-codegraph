# CodeGraph — mantenimiento nativo del candidato general

## Estado y frontera

Portados **cuatro comandos** al candidato OpenCode oficial2.2.7, conservando el
runtime CodeGraph (pin V2 vigente en el [README](README.md)): init, status, sync y reindex explícito. No instalados en el
perfil real. V1/workshop, índices reales, estados y configuración del operador no
se modificaron; no hubo init/sync/reindex real sobre sus repos.

MCP sigue siendo **sólo explore**, mismos cinco roles y root explícito con índice
existente. El mantenimiento es una **tool nativa separada** `codegraph-project`, no
otro MCP de administración, shell abierto o alternativa para eludir una consulta
denegada. No se crea índice por conectar, consultar, diagnosticar el stack o copiar
una reference. No modifica heurísticas, presupuestos, índices compartidos o motor.

El workshop anterior sigue query-only: la extensión legacy no habilita la nueva
tool si no recibe el contrato `maintenance`. Sus commands/scripts V1 no cambian.
No aplicar/recomponer el workshop para probar este incremento.

## Comandos y actores

| Comando candidato | Actor | Operación |
|---|---|---|
| codegraph-init | master-dev | init o adopción compatible, con permiso |
| codegraph-status | code-inspector | sólo status, sin registro del proyecto |
| codegraph-sync | master-dev | incremental existente compatible, con permiso |
| codegraph-reindex | master-dev | status/justificación/confirmación, luego reindex con permiso |

Tool visible sólo para master-dev/agent-design/code-inspector y build cuando esté
materializado por el stack; actores de escritura excluyen code-inspector. No se
agrega permiso shell/Edit al inspector ni se delega para sortear su límite. Sync
V1 apuntaba al inspector sin un grant funcional del wrapper: V2 lo lleva al
coordinador explícito, no abre capacidades de escritura al consumidor read-only.

Inputs cerrados: action enum, projectRoot absoluto exacto y confirmReindex boolean.
No flags CLI libres, binario/config/registro seleccionables por el modelo o campo
allowTemp. Reindex requiere confirmReindex:true y permiso nativo; las instrucciones
exigen explicar por qué sync no basta y pedir confirmación. Otros actores no
recuperan mutaciones mediante un allow de sesión. Los permisos/saved approvals
nativos siguen aplicando: no declarar los textos de prompt como enforcement OS.

Status requiere acción de lectura. Mutadores requieren `codegraph-project-write`
con recursos operación:root y registry:path; roots externos además requieren
external_directory. Preflight valida metadata sin ejecutar CLI de índice; después
de la aprobación el backend revalida root/binding antes de escribir.

## Runtime, roots y metadata

- Binding privado de ejecución es declarativo/público: runtime seleccionado y
  projects.json del owner, no contenido de state/DB. Se preservan referencias
  explícitas OPENCODE_CODEGRAPH_STATE_DIR/REGISTRY o defaults del runtime_home;
  path no canónico, symlink o nombre distinto de projects.json se rechaza.
- Reutiliza pin/binario administrado, sin install/upgrade/download. Mantiene tuning
  explícito de watchers/daemon/pool/CODEGRAPH_DIR; el nuevo helper usa ese mismo
  directorio, no otro índice. Telemetry/update checks off/NO_DOWNLOAD conservados.
- Root no puede ser /, HOME de runtime/proceso, relativo, symlink o subdirectorio.
  Git/worktree exacto. DB symlink/hardlink rechazada; no copia de SQLite/índices.
- Tmp roots se rechazan normalmente. La opt-in de host V1 para diagnóstico/tests
  se conserva, más acotada a /tmp/opencode: nunca es input de la tool ni se hereda
  por el launcher general. Tests la pasan explícitamente al proceso controlado.
- Mutadores revisan nombres de archivos tracked/no ignorados, sin contenidos de
  dotenv/keys/auth stores. Es screening, no detector universal de secretos; antes de
  indexar un repo real revisar ignore/tracked policy. CodeGraph sí lee código del
  scope autorizado para crear su grafo, no es una consulta sin efectos.
- Status puede abrir SQLite, locks/migraciones/cache normales: no promete cero
  writes físicos. En fixture real no inicializa DB ausente ni crea registry.
- Init adopta sólo índice compatible existente y no reconstruye; carpeta incompleta,
  worktree mismatch o reindex recomendado detienen adopción/sync sin fallback.
  Sync/reindex requieren DB existente; reparación de incompletos queda al operador,
  no un force implícito. Reindex sólo emite index ROOT --force después del permiso.
- Tras éxito, init añade una línea al Git info/exclude local (no .gitignore tracked
  ni codegraph.json), y mutadores actualizan el registro per-root. Status no lo hace.
  Cada worktree conserva su propia DB; el exclude Git común no comparte índices.

## Integridad, locks, output y fallos

Scripts/runtime helper/binding se pinnean por SHA antes de cada invocación. El
modelo no puede editar un script y ejecutarlo por la tool sin romper integridad.
Subprocess sin shell ni credenciales/preloads del host; stdout/stderr del CLI se
consumen sin persistir transcript. Se devuelve proyección de versiones, conteos,
pending y flags de estado: no código, outputs crudos o registry de otros roots.
Faltantes no son cero; arrays de pending se proyectan a conteos, no nombres.

Locks propios de metadata por worktree, registry y exclude evitan solapamientos
cooperativos; owner/shape/hardlink/symlink desconocidos se rechazan, no se adoptan
o borran. No sustituyen los locks de upstream o una transacción frente a otros
programas/operadores. Un fallo posterior a indexar puede dejar índice modificado
aunque falle el registro: no se simula rollback ni éxito de metadata.

Cancelación/timeout se dirige sólo al proceso CLI propio/grupo hijo; no descubre o
mata un daemon compartido por PID/nombre, ni ejecuta unlock/uninit. Bound de30 min y
4MiB de stdout aceptado, stderr descartado. Fallo/interrupción puede dejar trabajo
parcial: informar y esperar pedido, sin reparar/reintentar en silencio.

## Evidencia verificada

- Addon55 tests Python:54 OK,1 skip opt-in del adaptador Claude. Incluyen7 nuevos
  lifecycle, metadata/state/roots, symlinks y worktrees con ramas unborn sin commits.
- Copia temporal de sólo dos paquetes públicos del runtime1.5.0: status ausente,
  init, adopción, edición deliberada del fixture, sync, reindex confirmado y status
  final; conteos reales de archivo/nodos/aristas. Fuente modificada sólo por el test,
  no .gitignore o codegraph.json. No lectura/copia de HOME/cache/auth/índices reales.
  Test opts NO_DAEMON/NO_WATCH sólo en su binding temporal, no producción.
- Host2.2.7/mock prueba tool y slash status hacia inspector, rechazo interactivo,
  sync/reindex permitidos, falta de confirmación/actor/session bypass, subdirectorio
  y script tampered bloqueados. CLI falso sólo escribe índice sintético/metadata;
  no shell ampliado, secretos heredados o llamadas LLM reales.
- Candidato general:66 Node+3 Python, composición con22 roles/33 skills/**32 comandos**/
  7 registries/5 MCP. Plan/status reales sólo metadata, not-prepared219 assets tras benchmark.

## Benchmark nativo posterior: history/capture/report

El candidato ahora tiene quinto comando y tool `codegraph-benchmark`, separado de
MCP/lifecycle. API HTTP pública2.2.7 dentro del servidor, conexión del launcher por
pipe sólo RAM, proyección metadata y store schema3 separado; recaptura reemplaza
atómicamente la misma identidad como V1, sin duplicar corrida. Sin SQL,
export, shell o DB V1. Permisos read/capture ask, sin Edit general al inspector.
Total derivado versionado de componentes exclusivos, no total reportado/billing;
no pares mixtos V1/V2. El usuario delegó aplicar esta mejora, no recortar utilidad.

14 Node y57 Python (56 OK/1 skip) del owner: captura/report/history, compaction,
fork/revert activo, hijo/rangos/permisos/privacidad/frozen counters probados en
fixtures; general66+3 y smokes29/41 OK. No benchmark o datos/modelos reales.
Contrato y límites: [TELEMETRY-DESIGN.md](TELEMETRY-DESIGN.md). D06 se recuperó después
en base por atribución almacenada, no por D02; trabajo borrado/externo o migración
integral D01 siguen sin certificarse. Restan Documents/Notifier, ventana
autorizada de instalación/verificación y gates general→AUNE→proyecto.
