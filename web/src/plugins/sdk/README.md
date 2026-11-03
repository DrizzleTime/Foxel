# Media URLs

The raw `/api/fs/stream/{path}` and `/api/fs/thumb/{path}` endpoints require a
Bearer token and read permission for the requested path. Native media elements
cannot supply that header.

For playback, use `ctx.urls.streamUrl`, which is already resolved to a temporary
signed URL, or request a URL asynchronously:

```ts
const url = await ctx.host.getStreamUrl?.(ctx.filePath);
```

`host.getStreamUrl(path)` and `foxelApi.vfs.streamUrl(path)` now return
`Promise<string>` instead of `string`. Plugins calling either method must await
the result before assigning it to a media element. The existing
`host.getTempLink(path)` method remains available.

Signed URLs grant access to one file until they expire (one hour by default).
Request a new URL when resuming playback after expiration. Do not persist these
URLs or append the account's login token to media URLs.
