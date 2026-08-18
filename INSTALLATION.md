# Instalación

## Requisitos

- Linux, macOS o Windows/WSL soportado por CodeGraph 1.5.0,
- `node` y `npm` para instalar el launcher fijado,
- `python3`,
- `git`,
- OpenCode con configuración JSON válida.

## Instalación global

```bash
bash scripts/install.sh
```

El mismo contrato expone `scripts/preflight.sh`; la distribución lo ejecuta
antes de modificar el target para validar Python, Git, Node y npm.

Opciones:

```text
--target-dir <path>    config OpenCode destino
--runtime-dir <path>   prefix machine-local del runtime
--assets-only          no instalar ni actualizar runtime
--dry-run              mostrar acciones sin escribir
--no-validate          omitir opencode debug config
```

El installer es idempotente y falla cerrado si ya existe un bloque MCP o una regla `codegraph_*` incompatible que no le pertenece.

## Validación

```bash
bash scripts/status.sh
opencode debug config
```

Estado esperado:

```text
runtime_present=yes
runtime_version=1.5.0
mcp_configured=yes
mcp_enabled=yes
mcp_tools=explore
telemetry_disabled=yes
managed_files_missing=0
managed_files_mismatched=0
```

## Bootstrap de un proyecto

```bash
bash ~/.config/opencode/scripts/codegraph_project_init.sh --project-root /ruta/al/repo
```

El wrapper:

1. resuelve el root Git real,
2. rechaza roots inseguros,
3. protege `.codegraph/` en `.git/info/exclude`,
4. adopta un índice compatible o inicializa uno nuevo,
5. registra el proyecto machine-localmente,
6. devuelve `codegraph status --json`.

No genera `codegraph.json`; ese archivo solo corresponde cuando el repo necesita inclusiones/exclusiones no estándar.

## Desinstalación

```bash
bash scripts/uninstall.sh
```

Opciones:

```text
--keep-runtime         conservar runtime machine-local
--dry-run              mostrar acciones sin escribir
```

Los índices de proyecto se preservan siempre. Para remover uno se usa `codegraph uninit` manualmente fuera del lifecycle global, después de confirmación explícita.
