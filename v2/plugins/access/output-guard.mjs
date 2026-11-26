// Defense in depth, not a detector for arbitrary secrets or authority to
// index protected files. Rebuild only the reviewed text content shape.
export const withheld = 'OpenCode retuvo la respuesta de CodeGraph: contiene material potencialmente sensible o un formato no revisado.';
const protectedName = /(?:^|[\s`"'(/\\])(?:\.env[\w.-]*|\.ssh|\.gnupg|(?:auth|credentials|secrets|tokens?)\.json|[^/\s`"'()]+\.(?:key|pem|p12|pfx))(?=$|[\s`"'/\\:),\]])/im;
const credentialMarker = /-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----|\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})|(?:AKIA|ASIA)[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})\b/;
const acceptable = value => typeof value === 'string' && !protectedName.test(value) && !credentialMarker.test(value);

export function filterExploreResult(result) {
  const content = result?.content;
  if (acceptable(content)) return { content };
  if (Array.isArray(content) && content.length && content.every(part => part?.type === 'text' && acceptable(part.text)) &&
    acceptable(content.map(part => part.text).join(''))) {
    return { content: content.map(part => ({ type: 'text', text: part.text })) };
  }
  return { content: withheld };
}

export function guardExploreResult(event, tool) {
  if (event.tool !== tool) return;
  if (event.status === 'completed') event.result = filterExploreResult(event.result);
  if (event.status === 'error' && event.error) event.error.message = 'CodeGraph no pudo completar la consulta.';
}
