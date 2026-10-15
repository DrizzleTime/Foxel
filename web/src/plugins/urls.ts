/** Pure URL helpers. Importing this module never initializes a plugin runtime. */
export function withPluginRevision(url: string, revision?: string | null): string {
  if (!revision) return url;
  return `${url}${url.includes('?') ? '&' : '?'}v=${encodeURIComponent(revision)}`;
}
export function getPluginBundleUrl(pluginKey: string, revision?: string | null): string {
  return withPluginRevision(`/api/plugins/${encodeURIComponent(pluginKey)}/bundle.js`, revision);
}
export function getPluginAssetUrl(pluginKey: string, assetPath: string, revision?: string | null): string {
  const path = assetPath.replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/');
  return withPluginRevision(`/api/plugins/${encodeURIComponent(pluginKey)}/assets/${path}`, revision);
}
