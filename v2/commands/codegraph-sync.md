---
description: Sincroniza explícitamente un índice CodeGraph existente, sin init o reindex de fallback.
agent: master-dev
---
Sólo por pedido explícito, usá codegraph-project action sync con projectRoot absoluto exacto de $ARGUMENTS o del repo actual verificado. Conservar permiso nativo de escritura del índice; no ampliar permisos/shell de code-inspector para hacerlo. Requiere índice existente compatible. Ausente/incompleto/mismatch/reindex recomendado: detenerse, sin init/index --force ni reparación automática. Informar estado final y límites; puede haber writes normales de runtime, no cambios funcionales de aplicación. No sincronizar por conectar MCP o antes de cada consulta.
