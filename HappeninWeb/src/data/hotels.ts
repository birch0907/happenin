// White-label Hotel Concierge Portal configuration & walking distance helpers.

export type HotelTab = 'Tonight' | 'Dining' | 'Sights';

export type HotelPlace = {
  id: string;
  tab: 'Dining' | 'Sights';
  name: string;
  tagline: string;
  priceTier?: string;
  onProperty?: boolean;
  latitude: number;
  longitude: number;
  address?: string;
  description: string;
  menuUrl?: string;
  reserveUrl?: string;
  websiteUrl?: string;
};

export type HotelStyleVariant = 'standard' | 'verb-poster';

export type HotelConfig = {
  id: string;
  name: string;
  wordmark: string;
  subtitle: string;
  address: string;
  latitude: number;
  longitude: number;
  initialZoom: number;
  styleVariant?: HotelStyleVariant;
  mapStyle?: 'dark' | 'light';
  logoIcon?: 'pick';
  theme: {
    bg: string;
    panel: string;
    panelSolid: string;
    accent: string;
    border: string;
    borderStrong: string;
    textMuted: string;
  };
  places: HotelPlace[];
};

export const PLACE_TAB_COLORS: Record<'Dining' | 'Sights', string> = {
  Dining: '#F2B866',
  Sights: '#66D9B8',
};

export function getHotelParam(): string | null {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('hotel')?.trim().toLowerCase();
  if (!raw || !/^[a-z0-9-]+$/.test(raw)) return null;
  return raw;
}

/** Estimate walking minutes between two coordinates using Haversine * 1.25 urban factor. */
export function estimateWalkMinutes(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  const meters = 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const walkMetersPerMin = 80; // ~4.8 km/h walking pace
  return Math.max(1, Math.round((meters * 1.25) / walkMetersPerMin));
}

export function formatWalkLabel(
  hotel: HotelConfig,
  lat: number,
  lng: number,
  onProperty?: boolean
): string {
  if (onProperty) return 'On Property';
  const mins = estimateWalkMinutes(hotel.latitude, hotel.longitude, lat, lng);
  if (mins <= 25) return `${mins} min walk`;
  const miles = (mins / 20).toFixed(1);
  return `${miles} mi away`;
}

export function walkingDirectionsUrl(hotel: HotelConfig, lat: number, lng: number): string {
  return `https://www.google.com/maps/dir/?api=1&origin=${hotel.latitude},${hotel.longitude}&destination=${lat},${lng}&travelmode=walking`;
}
