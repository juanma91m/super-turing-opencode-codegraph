# CodeGraph en OpenCode V2 oficial — incremento de consulta

## Estado

`v2/general.mjs` agrega el aporte nativo al candidato general, sin
boundary de workshop ni init automático. Usa cwd de caché neutral y rechaza
ancestros con `codegraph.db`; una carpeta de estado sola no es índice. Catálogo,
permisos y paths se validaron en composición con fixtures, sin abrir índices reales.
MCP sigue query-only; cuatro comandos lifecycle/tool separados ya están portados y
probados en temporales: [NATIVE-LIFECYCLE.md](NATIVE-LIFECYCLE.md). Benchmark nativo
history/capture/report también implementado/probado, no compatible por nombre con V1. No activar/recomponer workshop por
este port. Ver `opencode-stack/v2/general/COMPOSED.md` para estado general vigente.
El contrato API, medición derivada versionada, transporte privado/proyección en RAM,
permisos y límites están en [TELEMETRY-DESIGN.md](TELEMETRY-DESIGN.md).14 Node OK y57
Python (56 OK/1 skip) del owner; no se abren DBs originales ni sesiones/modelos reales.
Corrección de paridad: capture reemplaza atómicamente la misma identidad como
atomic_write_json V1, para corregir evaluación sin duplicar corrida. Report no
recaptura por sí solo; retirado el no-overwrite añadido en el incremento inicial.
Incremento base D06: native-messages.mjs es ahora shim del transporte común de
opencode-stack/v2/native-history.mjs; conserva layout sibling en bundle. Función GET
opaca en RAM evita doble consumo fd3 por el bundler del pin. Atribución y benchmark
probados en ambos órdenes, permisos/proyección independientes; no DB V1/migración.

Implementado y aplicado por el operador con el host oficial **2.2.7**. El operador
confirma CodeGraph Connected y el plan posterior indica `applied; actual indexed
query is separate`, conservando Rovo resource-metadata. El plan no consulta el
estado conectado; esa evidencia es del operador. Una captura posterior confirma
carga de skill y una llamada real a codegraph_codegraph_explore con root explícito
autorizado, ejecutada por master-dev (también permitido). El resumen reporta datos
del índice, sin error ni avisos explícitos. La pregunta genérica de entrypoint
recuperó un script de carga, no el entrypoint principal; la relación informada no
quedó corroborada por el cuerpo de código devuelto. **Conexión/ejecución real
comprobadas; utilidad/relevancia de esa respuesta parcial**, sin certificar frescura
o cobertura. No persistir paths/símbolos o código del resultado en este documento.
No se inicializó, sincronizó o reindexó ningún proyecto real ni se modificó V1.

La auditoría de instalación V1 informó runtime **1.5.0**, 16 assets presentes sin
drift, MCP canónico habilitado, filtro `explore`, telemetría desactivada. Se reutiliza
ese runtime; no hay descarga, recompilación ni copia de índices o backends nuevos.

## Alcance y permisos

- Composición aditiva sobre Knowledge, Ticketing, Context7 y libnotify.
- 15 agentes, 20 skills, los mismos 11 comandos de addons anteriores.
- Sólo `explore`, para code-inspector, planner, reviewer, code-reviewer y master-dev.
  Los otros diez actores quedan sin acceso; tools desconocidas no reciben grants.
- En el wire upstream la tool se llama `codegraph_explore`. El host V2 antepone el
  nombre del servidor y expone **`codegraph_codegraph_explore`**, comprobado con
  llamadas nativas. La skill/playbook del perfil adaptan sólo esa referencia; los
  assets V1 y su identidad de tools no se reescriben.
- `projectPath` debe ser absoluto, root Git/worktree exacto y tener `.codegraph/`
  existente. El guard rechaza root implícito/relativo, symlinks, subdirectorios y
  uso accidental de un índice del checkout padre. No crea/adopta un índice ni
  comprueba su cobertura/frescura; esas limitaciones siguen siendo evidencia del
  backend, no motivo para reparar automáticamente.
- Los permisos nativos de rol/sesión siguen aplicando; un deny local no se elimina.
  No se habilita shell general ni lectura directa fuera de la frontera del piloto.

## Runtime y efectos

`selected-runtime.py` lee sólo el wiring actual revisado, exige pin y binario
administrado presentes y rechaza configuración distinta, credenciales o permisos
no reconciliados sin imprimir valores. `runtime.py` hace **exec** del launcher
existente `serve --mcp`, no es un proxy. Restaura HOME/XDG para conservar identidad
machine-local, elimina credenciales/preloads heredados y conserva tuning explícito
validado de watcher/daemon/debounce/pool; no añade flags para desactivarlos.
`CODEGRAPH_DIR` explícito se conserva y el guard consulta ese mismo directorio,
sin redirigir silenciosamente a otro índice del worktree.

Se fijan telemetría/update checks apagados, igual que V1. `CODEGRAPH_NO_DOWNLOAD=1`
evita self-heal por red si falta el bundle: falla con claridad en lugar de instalar.
El guardrail no cambia el runtime sano ya presente ni resuelve faltantes en silencio.

**Read-only semántico no significa cero escrituras físicas.** Al abrir proyectos,
CodeGraph conserva SQLite/WAL/migraciones, locks, daemon, catch-up y watchers normales.
El servidor del workshop se inicia fuera de índices por defecto y las consultas
eligen root explícito; no se desactivan mecanismos upstream ni se promete un sandbox
OS. El coordinador rechaza abrir MCP si el workshop tiene un ancestro con DB de índice.

## Qué quedó fuera del piloto histórico de consulta

En el workshop no se habilitan lifecycle/benchmark. El candidato general posterior
ya tiene cuatro comandos con tool tipada, no shell; no son parte del piloto. Sus
wrappers/globales V1 siguen intactos para el operador. No se copian
comandos que después apunten a runtime inexistente o a la DB V1 desde el HOME V2.

El benchmark V1 valida tablas `session/message/part`: no ejecutarlo contra V2.
El candidato tiene adapter público distinto y store schema3, sin importar legacy,
con total derivado explícito y reported_total n/a. Su recuperación sintética no
autoriza benchmark real ni certifica historia borrada/externa o runtime histórico.
La aceptación real del candidato y el corte global conservan sus gates separados.

## Validación realizada

Desde el addon:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp/opencode python3 -m unittest discover -s tests -v
```

47 tests ejecutados: 46 OK y un skip del adaptador Claude no solicitado. Incluye
selección metadata-only, rechazo de drift/secretos/overrides, runtime ausente,
aislamiento de entorno y preservación de tuning explícito.

Desde opencode-stack:

```bash
KNOWLEDGE_API_NATIVE=1 node --test migrations/v2/test/*.test.mjs
node migrations/v2/smoke-codegraph.mjs
node migrations/v2/smoke-ticketing.mjs
node migrations/v2/smoke-ticketing-oauth.mjs
node migrations/v2/codegraph.mjs plan
```

- **71 tests de migración** pasaron, incluyendo API nativa y upgrade/reapertura.
- **23 casos nativos CodeGraph**: cinco actores permitidos, diez denegados, roots
  inválidos/sin índice/symlink/subdirectorio, tools fuera de catálogo e init, deny
  de sesión, respuesta útil fixture comprobada y aplicación intacta.
- El runtime **real 1.5.0** completó initialize/catalog con V2 sobre root desechable
  no indexado; no hubo tools/call reales, índices creados o consultas a repos reales.
- El smoke mantiene cuatro MCP y ejecuta los inspectores Knowledge/Ticketing,
  con credenciales/modelos ficticios y sin calls Jira/Confluence.
- Pasaron también 21 casos Ticketing y los cinco modos OAuth loopback anteriores.
- Pasó `debug config --standalone` oficial, sin parches de core o Background.
- Se verificó preservación de app/CLI/guardas y de Rovo **resource-metadata**, sin
  volver al scope explícito que había provocado el problema de integración.

## Aplicación al workshop

Cerrar primero el cliente del workshop V2, no producción V1. `--client-closed` es
confirmación humana, no detección automática ni autorización para matar procesos.

```bash
node "$HOME/.local/src/opencode-stack/migrations/v2/codegraph.mjs" apply --client-closed
node "$HOME/.local/src/opencode-stack/migrations/v2/codegraph.mjs" chat
```

Si apply falla, detenerse; no repetir instaladores ni indexar para corregirlo.
La actualización compara el lote conocido antes de reemplazar, hace backups
`.pre-codegraph.bak` y deja `.codegraph-v2-enabled.json`. Es atómica por archivo,
no una transacción FS global. `ticketing-profile.mjs` reconstruye el estado previo
sin desplegarlo. El launcher Ticketing anterior rechaza recomponer después del
marker CodeGraph; usar **codegraph.mjs chat|verify** para conservar todos los addons.

Apply/verify inspeccionan estado/catálogos y roles, sin ejecutar consultas de índice
o tools Jira. No equivalen a probar una pregunta sobre un índice existente.

## Prueba real: ejecución comprobada, relevancia parcial

La primera prueba ya se ejecutó, con el límite descrito en Estado. Si se quiere
evaluar utilidad antes de ampliar el uso, elegir una función/clase/endpoint de
aplicación conocido y una frontera concretos; no repetir la consulta genérica ni
reindexar por un resultado poco alineado. No tratar el OK técnico como calidad
funcional. El procedimiento siguiente queda como referencia de la prueba inicial.

En una sesión nueva del workshop, seleccionar **planner**. El operador elige un
root Git/worktree **absoluto, ya indexado**, y un símbolo/pregunta concretos. No
tomar otro repo por proximidad ni crear `.codegraph/` para hacer pasar la prueba.

```text
Probemos CodeGraph sólo en lectura.
Root autorizado ya indexado: <ROOT_GIT_ABSOLUTO>
Símbolo o flujo acotado: <SIMBOLO_O_FLUJO>

Cargá la skill codegraph-analisis-estructural y usá una sola consulta de
codegraph_codegraph_explore con projectPath explícito a ese root. Necesito
comprobar si devuelve evidencia estructural útil (símbolo y una relación o
ubicación concreta), no un mapa global ni una mera orientación sin grafo.

No inicialices, sincronices, reindexes, copies índices, cambies watchers ni
ejecutes lifecycle/benchmark. No modifiques archivos ni guardes outputs en
memoria/corpus. Si falta índice, acceso o hay degradación/staleness, informalo
y detené la prueba sin reparaciones. No uses CLI/delegación como bypass.

Informá sólo tool usada, root correcto sí/no, evidencia estructural presente
sí/no y avisos/limitaciones. No copies código privado ni secretos en el resumen.
```

El operador puede compartir el resultado resumido, sin outputs crudos. Una respuesta
con nodos/aristas no demuestra cobertura total ni vigencia de toda la arquitectura.
