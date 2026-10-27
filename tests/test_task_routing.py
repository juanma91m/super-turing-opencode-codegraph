"""Contract regressions, not a runtime router or proof of model obedience."""
from __future__ import annotations

import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / 'skills/codegraph-analisis-estructural/SKILL.md').read_text()
PLAYBOOK = (ROOT / 'PLAYBOOK-CODEGRAPH.md').read_text()
README = (ROOT / 'README.md').read_text()


def section(text: str, heading: str) -> str:
    return text.split(heading + '\n', 1)[1].split('\n## ', 1)[0]


def normalize_client(text: str) -> list[str]:
    text = text.replace('la tool `mcp__codegraph__explore`', '`codegraph_explore`')
    text = text.replace('`Glob`/`Grep`/`Read`', '`glob`/`grep`/`read`')
    text = text.replace('`Grep`/`Read`', '`grep/read`')
    for before, after in (('`Glob`', '`glob`'), ('`Grep`', '`grep`'), ('`Read`', '`read`')):
        text = text.replace(before, after)
    text = text.replace('entre worktrees — cada worktree necesita su propio índice.', 'entre worktrees.')
    return [line.strip() for line in text.splitlines() if line.strip()]


class TaskRoutingContractTest(unittest.TestCase):
    def test_existing_metadata_and_tool_identity_remain_explicit(self):
        header, body = SKILL.split('\n---\n', 1)
        self.assertIn('name: codegraph-analisis-estructural', header)
        self.assertIn('compatibility: opencode', header)
        self.assertIn('no usar para búsquedas literales ni para inicializar índices autónomamente', header)
        self.assertIn('Consultar `codegraph_explore`', body)
        self.assertNotIn('mcp__codegraph__', SKILL)

    def test_structural_priority_is_not_removed_by_finding_a_file(self):
        selection = section(SKILL, '## Elección de evidencia')
        for clause in ('Priorizar el grafo si falta una relación estructural',
                       'el índice existe y el rol tiene acceso autorizado',
                       'sin incertidumbre estructural, preferir lectura directa',
                       'existencia o tamaño del índice no obligan',
                       'Un símbolo localizado puede seguir requiriendo análisis de callers/impacto',
                       'Preservar las prioridades de dominio y contratos locales, sin ampliar permisos'):
            self.assertIn(clause, selection)

    def test_real_absolute_root_is_required_on_every_query(self):
        flow = section(SKILL, '## Flujo')
        for clause in ('root Git/worktree real y absoluto', 'no el directorio de su overlay',
                       '`projectPath` absoluto en cada consulta', 'también desde subdirectorios',
                       'no depender del default implícito'):
            self.assertIn(clause, flow)
        self.assertNotIn('siempre que no haya default inequívoco', SKILL)
        self.assertIn('Una reference no crea aristas cross-repo ni autoriza indexar otro checkout', SKILL)

    def test_scope_is_bounded_without_prohibiting_requested_architecture(self):
        flow = section(SKILL, '## Flujo')
        self.assertIn('pregunta corta, símbolos concretos y una frontera de módulo/componente', flow)
        self.assertIn('mapa global solo si es el pedido', flow)
        self.assertIn('argumentos soportados por el schema anunciado', flow)
        self.assertIn('no inventar parámetros ni cambiar el motor', SKILL)

    def test_only_received_fragments_are_read_evidence(self):
        flow = section(SKILL, '## Flujo')
        for clause in ('solo el fragmento realmente devuelto', 'no el archivo entero por ver su nombre',
                       'donde falte evidencia material', 'no repetir una exploración completa ya cubierta',
                       'Contrastar findings materiales con diff, tests o lectura directa'):
            self.assertIn(clause, flow)

    def test_previous_budgets_remain_budgets_not_quotas(self):
        budget = section(SKILL, '## Presupuesto de consultas')
        self.assertIn('En code review, usar una sola consulta compacta centrada en los símbolos del diff.', budget)
        self.assertIn('En planning o implementación, usar normalmente hasta tres consultas: mapa inicial, una profundización y una verificación puntual.', budget)
        for clause in ('debe reemplazar exploración manual', 'Si la primera respuesta no reduce lecturas',
                       'Son presupuestos, no cuotas', 'una consulta suficiente permite terminar',
                       'No multiplicarlos por cada root referenciado', 'ni relajar el contrato del review formal'):
            self.assertIn(clause, budget)

    def test_fallback_covers_unavailable_partial_stale_and_soft_guidance(self):
        fallback = section(SKILL, '## Fallback')
        for clause in ('falta índice/tool/acceso', 'la respuesta es parcial', 'staleness/degradación',
                       'usar `glob`/`grep`/`read`', 'una orientación sin `isError` no prueba',
                       'no repetir los mismos argumentos', 'CLI u otro agente para eludir restricciones'):
            self.assertIn(clause, fallback)

    def test_fallback_does_not_become_lifecycle_or_permissions_autonomy(self):
        fallback = section(SKILL, '## Fallback')
        for clause in ('no inicializar ni reindexar por cuenta propia',
                       'no lanzar `status` antes de cada consulta ni reparaciones automáticas',
                       'no alterar watcher/autosync configurados'):
            self.assertIn(clause, fallback)
        self.assertIn('si el usuario quiere habilitarlo', fallback)

    def test_index_limits_and_privacy_are_not_shortcuts(self):
        limits = section(SKILL, '## Límites')
        for clause in ('parsing dinámico o código generado', 'No usarlo como prueba única de ausencia de callers',
                       'No guardar el output crudo', 'No compartir `.codegraph/` entre worktrees',
                       'no certifican cobertura, compatibilidad o frescura',
                       'Configuración externa y relaciones dinámicas/generadas requieren corroboración'):
            self.assertIn(clause, limits)

    def test_global_playbook_and_readme_agree_on_selection_and_roots(self):
        for text in (PLAYBOOK, README):
            with self.subTest(document='playbook' if text == PLAYBOOK else 'README'):
                for clause in ('incertidumbre', '`projectPath` absoluto', 'subdirectorio',
                               'fragmento', 'reference', 'permisos'):
                    self.assertIn(clause, text)
        for clause in ('## Lifecycle', '## Worktrees', '## Roles', '## Medición A/B',
                       'con consentimiento del usuario', 'reindex', 'no inicializar ni reindexar',
                       'sin `isError`', 'no como estación previa a todo'):
            self.assertIn(clause, PLAYBOOK)

    @unittest.skipUnless(os.environ.get('CLAUDE_CODEGRAPH_SKILL'), 'Explicit Claude adapter source required')
    def test_client_adaptation_preserves_the_same_policy_without_normalizing_ids(self):
        claude = Path(os.environ['CLAUDE_CODEGRAPH_SKILL']).read_text()
        self.assertIn('mcp__codegraph__explore', claude.split('\n---\n', 1)[0])
        self.assertIn('Consultar la tool `mcp__codegraph__explore`', claude)
        self.assertNotIn('compatibility: opencode', claude)
        for heading in ('## Cuándo cargar esta skill', '## Elección de evidencia', '## Flujo',
                        '## Presupuesto de consultas', '## Fallback', '## Límites'):
            with self.subTest(section=heading):
                self.assertEqual(normalize_client(section(SKILL, heading)),
                                 normalize_client(section(claude, heading)))
        self.assertRegex(claude, r'(?m)^name: codegraph-analisis-estructural$')
        self.assertIn('su vigencia y cobertura deben corroborarse', claude)


if __name__ == '__main__':
    unittest.main()
