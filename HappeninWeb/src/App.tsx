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
import { MapView } from './components/MapView';
import { EventCard } from './components/EventCard';

export default function App() {
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

  const availableDates = useMemo(
    () => Array.from({ length: DATE_COUNT }, (_, idx) => addCalendarDays(today, idx)),
    [today]
  );

  const visibleEvents = useMemo(
    () =>
      allEvents.filter(
        (ev) => activeCategories.includes(ev.category) && eventVisibleAtTime(ev, selectedTime)
      ),
    [allEvents, activeCategories, selectedTime]
  );

  const clusters = useMemo(() => groupEventsByPin(visibleEvents), [visibleEvents]);

  const selectedCluster = useMemo(
    () => (selectedClusterKey ? clusters.find((c) => c.key === selectedClusterKey) || null : null),
    [clusters, selectedClusterKey]
  );

  // When very few events are live at the selected time, find the nearest peak evening slot.
  const previewSuggestion = useMemo(() => {
    if (loading || selectedCluster || visibleEvents.length > 3 || allEvents.length === 0) {
      return null;
    }
    const matching = allEvents.filter((ev) => activeCategories.includes(ev.category));
    if (matching.length === 0) return null;

    // 1. Check later slots inside the current 24-hour window (30-min steps).
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

    // 2. Otherwise check 8:00 PM on the next few upcoming days.
    for (const date of availableDates.slice(1, 6)) {
      const start = futureWindowStart(date); // 4:00 PM Eastern
      const evening = start + 4 * 60 * 60 * 1000; // 8:00 PM Eastern
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

  const totalSteps = Math.round(WINDOW_MS / QUARTER_MS);
  const currentStep = Math.max(
    0,
    Math.min(totalSteps, Math.round((selectedTime - windowStart) / QUARTER_MS))
  );
  const progressPct = (currentStep / totalSteps) * 100;
  const isAtNow = selectedDate === today && Math.abs(selectedTime - currentQuarter()) < QUARTER_MS;

  const selectedDateInfo = dateParts(selectedDate);

  return (
    <main className="app-shell">
      <MapView
        clusters={clusters}
        selectedClusterKey={selectedCluster ? selectedCluster.key : null}
        onSelectCluster={(cluster) => setSelectedClusterKey(cluster.key)}
        onMapBackgroundClick={() => setSelectedClusterKey(null)}
      />

      {loading && <div className="status-banner">Loading what&apos;s happenin&apos;…</div>}
      {error && <div className="status-banner">{error}</div>}

      {/* TOP HEADER & CATEGORY FILTERS */}
      <header className="top-overlay">
        <div className="filter-panel">
          <div className="brand-row">
            <div className="brand-title">
              <span className="brand-wordmark">
                HAPPENIN<span>&apos;</span>
              </span>
              <span className="event-count">
                {visibleEvents.length} {visibleEvents.length === 1 ? 'event' : 'events'}
              </span>
            </div>
            {!isAtNow && (
              <button type="button" className="now-jump-btn" onClick={jumpToNow}>
                Back to Now
              </button>
            )}
          </div>

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
        </div>
      </header>

      {/* BOTTOM STACK: EVENT CARD + PREVIEW PILL + DATE STRIP + TIME SLIDER */}
      <div className="bottom-overlay">
        {selectedCluster && (
          <EventCard cluster={selectedCluster} onClose={() => setSelectedClusterKey(null)} />
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
              {selectedDate === today ? 'HAPPENING AT' : `${selectedDateInfo.weekday.toUpperCase()} ${selectedDateInfo.month.toUpperCase()} ${selectedDateInfo.day}`}
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
                background: `linear-gradient(to right, #2FE6E6 0%, #2FE6E6 ${progressPct}%, rgba(138, 114, 189, 0.35) ${progressPct}%, rgba(138, 114, 189, 0.35) 100%)`,
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
      </div>
    </main>
  );
}
