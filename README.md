# super-turing-opencode-codegraph

Addon global y opcional para incorporar [CodeGraph](https://github.com/colbymchenry/codegraph) al ecosistema `super-turing-opencode` sin duplicar integración en cada proyecto.

## Responsabilidad

Este repo es dueño de:

- runtime CodeGraph fijado y reproducible,
- registro MCP global en OpenCode,
- exposición mínima de `codegraph_explore`,
- wrappers seguros para `init`, `status`, `sync` y reindex explícito,
- lifecycle `install` / `status` / `uninstall`,
- skill y playbook de análisis estructural.
- benchmark A/B sanitizado para medir costo, reemplazo de búsqueda manual y calidad.

No es dueño de:

- memoria durable ni corpus semántico (`super-turing-opencode-knowledge`),
- reglas de dominio de un producto,
- índices compartidos entre repositorios o worktrees,
- modificaciones funcionales de los proyectos indexados.

## Modelo de despliegue

```text
~/.config/opencode/                         assets + MCP global
~/.local/share/super-turing-opencode-codegraph/runtime/
                                            runtime fijado
~/.local/state/super-turing-opencode-codegraph/projects.json
                                            inventario machine-local
<repo>/.codegraph/                          índice regenerable por root
```

La capacidad es global, pero el grafo permanece junto al checkout que representa. El addon agrega `.codegraph/` a `.git/info/exclude`; no obliga a versionar archivos del índice ni crea overlays `.opencode/` por proyecto.

## Upstream fijado

- CodeGraph: `1.5.0`
- npm: `@colbymchenry/codegraph@1.5.0`
- release: <https://github.com/colbymchenry/codegraph/releases/tag/v1.5.0>

El pin vive en `CODEGRAPH-MANIFEST.json`. Una actualización de upstream debe cambiar ese pin, validar compatibilidad de índices, actualizar `CHANGELOG.md` y subir la versión del addon.

## Instalación

```bash
git clone git@github-juanma91m-v2:juanma91m/super-turing-opencode-codegraph.git
cd super-turing-opencode-codegraph
bash scripts/install.sh
```

La instalación:

1. instala la versión fijada en un prefix machine-local,
2. copia commands, skill, playbook y wrappers,
3. registra el MCP `codegraph` en `~/.config/opencode/opencode.json`,
4. deshabilita telemetría y update checks en el proceso MCP,
5. oculta `codegraph_*` globalmente y lo habilita solo en agentes de análisis aprobados,
6. valida con `opencode debug config`.

Reiniciá OpenCode después de instalar para cargar el nuevo MCP y los assets.

## Uso por proyecto

El routing se decide por la pregunta: priorizar el grafo para relaciones, flujos o
impacto estructural que aún falten, no para un dato literal ya localizado sin esa
incertidumbre. Un símbolo localizado puede seguir requiriendo análisis de coupling.
Conservar las prioridades locales; el tamaño del repo o del índice no obliga a
consultarlo. El contrato común vive en la skill y el playbook, sin copiar dominio
ni reescribir agentes por proyecto. Claude mantiene su adaptación de identificadores.

Cada consulta debe pasar `projectPath` absoluto del root Git/worktree real, también
desde un subdirectorio. Acotar símbolos/componentes y leer directamente solo lo
que falte: el fragmento recibido no equivale al archivo entero. Ante falta de acceso,
índice o respuesta suficiente, declarar la limitación sin bypass o reparación
automática. Una reference no crea un grafo cross-repo. Los presupuestos no son cuotas
ni se multiplican por root; no cambiar lifecycle, permisos o motor para cumplirlos.

Inicializar o adoptar un índice:

```bash
/codegraph-init /ruta/al/repo
```

Operaciones normales:

```bash
/codegraph-status /ruta/al/repo
/codegraph-sync /ruta/al/repo
```

Medir dos sesiones equivalentes:

```bash
/codegraph-benchmark capture --session <id-con> --variant with-codegraph --pair-id flujo-auth-01 --project <proyecto> --task-kind blast-radius --policy-version <política> --dedicated-task --outcome accepted --utility yes --corrections-required 0
/codegraph-benchmark capture --session <id-sin> --variant without-codegraph --pair-id flujo-auth-01 --project <proyecto> --task-kind blast-radius --policy-version <política> --dedicated-task --outcome accepted --utility not-applicable --corrections-required 0
/codegraph-benchmark report
```

El porcentaje principal compara tokens totales por pares y solo incluye resultados
`accepted` del mismo proyecto, modelo y tipo de tarea. Los registros se guardan en
`~/.local/state/super-turing-opencode-codegraph/benchmarks/` sin prompts ni outputs
crudos.

La captura debe ejecutarse desde una sesión operadora distinta de las dos sesiones
medidas, para no agregar el propio comando de benchmark a sus tokens y tools.

### Telemetría retrospectiva (sin capturas previas)

```bash
/codegraph-benchmark history --since 2026-09-12 --until 2026-10-25
```

Lee la base local de OpenCode en modo read-only, seleccionando en SQL solo uso,
nombres de tools, relaciones y tiempos, nunca prompts, argumentos ni outputs crudos.
Agrupa familias no solapadas por proyecto/modelo; no son tareas equivalentes.
Incluye desglose de tokens, latencia, búsqueda manual y sesiones hijas verificables.
No infiere calidad, tipo de tarea ni versión histórica de la política. No calcula
porcentajes causales. Campos ausentes: `null` en JSON y `n/a` en Markdown.

El esquema de métricas es v2 e independiente del pin de runtime. Para actualizar
solo esta instrumentación: `bash scripts/install.sh --metrics-only`.

Reindexar es explícito porque reemplaza el índice regenerable actual:

```bash
/codegraph-reindex /ruta/al/repo
```

## Compatibilidad y adopción

- Si `.codegraph/` no existe, el wrapper ejecuta `codegraph init`.
- Si existe, ejecuta `status` y lo adopta sin reinicializar.
- Si CodeGraph recomienda reindex, el wrapper se detiene y lo informa.
- Nunca mueve el índice a Qdrant, Engram ni al directorio del addon.
- Cada worktree debe inicializar su propio `.codegraph/`.

## Seguridad y privacidad

- MCP limitado a `CODEGRAPH_MCP_TOOLS=explore`.
- `codegraph_explore` es read-only.
- `CODEGRAPH_TELEMETRY=0`, `DO_NOT_TRACK=1` y `CODEGRAPH_NO_UPDATE_CHECK=1` se fijan en el MCP y wrappers.
- Roots `/`, `$HOME`, directorios temporales y escapes por symlink son rechazados.
- `uninit` y `unlock` no se exponen como autonomía normal.
- El output del grafo se trata como evidencia; no reemplaza lectura puntual ni criterio técnico.
- La instrumentación lee proyecciones de SQLite read-only y persiste únicamente agregados y metadatos mínimos. Los exports sanitizados siguen siendo compatibles con el extractor, pero no son necesarios para `history`/`capture`.

## Estado y desinstalación

```bash
bash scripts/status.sh
bash scripts/uninstall.sh
```

El uninstall remueve assets globales, wiring MCP y runtime administrado. Preserva todos los `<repo>/.codegraph/` y `codegraph.json` existentes.

Más detalle en [INSTALLATION.md](INSTALLATION.md) y [PLAYBOOK-CODEGRAPH.md](PLAYBOOK-CODEGRAPH.md).
