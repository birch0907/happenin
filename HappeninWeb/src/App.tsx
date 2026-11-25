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
import { HotelConfig, HotelTab, getHotelParam } from './data/hotels';
import { MapView } from './components/MapView';
import { EventCard } from './components/EventCard';
import { PlaceCard } from './components/PlaceCard';

const HOTEL_TABS: HotelTab[] = ['Tonight', 'Dining', 'Sights'];

export default function App() {
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

  const visibleEvents = useMemo(
    () =>
      showingEvents
        ? allEvents.filter(
            (ev) => activeCategories.includes(ev.category) && eventVisibleAtTime(ev, selectedTime)
          )
        : [],
    [showingEvents, allEvents, activeCategories, selectedTime]
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
    if (!showingEvents || loading || selectedCluster || visibleEvents.length > 3 || allEvents.length === 0) {
      return null;
    }
    const matching = allEvents.filter((ev) => activeCategories.includes(ev.category));
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
    allEvents,
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

  return (
    <main className={`app-shell${hotel ? ' hotel-mode' : ''}`} style={themeStyle}>
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
                  <span className="brand-wordmark hotel-wordmark">{hotel.wordmark}</span>
                  <span className="event-count">{hotel.subtitle}</span>
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
                    style={{ '--chip-color': CATEGORY_COLORS[category] } as React.CSSProperties}
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
                    background: `linear-gradient(to right, ${accentColor} 0%, ${accentColor} ${progressPct}%, rgba(180, 170, 195, 0.28) ${progressPct}%, rgba(180, 170, 195, 0.28) 100%)`,
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
