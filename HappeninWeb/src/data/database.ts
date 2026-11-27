export type VenueStatus =
  | 'Live (First-Party)'
  | 'Aggregator Only'
  | 'Ready (0 Events)'
  | 'Not Pulling'
  | 'Paused / Closed';

export type VenuePriority = 'A' | 'B' | 'C' | 'Unranked';

export type RecurringRule = {
  title: string;
  weekdays: string[];
  start_time: string | null;
  end_time: string | null;
  description: string;
};

export type DbVenue = {
  id: string;
  canonicalKey: string;
  venue: string;
  region?: 'boston' | 'seacoast';
  area: string;
  neighborhood: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  priority: VenuePriority;
  status: VenueStatus;
  collectorMethods: string[];
  primaryMethod: string;
  eventCount: number;
  eventIds: string[];
  categories: string[];
  vibe: string;
  url: string;
  notes: string;
  sourceSheets: string[];
  liveSources: string[];
  recurringRules: RecurringRule[];
  configIds: string[];
};

export type DbEvent = {
  id: string;
  venueId: string | null;
  venue: string;
  region?: 'boston' | 'seacoast';
  area: string;
  neighborhood: string;
  title: string;
  start: string | null;
  end: string | null;
  category: string;
  admissionType: string;
  price: string;
  summary: string;
  description: string;
  tags: string[];
  sourceName: string;
  provenance: 'First-Party' | 'Ticketmaster' | 'POSH';
  sourceUrl: string;
  latitude: number | null;
  longitude: number | null;
  address: string;
  contentRating?: 'PG' | 'R' | 'Explicit';
  safetyReason?: string;
  hotelBlocked?: boolean;
};

export type DbConcierge = {
  id: string;
  name: string;
  wordmark: string;
  subtitle: string;
  address: string;
  region: 'boston' | 'seacoast';
  mapStyle: 'dark' | 'light';
  styleVariant: string;
  accent: string;
  bg: string;
  maxRating: 'PG' | 'R' | 'Explicit';
  diningCount: number;
  sightsCount: number;
  totalPlaces: number;
  eligibleEventCount: number;
};

export type DbPayload = {
  generatedAt: string;
  stats: {
    totalVenues: number;
    totalEvents: number;
    totalConcierges?: number;
    statusCounts: Record<string, number>;
    areaCounts: Record<string, number>;
    priorityCounts: Record<string, number>;
    attentionCount: number;
  };
  concierges?: DbConcierge[];
  venues: DbVenue[];
  events: DbEvent[];
};

export const VENUE_STATUSES: VenueStatus[] = [
  'Live (First-Party)',
  'Aggregator Only',
  'Ready (0 Events)',
  'Not Pulling',
  'Paused / Closed',
];

export const VENUE_PRIORITIES: VenuePriority[] = ['A', 'B', 'C', 'Unranked'];

export const METHOD_LABELS: Record<string, string> = {
  tockify: 'Tockify API',
  tunehatch: 'TuneHatch API',
  tribe_api: 'WP Tribe API',
  squarespace_json: 'Squarespace JSON',
  bentobox_jsonld: 'BentoBox JSON-LD',
  wix_events_jsonld: 'Wix JSON-LD',
  musicidb: 'MusicIDB',
  ics: 'ICS Calendar',
  llm_html: 'AI HTML Scraper',
  recurring: 'Recurring Rule',
  legacy_custom: 'Custom Scraper',
  ticketmaster: 'Ticketmaster',
  posh: 'POSH',
  none: 'None',
};

export const AREA_ORDER = [
  'Boston Proper',
  'Cambridge',
  'Somerville',
  'Allston / Brighton',
  'Brookline',
  'Jamaica Plain',
  'Dorchester',
  'Roxbury',
  'East Boston',
  'Portsmouth NH',
  'Hampton / Beach NH',
  'Seacoast NH',
  'Greater Boston',
];

export function formatMethod(method: string): string {
  return METHOD_LABELS[method] || method;
}

export function eventDayKey(iso: string | null): string {
  if (!iso) return 'TBD';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'TBD';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(d);
  const y = parts.find((p) => p.type === 'year')?.value;
  const m = parts.find((p) => p.type === 'month')?.value;
  const day = parts.find((p) => p.type === 'day')?.value;
  return y && m && day ? `${y}-${m}-${day}` : 'TBD';
}

export function formatDayHeader(dayKey: string): string {
  if (!dayKey || dayKey === 'TBD') return 'Date TBD';
  const d = new Date(`${dayKey}T12:00:00-05:00`);
  if (Number.isNaN(d.getTime())) return dayKey;
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).format(d);
}

export function formatEventTime(startIso: string | null, endIso: string | null): string {
  if (!startIso) return 'Time TBD';
  const s = new Date(startIso);
  if (Number.isNaN(s.getTime())) return 'Time TBD';
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: '2-digit',
  });
  const startTxt = fmt.format(s);
  if (!endIso) return startTxt;
  const e = new Date(endIso);
  if (Number.isNaN(e.getTime())) return startTxt;
  return `${startTxt} – ${fmt.format(e)}`;
}

export function formatShortDateTime(startIso: string | null): string {
  if (!startIso) return 'TBD';
  const s = new Date(startIso);
  if (Number.isNaN(s.getTime())) return 'TBD';
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(s);
}

export function formatRuleTime(hhmm: string | null): string {
  if (!hhmm) return '';
  const [hStr, mStr] = hhmm.split(':');
  const h = Number(hStr);
  const m = Number(mStr || 0);
  if (Number.isNaN(h)) return hhmm;
  const suffix = h >= 12 ? 'PM' : 'AM';
  const hr12 = h % 12 || 12;
  return m === 0 ? `${hr12} ${suffix}` : `${hr12}:${String(m).padStart(2, '0')} ${suffix}`;
}

export function statusSlug(status: VenueStatus): string {
  switch (status) {
    case 'Live (First-Party)':
      return 'live';
    case 'Aggregator Only':
      return 'aggregator';
    case 'Ready (0 Events)':
      return 'ready';
    case 'Not Pulling':
      return 'not-pulling';
    case 'Paused / Closed':
      return 'paused';
  }
}

export function categoryColor(cat: string): string {
  if (cat === 'Live Music') return '#FF4FA3';
  if (cat === 'DJ') return '#2FE6E6';
  return '#B388FF';
}
