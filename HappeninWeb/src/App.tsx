import { useEffect, useMemo, useState } from 'react';
import {
  CATEGORIES,
  CATEGORY_COLORS,
  DATE_COUNT,
  EventCategory,
  HappeninEvent,
  QUARTER_MS,
  REGIONS,
  RawEvent,
  RegionId,
  addCalendarDays,
  currentQuarter,
  dateParts,
  defaultTimeForDate,
  easternToday,
  eventVisibleAtTime,
  formatTimelineTime,
  getRegionParam,
  getScrubberWindow,
  groupEventsByPin,
  normalizeEvents,
} from './data/events';
import { HotelConfig, HotelTab, eventAllowedForHotel, getHotelParam } from './data/hotels';
import {
  CustomPin,
  getDeskModeParam,
  getUrlSharedPins,
  loadGuestPins,
  reverseGeocodePoint,
  saveGuestPins,
} from './data/customPins';
import { MapView } from './components/MapView';
import { EventCard } from './components/EventCard';
import { PlaceCard } from './components/PlaceCard';
import { CustomPinCard } from './components/CustomPinCard';
import { DraftPinLocation, PinDropSheet } from './components/PinDropSheet';
import { SharePinsModal } from './components/SharePinsModal';
import { DatabaseView } from './components/DatabaseView';

const HOTEL_TABS: HotelTab[] = ['Dining', 'Sights', 'Tonight'];

function isDatabaseMode(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get('view') === 'db';
}

function getThemeParam(): 'miami-vice' | 'classic' {
  const params = new URLSearchParams(window.location.search);
  return params.get('theme')?.trim().toLowerCase() === 'classic' ? 'classic' : 'miami-vice';
}

function synthwaveBarColor(pct: number): string {
  // Interpolate smoothly from hot Miami pink (#FF3EA5) -> electric violet (#B64CFF) -> laser cyan (#2FE6E6)
  const clamped = Math.max(0, Math.min(1, pct));
  const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
  if (clamped < 0.55) {
    const t = clamped / 0.55;
    return `rgb(${lerp(255, 182, t)}, ${lerp(62, 76, t)}, ${lerp(165, 255, t)})`;
  }
  const t = (clamped - 0.55) / 0.45;
  return `rgb(${lerp(182, 47, t)}, ${lerp(76, 230, t)}, ${lerp(255, 230, t)})`;
}

export default function App() {
  if (isDatabaseMode()) {
    return <DatabaseView />;
  }
  return <MapApp />;
}

function MapApp() {
  const initialHotelParam = useMemo(() => getHotelParam(), []);
  const initialRegionParam = useMemo(() => getRegionParam(), []);
  const isDeskMode = useMemo(() => getDeskModeParam(), []);
  const [hotel, setHotel] = useState<HotelConfig | null>(null);
  const [hotelTab, setHotelTab] = useState<HotelTab>('Tonight');
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [region, setRegion] = useState<RegionId>(initialRegionParam || 'boston');
  const [showRegionPicker, setShowRegionPicker] = useState<boolean>(
    () => !initialHotelParam && !initialRegionParam
  );

  // Custom Pin Drop state (Concierge Desk + Guest Self-Drop)
  const [sharedPins] = useState<CustomPin[]>(() => getUrlSharedPins());
  const [guestPins, setGuestPins] = useState<CustomPin[]>([]);
  const [deskPins, setDeskPins] = useState<CustomPin[]>(() => (isDeskMode ? getUrlSharedPins() : []));
  const [selectedCustomPinId, setSelectedCustomPinId] = useState<string | null>(
    () => (!isDeskMode && getUrlSharedPins()[0]?.id) || null
  );
  const [pinDropActive, setPinDropActive] = useState(false);
  const [draftPinLocation, setDraftPinLocation] = useState<DraftPinLocation | null>(null);
  const [shareModalOpen, setShareModalOpen] = useState(false);

  const [allEvents, setAllEvents] = useState<HappeninEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeCategories, setActiveCategories] = useState<EventCategory[]>([...CATEGORIES]);
  const [today, setToday] = useState(easternToday);
  const [selectedDate, setSelectedDate] = useState(easternToday);
  const [datesExpanded, setDatesExpanded] = useState(false);

  const isHotelMode = Boolean(hotel || initialHotelParam);
  const [selectedTime, setSelectedTime] = useState(() => {
    const t = easternToday();
    return defaultTimeForDate(t, Boolean(initialHotelParam), t);
  });
  const [clockQuarter, setClockQuarter] = useState(currentQuarter);
  const [selectedClusterKey, setSelectedClusterKey] = useState<string | null>(null);

  // Load optional white-label hotel config from ?hotel=<id>
  useEffect(() => {
    const hotelId = getHotelParam();
    if (!hotelId) return;
    let cancelled = false;
    fetch(`./hotels/${hotelId}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg: HotelConfig | null) => {
        if (cancelled || !cfg) return;
        setHotel(cfg);
        if (!isDeskMode) {
          setGuestPins(loadGuestPins(cfg.id));
        }
        document.title = isDeskMode
          ? `${cfg.name} · Concierge Desk`
          : `${cfg.name} · ${cfg.subtitle}`;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Load live events.json feed.
  useEffect(() => {
    let cancelled = false;
    fetch('./events.json')
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load events (${r.status})`);
        return r.json();
      })
      .then((raw: RawEvent[]) => {
        if (cancelled) return;
        setAllEvents(normalizeEvents(raw));
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Could not load events');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Keep logical "today" and live clock synced every minute.
  useEffect(() => {
    const refresh = () => {
      const nextNow = currentQuarter();
      const newToday = easternToday();
      setToday(newToday);
      setClockQuarter((prevNow) => {
        setSelectedDate((prevDate) => {
          if (prevDate < newToday) {
            setSelectedTime(defaultTimeForDate(newToday, isHotelMode, newToday));
            setDatesExpanded(false);
            return newToday;
          }
          if (prevDate === newToday) {
            const win = getScrubberWindow(newToday, isHotelMode);
            setSelectedTime((prevSel) => {
              // If user was tracking "Now" and we're in the active window, advance with the clock.
              if (nextNow >= win.start && nextNow <= win.end && Math.abs(prevSel - prevNow) < QUARTER_MS) {
                return nextNow;
              }
              return Math.max(win.start, Math.min(win.end, prevSel));
            });
          }
          return prevDate;
        });
        return nextNow;
      });
    };

    const timer = window.setInterval(refresh, 60 * 1000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [isHotelMode]);

  const scrubberWindow = useMemo(
    () => getScrubberWindow(selectedDate, isHotelMode),
    [selectedDate, isHotelMode]
  );
  const todayWindow = useMemo(
    () => getScrubberWindow(today, isHotelMode),
    [today, isHotelMode]
  );
  const windowStart = scrubberWindow.start;
  const windowEnd = scrubberWindow.end;
  const nowInTodayWindow = clockQuarter >= todayWindow.start && clockQuarter <= todayWindow.end;

  const showingEvents = !hotel || hotelTab === 'Tonight';

  const availableDates = useMemo(
    () => Array.from({ length: DATE_COUNT }, (_, idx) => addCalendarDays(today, idx)),
    [today]
  );

  const regionCounts = useMemo(() => {
    let boston = 0;
    let seacoast = 0;
    for (const ev of allEvents) {
      if (ev.region === 'seacoast') seacoast++;
      else boston++;
    }
    return { boston, seacoast };
  }, [allEvents]);

  const activeRegion: RegionId = hotel
    ? hotel.region || (hotel.latitude >= 42.82 ? 'seacoast' : 'boston')
    : region;

  const eligibleEvents = useMemo(
    () =>
      allEvents.filter((ev) => {
        if (ev.region !== activeRegion) return false;
        return hotel ? eventAllowedForHotel(ev, hotel) : true;
      }),
    [allEvents, activeRegion, hotel]
  );

  const visibleEvents = useMemo(
    () =>
      showingEvents
        ? eligibleEvents.filter(
            (ev) => activeCategories.includes(ev.category) && eventVisibleAtTime(ev, selectedTime)
          )
        : [],
    [showingEvents, eligibleEvents, activeCategories, selectedTime]
  );

  const clusters = useMemo(() => groupEventsByPin(visibleEvents), [visibleEvents]);

  const visiblePlaces = useMemo(() => {
    if (!hotel || hotelTab === 'Tonight') return [];
    return hotel.places.filter((p) => p.tab === hotelTab);
  }, [hotel, hotelTab]);

  const customPins = useMemo(
    () => (isDeskMode ? deskPins : [...sharedPins, ...guestPins]),
    [isDeskMode, deskPins, sharedPins, guestPins]
  );

  const selectedCustomPin = useMemo(
    () => (selectedCustomPinId ? customPins.find((p) => p.id === selectedCustomPinId) || null : null),
    [customPins, selectedCustomPinId]
  );

  const selectedCluster = useMemo(
    () => (selectedClusterKey ? clusters.find((c) => c.key === selectedClusterKey) || null : null),
    [clusters, selectedClusterKey]
  );

  const selectedPlace = useMemo(
    () => (selectedPlaceId ? visiblePlaces.find((p) => p.id === selectedPlaceId) || null : null),
    [visiblePlaces, selectedPlaceId]
  );

  function startPinDrop() {
    setSelectedClusterKey(null);
    setSelectedPlaceId(null);
    setSelectedCustomPinId(null);
    setDraftPinLocation(null);
    setDatesExpanded(false);
    setPinDropActive(true);
  }

  function handleMapPinDropClick(coords: { latitude: number; longitude: number }) {
    setDraftPinLocation({ latitude: coords.latitude, longitude: coords.longitude });
    reverseGeocodePoint(coords.latitude, coords.longitude).then((info) => {
      setDraftPinLocation((prev) => {
        if (!prev || prev.latitude !== coords.latitude || prev.longitude !== coords.longitude) {
          return prev;
        }
        return {
          ...prev,
          suggestedName: prev.suggestedName || info.name,
          address: prev.address || info.address,
        };
      });
    });
  }

  function handleSaveCustomPin(input: {
    name: string;
    note: string;
    address?: string;
    latitude: number;
    longitude: number;
  }) {
    if (!hotel) return;
    const newPin: CustomPin = {
      id: `${isDeskMode ? 'desk' : 'guest'}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: input.name,
      note: input.note || undefined,
      address: input.address,
      latitude: input.latitude,
      longitude: input.longitude,
      origin: isDeskMode ? 'concierge' : 'guest',
    };
    if (isDeskMode) {
      setDeskPins((prev) => [...prev, newPin]);
    } else {
      setGuestPins((prev) => {
        const next = [...prev, newPin];
        saveGuestPins(hotel.id, next);
        return next;
      });
    }
    setPinDropActive(false);
    setDraftPinLocation(null);
    setSelectedCustomPinId(newPin.id);
  }

  function handleDeleteCustomPin(id: string) {
    if (!hotel) return;
    if (isDeskMode) {
      setDeskPins((prev) => prev.filter((p) => p.id !== id));
    } else {
      setGuestPins((prev) => {
        const next = prev.filter((p) => p.id !== id);
        saveGuestPins(hotel.id, next);
        return next;
      });
    }
    if (selectedCustomPinId === id) setSelectedCustomPinId(null);
  }

  function handleClearDeskPins() {
    setDeskPins([]);
    setSelectedCustomPinId(null);
    setShareModalOpen(false);
  }

  // Activity density across the current scrubber window (30-min bins) for the heat strip.
  const activityHeat = useMemo(() => {
    const binMs = 30 * 60 * 1000;
    const binCount = Math.max(1, Math.round((windowEnd - windowStart) / binMs));
    const matching = eligibleEvents.filter((ev) => activeCategories.includes(ev.category));
    const counts: number[] = [];
    let maxCount = 0;
    for (let i = 0; i < binCount; i++) {
      const sampleTime = windowStart + i * binMs + binMs / 2;
      let c = 0;
      for (const ev of matching) {
        if (eventVisibleAtTime(ev, sampleTime)) c++;
      }
      counts.push(c);
      if (c > maxCount) maxCount = c;
    }
    return { counts, maxCount };
  }, [eligibleEvents, activeCategories, windowStart, windowEnd]);

  function toggleCategory(cat: EventCategory) {
    setActiveCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
    setSelectedClusterKey(null);
  }

  function handleSelectDate(date: string) {
    setSelectedDate(date);
    setSelectedTime(defaultTimeForDate(date, isHotelMode, today));
    setDatesExpanded(false);
    setSelectedClusterKey(null);
  }

  function jumpToNow() {
    const t = easternToday();
    setToday(t);
    setClockQuarter(currentQuarter());
    setSelectedDate(t);
    setSelectedTime(defaultTimeForDate(t, isHotelMode, t));
    setDatesExpanded(false);
    setSelectedClusterKey(null);
  }

  function switchHotelTab(tab: HotelTab) {
    setHotelTab(tab);
    setSelectedClusterKey(null);
    setSelectedPlaceId(null);
    setDatesExpanded(false);
  }

  const totalSteps = scrubberWindow.totalSteps;
  const currentStep = Math.max(
    0,
    Math.min(totalSteps, Math.round((selectedTime - windowStart) / QUARTER_MS))
  );
  const progressPct = (currentStep / totalSteps) * 100;
  const defaultTodayTime = defaultTimeForDate(today, isHotelMode, today);
  const isAtDefault =
    selectedDate === today && Math.abs(selectedTime - defaultTodayTime) < QUARTER_MS;
  const selectedDateInfo = dateParts(selectedDate);

  const isVerbPoster = hotel?.styleVariant === 'verb-poster';
  const isStudioGallery = hotel?.styleVariant === 'studio-gallery';
  const isMiamiVice = !isHotelMode && getThemeParam() === 'miami-vice';
  const accentColor = hotel ? hotel.theme.accent : '#2FE6E6';
  const themeStyle = hotel
    ? ({
        '--bg': hotel.theme.bg,
        '--panel': hotel.theme.panel,
        '--panel-solid': hotel.theme.panelSolid,
        '--border': hotel.theme.border,
        '--border-strong': hotel.theme.borderStrong,
        '--text-muted': hotel.theme.textMuted,
        '--cyan': hotel.theme.accent,
      } as React.CSSProperties)
    : undefined;

  const chipPalette: Record<EventCategory, string> =
    isVerbPoster || isStudioGallery
      ? { 'Live Music': '#E63946', DJ: '#00A6B4', Social: '#7B2CBF' }
      : CATEGORY_COLORS;

  return (
    <main
      className={`app-shell${hotel ? ' hotel-mode' : ''}${isMiamiVice ? ' theme-miami-vice' : ''}${isVerbPoster ? ' variant-verb-poster' : ''}${isStudioGallery ? ' variant-studio-gallery' : ''}`}
      style={themeStyle}
    >
      <MapView
        clusters={clusters}
        selectedClusterKey={selectedCluster ? selectedCluster.key : null}
        onSelectCluster={(cluster) => {
          setSelectedPlaceId(null);
          setSelectedCustomPinId(null);
          setSelectedClusterKey(cluster.key);
        }}
        places={visiblePlaces}
        selectedPlaceId={selectedPlace ? selectedPlace.id : null}
        onSelectPlace={(place) => {
          setSelectedClusterKey(null);
          setSelectedCustomPinId(null);
          setSelectedPlaceId(place.id);
        }}
        customPins={hotel ? customPins : []}
        selectedCustomPinId={selectedCustomPin ? selectedCustomPin.id : null}
        onSelectCustomPin={(pin) => {
          setSelectedClusterKey(null);
          setSelectedPlaceId(null);
          setSelectedCustomPinId(pin.id);
        }}
        draftPin={
          pinDropActive && draftPinLocation
            ? {
                latitude: draftPinLocation.latitude,
                longitude: draftPinLocation.longitude,
                name: draftPinLocation.suggestedName,
              }
            : null
        }
        pinDropActive={pinDropActive}
        onMapPinDropClick={handleMapPinDropClick}
        hotel={hotel}
        region={activeRegion}
        miamiVice={isMiamiVice}
        onMapBackgroundClick={() => {
          setSelectedClusterKey(null);
          setSelectedPlaceId(null);
          setSelectedCustomPinId(null);
        }}
      />

      {/* FLOATING PIN DROP + SHARE CONTROLS (Digital Concierge only) */}
      {hotel && !pinDropActive && (
        <div className="pin-fab-stack">
          {isDeskMode && customPins.length > 0 && (
            <button
              type="button"
              className="pin-fab pin-fab-share"
              onClick={() => setShareModalOpen(true)}
              title="Share picks with guest (QR)"
              aria-label="Share custom pins"
            >
              <span className="pin-fab-star" aria-hidden="true">★</span>
              <span className="pin-fab-label">Share QR</span>
              <span className="pin-fab-count">{customPins.length}</span>
            </button>
          )}
          <button
            type="button"
            className="pin-fab pin-fab-drop"
            onClick={startPinDrop}
            title={isDeskMode ? 'Drop a custom concierge pin' : 'Drop a custom pin on the map'}
            aria-label="Drop a pin"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 21s-6-5.686-6-10a6 6 0 1 1 12 0c0 4.314-6 10-6 10z" />
              <circle cx="12" cy="11" r="2.2" />
            </svg>
            <span className="pin-fab-label">Drop Pin</span>
          </button>
        </div>
      )}

      {loading && <div className="status-banner">Loading what&apos;s happenin&apos;…</div>}
      {error && <div className="status-banner">{error}</div>}

      {/* TOP HEADER & FILTERS */}
      <header className="top-overlay">
        <div className="filter-panel">
          <div className="brand-row">
            <div className="brand-title">
              {hotel ? (
                <>
                  {hotel.logoIcon === 'pick' && (
                    <span className="verb-pick-badge" aria-hidden="true">
                      <svg width="24" height="26" viewBox="0 0 28 32" fill="none">
                        <path
                          d="M14 2C21.5 2 26 5.2 26 11.5C26 19.2 18.8 29.5 14 30C9.2 29.5 2 19.2 2 11.5C2 5.2 6.5 2 14 2Z"
                          fill="#0D0D0D"
                        />
                        <text
                          x="14"
                          y="17"
                          textAnchor="middle"
                          fill="#FFFFFF"
                          fontFamily="Oswald, sans-serif"
                          fontWeight="700"
                          fontSize="9.5"
                          letterSpacing="0.5"
                        >
                          VERB
                        </text>
                      </svg>
                    </span>
                  )}
                  {hotel.logoIcon === 'studio-frame' && (
                    <span className="studio-frame-badge" aria-hidden="true">
                      <svg width="34" height="34" viewBox="0 0 52 52" fill="none">
                        <g
                          transform="rotate(15 26 26)"
                          stroke="#141C20"
                          strokeWidth="2.5"
                          strokeLinecap="butt"
                          strokeLinejoin="miter"
                        >
                          <rect x="12" y="13" width="23" height="23" />
                          <path d="M13.5 36 L34.5 7.5" />
                          <path d="M35 7.5 C23.5 5 18.5 16 22.5 24 C25.5 29.5 32 30.5 42 30.5" />
                          <path d="M12 22.5 C22 23 24.5 32 19 38.5 C15.5 42.5 10.5 42.5 7.5 41.5" />
                        </g>
                      </svg>
                    </span>
                  )}
                  <span className="brand-wordmark hotel-wordmark">{hotel.wordmark}</span>
                  {isStudioGallery ? (
                    <span className="studio-handwritten-subtitle" aria-label={hotel.subtitle}>
                      <svg width="132" height="17" viewBox="0 0 208 26" fill="none">
                        <g
                          stroke="#1A9196"
                          strokeWidth="1.75"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          {/* D */}
                          <path d="M6 21 L8.5 7.5 M7.8 8 C15 7.5 16.5 12 15.2 16.5 C14 20.5 9.5 21.5 5.5 20.8" />
                          {/* I */}
                          <path d="M20.5 20.5 L22.8 8" />
                          {/* G */}
                          <path d="M36 9.5 C32 6.5 27.5 10.5 26.8 15.5 C26.2 20 30.2 21.8 34 20 L35.2 15.2 L31.2 15.6" />
                          {/* I */}
                          <path d="M40.5 21 L42.6 8.5" />
                          {/* T */}
                          <path d="M49.5 20.5 L52 8.2 M46.2 8.8 L57.5 7.2" />
                          {/* A */}
                          <path d="M57.5 21.2 L64.5 7.5 L67 20.8 M59.5 16.2 L66.5 15.2" />
                          {/* L */}
                          <path d="M72 8 L70.2 20.8 L78.5 20.2" />
                          {/* C */}
                          <path d="M97.5 9.2 C93.2 6.8 88.5 10.8 88 15.8 C87.5 20.4 92.2 21.8 96.5 19.6" />
                          {/* O */}
                          <path d="M106.5 8 C101.8 8.2 99.5 13.5 100.5 17.8 C101.5 21.5 106.8 21.6 109.2 17.5 C111.5 13.5 110.2 7.8 106.5 8" />
                          {/* N */}
                          <path d="M114.2 21 L116.5 8.2 L122.8 20.5 L125.5 7.8" />
                          {/* C */}
                          <path d="M138.8 9.2 C134.5 6.8 129.8 11 129.4 16 C129 20.5 133.5 21.8 137.8 19.5" />
                          {/* I */}
                          <path d="M143.5 20.8 L145.6 8.2" />
                          {/* E */}
                          <path d="M150.2 20.8 L152.6 8 M152 8.2 L159.5 7.2 M151.4 14.5 L157.8 13.8 M150 20.8 L158.8 19.8" />
                          {/* R */}
                          <path d="M163.8 21 L166.2 8 M165.6 8.2 C171.8 7.4 173.8 10.6 171.8 13.4 C170.2 15.2 167 15.2 165.2 15 M168 15 L172.8 21" />
                          {/* G */}
                          <path d="M186.5 9.2 C182.5 6.5 177.8 10.5 177.2 15.8 C176.6 20.2 180.8 21.8 184.5 20 L185.8 15.2 L181.8 15.6" />
                          {/* E */}
                          <path d="M190.8 20.8 L193.2 8 M192.6 8.2 L200.5 7.2 M192 14.4 L198.5 13.7 M190.6 20.8 L199.6 19.8" />
                        </g>
                      </svg>
                    </span>
                  ) : (
                    <span className="event-count">{hotel.subtitle}</span>
                  )}
                </>
              ) : (
                <button
                  type="button"
                  className="brand-wordmark brand-wordmark-btn"
                  onClick={() => setShowRegionPicker(true)}
                  title={`Location: ${REGIONS[region].label} (tap to switch)`}
                  aria-label={`Happenin' (${REGIONS[region].label}) — tap to switch location`}
                >
                  HAPPENIN<span>&apos;</span>
                </button>
              )}
            </div>
            <div className="brand-right-actions">
              {!hotel && (
                <span className="event-count">
                  {visibleEvents.length} {visibleEvents.length === 1 ? 'event' : 'events'}
                </span>
              )}
              {hotel && isDeskMode && (
                <span className="desk-mode-badge" title="Front Desk Pin Drop Mode">
                  CONCIERGE DESK
                </span>
              )}
            </div>
          </div>

          {hotel && (
            <div className="hotel-mode-tabs" role="tablist" aria-label="Neighborhood guide mode">
              {HOTEL_TABS.map((tab) => {
                const count =
                  tab === 'Tonight'
                    ? visibleEvents.length
                    : hotel.places.filter((p) => p.tab === tab).length;
                return (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={hotelTab === tab}
                    className={`hotel-tab-btn${hotelTab === tab ? ' active' : ''}`}
                    onClick={() => switchHotelTab(tab)}
                  >
                    {tab === 'Tonight' ? 'Events' : tab}
                    <span className="hotel-tab-count">{count}</span>
                  </button>
                );
              })}
            </div>
          )}

          {showingEvents && (
            <div className="category-row" role="group" aria-label="Filter by category">
              {CATEGORIES.map((category) => {
                const active = activeCategories.includes(category);
                return (
                  <button
                    key={category}
                    type="button"
                    className={`category-chip${active ? ' active' : ''}`}
                    style={{ '--chip-color': chipPalette[category] } as React.CSSProperties}
                    onClick={() => toggleCategory(category)}
                    aria-pressed={active}
                  >
                    <span className="category-dot" />
                    {category}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </header>

      {/* BOTTOM STACK: PIN DROP / EVENT / PLACE / CUSTOM PIN CARD + PREVIEW PILL + DATE STRIP + TIME SLIDER */}
      <div className="bottom-overlay">
        {pinDropActive && hotel && (
          <PinDropSheet
            hotel={hotel}
            isDeskMode={isDeskMode}
            draftLocation={draftPinLocation}
            onSelectSearchResult={(r) =>
              setDraftPinLocation({
                latitude: r.latitude,
                longitude: r.longitude,
                suggestedName: r.name,
                address: r.address,
              })
            }
            onSavePin={handleSaveCustomPin}
            onCancel={() => {
              setPinDropActive(false);
              setDraftPinLocation(null);
            }}
          />
        )}

        {!pinDropActive && selectedCustomPin && hotel && (
          <CustomPinCard
            pin={selectedCustomPin}
            hotel={hotel}
            canDelete={isDeskMode || selectedCustomPin.origin === 'guest'}
            onDelete={handleDeleteCustomPin}
            onShare={isDeskMode ? () => setShareModalOpen(true) : undefined}
            onClose={() => setSelectedCustomPinId(null)}
          />
        )}

        {!pinDropActive && selectedCluster && (
          <EventCard
            cluster={selectedCluster}
            hotel={hotel}
            onClose={() => setSelectedClusterKey(null)}
          />
        )}

        {!pinDropActive && selectedPlace && hotel && (
          <PlaceCard
            place={selectedPlace}
            hotel={hotel}
            onClose={() => setSelectedPlaceId(null)}
          />
        )}

        {!pinDropActive && showingEvents && (
          <>
            <div className="date-row">
              <button
                type="button"
                className="date-tile selected"
                onClick={() => setDatesExpanded((prev) => !prev)}
                aria-expanded={datesExpanded}
                aria-label="Choose event date"
              >
                <span className="date-weekday">
                  {selectedDate === today ? 'Today' : selectedDateInfo.weekday}
                </span>
                <span className="date-day">{selectedDateInfo.day}</span>
              </button>

              {!datesExpanded && !isAtDefault && (
                <button type="button" className="now-jump-btn" onClick={jumpToNow}>
                  {nowInTodayWindow ? 'Back to Now' : 'Back to Tonight'}
                </button>
              )}

              {datesExpanded && (
                <div className="date-scroll" role="list" aria-label="Upcoming dates">
                  {availableDates
                    .filter((d) => d !== selectedDate)
                    .map((date) => {
                      const parts = dateParts(date);
                      return (
                        <button
                          key={date}
                          type="button"
                          className="date-tile"
                          onClick={() => handleSelectDate(date)}
                          aria-label={`Show events for ${parts.month} ${parts.day}`}
                        >
                          <span className="date-weekday">
                            {date === today ? 'Today' : parts.weekday}
                          </span>
                          <span className="date-day">{parts.day}</span>
                        </button>
                      );
                    })}
                </div>
              )}
            </div>

            <section className="time-panel" aria-label="Event time selector">
              <div className="time-header">
                <span className="time-label">
                  {selectedDate === today
                    ? 'HAPPENING AT'
                    : `${selectedDateInfo.weekday.toUpperCase()} ${selectedDateInfo.month.toUpperCase()} ${selectedDateInfo.day}`}
                </span>
                <span className="time-readout">{formatTimelineTime(selectedTime)}</span>
              </div>

              <div className="time-heat-strip" aria-hidden="true">
                {activityHeat.counts.map((count, idx) => {
                  const ratio = activityHeat.maxCount > 0 ? count / activityHeat.maxCount : 0;
                  const heightPct = count === 0 ? 12 : Math.round(24 + ratio * 76);
                  const binPct = ((idx + 0.5) / activityHeat.counts.length) * 100;
                  const isPassed = binPct <= progressPct + 1.5;
                  const barColor = isMiamiVice
                    ? synthwaveBarColor((idx + 0.5) / activityHeat.counts.length)
                    : undefined;
                  return (
                    <span
                      key={idx}
                      className={`time-heat-bar${isPassed ? ' passed' : ''}${count === 0 ? ' empty' : ''}`}
                      style={{
                        height: `${heightPct}%`,
                        ...(barColor ? { background: barColor } : {}),
                      }}
                    />
                  );
                })}
              </div>

              <div className="slider-wrap">
                <input
                  type="range"
                  className="time-range"
                  min={0}
                  max={totalSteps}
                  step={1}
                  value={currentStep}
                  aria-label="Scrub event time"
                  style={{
                    background: isVerbPoster
                      ? `linear-gradient(to right, #0D0D0D 0%, #0D0D0D ${progressPct}%, rgba(13, 13, 13, 0.2) ${progressPct}%, rgba(13, 13, 13, 0.2) 100%)`
                      : isStudioGallery
                        ? `linear-gradient(to right, #1a9196 0%, #1a9196 ${progressPct}%, rgba(86, 149, 179, 0.24) ${progressPct}%, rgba(86, 149, 179, 0.24) 100%)`
                        : isMiamiVice
                          ? `linear-gradient(to right, #FF3EA5 0%, #B64CFF ${Math.max(0, progressPct * 0.55)}%, #2FE6E6 ${progressPct}%, rgba(155, 110, 235, 0.26) ${progressPct}%, rgba(155, 110, 235, 0.26) 100%)`
                          : `linear-gradient(to right, ${accentColor} 0%, ${accentColor} ${progressPct}%, rgba(180, 170, 195, 0.28) ${progressPct}%, rgba(180, 170, 195, 0.28) 100%)`,
                  }}
                  onChange={(e) => {
                    const step = Number(e.target.value);
                    setSelectedTime(windowStart + step * QUARTER_MS);
                    setSelectedClusterKey(null);
                  }}
                />
              </div>

              <div className="time-endpoints">
                <span>{formatTimelineTime(windowStart)}</span>
                <span>{formatTimelineTime(scrubberWindow.midpoint)}</span>
                <span>{formatTimelineTime(windowEnd)}</span>
              </div>
            </section>
          </>
        )}

        {hotel && !pinDropActive && !showingEvents && !selectedPlace && !selectedCustomPin && (
          <div className="hotel-footer-hint">
            Curated by {hotel.name} · Tap any pin for details, or Drop Pin to save a spot
          </div>
        )}
      </div>

      {/* SHARE CUSTOM PINS / QR CODE MODAL (Concierge Desk mode only) */}
      {isDeskMode && shareModalOpen && hotel && (
        <SharePinsModal
          hotel={hotel}
          pins={customPins}
          isDeskMode={isDeskMode}
          onDeletePin={handleDeleteCustomPin}
          onClearAll={handleClearDeskPins}
          onClose={() => setShareModalOpen(false)}
        />
      )}

      {/* LOCATION PICKER MODAL (Happenin' standalone only; bypassed for all hotel concierges) */}
      {!hotel && !initialHotelParam && showRegionPicker && (
        <div
          className="region-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Pick location"
        >
          <div className="region-modal">
            <div className="region-modal-brand">
              HAPPENIN<span>&apos;</span>
            </div>
            <p className="region-modal-prompt">Pick a location</p>
            <div className="region-choice-grid">
              {(['boston', 'seacoast'] as RegionId[]).map((rid) => (
                <button
                  key={rid}
                  type="button"
                  className="region-choice-btn"
                  onClick={() => {
                    setRegion(rid);
                    setSelectedClusterKey(null);
                    setShowRegionPicker(false);
                  }}
                >
                  <span className="region-choice-name">{REGIONS[rid].label}</span>
                  {!loading && (
                    <span className="region-choice-count">{regionCounts[rid]} upcoming</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
