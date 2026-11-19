# Benchmark V2 — contrato nativo y medición versionada

**Corrección de paridad V1:** recapturar la misma identidad reemplaza atómicamente
ese registro, igual que atomic_write_json de scripts/codegraph_metrics.py. La
inmutabilidad/no-overwrite descrita en el incremento inicial fue una regla añadida
y ya no aplica. Report no recalcula capturas solo; los cambios de evaluación se
guardan al ejecutar capture, sin duplicar corrida. Tests verifican actualización
de outcome y exclusión del par revisado, además de privacidad/guardas existentes.

## Estado y decisión

Implementados **history/capture/report** por tool `codegraph-benchmark` y comando
nativo en el candidato general, probados contra OpenCode oficial **2.2.7**. No están
instalados en el perfil real ni en el workshop. El usuario delegó aplicar la mejor
mejora conservando utilidad: se eligió proyección en RAM del servidor y una métrica
derivada explícita, no abandonar la comparación porque falta el total reportado.

No se abrió una DB original, sesión real o auth store. No SQL/export/CLI V1,
benchmark real, proveedor real, índice nuevo ni consulta a código del operador.
Las variantes A/B de los tests son fixtures sintéticos, no resultados de ahorro.
Esto recupera D02 en el candidato; no cierra por sí mismo D06/general→AUNE→proyecto ni autoriza
instalación, corridas reales o corte.

## Contrato comprobado en el pin

- `ctx.session.get/list` son públicos en el plugin. **`ctx.session.message` no
  existe en Plugin.Context 2.2.7**. La operación `session.message.list/get` está en
  la **API HTTP pública** `/api/session/{sessionID}/message[/{messageID}]`.
- La lista almacenada pagina por type/order/cursor. No tiene fields/projection/
  content=false/metadataOnly: assistant trae textos/reasoning y tools con cuerpos.
  Los límites de rango también pueden materializar el mensaje user en RAM.
- `session.context` no es la historia completa. Compaction completada conserva
  eventos assistant anteriores en la API almacenada del fixture; se cuenta su uso
  aparte y una sola vez. Fork es procedencia de copia distinta de `parentID` de
  subagente: se rechaza medir el fork, sin absorberlo en la familia fuente.
- Stats experimental agrega periodo/proyecto/tools, sin filtro sessionID ni bytes
  por output. No reconstruye una tarea comparable con límites de mensajes.
- `TokenUsage.Info`, Session.Info y stats no exponen `total`. Con fixture de entrada
 101, salida17, caché11 y reasoning3, el pin publica input90/output14/reasoning3/
 cache.read11/cache.write0: particiones exclusivas. `total_tokens:999` deliberado
  del proveedor simulado **no se conserva**.

Fuentes públicas del pin: `@opencode/plugin@2.2.7/dist/promise/{plugin,session}.d.ts`,
OpenAPI del host y tests reproducibles; no formatos privados de blobs `native`.

## Transporte y privacidad

El launcher base `owned-server.mjs` entrega la conexión a **su propio servidor** por
un pipe heredado fd3, después de recibir el loopback/puerto efímero de `serve --stdio`.
Descriptor pequeño con PID/versión/URL/password efímero; no archivos, argv, logs o
variable nueva con secreto. El flag de entorno contiene sólo el número de fd.
El adaptador lee/cierra el pipe una vez, valida PID propio y URL HTTP127.0.0.1 sin
credenciales/query/ruta, y retiene auth sólo en RAM. Sin launcher compatible falla
cerrado: no buscar otro daemon, DB, credenciales o endpoint por fallback.

Incremento D06: el transporte canónico ahora es base `v2/native-history.mjs`;
este owner conserva shim relativo, mismo layout en source y bundle. El pin compila
imports por plugin y duplica caches: compartir path no bastó. Una función GET
acotada en RAM del host comparte el lector/auth cerrado en closure, no descriptor
URL/password global o RPC nuevo; no vuelve a leer fd3. Probado con clon de módulo
y host oficial atribución→benchmark y orden inverso. Consumidores conservan sus
propios permisos/proyecciones; no sandbox contra plugins confiables del proceso.

Sólo hace GET de las dos rutas públicas de mensajes. No RPC privado/core import,
redirect, shell, inferencia o mutación del grafo. Errores HTTP/parser no vuelcan body,
endpoint o auth; timeout20s, cancelación y página8MiB. El permiso nativo se verifica
antes de leer cuerpos; roles y roots externos siguen restringidos.

Cada página se proyecta dentro del servidor antes de Python/tool/modelo/archivos:
IDs mínimos, tiempos, modelo/agente, estado/cantidad/nombre técnico de tools, bytes
y usage numérico. Se descartan prompt, adjuntos, texto, reasoning, argumentos,
outputs crudos, resumen/checkpoint, títulos, metadata arbitraria y blobs native.
El worker sólo recibe DTO de métricas. No se generan exports ni archivos temporales
con cuerpos; el store contiene únicamente metadata validada. No es sandbox contra
plugins/procesos confiables del mismo UID, secure erase o garantía sobre logs del core.

## Medición V2

```json
{
  "backend": "opencode-public-api-2.2.7",
  "tokens": "normalized-exclusive-component-sum-v1",
  "bytes": "stored-tool-content-json-utf8-v1",
  "history": "stored-assistant-plus-completed-compaction-v1"
}
```

- `metrics.tokens.total` = suma **derivada** de input/output/reasoning/cache.read/
  cache.write exclusivos. Fixture por llamada:118, no999 ni razonamiento sumado
  dos veces. `reported_total:null`; no equivalencia a billing o total reportado V1.
- Componente ausente/uso incompleto → null y cobertura missing, nunca cero inventado.
  Modelo/compaction incompletos impiden captura comparable. El flag scope.complete
  verifica enumeración observable/metadata, no trabajo borrado, externo o no enlazado.
- Bytes = UTF8 de output string o JSON del ToolContent almacenado estructurado,
  no bytes SQL V1 ni tokens visibles al modelo. Latencia y búsqueda manual también
  son observadas: glob/grep/read, no todo Bash/wrapper/búsqueda posible.
- Sólo `codegraph_codegraph_explore` cuenta como grafo; lifecycle/benchmark no cuentan.
  Cálculo puro reutiliza funciones canónicas V1 extraídas por AST con allowlists de
  funciones/constantes/calls. No CLI/SQL/export ni sus imports al runtime V2; cambios
  no revisados fallan. Worker y cálculo generado tienen SHA antes de cada invocación.

## Acciones, permisos y persistencia

- Actores: master-dev/agent-design/code-inspector/build materializado. Tool allow
  acotado, `codegraph-benchmark-read` y `codegraph-benchmark-capture` **ask**. No Edit
  ni shell general al inspector; escritura sólo al store fijo owner del binding.
- `history`: ventana UTC explícita since inclusivo/until exclusivo y directorio
  actual, model opcional. Familias raíz con parentID, operador/forks/roots activos o
  revertidos excluidos, vacíos omitidos. Devuelve distribuciones sin IDs de sesiones,
  calidad/política inferidas o ahorro causal. Familia hija ambigua/cambiante puede
  detener el historial completo: no devolver silenciosamente una parte como total.
- `capture`: sessionID/variant/pairID/project-label/taskKind/policyVersion/outcome,
  dedicatedTask o ambos límites exactos de mensaje. Operador fuera de la familia;
  hijos sólo parentID, una vez, permisos propios y clipping temporal en rangos.
  Utility/corrections son input explícito; no inferir aceptación por menor costo.
- Rechaza fork/revert activo, contaminación por operador, cursores/IDs duplicados,
  actor/permiso denegado, cobertura/modelo incompletos y variantes sin/con llamadas
  incompatibles. Hasta100 sesiones,100 páginas/lista,10000 eventos proyectados.
  Revalida metadata/uso/modelo/descendencia tras lectura **y después del permiso de
  captura**. Es control cooperativo, no snapshot/transacción de DB contra terceros.
- Store nuevo separado `runtime_home/.local/state/super-turing-opencode-codegraph/
  benchmarks-v2`, marker owner+measurement, directorios0700/registros0600, schema3,
  sin import legacy. Symlinks/hardlinks, permisos amplios, owner/medición/campos
   desconocidos rechazados. Reemplazo atómico de la misma identidad al recapturar,
   como V1; permite corregir evaluación sin duplicar corrida. No refresh implícito.
  Un crash puede dejar staging sólo de metadata; no adoptarlo/limpiarlo por reflejo.
- `report`: sólo capturas metadata fijas, hasta1000. Pares aceptados con una corrida
  por variante y mismas dimensiones/modelo/policy/alcance/measurement; mixtos V1/V2
  no se comparan. Porcentajes negativos se preservan, ceros/faltantes no son ahorro.
  Heurísticas1 llamada review/3 otras/10KiB no son cuotas ni política del motor.
  Versiones runtime describen el pin declarado al capturar, no prueba histórica.

## Evidencia y límites

```text
node --test v2/test/*.test.mjs
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test*.py'
```

14 Node OK;57 Python:56 OK/1 opt-in skip. Integración oficial: captura con354/sin236,
reporte negativo real para el fixture, history observacional, compaction sintética
almacenada (479 contando uso7 del hook), fork rechazado/fuente sin doble cuenta,
revert activo rechazado/clear, hijo contado una vez, rango118 y operador excluido.
33 requests mock explícitos; cero inferencia oculta de benchmark, cero modelo real.
Capturas previas354/236 no cambian por cambios de origen sin recaptura explícita.
Recaptura de misma identidad actualiza outcome/utilidad/correcciones y report
excluye el par revisado sin duplicados, igual que V1. Tests de
store/links/drift/approval/paginación/transporte validan rechazo sin cuerpos/secretos.
Worker Python -I/-B no importa módulos del cwd/adyacentes ni pyc del cálculo: carga
sólo los bytes fuente del asset pinneado. Shadow json.py del proyecto/config no ejecuta.

Falta uso real autorizado. Historial borrado/commit de revert, trabajo sin parentID,
externo/eliminado o runtime histórico no se reconstruyen ni se consideran completos.
D06 se recuperó posteriormente en base: agent_attribution general usa páginas
almacenadas y declara cobertura sólo de la sesión enumerada; workshop histórico
permanece context-scoped. Ver base v2/general/ATTRIBUTION.md. Ni ese cambio ni el
benchmark recuperan trabajo borrado/externo o certifican migración íntegra V1 D01,
ahorro estadístico o corte. Documents/Notifier y gates AUNE/proyectos siguen aparte.
