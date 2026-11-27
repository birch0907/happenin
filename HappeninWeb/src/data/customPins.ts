// Happenin' Digital Concierge — Custom Pin Drop (Concierge Desk + Guest Self-Drop)
// Encodes concierge picks compactly into ?picks=... URLs (zero backend required)
// and persists guest-dropped pins in localStorage per hotel.

export type CustomPin = {
  id: string;
  name: string;
  note?: string;
  address?: string;
  latitude: number;
  longitude: number;
  origin: 'concierge' | 'guest';
};

type WirePin = {
  n: string;
  d?: string;
  a?: string;
  lat: number;
  lng: number;
};

function bytesToBase64Url(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) {
    bin += String.fromCharCode(bytes[i]);
  }
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlToBytes(str: string): Uint8Array {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((str.length + 3) % 4);
  const bin = atob(padded);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) {
    out[i] = bin.charCodeAt(i);
  }
  return out;
}

export function encodePinsToParam(pins: CustomPin[]): string {
  if (pins.length === 0) return '';
  const wire: WirePin[] = pins.map((p) => {
    const item: WirePin = {
      n: p.name.trim().slice(0, 80),
      lat: Number(p.latitude.toFixed(5)),
      lng: Number(p.longitude.toFixed(5)),
    };
    if (p.note?.trim()) item.d = p.note.trim().slice(0, 220);
    if (p.address?.trim()) item.a = p.address.trim().slice(0, 90);
    return item;
  });
  const json = JSON.stringify(wire);
  const bytes = new TextEncoder().encode(json);
  return bytesToBase64Url(bytes);
}

export function decodePinsFromParam(param: string | null): CustomPin[] {
  if (!param) return [];
  try {
    const bytes = base64UrlToBytes(param.trim());
    const json = new TextDecoder().decode(bytes);
    const parsed = JSON.parse(json);
    if (!Array.isArray(parsed)) return [];
    const out: CustomPin[] = [];
    for (let i = 0; i < parsed.length; i++) {
      const item = parsed[i];
      if (!item || typeof item !== 'object') continue;
      const lat = Number(item.lat);
      const lng = Number(item.lng);
      const name = String(item.n || '').trim();
      if (!name || Number.isNaN(lat) || Number.isNaN(lng)) continue;
      out.push({
        id: `pick-${i}-${Math.round(lat * 10000)}-${Math.round(lng * 10000)}`,
        name,
        note: item.d ? String(item.d).trim() : undefined,
        address: item.a ? String(item.a).trim() : undefined,
        latitude: lat,
        longitude: lng,
        origin: 'concierge',
      });
    }
    return out;
  } catch {
    return [];
  }
}

export function getDeskModeParam(): boolean {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('desk')?.trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes';
}

export function getUrlSharedPins(): CustomPin[] {
  const params = new URLSearchParams(window.location.search);
  return decodePinsFromParam(params.get('picks'));
}

export function buildGuestShareUrl(hotelId: string, pins: CustomPin[]): string {
  const url = new URL(window.location.href);
  url.search = '';
  url.hash = '';
  url.searchParams.set('hotel', hotelId);
  const encoded = encodePinsToParam(pins);
  if (encoded) {
    url.searchParams.set('picks', encoded);
  }
  return url.toString();
}

function storageKey(hotelId: string): string {
  return `happenin:guest-pins:${hotelId}`;
}

export function loadGuestPins(hotelId: string): CustomPin[] {
  try {
    const raw = window.localStorage.getItem(storageKey(hotelId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (p): p is CustomPin =>
        p &&
        typeof p.id === 'string' &&
        typeof p.name === 'string' &&
        typeof p.latitude === 'number' &&
        typeof p.longitude === 'number'
    );
  } catch {
    return [];
  }
}

export function saveGuestPins(hotelId: string, pins: CustomPin[]): void {
  try {
    if (pins.length === 0) {
      window.localStorage.removeItem(storageKey(hotelId));
    } else {
      window.localStorage.setItem(storageKey(hotelId), JSON.stringify(pins));
    }
  } catch {
    // Ignore private browsing / quota errors
  }
}

export type PlaceSearchResult = {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
};

function formatPhotonAddress(props: Record<string, string | undefined>): string {
  const street = [props.housenumber, props.street].filter(Boolean).join(' ');
  const city = props.city || props.town || props.village || props.district;
  const state = props.state;
  return [street, city, state].filter(Boolean).join(', ');
}

export async function searchNearbyPlaces(
  query: string,
  nearLat: number,
  nearLng: number,
  signal?: AbortSignal
): Promise<PlaceSearchResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) return [];
  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(trimmed)}&lat=${nearLat}&lon=${nearLng}&limit=5&lang=en`;
  try {
    const resp = await fetch(url, { signal });
    if (!resp.ok) return [];
    const data = await resp.json();
    const features = Array.isArray(data?.features) ? data.features : [];
    return features
      .map((f: { geometry?: { coordinates?: [number, number] }; properties?: Record<string, string | undefined> }, idx: number) => {
        const coords = f.geometry?.coordinates;
        if (!coords || coords.length < 2) return null;
        const props = f.properties || {};
        const address = formatPhotonAddress(props);
        const name = props.name || address || trimmed;
        return {
          id: `photon-${idx}-${coords[0].toFixed(5)}-${coords[1].toFixed(5)}`,
          name,
          address: address && address !== name ? address : [props.city || props.town, props.state].filter(Boolean).join(', '),
          longitude: coords[0],
          latitude: coords[1],
        };
      })
      .filter((x: PlaceSearchResult | null): x is PlaceSearchResult => Boolean(x));
  } catch {
    return [];
  }
}

export async function reverseGeocodePoint(
  lat: number,
  lng: number
): Promise<{ name?: string; address?: string }> {
  try {
    const resp = await fetch(
      `https://photon.komoot.io/reverse?lat=${lat}&lon=${lng}&lang=en`
    );
    if (!resp.ok) return {};
    const data = await resp.json();
    const props = data?.features?.[0]?.properties;
    if (!props) return {};
    const address = formatPhotonAddress(props);
    return {
      name: props.name || undefined,
      address: address || undefined,
    };
  } catch {
    return {};
  }
}
