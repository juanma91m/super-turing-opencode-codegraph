import { Plugin } from '@opencode/plugin';
import { register } from './access.mjs';

export default Plugin.define({ id: 'opencode-codegraph.access', setup: register });
