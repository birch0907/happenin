import { useEffect, useMemo, useState } from 'react';
import {
  CATEGORIES,
  CATEGORY_COLORS,
  DATE_COUNT,
  EventCategory,
  HappeninEvent,
  QUARTER_MS,
  RawEvent,
  WINDOW_MS,
  addCalendarDays,
  currentQuarter,
  dateParts,
  easternToday,
  eventVisibleAtTime,
  formatTimelineTime,
  futureWindowStart,
  groupEventsByPin,
  normalizeEvents,
} from './data/events';
import { HotelConfig, HotelTab, eventAllowedForHotel, getHotelParam } from './data/hotels';
import { MapView } from './components/MapView';
import { EventCard } from './components/EventCard';
import { PlaceCard } from './components/PlaceCard';
import { DatabaseView } from './components/DatabaseView';

const HOTEL_TABS: HotelTab[] = ['Dining', 'Sights', 'Tonight'];

function isDatabaseMode(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get('view') === 'db';
}

export default function App() {
  if (isDatabaseMode()) {
    return <DatabaseView />;
  }
  return <MapApp />;
}

function MapApp() {
  const [hotel, setHotel] = useState<HotelConfig | null>(null);
  const [hotelTab, setHotelTab] = useState<HotelTab>('Tonight');
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);

  const [allEvents, setAllEvents] = useState<HappeninEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeCategories, setActiveCategories] = useState<EventCategory[]>([...CATEGORIES]);
  const [today, setToday] = useState(easternToday);
  const [selectedDate, setSelectedDate] = useState(easternToday);
  const [datesExpanded, setDatesExpanded] = useState(false);

  const [windowStart, setWindowStart] = useState(currentQuarter);
  const [selectedTime, setSelectedTime] = useState(currentQuarter);
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
        document.title = `${cfg.name} · ${cfg.subtitle}`;
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

  // Keep the rolling 24-hour window aligned with the current 15-minute quarter.
  useEffect(() => {
    const refresh = () => {
      const nextStart = currentQuarter();
      const newToday = easternToday();
      setToday(newToday);
      setSelectedDate((prevDate) => {
        if (prevDate < newToday) {
          setWindowStart(nextStart);
          setSelectedTime(nextStart);
          setDatesExpanded(false);
          return newToday;
        }
        if (prevDate === newToday) {
          setWindowStart((oldStart) => {
            if (oldStart === nextStart) return oldStart;
            setSelectedTime((prevSel) =>
              prevSel <= oldStart
                ? nextStart
                : Math.max(nextStart, Math.min(nextStart + WINDOW_MS, prevSel))
            );
            return nextStart;
          });
        }
        return prevDate;
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
  }, []);

  const showingEvents = !hotel || hotelTab === 'Tonight';

  const availableDates = useMemo(
    () => Array.from({ length: DATE_COUNT }, (_, idx) => addCalendarDays(today, idx)),
    [today]
  );

  const eligibleEvents = useMemo(
    () => (hotel ? allEvents.filter((ev) => eventAllowedForHotel(ev, hotel)) : allEvents),
    [allEvents, hotel]
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

  const selectedCluster = useMemo(
    () => (selectedClusterKey ? clusters.find((c) => c.key === selectedClusterKey) || null : null),
    [clusters, selectedClusterKey]
  );

  const selectedPlace = useMemo(
    () => (selectedPlaceId ? visiblePlaces.find((p) => p.id === selectedPlaceId) || null : null),
    [visiblePlaces, selectedPlaceId]
  );

  // When very few events are live at the selected time, find the nearest peak evening slot.
  const previewSuggestion = useMemo(() => {
    if (!showingEvents || loading || selectedCluster || visibleEvents.length > 3 || eligibleEvents.length === 0) {
      return null;
    }
    const matching = eligibleEvents.filter((ev) => activeCategories.includes(ev.category));
    if (matching.length === 0) return null;

    let bestTime = selectedTime;
    let bestCount = visibleEvents.length;
    const stepMs = 30 * 60 * 1000;
    for (let t = windowStart; t <= windowStart + WINDOW_MS; t += stepMs) {
      if (Math.abs(t - selectedTime) < stepMs) continue;
      let count = 0;
      for (const ev of matching) {
        if (eventVisibleAtTime(ev, t)) count++;
      }
      if (count > bestCount) {
        bestCount = count;
        bestTime = t;
      }
    }
    if (bestCount >= Math.max(2, visibleEvents.length + 2)) {
      const label =
        selectedDate === today
          ? `Preview ${formatTimelineTime(bestTime)}`
          : `Jump to ${formatTimelineTime(bestTime)}`;
      return { date: selectedDate, windowStart, time: bestTime, count: bestCount, label };
    }

    for (const date of availableDates.slice(1, 6)) {
      const start = futureWindowStart(date);
      const evening = start + 4 * 60 * 60 * 1000;
      let count = 0;
      for (const ev of matching) {
        if (eventVisibleAtTime(ev, evening)) count++;
      }
      if (count >= Math.max(2, visibleEvents.length + 2)) {
        const parts = dateParts(date);
        return {
          date,
          windowStart: start,
          time: evening,
          count,
          label: `Preview ${parts.weekday} 8:00 PM`,
        };
      }
    }
    return null;
  }, [
    showingEvents,
    loading,
    selectedCluster,
    visibleEvents.length,
    eligibleEvents,
    activeCategories,
    selectedTime,
    windowStart,
    selectedDate,
    today,
    availableDates,
  ]);

  function toggleCategory(cat: EventCategory) {
    setActiveCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
    setSelectedClusterKey(null);
  }

  function handleSelectDate(date: string) {
    const start = date === today ? currentQuarter() : futureWindowStart(date);
    setSelectedDate(date);
    setWindowStart(start);
    setSelectedTime(start);
    setDatesExpanded(false);
    setSelectedClusterKey(null);
  }

  function jumpToNow() {
    const now = currentQuarter();
    const t = easternToday();
    setToday(t);
    setSelectedDate(t);
    setWindowStart(now);
    setSelectedTime(now);
    setDatesExpanded(false);
    setSelectedClusterKey(null);
  }

  function switchHotelTab(tab: HotelTab) {
    setHotelTab(tab);
    setSelectedClusterKey(null);
    setSelectedPlaceId(null);
    setDatesExpanded(false);
  }

  const totalSteps = Math.round(WINDOW_MS / QUARTER_MS);
  const currentStep = Math.max(
    0,
    Math.min(totalSteps, Math.round((selectedTime - windowStart) / QUARTER_MS))
  );
  const progressPct = (currentStep / totalSteps) * 100;
  const isAtNow = selectedDate === today && Math.abs(selectedTime - currentQuarter()) < QUARTER_MS;
  const selectedDateInfo = dateParts(selectedDate);

  const isVerbPoster = hotel?.styleVariant === 'verb-poster';
  const isStudioGallery = hotel?.styleVariant === 'studio-gallery';
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
      className={`app-shell${hotel ? ' hotel-mode' : ''}${isVerbPoster ? ' variant-verb-poster' : ''}${isStudioGallery ? ' variant-studio-gallery' : ''}`}
      style={themeStyle}
    >
      <MapView
        clusters={clusters}
        selectedClusterKey={selectedCluster ? selectedCluster.key : null}
        onSelectCluster={(cluster) => {
          setSelectedPlaceId(null);
          setSelectedClusterKey(cluster.key);
        }}
        places={visiblePlaces}
        selectedPlaceId={selectedPlace ? selectedPlace.id : null}
        onSelectPlace={(place) => {
          setSelectedClusterKey(null);
          setSelectedPlaceId(place.id);
        }}
        hotel={hotel}
        onMapBackgroundClick={() => {
          setSelectedClusterKey(null);
          setSelectedPlaceId(null);
        }}
      />

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
                <>
                  <span className="brand-wordmark">
                    HAPPENIN<span>&apos;</span>
                  </span>
                  <span className="event-count">
                    {visibleEvents.length} {visibleEvents.length === 1 ? 'event' : 'events'}
                  </span>
                </>
              )}
            </div>
            {showingEvents && !isAtNow && (
              <button type="button" className="now-jump-btn" onClick={jumpToNow}>
                Back to Now
              </button>
            )}
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
                    {tab === 'Tonight' ? 'Tonight Live' : tab}
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

      {/* BOTTOM STACK: EVENT / PLACE CARD + PREVIEW PILL + DATE STRIP + TIME SLIDER */}
      <div className="bottom-overlay">
        {selectedCluster && (
          <EventCard
            cluster={selectedCluster}
            hotel={hotel}
            onClose={() => setSelectedClusterKey(null)}
          />
        )}

        {selectedPlace && hotel && (
          <PlaceCard
            place={selectedPlace}
            hotel={hotel}
            onClose={() => setSelectedPlaceId(null)}
          />
        )}

        {previewSuggestion && (
          <button
            type="button"
            className="preview-tonight-pill"
            onClick={() => {
              setSelectedDate(previewSuggestion.date);
              setWindowStart(previewSuggestion.windowStart);
              setSelectedTime(previewSuggestion.time);
              setDatesExpanded(false);
              setSelectedClusterKey(null);
            }}
          >
            <span className="preview-muted">Quiet right now</span>
            <span className="preview-dot">·</span>
            <span className="preview-cta">
              {previewSuggestion.label} ({previewSuggestion.count} events) →
            </span>
          </button>
        )}

        {showingEvents && (
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
                <span>{formatTimelineTime(windowStart + WINDOW_MS)}</span>
              </div>
            </section>
          </>
        )}

        {hotel && !showingEvents && !selectedPlace && (
          <div className="hotel-footer-hint">
            Curated by {hotel.name} · Tap any pin for menus, details & walking directions
          </div>
        )}
      </div>
    </main>
  );
}
