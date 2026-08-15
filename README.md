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

Inicializar o adoptar un índice:

```bash
/codegraph-init /ruta/al/repo
```

Operaciones normales:

```bash
/codegraph-status /ruta/al/repo
/codegraph-sync /ruta/al/repo
```

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

## Estado y desinstalación

```bash
bash scripts/status.sh
bash scripts/uninstall.sh
```

El uninstall remueve assets globales, wiring MCP y runtime administrado. Preserva todos los `<repo>/.codegraph/` y `codegraph.json` existentes.

Más detalle en [INSTALLATION.md](INSTALLATION.md) y [PLAYBOOK-CODEGRAPH.md](PLAYBOOK-CODEGRAPH.md).
