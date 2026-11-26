# CodeGraph en OpenCode V2

## Runtime vigente y actualización

El addon nativo V2 usa **CodeGraph 1.6.4** (SQLite schema 16,
extractor 29). El pin y la integridad publicados están en `nativeV2`
de `CODEGRAPH-MANIFEST.json`. La instalación legacy V1 conserva su
pin y flujo anteriores; no se usa su binario como fallback de V2.

El operador prepara el paquete `@colbymchenry/codegraph@1.6.4` desde
npm en un prefijo nuevo `~/.local/share/super-turing-opencode-codegraph/runtime-v2-1.6.4`,
con las dependencias opcionales de la plataforma y el `dist.integrity`
del manifiesto. Por ejemplo, desde el repo del addon, con autorización
de instalación y un prefijo todavía inexistente:

```bash
version=$(jq -er .nativeV2.version CODEGRAPH-MANIFEST.json)
integrity=$(jq -er .nativeV2.npmIntegrity CODEGRAPH-MANIFEST.json)
package="@colbymchenry/codegraph@$version"
prefix="$HOME/.local/share/super-turing-opencode-codegraph/runtime-v2-$version"
test ! -e "$prefix" && test ! -L "$prefix" &&
test "$(npm view "$package" dist.integrity --registry=https://registry.npmjs.org/)" = "$integrity" &&
npm install --prefix "$prefix" --save-exact --ignore-scripts --include=optional --no-audit --no-fund \
  --registry=https://registry.npmjs.org/ "$package" &&
test "$(jq -er '.packages["node_modules/@colbymchenry/codegraph"].integrity' "$prefix/package-lock.json")" = "$integrity" &&
test "$(CODEGRAPH_NO_DOWNLOAD=1 CODEGRAPH_TELEMETRY=0 CODEGRAPH_NO_UPDATE_CHECK=1 "$prefix/node_modules/.bin/codegraph" --version)" = "$version"
```

No componer si falla alguna verificación; no reemplazar un prefijo activo.
El selector
también acepta un `runtime-candidate-1.6.4` ya instalado si el nuevo
prefijo no existe, pero nunca un runtime de otra versión. La selección
no instala ni modifica el OpenCode activo.

1. Cerrar los clientes que usen el índice a trasladar. Preservar su
   directorio completo y el binding anterior para rollback.
2. Reusar el índice existente si su esquema, extractor, estado e
   identidad de checkout son compatibles. No repetir `init` por
   rutina ni copiar SQLite entre worktrees.
3. Un índice de esquema distinto no se abre ni con `status` ni con
   `reindex` confirmado. Para renovarlo, preparar una ruta aislada y
   usar el lifecycle nativo con la aprobación del operador. Si sólo
   cambia el extractor y el esquema es compatible, el `reindex`
   confirmado sigue disponible. Validar antes de activar la ruta
   definitiva y retirar binarios o copias antiguas.

El arranque MCP usa un cwd sin índice ancestro. La consulta y el
mantenimiento comprueban metadatos SQLite checkpointed de sólo
lectura antes de iniciar cualquier apertura del índice. Un resultado
incompleto o no comprobable se rechaza sin migrar. La guarda por
nombres versionados se mantiene: `codegraph.json` y el filtro de
salida no autorizan abrir fuentes protegidas ni saltar esa guarda.
El filtro nativo retiene resultados de `explore` con nombres o
marcadores reconocidos antes del historial y del próximo turno; no
es un detector universal ni sanea resultados anteriores.

El benchmark registra el pin del binding y la versión de OpenCode
**al capturar**; no prueba qué versión ejecutó la sesión histórica.
Pares con pins faltantes, etiquetas antiguas o bindings distintos
quedan fuera de la comparación sin reescribir capturas previas.

## Puesta en servicio original (histórica)

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

La auditoría de instalación V1 original informó runtime **1.5.0**,
16 assets presentes sin drift, MCP canónico habilitado, filtro `explore`
y telemetría desactivada. Ese runtime no es el binding V2 vigente.

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

**Read-only semántico no significa cero escrituras físicas.** Tras
el control de compatibilidad, CodeGraph conserva SQLite/WAL, locks,
daemon, catch-up y watchers normales. No se abre un esquema anterior
para migrarlo en sitio.
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


Usá la entrada gestionada con el addon configurado; ver [Core](https://github.com/juanma91m/super-turing-opencode/blob/main/v2/install/README.md).


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


Usá la entrada gestionada con el addon configurado; ver [Core](https://github.com/juanma91m/super-turing-opencode/blob/main/v2/install/README.md).


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
