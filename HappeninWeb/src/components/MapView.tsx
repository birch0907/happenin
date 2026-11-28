import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { CATEGORY_COLORS, REGIONS, RegionId, VenueCluster } from '../data/events';
import { HotelConfig, HotelPlace, PLACE_TAB_COLORS } from '../data/hotels';
import { CustomPin } from '../data/customPins';

type MapViewProps = {
  clusters: VenueCluster[];
  selectedClusterKey: string | null;
  onSelectCluster: (cluster: VenueCluster) => void;
  places?: HotelPlace[];
  selectedPlaceId?: string | null;
  onSelectPlace?: (place: HotelPlace) => void;
  customPins?: CustomPin[];
  selectedCustomPinId?: string | null;
  onSelectCustomPin?: (pin: CustomPin) => void;
  draftPin?: { latitude: number; longitude: number; name?: string } | null;
  pinDropActive?: boolean;
  onMapPinDropClick?: (lngLat: { latitude: number; longitude: number }) => void;
  hotel?: HotelConfig | null;
  region?: RegionId;
  miamiVice?: boolean;
  onMapBackgroundClick: () => void;
};

const DARK_MATTER_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const POSITRON_LIGHT_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
const DEFAULT_CENTER: [number, number] = [-71.092, 42.348];
const DEFAULT_ZOOM = 11.5;

const LIGHT_EVENT_COLORS: Record<string, string> = {
  'Live Music': '#E63946',
  DJ: '#00A6B4',
  Social: '#7B2CBF',
};

const LIGHT_PLACE_COLORS: Record<'Dining' | 'Sights', string> = {
  Dining: '#E85D04',
  Sights: '#1D4ED8',
};

const EVENT_SOURCE_ID = 'happenin-pins';
const PLACE_SOURCE_ID = 'hotel-places';
const HOME_SOURCE_ID = 'hotel-home';
const CUSTOM_SOURCE_ID = 'custom-pins';
const DRAFT_SOURCE_ID = 'draft-pin';

function clustersToGeoJSON(
  clusters: VenueCluster[],
  selectedKey: string | null,
  isLight: boolean
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: clusters.map((cluster) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [cluster.longitude, cluster.latitude],
      },
      properties: {
        key: cluster.key,
        venue: cluster.venue,
        count: cluster.events.length,
        color: isLight
          ? LIGHT_EVENT_COLORS[cluster.primaryCategory] || CATEGORY_COLORS[cluster.primaryCategory]
          : CATEGORY_COLORS[cluster.primaryCategory],
        selected: cluster.key === selectedKey,
      },
    })),
  };
}

function placesToGeoJSON(
  places: HotelPlace[],
  selectedPlaceId: string | null,
  isLight: boolean
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: places.map((place) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [place.longitude, place.latitude],
      },
      properties: {
        id: place.id,
        name: place.name,
        color: isLight ? LIGHT_PLACE_COLORS[place.tab] : PLACE_TAB_COLORS[place.tab],
        selected: place.id === selectedPlaceId,
      },
    })),
  };
}

function homeToGeoJSON(hotel: HotelConfig | null | undefined): GeoJSON.FeatureCollection<GeoJSON.Point> {
  if (!hotel) return { type: 'FeatureCollection', features: [] };
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [hotel.longitude, hotel.latitude],
        },
        properties: {
          name: hotel.name,
          accent: hotel.homePinColor || hotel.theme.accent,
          dotColor: hotel.homePinColor
            ? hotel.homePinColor
            : hotel.mapStyle === 'light'
              ? '#0D0D0D'
              : '#ffffff',
          strokeColor: hotel.homePinColor
            ? '#FFFFFF'
            : hotel.theme.accent,
        },
      },
    ],
  };
}

function customPinsToGeoJSON(
  pins: CustomPin[],
  selectedId: string | null
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: pins.map((pin) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [pin.longitude, pin.latitude],
      },
      properties: {
        id: pin.id,
        name: pin.name,
        origin: pin.origin,
        selected: pin.id === selectedId,
      },
    })),
  };
}

function draftPinToGeoJSON(
  draft: { latitude: number; longitude: number; name?: string } | null | undefined
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  if (!draft) return { type: 'FeatureCollection', features: [] };
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [draft.longitude, draft.latitude],
        },
        properties: {
          name: draft.name || 'New Pin',
        },
      },
    ],
  };
}

function applyMiamiViceMapTheme(map: maplibregl.Map) {
  const setPaint = (id: string, prop: string, val: unknown) => {
    if (map.getLayer(id)) {
      try {
        map.setPaintProperty(id, prop, val);
      } catch {
        // Ignore if layer doesn't accept property
      }
    }
  };

  // Deep plum-black land & synthwave indigo water
  setPaint('background', 'background-color', '#0B0616');
  for (const id of ['landcover', 'landuse', 'landuse_residential']) {
    setPaint(id, 'fill-color', '#100920');
  }
  for (const id of ['park_national_park', 'park_nature_reserve']) {
    setPaint(id, 'fill-color', '#140B29');
  }
  setPaint('water', 'fill-color', '#1A1344');
  setPaint('water_shadow', 'fill-color', '#241A59');
  setPaint('waterway', 'line-color', '#34C8D8');
  setPaint('building', 'fill-color', '#150C2B');
  setPaint('building-top', 'fill-color', '#1C1036');
  setPaint('building-top', 'fill-outline-color', '#2C1A54');

  // Turquoise shoreline glow right over Carto's water layer
  const waterLayer = map.getLayer('water') as (maplibregl.LayerSpecification & { source?: string; 'source-layer'?: string }) | undefined;
  const waterSource = waterLayer?.source;
  const waterSourceLayer = waterLayer?.['source-layer'];
  if (waterSource && waterSourceLayer) {
    const beforeId = map.getLayer('aeroway-runway') ? 'aeroway-runway' : undefined;
    if (!map.getLayer('miami-shore-bloom')) {
      map.addLayer(
        {
          id: 'miami-shore-bloom',
          type: 'line',
          source: waterSource,
          'source-layer': waterSourceLayer,
          paint: {
            'line-color': '#2FE6E6',
            'line-width': ['interpolate', ['linear'], ['zoom'], 9, 4, 13, 8, 16, 11],
            'line-blur': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 7],
            'line-opacity': 0.42,
          },
        },
        beforeId
      );
    }
    if (!map.getLayer('miami-shore-rim')) {
      map.addLayer(
        {
          id: 'miami-shore-rim',
          type: 'line',
          source: waterSource,
          'source-layer': waterSourceLayer,
          paint: {
            'line-color': '#5CF7F7',
            'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.7, 13, 1.3, 16, 1.8],
            'line-opacity': 0.55,
          },
        },
        beforeId
      );
    }
  }

  // Synthwave violet / electric-plum road hierarchy
  for (const layer of map.getStyle()?.layers || []) {
    const id = layer.id;
    if (layer.type === 'line') {
      if (/_mot_fill/.test(id)) {
        setPaint(id, 'line-color', '#9B42E8');
      } else if (/_mot_case/.test(id)) {
        setPaint(id, 'line-color', '#3E146B');
      } else if (/_trunk_fill|_pri_fill/.test(id)) {
        setPaint(id, 'line-color', '#6F30B8');
      } else if (/_trunk_case|_pri_case/.test(id)) {
        setPaint(id, 'line-color', '#2A104C');
      } else if (/_sec_fill/.test(id)) {
        setPaint(id, 'line-color', '#47217A');
      } else if (/_sec_case/.test(id)) {
        setPaint(id, 'line-color', '#1E0D38');
      } else if (/_minor_fill|_service_fill|road_path|tunnel_path|bridge_path/.test(id)) {
        setPaint(id, 'line-color', '#2B164B');
      } else if (/_minor_case|_service_case/.test(id)) {
        setPaint(id, 'line-color', '#150A29');
      } else if (id === 'rail' || id === 'rail_dash' || id === 'tunnel_rail' || id === 'tunnel_rail_dash') {
        setPaint(id, 'line-color', '#381B63');
      }
    } else if (layer.type === 'symbol') {
      if (id.startsWith('place_')) {
        setPaint(id, 'text-color', '#F2ECFF');
        setPaint(id, 'text-halo-color', '#0B0616');
        setPaint(id, 'text-halo-width', 1.8);
      } else if (id.startsWith('roadname_')) {
        setPaint(id, 'text-color', '#B79FE6');
        setPaint(id, 'text-halo-color', '#0B0616');
      } else if (id.startsWith('watername_') || id === 'waterway_label') {
        setPaint(id, 'text-color', '#6BDCE8');
        setPaint(id, 'text-halo-color', '#15103B');
      }
    }
  }
}

export function MapView({
  clusters,
  selectedClusterKey,
  onSelectCluster,
  places = [],
  selectedPlaceId = null,
  onSelectPlace,
  customPins = [],
  selectedCustomPinId = null,
  onSelectCustomPin,
  draftPin = null,
  pinDropActive = false,
  onMapPinDropClick,
  hotel = null,
  region = 'boston',
  miamiVice = false,
  onMapBackgroundClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const styleLoadedRef = useRef(false);
  const activeStyleModeRef = useRef<'dark' | 'light'>('dark');
  const centeredRegionRef = useRef<RegionId>(region);
  const centeredHotelRef = useRef<string | null>(null);

  const clustersRef = useRef(clusters);
  const selectedKeyRef = useRef(selectedClusterKey);
  const placesRef = useRef(places);
  const selectedPlaceRef = useRef(selectedPlaceId);
  const customPinsRef = useRef(customPins);
  const selectedCustomPinRef = useRef(selectedCustomPinId);
  const draftPinRef = useRef(draftPin);
  const pinDropActiveRef = useRef(pinDropActive);
  const hotelRef = useRef(hotel);
  const miamiViceRef = useRef(miamiVice);
  const onSelectRef = useRef(onSelectCluster);
  const onSelectPlaceRef = useRef(onSelectPlace);
  const onSelectCustomPinRef = useRef(onSelectCustomPin);
  const onMapPinDropClickRef = useRef(onMapPinDropClick);
  const onBgClickRef = useRef(onMapBackgroundClick);

  clustersRef.current = clusters;
  selectedKeyRef.current = selectedClusterKey;
  placesRef.current = places;
  selectedPlaceRef.current = selectedPlaceId;
  customPinsRef.current = customPins;
  selectedCustomPinRef.current = selectedCustomPinId;
  draftPinRef.current = draftPin;
  pinDropActiveRef.current = pinDropActive;
  hotelRef.current = hotel;
  miamiViceRef.current = miamiVice;
  onSelectRef.current = onSelectCluster;
  onSelectPlaceRef.current = onSelectPlace;
  onSelectCustomPinRef.current = onSelectCustomPin;
  onMapPinDropClickRef.current = onMapPinDropClick;
  onBgClickRef.current = onMapBackgroundClick;

  const isLight = hotel?.mapStyle === 'light';

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const initialMode: 'dark' | 'light' = hotelRef.current?.mapStyle === 'light' ? 'light' : 'dark';
    activeStyleModeRef.current = initialMode;

    const initialCenter: [number, number] = hotelRef.current
      ? [hotelRef.current.longitude, hotelRef.current.latitude]
      : REGIONS[region].center;
    const initialZoom = hotelRef.current ? hotelRef.current.initialZoom : REGIONS[region].zoom;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: initialMode === 'light' ? POSITRON_LIGHT_STYLE : DARK_MATTER_STYLE,
      center: initialCenter,
      zoom: initialZoom,
      pitch: 0,
      maxPitch: 0,
      minPitch: 0,
      bearing: 0,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: { compact: true },
    });

    map.touchZoomRotate.disableRotation();

    function mountLayers() {
      const light = activeStyleModeRef.current === 'light';
      const synthwave = miamiViceRef.current && !light;
      styleLoadedRef.current = true;

      if (synthwave) {
        applyMiamiViceMapTheme(map);
      }

      const labelTextColor = light ? '#0D0D0D' : '#f5f2ea';
      const labelHaloColor = light ? '#FFFFFF' : '#0f1420';
      const defaultStrokeColor = light ? '#0D0D0D' : '#120e24';
      const selectedStrokeColor = light ? '#FAF089' : '#ffffff';

      // 1. Hotel Home Marker ("You Are Here")
      if (!map.getSource(HOME_SOURCE_ID)) {
        map.addSource(HOME_SOURCE_ID, {
          type: 'geojson',
          data: homeToGeoJSON(hotelRef.current),
        });
      }

      map.addLayer({
        id: 'hotel-home-halo',
        type: 'circle',
        source: HOME_SOURCE_ID,
        paint: {
          'circle-radius': light ? 22 : 24,
          'circle-color': ['get', 'accent'],
          'circle-opacity': light ? 0.45 : 0.28,
          'circle-blur': light ? 0.25 : 0.55,
        },
      });

      map.addLayer({
        id: 'hotel-home-dot',
        type: 'circle',
        source: HOME_SOURCE_ID,
        paint: {
          'circle-radius': 9,
          'circle-color': ['get', 'dotColor'],
          'circle-stroke-width': 3,
          'circle-stroke-color': ['get', 'strokeColor'],
        },
      });

      map.addLayer({
        id: 'hotel-home-label',
        type: 'symbol',
        source: HOME_SOURCE_ID,
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 11.5,
          'text-offset': [0, 1.55],
          'text-anchor': 'top',
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': labelTextColor,
          'text-halo-color': labelHaloColor,
          'text-halo-width': 2,
        },
      });

      // 2. Curated Hotel Places (Dining / Sights)
      if (!map.getSource(PLACE_SOURCE_ID)) {
        map.addSource(PLACE_SOURCE_ID, {
          type: 'geojson',
          data: placesToGeoJSON(placesRef.current, selectedPlaceRef.current, light),
        });
      }

      map.addLayer({
        id: 'places-hit',
        type: 'circle',
        source: PLACE_SOURCE_ID,
        paint: { 'circle-radius': 24, 'circle-color': '#000000', 'circle-opacity': 0 },
      });

      map.addLayer({
        id: 'places-glow',
        type: 'circle',
        source: PLACE_SOURCE_ID,
        paint: {
          'circle-radius': ['case', ['==', ['get', 'selected'], true], 22, 15],
          'circle-color': light ? '#FAF089' : ['get', 'color'],
          'circle-opacity': light
            ? ['case', ['==', ['get', 'selected'], true], 0.9, 0]
            : ['case', ['==', ['get', 'selected'], true], 0.55, 0.3],
          'circle-blur': light ? 0.1 : 0.7,
        },
      });

      map.addLayer({
        id: 'places-dot',
        type: 'circle',
        source: PLACE_SOURCE_ID,
        paint: {
          'circle-radius': ['case', ['==', ['get', 'selected'], true], 10, 8],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': light ? 2.5 : ['case', ['==', ['get', 'selected'], true], 3, 2.2],
          'circle-stroke-color': ['case', ['==', ['get', 'selected'], true], selectedStrokeColor, defaultStrokeColor],
        },
      });

      map.addLayer({
        id: 'places-label',
        type: 'symbol',
        source: PLACE_SOURCE_ID,
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 11,
          'text-offset': [0, 1.25],
          'text-anchor': 'top',
          'text-optional': true,
        },
        paint: {
          'text-color': labelTextColor,
          'text-halo-color': labelHaloColor,
          'text-halo-width': 1.8,
        },
      });

      // 3. Live Happenin' Event Pins
      if (!map.getSource(EVENT_SOURCE_ID)) {
        map.addSource(EVENT_SOURCE_ID, {
          type: 'geojson',
          data: clustersToGeoJSON(clustersRef.current, selectedKeyRef.current, light),
        });
      }

      map.addLayer({
        id: 'pins-hit',
        type: 'circle',
        source: EVENT_SOURCE_ID,
        paint: { 'circle-radius': 22, 'circle-color': '#000000', 'circle-opacity': 0 },
      });

      map.addLayer({
        id: 'pins-glow',
        type: 'circle',
        source: EVENT_SOURCE_ID,
        paint: {
          'circle-radius': [
            'case',
            ['==', ['get', 'selected'], true], synthwave ? 32 : 24,
            ['>', ['get', 'count'], 1], synthwave ? 26 : 19,
            synthwave ? 21 : 15,
          ],
          'circle-color': light ? '#FAF089' : ['get', 'color'],
          'circle-opacity': light
            ? ['case', ['==', ['get', 'selected'], true], 0.9, 0.2]
            : synthwave
              ? ['case', ['==', ['get', 'selected'], true], 0.8, 0.56]
              : ['case', ['==', ['get', 'selected'], true], 0.55, 0.34],
          'circle-blur': light ? 0.15 : synthwave ? 0.85 : 0.75,
        },
      });

      map.addLayer({
        id: 'pins-dot',
        type: 'circle',
        source: EVENT_SOURCE_ID,
        paint: {
          'circle-radius': [
            'case',
            ['>', ['get', 'count'], 1], 12,
            ['==', ['get', 'selected'], true], 10,
            8,
          ],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': light ? 2.5 : ['case', ['==', ['get', 'selected'], true], 3, 2.2],
          'circle-stroke-color': ['case', ['==', ['get', 'selected'], true], selectedStrokeColor, defaultStrokeColor],
        },
      });

      map.addLayer({
        id: 'pins-count',
        type: 'symbol',
        source: EVENT_SOURCE_ID,
        filter: ['>', ['get', 'count'], 1],
        layout: {
          'text-field': ['to-string', ['get', 'count']],
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 11,
          'text-allow-overlap': true,
          'text-ignore-placement': true,
        },
        paint: {
          'text-color': light ? '#FFFFFF' : '#120e24',
        },
      });

      // 4. Custom Concierge & Guest Dropped Pins (always on top of regular layers)
      if (!map.getSource(CUSTOM_SOURCE_ID)) {
        map.addSource(CUSTOM_SOURCE_ID, {
          type: 'geojson',
          data: customPinsToGeoJSON(customPinsRef.current, selectedCustomPinRef.current),
        });
      }

      map.addLayer({
        id: 'custom-hit',
        type: 'circle',
        source: CUSTOM_SOURCE_ID,
        paint: { 'circle-radius': 24, 'circle-color': '#000000', 'circle-opacity': 0 },
      });

      map.addLayer({
        id: 'custom-glow',
        type: 'circle',
        source: CUSTOM_SOURCE_ID,
        paint: {
          'circle-radius': ['case', ['==', ['get', 'selected'], true], 24, 18],
          'circle-color': '#F59E0B',
          'circle-opacity': ['case', ['==', ['get', 'selected'], true], 0.55, 0.32],
          'circle-blur': 0.55,
        },
      });

      map.addLayer({
        id: 'custom-dot',
        type: 'circle',
        source: CUSTOM_SOURCE_ID,
        paint: {
          'circle-radius': ['case', ['==', ['get', 'selected'], true], 12, 10.5],
          'circle-color': '#F59E0B',
          'circle-stroke-width': 2.8,
          'circle-stroke-color': light ? '#0D0D0D' : '#FFFFFF',
        },
      });

      map.addLayer({
        id: 'custom-star',
        type: 'symbol',
        source: CUSTOM_SOURCE_ID,
        layout: {
          'text-field': '★',
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 12,
          'text-allow-overlap': true,
          'text-ignore-placement': true,
        },
        paint: {
          'text-color': '#0D0D0D',
        },
      });

      map.addLayer({
        id: 'custom-label',
        type: 'symbol',
        source: CUSTOM_SOURCE_ID,
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 11.5,
          'text-offset': [0, 1.4],
          'text-anchor': 'top',
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': labelTextColor,
          'text-halo-color': labelHaloColor,
          'text-halo-width': 2,
        },
      });

      // 5. Draft Pin Preview while placing
      if (!map.getSource(DRAFT_SOURCE_ID)) {
        map.addSource(DRAFT_SOURCE_ID, {
          type: 'geojson',
          data: draftPinToGeoJSON(draftPinRef.current),
        });
      }

      map.addLayer({
        id: 'draft-halo',
        type: 'circle',
        source: DRAFT_SOURCE_ID,
        paint: {
          'circle-radius': 24,
          'circle-color': '#F59E0B',
          'circle-opacity': 0.42,
          'circle-blur': 0.35,
        },
      });

      map.addLayer({
        id: 'draft-dot',
        type: 'circle',
        source: DRAFT_SOURCE_ID,
        paint: {
          'circle-radius': 10,
          'circle-color': '#FFFFFF',
          'circle-stroke-width': 3.5,
          'circle-stroke-color': '#F59E0B',
        },
      });

      for (const layer of ['pins-hit', 'places-hit', 'custom-hit']) {
        map.on('mouseenter', layer, () => {
          map.getCanvas().style.cursor = pinDropActiveRef.current ? 'crosshair' : 'pointer';
        });
        map.on('mouseleave', layer, () => {
          map.getCanvas().style.cursor = pinDropActiveRef.current ? 'crosshair' : '';
        });
      }
    }

    map.on('style.load', mountLayers);

    map.on('click', (e) => {
      if (pinDropActiveRef.current && onMapPinDropClickRef.current) {
        onMapPinDropClickRef.current({
          latitude: e.lngLat.lat,
          longitude: e.lngLat.lng,
        });
        return;
      }
      if (!styleLoadedRef.current) {
        onBgClickRef.current();
        return;
      }
      const customHits = map.queryRenderedFeatures(e.point, { layers: ['custom-hit'] });
      const hitCustomId = customHits[0]?.properties?.id as string | undefined;
      if (hitCustomId && onSelectCustomPinRef.current) {
        const match = customPinsRef.current.find((p) => p.id === hitCustomId);
        if (match) {
          onSelectCustomPinRef.current(match);
          return;
        }
      }
      const eventHits = map.queryRenderedFeatures(e.point, { layers: ['pins-hit'] });
      const hitKey = eventHits[0]?.properties?.key as string | undefined;
      if (hitKey) {
        const match = clustersRef.current.find((c) => c.key === hitKey);
        if (match) {
          onSelectRef.current(match);
          return;
        }
      }
      const placeHits = map.queryRenderedFeatures(e.point, { layers: ['places-hit'] });
      const hitPlaceId = placeHits[0]?.properties?.id as string | undefined;
      if (hitPlaceId && onSelectPlaceRef.current) {
        const match = placesRef.current.find((p) => p.id === hitPlaceId);
        if (match) {
          onSelectPlaceRef.current(match);
          return;
        }
      }
      onBgClickRef.current();
    });

    mapRef.current = map;
    return () => {
      styleLoadedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Switch basemap cleanly if hotel config asks for 'light' vs 'dark'.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const desiredMode: 'dark' | 'light' = isLight ? 'light' : 'dark';
    if (desiredMode !== activeStyleModeRef.current) {
      activeStyleModeRef.current = desiredMode;
      styleLoadedRef.current = false;
      map.setStyle(desiredMode === 'light' ? POSITRON_LIGHT_STYLE : DARK_MATTER_STYLE);
    }
  }, [isLight]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(EVENT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(clustersToGeoJSON(clusters, selectedClusterKey, isLight));
  }, [clusters, selectedClusterKey, isLight]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(PLACE_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(placesToGeoJSON(places, selectedPlaceId, isLight));
  }, [places, selectedPlaceId, isLight]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(CUSTOM_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(customPinsToGeoJSON(customPins, selectedCustomPinId));
  }, [customPins, selectedCustomPinId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(DRAFT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(draftPinToGeoJSON(draftPin));
  }, [draftPin]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getCanvas().style.cursor = pinDropActive ? 'crosshair' : '';
  }, [pinDropActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !draftPin) return;
    map.easeTo({
      center: [draftPin.longitude, draftPin.latitude],
      offset: [0, -135],
      duration: 320,
    });
  }, [draftPin]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedCustomPinId) return;
    const target = customPins.find((p) => p.id === selectedCustomPinId);
    if (!target) return;
    map.easeTo({
      center: [target.longitude, target.latitude],
      offset: [0, -110],
      duration: 280,
    });
  }, [selectedCustomPinId, customPins]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (styleLoadedRef.current) {
      const source = map.getSource(HOME_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (source) source.setData(homeToGeoJSON(hotel));
    }
    if (hotel && centeredHotelRef.current !== hotel.id) {
      centeredHotelRef.current = hotel.id;
      map.jumpTo({
        center: [hotel.longitude, hotel.latitude],
        zoom: hotel.initialZoom,
      });
    }
  }, [hotel]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || hotel || centeredRegionRef.current === region) return;
    centeredRegionRef.current = region;
    map.flyTo({
      center: REGIONS[region].center,
      zoom: REGIONS[region].zoom,
      duration: 850,
    });
  }, [region, hotel]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedClusterKey) return;
    const target = clusters.find((c) => c.key === selectedClusterKey);
    if (!target) return;
    map.easeTo({
      center: [target.longitude, target.latitude],
      offset: [0, -110],
      duration: 280,
    });
  }, [selectedClusterKey, clusters]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedPlaceId) return;
    const target = places.find((p) => p.id === selectedPlaceId);
    if (!target) return;
    map.easeTo({
      center: [target.longitude, target.latitude],
      offset: [0, -110],
      duration: 280,
    });
  }, [selectedPlaceId, places]);

  function handleLocateMe() {
    const map = mapRef.current;
    if (!map) return;
    if (hotel) {
      map.flyTo({
        center: [hotel.longitude, hotel.latitude],
        zoom: hotel.initialZoom,
        duration: 450,
      });
      return;
    }
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        map.flyTo({
          center: [pos.coords.longitude, pos.coords.latitude],
          zoom: 14.5,
          duration: 500,
        });
      },
      () => {
        map.flyTo({ center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM, duration: 450 });
      },
      { enableHighAccuracy: false, timeout: 5000 }
    );
  }

  return (
    <>
      <div ref={containerRef} className="map-container" />
      <button
        type="button"
        className="locate-btn"
        onClick={handleLocateMe}
        title={hotel ? `Re-center on ${hotel.name}` : 'Center on my location'}
        aria-label={hotel ? `Re-center on ${hotel.name}` : 'Center on my location'}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
          <circle cx="12" cy="12" r="7" opacity="0.45" />
        </svg>
      </button>
    </>
  );
}
