import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { CATEGORY_COLORS, VenueCluster } from '../data/events';

type MapViewProps = {
  clusters: VenueCluster[];
  selectedClusterKey: string | null;
  onSelectCluster: (cluster: VenueCluster) => void;
  onMapBackgroundClick: () => void;
};

const DARK_MATTER_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

// Centered on Central Square / Cambridge; users can pan freely into Somerville & Boston.
const INITIAL_CENTER: [number, number] = [-71.106, 42.369];
const INITIAL_ZOOM = 13.4;
const SOURCE_ID = 'happenin-pins';

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

export function MapView({
  clusters,
  selectedClusterKey,
  onSelectCluster,
  onMapBackgroundClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const styleLoadedRef = useRef(false);

  const clustersRef = useRef(clusters);
  const selectedKeyRef = useRef(selectedClusterKey);
  const onSelectRef = useRef(onSelectCluster);
  const onBgClickRef = useRef(onMapBackgroundClick);

  clustersRef.current = clusters;
  selectedKeyRef.current = selectedClusterKey;
  onSelectRef.current = onSelectCluster;
  onBgClickRef.current = onMapBackgroundClick;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_MATTER_STYLE,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      pitch: 0,
      maxPitch: 0,
      minPitch: 0,
      bearing: 0,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: { compact: true },
    });

    // Keep map strictly flat and north-up on touch devices too.
    map.touchZoomRotate.disableRotation();

    map.on('load', () => {
      styleLoadedRef.current = true;

      map.addSource(SOURCE_ID, {
        type: 'geojson',
        data: clustersToGeoJSON(clustersRef.current, selectedKeyRef.current),
      });

      // Invisible generous touch/click hit target rendered in WebGL coordinates.
      map.addLayer({
        id: 'pins-hit',
        type: 'circle',
        source: SOURCE_ID,
        paint: {
          'circle-radius': 22,
          'circle-color': '#000000',
          'circle-opacity': 0,
        },
      });

      // Soft neon outer glow locked 1:1 to WebGL projection.
      map.addLayer({
        id: 'pins-glow',
        type: 'circle',
        source: SOURCE_ID,
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

      // Crisp inner pin dot.
      map.addLayer({
        id: 'pins-dot',
        type: 'circle',
        source: SOURCE_ID,
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

      // Event count label for venues with multiple simultaneous events.
      map.addLayer({
        id: 'pins-count',
        type: 'symbol',
        source: SOURCE_ID,
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

      map.on('mouseenter', 'pins-hit', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'pins-hit', () => {
        map.getCanvas().style.cursor = '';
      });
    });

    map.on('click', (e) => {
      if (!styleLoadedRef.current) {
        onBgClickRef.current();
        return;
      }
      const features = map.queryRenderedFeatures(e.point, { layers: ['pins-hit'] });
      const hitKey = features[0]?.properties?.key as string | undefined;
      if (hitKey) {
        const match = clustersRef.current.find((c) => c.key === hitKey);
        if (match) {
          onSelectRef.current(match);
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

  // Push updated pins to the GPU source instantly with zero DOM lag.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(clustersToGeoJSON(clusters, selectedClusterKey));
    }
  }, [clusters, selectedClusterKey]);

  // Gently pan to selected pin (offset upward so it stays above the event card).
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

  function handleLocateMe() {
    const map = mapRef.current;
    if (!map || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        map.flyTo({
          center: [pos.coords.longitude, pos.coords.latitude],
          zoom: 14.5,
          duration: 500,
        });
      },
      () => {
        map.flyTo({ center: INITIAL_CENTER, zoom: INITIAL_ZOOM, duration: 450 });
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
        title="Center on my location"
        aria-label="Center on my location"
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
