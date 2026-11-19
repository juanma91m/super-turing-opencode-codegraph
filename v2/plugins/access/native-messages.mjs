// Shared base transport; the same sibling layout is retained in native bundles.
// Do not copy the fd reader: attribution and benchmark share one owned connection.
export { nativeMessages } from '../../../../opencode-stack/v2/native-history.mjs';
