type Version = { numbers: bigint[]; prerelease: string[] };

function parseVersion(value: string): Version | undefined {
  const match = /^v?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.exec(value.trim());
  if (!match) return;
  return {
    numbers: match[1].split('.').map(part => BigInt(part)),
    prerelease: match[2]?.split('.') || [],
  };
}

/** Compare numeric releases and SemVer prereleases; unknown formats never trigger an upgrade. */
export function isNewerPluginVersion(latest?: string | null, installed?: string | null): boolean {
  if (!latest || !installed) return false;
  const next = parseVersion(latest);
  const current = parseVersion(installed);
  if (!next || !current) return false;

  for (let i = 0; i < Math.max(next.numbers.length, current.numbers.length); i++) {
    const a = next.numbers[i] ?? 0n;
    const b = current.numbers[i] ?? 0n;
    if (a !== b) return a > b;
  }
  if (!next.prerelease.length || !current.prerelease.length) {
    return !next.prerelease.length && !!current.prerelease.length;
  }
  for (let i = 0; i < Math.max(next.prerelease.length, current.prerelease.length); i++) {
    const a = next.prerelease[i];
    const b = current.prerelease[i];
    if (a === undefined || b === undefined) return a !== undefined;
    if (a === b) continue;
    const aNumeric = /^\d+$/.test(a);
    const bNumeric = /^\d+$/.test(b);
    if (aNumeric && bNumeric) {
      if (BigInt(a) === BigInt(b)) continue;
      return BigInt(a) > BigInt(b);
    }
    if (aNumeric !== bNumeric) return !aNumeric;
    return a > b;
  }
  return false;
}
