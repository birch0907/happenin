// Happenin' — Event normalization, time window, and venue grouping helpers.
// Source of truth is the Python ingestion feed (/events.json).

export type EventCategory = 'Live Music' | 'DJ' | 'Social';

export const CATEGORIES: EventCategory[] = ['Live Music', 'DJ', 'Social'];

export const CATEGORY_COLORS: Record<EventCategory, string> = {
  'Live Music': '#FF4FA3',
  DJ: '#2FE6E6',
  Social: '#B388FF',
};

export type AdmissionType = 'free' | 'cover' | 'ticketed';

export type ContentRating = 'PG' | 'R' | 'Explicit';

export type RawEvent = {
  id?: string;
  source_id?: string;
  title: string;
  start: string;
  end?: string | null;
  venue?: string;
  address?: string;
  city?: string;
  state?: string;
  latitude?: number | null;
  longitude?: number | null;
  location_precision?: string;
  segment?: string;
  genre?: string | null;
  subgenre?: string | null;
  source_name?: string;
  source_url?: string;
  url?: string;
  ticket_links?: string[];
  description?: string;
  image_url?: string;
  price?: string | null;
  min_ticket_price?: number | null;
  admission_type?: AdmissionType | null;
  ages?: string | null;
  ai_category?: EventCategory | 'Exclude';
  ai_summary?: string | null;
  ai_tags?: string[] | null;
  ai_price?: string | null;
  default_category?: EventCategory;
  content_rating?: ContentRating;
  safety_reason?: string;
  hotel_blocked?: boolean;
};

export type HappeninEvent = {
  id: string;
  title: string;
  venue: string;
  address?: string;
  city?: string;
  category: EventCategory;
  tags: string[];
  admissionType?: AdmissionType;
  admissionLabel?: string;
  price?: string;
  contentRating: ContentRating;
  safetyReason?: string;
  hotelBlocked: boolean;
  latitude: number;
  longitude: number;
  start: string;
  end: string | null;
  startMs: number;
  effectiveEndMs: number;
  url?: string;
  description?: string;
  imageUrl?: string;
  sourceName?: string;
};

export type VenueCluster = {
  key: string;
  latitude: number;
  longitude: number;
  venue: string;
  events: HappeninEvent[];
  primaryCategory: EventCategory;
};

const djWords =
  /\b(dj|disco|techno|house music|afro house|deep house|rave|dance party|dance night|club night|edm|reggaeton|afrobeats|drum\s*(?:and|&)\s*bass|dubstep|trance|vinyl set|open decks|goth|industrial|salsa|bachata|heroes|crypt|automatique|throwback|90s party|hyperpop)\b/i;
const socialWords =
  /\b(trivia|karaoke|mixer|meetup|meet market|networking|board games?|game night|night market|street fair|festival|speed dating|singles|social|community gathering|craft fair|art walk|open mic|yoga|comedy|stand[- ]?up|bingo|lo-fi|candle)\b/i;
const liveWords =
  /\b(live music|live band|live jazz|live performance|concert|acoustic|open jam|jam session|songwriter|blues night|trio|quartet|quintet|orchestra|irish session|after-hours|midnight at the mad monkfish)\b/i;
const excludedWords =
  /\b(meet\s*(?:and|&)\s*greet|vip upgrade|parking pass|ticket insurance|add[- ]on|fast lane|lounge access)\b/i;

const DEFAULT_VISIBILITY_HOURS = 4;

function classify(e: RawEvent): EventCategory | null {
  const title = e.title || '';
  if (excludedWords.test(title)) return null;
  if (e.ai_category === 'Exclude') return null;
  if (e.ai_category && CATEGORIES.includes(e.ai_category)) return e.ai_category;

  const combined = `${title} ${e.genre || ''} ${e.subgenre || ''} ${e.description || ''}`;
  if (djWords.test(title) || /dance\/electronic/i.test(e.genre || '')) return 'DJ';
  if (socialWords.test(title)) return 'Social';
  if (liveWords.test(title)) return 'Live Music';
  if (djWords.test(combined) && ['ManRay', 'Havana Club', 'Middlesex Lounge', 'POSH'].includes(e.source_name || '')) {
    return 'DJ';
  }
  if (e.segment === 'Music') return 'Live Music';
  if (
    [
      'Lilypad',
      'The Lilypad',
      'Sinclair',
      'The Sinclair',
      "Lou's",
      'The Plough and Stars',
      'The Mad Monkfish',
      "McCarthy's",
    ].includes(e.source_name || '')
  ) {
    return 'Live Music';
  }
  if (['Lamplighter', 'Lamplighter Brewing Co.'].includes(e.source_name || '')) {
    return 'Social';
  }
  if (['ManRay', 'Havana Club', 'Middlesex Lounge', 'The Phoenix Landing', 'Dante Alighieri Society'].includes(e.source_name || '')) {
    return 'DJ';
  }
  if (e.default_category && CATEGORIES.includes(e.default_category)) {
    return e.default_category;
  }
  return null;
}

function extractTags(e: RawEvent): string[] {
  if (Array.isArray(e.ai_tags) && e.ai_tags.length > 0) {
    return e.ai_tags
      .map((t) => String(t || '').trim())
      .filter(Boolean)
      .slice(0, 3);
  }
  const tags: string[] = [];
  const add = (t?: string | null) => {
    if (!t) return;
    const cleaned = t.trim();
    if (!cleaned || /^undefined$|^other$|^miscellaneous$/i.test(cleaned)) return;
    if (!tags.some((x) => x.toLowerCase() === cleaned.toLowerCase())) {
      tags.push(cleaned);
    }
  };

  add(e.genre);
  if (e.subgenre && e.subgenre !== e.genre) add(e.subgenre);

  const text = `${e.title || ''} ${e.description || ''}`;
  if (/\bjazz\b/i.test(text)) add('Jazz');
  if (/\bgoth\b/i.test(text)) add('Goth');
  if (/\bindustrial\b/i.test(text)) add('Industrial');
  if (/\bsalsa\b/i.test(text)) add('Salsa');
  if (/\bbachata\b/i.test(text)) add('Bachata');
  if (/\birish\b/i.test(text)) add('Irish Trad');
  if (/\bjam\b/i.test(text)) add('Jam Session');
  if (/\btrivia\b/i.test(text)) add('Trivia');
  if (/\bkaraoke\b/i.test(text)) add('Karaoke');
  if (/\bopen mic\b/i.test(text)) add('Open Mic');
  if (/\b21\+\b/.test(text) || e.ages === '21+') add('21+');
  else if (/\b18\+\b/.test(text)) add('18+');
  else if (/\b19\+\b/.test(text)) add('19+');
  else if (/\ball ages\b/i.test(text)) add('All Ages');

  return tags.slice(0, 3);
}

function normalizePrice(raw?: string | null): string | undefined {
  if (!raw) return undefined;
  const cleaned = raw.replace(/\.00\b/g, '').replace(/\s*-\s*/g, '–').trim();
  return cleaned || undefined;
}

function extractPrice(e: RawEvent): string | undefined {
  const direct = normalizePrice(e.ai_price || e.price);
  if (direct) return direct;
  if (typeof e.min_ticket_price === 'number') {
    return e.min_ticket_price === 0 ? 'Free' : `$${Math.round(e.min_ticket_price)}`;
  }
  const text = `${e.title || ''} ${e.description || ''}`;
  if (/\bno cover\b|\bfree entry\b|\bfree admission\b/i.test(text)) return 'Free';
  const dollar = text.match(/\$\d{1,3}(?:[-–]\$?\d{1,3})?/);
  if (dollar) return normalizePrice(dollar[0]);
  return undefined;
}

function resolveAdmission(
  e: RawEvent,
  price?: string
): { admissionType?: AdmissionType; admissionLabel?: string } {
  const priceLower = (price || '').toLowerCase();
  const isFree = priceLower === 'free' || priceLower === '$0' || priceLower === 'no cover';
  const url = (e.ticket_links?.[0] || e.source_url || e.url || '').toLowerCase();
  const isTicketingUrl = /ticketmaster|ticketweb|axs\.com|eventbrite|dice\.fm|posh\.vip|seetickets|etix/.test(url);

  let admissionType: AdmissionType | undefined;
  if (isFree) {
    admissionType = 'free';
  } else if (e.admission_type) {
    admissionType = e.admission_type;
  } else if (isTicketingUrl) {
    admissionType = 'ticketed';
  } else if (price) {
    admissionType = 'cover';
  }

  if (!admissionType) return {};

  if (admissionType === 'free') {
    return { admissionType: 'free', admissionLabel: 'Free' };
  }
  if (admissionType === 'ticketed') {
    return {
      admissionType: 'ticketed',
      admissionLabel: price ? `Tickets · ${price}` : 'Ticketed',
    };
  }
  // cover / door
  if (price && /seat|before|after|door|cover/i.test(price)) {
    return { admissionType: 'cover', admissionLabel: price };
  }
  return {
    admissionType: 'cover',
    admissionLabel: price ? `Cover · ${price}` : 'Cover at Door',
  };
}

function cleanDescription(raw?: string): string | undefined {
  if (!raw) return undefined;
  const cleaned = raw
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&rsquo;|&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned || undefined;
}

function pickUsefulSummary(e: RawEvent): string | undefined {
  // Only show a description when the underlying listing actually had real info
  // (avoids fluffy AI rewrites of just the title & venue name).
  const rawDesc = cleanDescription(e.description);
  if (!rawDesc || rawDesc.length < 35) return undefined;
  return cleanDescription(e.ai_summary || rawDesc);
}

function isMapLocation(e: RawEvent): boolean {
  return (
    typeof e.latitude === 'number' &&
    Number.isFinite(e.latitude) &&
    typeof e.longitude === 'number' &&
    Number.isFinite(e.longitude) &&
    e.latitude >= -90 &&
    e.latitude <= 90 &&
    e.longitude >= -180 &&
    e.longitude <= 180 &&
    !(e.latitude === 0 && e.longitude === 0) &&
    e.location_precision !== 'city' &&
    e.location_precision !== 'region'
  );
}

function venueKey(venue: string): string {
  return venue.toLowerCase().replace(/[^a-z0-9]/g, '');
}

export function normalizeEvents(rawEvents: RawEvent[]): HappeninEvent[] {
  const parsed: HappeninEvent[] = [];

  for (let index = 0; index < rawEvents.length; index++) {
    const e = rawEvents[index];
    const category = classify(e);
    if (!category || !isMapLocation(e) || !e.start || !e.title) continue;
    const startMs = Date.parse(e.start);
    if (!Number.isFinite(startMs)) continue;

    let effectiveEndMs = e.end ? Date.parse(e.end) : NaN;
    const hasExplicitEnd = Number.isFinite(effectiveEndMs) && effectiveEndMs > startMs;
    if (!hasExplicitEnd) {
      effectiveEndMs = startMs + DEFAULT_VISIBILITY_HOURS * 60 * 60 * 1000;
    }

    const price = extractPrice(e);
    const { admissionType, admissionLabel } = resolveAdmission(e, price);

    parsed.push({
      id: `${e.source_name || 'event'}:${e.id || e.source_id || index}:${e.start}`,
      title: e.title.trim(),
      venue: (e.venue || e.address || 'Venue TBA').trim(),
      address: e.address?.trim(),
      city: e.city?.trim(),
      category,
      tags: extractTags(e),
      admissionType,
      admissionLabel,
      price,
      contentRating: e.content_rating === 'R' || e.content_rating === 'Explicit' ? e.content_rating : 'PG',
      safetyReason: e.safety_reason || undefined,
      hotelBlocked: Boolean(e.hotel_blocked || e.content_rating === 'Explicit'),
      latitude: e.latitude!,
      longitude: e.longitude!,
      start: e.start,
      end: e.end || null,
      startMs,
      effectiveEndMs,
      url: e.ticket_links?.[0] || e.source_url || e.url,
      description: pickUsefulSummary(e),
      imageUrl: e.image_url,
      sourceName: e.source_name,
    });
  }

  // Precompute unknown-duration truncation once on load (O(1) visibility check during slider drag).
  const byVenue = new Map<string, HappeninEvent[]>();
  for (const ev of parsed) {
    const key = venueKey(ev.venue);
    if (!key || key === 'venuetba') continue;
    const list = byVenue.get(key) || [];
    list.push(ev);
    byVenue.set(key, list);
  }
  for (const list of byVenue.values()) {
    list.sort((a, b) => a.startMs - b.startMs);
    for (let i = 0; i < list.length; i++) {
      const ev = list[i];
      if (ev.end) continue;
      for (let j = i + 1; j < list.length; j++) {
        if (list[j].startMs > ev.startMs) {
          if (list[j].startMs < ev.effectiveEndMs) {
            ev.effectiveEndMs = list[j].startMs;
          }
          break;
        }
      }
    }
  }

  return parsed.sort((a, b) => a.startMs - b.startMs);
}

export function eventVisibleAtTime(event: HappeninEvent, targetMs: number): boolean {
  return targetMs >= event.startMs && targetMs < event.effectiveEndMs;
}

export function groupEventsByPin(events: HappeninEvent[]): VenueCluster[] {
  const map = new Map<string, VenueCluster>();
  for (const ev of events) {
    const key = `${ev.latitude.toFixed(4)},${ev.longitude.toFixed(4)}`;
    const existing = map.get(key);
    if (existing) {
      existing.events.push(ev);
    } else {
      map.set(key, {
        key,
        latitude: ev.latitude,
        longitude: ev.longitude,
        venue: ev.venue,
        events: [ev],
        primaryCategory: ev.category,
      });
    }
  }
  return Array.from(map.values());
}

// ---------------------------------------------------------------------------
// BOSTON / EASTERN TIME UTILITIES
// ---------------------------------------------------------------------------

export const WINDOW_HOURS = 24;
export const QUARTER_MS = 15 * 60 * 1000;
export const WINDOW_MS = WINDOW_HOURS * 60 * 60 * 1000;
export const DATE_COUNT = 14;

export function currentQuarter(): number {
  return Math.floor(Date.now() / QUARTER_MS) * QUARTER_MS;
}

export function easternToday(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function addCalendarDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function dateParts(date: string): { weekday: string; day: number; month: string } {
  const d = new Date(`${date}T12:00:00Z`);
  return {
    weekday: new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'UTC' }).format(d),
    day: d.getUTCDate(),
    month: new Intl.DateTimeFormat('en-US', { month: 'short', timeZone: 'UTC' }).format(d),
  };
}

// Convert 4 PM in Boston to a real timestamp, including DST transitions.
export function futureWindowStart(date: string): number {
  const utcWallClock = Date.parse(`${date}T16:00:00Z`);
  let instant = utcWallClock + 4 * 60 * 60 * 1000;
  for (let attempt = 0; attempt < 3; attempt++) {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).formatToParts(new Date(instant));
    const part = (type: string) => parts.find((p) => p.type === type)?.value || '0';
    const wallClock = Date.UTC(
      Number(part('year')),
      Number(part('month')) - 1,
      Number(part('day')),
      Number(part('hour')),
      Number(part('minute'))
    );
    const diff = utcWallClock - wallClock;
    instant += diff;
    if (diff === 0) break;
  }
  return instant;
}

export function formatTimelineTime(timestamp: number): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(new Date(timestamp));
}

export function formatEventTime(iso: string): string {
  const hour = Number(iso.slice(11, 13));
  const minute = Number(iso.slice(14, 16));
  return `${hour % 12 || 12}:${String(minute).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`;
}

export function directionsUrl(event: HappeninEvent): string {
  const dest = encodeURIComponent(`${event.venue} ${event.address || ''}`.trim() || `${event.latitude},${event.longitude}`);
  return `https://www.google.com/maps/dir/?api=1&destination=${event.latitude},${event.longitude}&destination_place_id=&query=${dest}`;
}
