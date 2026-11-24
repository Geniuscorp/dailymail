// The API sends naive UTC timestamps ("2026-11-19T11:54:00", no zone). `new Date()` reads
// those as LOCAL time, which shows the UTC clock face: an hour behind in UTC+1, and so on.
// Treat a timestamp without a zone as UTC; one that already has a zone is left alone.
export function parseUtc(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`)
}

export function formatDateTime(
  value: string | null | undefined,
  style: 'short' | 'long' = 'short',
): string {
  if (!value) return '—'
  return parseUtc(value).toLocaleString('pt-PT', { dateStyle: style, timeStyle: 'short' })
}
