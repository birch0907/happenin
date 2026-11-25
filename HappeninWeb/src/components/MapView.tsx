import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { CATEGORY_COLORS, VenueCluster } from '../data/events';
import { HotelConfig, HotelPlace, PLACE_TAB_COLORS } from '../data/hotels';

type MapViewProps = {
  clusters: VenueCluster[];
  selectedClusterKey: string | null;
  onSelectCluster: (cluster: VenueCluster) => void;
  places?: HotelPlace[];
  selectedPlaceId?: string | null;
  onSelectPlace?: (place: HotelPlace) => void;
  hotel?: HotelConfig | null;
  onMapBackgroundClick: () => void;
};

const DARK_MATTER_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const DEFAULT_CENTER: [number, number] = [-71.106, 42.369];
const DEFAULT_ZOOM = 13.4;

const EVENT_SOURCE_ID = 'happenin-pins';
const PLACE_SOURCE_ID = 'hotel-places';
const HOME_SOURCE_ID = 'hotel-home';

function clustersToGeoJSON(
  clusters: VenueCluster[],
  selectedKey: string | null
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
        color: CATEGORY_COLORS[cluster.primaryCategory],
        selected: cluster.key === selectedKey,
      },
    })),
  };
}

function placesToGeoJSON(
  places: HotelPlace[],
  selectedPlaceId: string | null
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
        color: PLACE_TAB_COLORS[place.tab],
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
          accent: hotel.theme.accent,
        },
      },
    ],
  };
}

export function MapView({
  clusters,
  selectedClusterKey,
  onSelectCluster,
  places = [],
  selectedPlaceId = null,
  onSelectPlace,
  hotel = null,
  onMapBackgroundClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const styleLoadedRef = useRef(false);
  const centeredHotelRef = useRef<string | null>(null);

  const clustersRef = useRef(clusters);
  const selectedKeyRef = useRef(selectedClusterKey);
  const placesRef = useRef(places);
  const selectedPlaceRef = useRef(selectedPlaceId);
  const hotelRef = useRef(hotel);
  const onSelectRef = useRef(onSelectCluster);
  const onSelectPlaceRef = useRef(onSelectPlace);
  const onBgClickRef = useRef(onMapBackgroundClick);

  clustersRef.current = clusters;
  selectedKeyRef.current = selectedClusterKey;
  placesRef.current = places;
  selectedPlaceRef.current = selectedPlaceId;
  hotelRef.current = hotel;
  onSelectRef.current = onSelectCluster;
  onSelectPlaceRef.current = onSelectPlace;
  onBgClickRef.current = onMapBackgroundClick;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const initialCenter: [number, number] = hotelRef.current
      ? [hotelRef.current.longitude, hotelRef.current.latitude]
      : DEFAULT_CENTER;
    const initialZoom = hotelRef.current ? hotelRef.current.initialZoom : DEFAULT_ZOOM;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_MATTER_STYLE,
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

    map.on('load', () => {
      styleLoadedRef.current = true;

      // 1. Hotel Home Marker ("You Are Here")
      map.addSource(HOME_SOURCE_ID, {
        type: 'geojson',
        data: homeToGeoJSON(hotelRef.current),
      });

      map.addLayer({
        id: 'hotel-home-halo',
        type: 'circle',
        source: HOME_SOURCE_ID,
        paint: {
          'circle-radius': 24,
          'circle-color': ['get', 'accent'],
          'circle-opacity': 0.28,
          'circle-blur': 0.55,
        },
      });

      map.addLayer({
        id: 'hotel-home-dot',
        type: 'circle',
        source: HOME_SOURCE_ID,
        paint: {
          'circle-radius': 9,
          'circle-color': '#ffffff',
          'circle-stroke-width': 3.5,
          'circle-stroke-color': ['get', 'accent'],
        },
      });

      map.addLayer({
        id: 'hotel-home-label',
        type: 'symbol',
        source: HOME_SOURCE_ID,
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 11,
          'text-offset': [0, 1.55],
          'text-anchor': 'top',
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': '#f7f4ec',
          'text-halo-color': '#0f1420',
          'text-halo-width': 1.5,
        },
      });

      // 2. Curated Hotel Places (Dining / Sights)
      map.addSource(PLACE_SOURCE_ID, {
        type: 'geojson',
        data: placesToGeoJSON(placesRef.current, selectedPlaceRef.current),
      });

      map.addLayer({
        id: 'places-hit',
        type: 'circle',
        source: PLACE_SOURCE_ID,
        paint: {
          'circle-radius': 24,
          'circle-color': '#000000',
          'circle-opacity': 0,
        },
      });

      map.addLayer({
        id: 'places-glow',
        type: 'circle',
        source: PLACE_SOURCE_ID,
        paint: {
          'circle-radius': ['case', ['==', ['get', 'selected'], true], 24, 16],
          'circle-color': ['get', 'color'],
          'circle-opacity': ['case', ['==', ['get', 'selected'], true], 0.55, 0.3],
          'circle-blur': 0.7,
        },
      });

      map.addLayer({
        id: 'places-dot',
        type: 'circle',
        source: PLACE_SOURCE_ID,
        paint: {
          'circle-radius': ['case', ['==', ['get', 'selected'], true], 10, 7.5],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': ['case', ['==', ['get', 'selected'], true], 3, 2.2],
          'circle-stroke-color': ['case', ['==', ['get', 'selected'], true], '#ffffff', '#0f1420'],
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
          'text-color': '#f5f2ea',
          'text-halo-color': '#0f1420',
          'text-halo-width': 1.4,
        },
      });

      // 3. Live Happenin' Event Pins
      map.addSource(EVENT_SOURCE_ID, {
        type: 'geojson',
        data: clustersToGeoJSON(clustersRef.current, selectedKeyRef.current),
      });

      map.addLayer({
        id: 'pins-hit',
        type: 'circle',
        source: EVENT_SOURCE_ID,
        paint: {
          'circle-radius': 22,
          'circle-color': '#000000',
          'circle-opacity': 0,
        },
      });

      map.addLayer({
        id: 'pins-glow',
        type: 'circle',
        source: EVENT_SOURCE_ID,
        paint: {
          'circle-radius': [
            'case',
            ['==', ['get', 'selected'], true], 26,
            ['>', ['get', 'count'], 1], 21,
            16,
          ],
          'circle-color': ['get', 'color'],
          'circle-opacity': [
            'case',
            ['==', ['get', 'selected'], true], 0.55,
            0.34,
          ],
          'circle-blur': 0.75,
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
            7.5,
          ],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': [
            'case',
            ['==', ['get', 'selected'], true], 3,
            2.2,
          ],
          'circle-stroke-color': [
            'case',
            ['==', ['get', 'selected'], true], '#ffffff',
            '#120e24',
          ],
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
          'text-color': '#120e24',
        },
      });

      for (const layer of ['pins-hit', 'places-hit']) {
        map.on('mouseenter', layer, () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', layer, () => {
          map.getCanvas().style.cursor = '';
        });
      }
    });

    map.on('click', (e) => {
      if (!styleLoadedRef.current) {
        onBgClickRef.current();
        return;
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

  // Update event pins GPU source.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(EVENT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(clustersToGeoJSON(clusters, selectedClusterKey));
  }, [clusters, selectedClusterKey]);

  // Update hotel places GPU source.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(PLACE_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) source.setData(placesToGeoJSON(places, selectedPlaceId));
  }, [places, selectedPlaceId]);

  // Update hotel home pin and center when hotel config loads.
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

  // Gently pan to selected event pin.
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

  // Gently pan to selected hotel place pin.
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
