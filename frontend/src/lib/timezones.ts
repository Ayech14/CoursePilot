export function detectTimeZone(): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return zone && zone !== "Etc/Unknown" ? zone : "UTC";
}

/** All zones the browser knows, always including `current`, even if it is an older alias. */
export function timeZoneOptions(current: string): string[] {
  const zones = new Set(Intl.supportedValuesOf("timeZone"));
  zones.add("UTC");
  zones.add(current);
  return [...zones].sort();
}
