import { useEffect, useMemo, useState } from 'react';
import {
  AREA_ORDER,
  DbEvent,
  DbPayload,
  DbVenue,
  VENUE_PRIORITIES,
  VENUE_STATUSES,
  VenuePriority,
  VenueStatus,
  categoryColor,
  eventDayKey,
  formatDayHeader,
  formatEventTime,
  formatMethod,
  formatRuleTime,
  formatShortDateTime,
  statusSlug,
} from '../data/database';

type DbMode = 'venues' | 'events' | 'attention' | 'concierges';
type VenueGroupBy = 'area' | 'status' | 'priority' | 'method' | 'neighborhood' | 'none';
type VenueSortBy = 'priority' | 'events' | 'name' | 'area' | 'status';
type EventGroupBy = 'day' | 'venue' | 'area' | 'category' | 'provenance' | 'none';

const PRIO_RANK: Record<string, number> = { A: 0, B: 1, C: 2, Unranked: 3 };
const STATUS_RANK: Record<string, number> = {
  'Live (First-Party)': 0,
  'Aggregator Only': 1,
  'Ready (0 Events)': 2,
  'Not Pulling': 3,
  'Paused / Closed': 4,
};

function admissionBadgeLabel(admissionType: string, price: string): { label: string; kind: string } | null {
  const p = price.trim();
  if (admissionType === 'free' || p.toLowerCase() === 'free') {
    return { label: 'Free', kind: 'free' };
  }
  if (admissionType === 'cover') {
    return { label: p ? `Cover · ${p}` : 'Cover', kind: 'cover' };
  }
  if (admissionType === 'ticketed') {
    return { label: p ? `Tickets · ${p}` : 'Tickets', kind: 'ticketed' };
  }
  if (p) {
    return { label: p, kind: 'ticketed' };
  }
  return null;
}

export function DatabaseView() {
  const [data, setData] = useState<DbPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<DbMode>('venues');
  const [search, setSearch] = useState('');
  const [regionFilter, setRegionFilter] = useState<'ALL' | 'boston' | 'seacoast'>('ALL');
  const [areaFilter, setAreaFilter] = useState<string>('ALL');

  // Venue filters & grouping
  const [statusFilter, setStatusFilter] = useState<VenueStatus | 'ALL'>('ALL');
  const [priorityFilter, setPriorityFilter] = useState<VenuePriority | 'ALL'>('ALL');
  const [methodFilter, setMethodFilter] = useState<string>('ALL');
  const [venueGroupBy, setVenueGroupBy] = useState<VenueGroupBy>('area');
  const [venueSortBy, setVenueSortBy] = useState<VenueSortBy>('priority');

  // Event filters & grouping
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [admissionFilter, setAdmissionFilter] = useState<string>('ALL');
  const [provenanceFilter, setProvenanceFilter] = useState<string>('ALL');
  const [ratingFilter, setRatingFilter] = useState<string>('ALL');
  const [dayFilter, setDayFilter] = useState<string>('ALL');
  const [eventGroupBy, setEventGroupBy] = useState<EventGroupBy>('day');

  // Collapsible groups & Inspector drawer
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [selectedVenueId, setSelectedVenueId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Happenin' · Venue & Event Database";
    let cancelled = false;
    fetch('./database.json')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((payload: DbPayload) => {
        if (!cancelled) {
          setData(payload);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(`Could not load database.json (${err.message}). Run build_database.py first.`);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Close drawer on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setSelectedVenueId(null);
        setSelectedEventId(null);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const venueMap = useMemo(() => {
    const map = new Map<string, DbVenue>();
    for (const v of data?.venues || []) map.set(v.id, v);
    return map;
  }, [data]);

  const eventsByVenueId = useMemo(() => {
    const map = new Map<string, DbEvent[]>();
    for (const ev of data?.events || []) {
      if (!ev.venueId) continue;
      const list = map.get(ev.venueId);
      if (list) list.push(ev);
      else map.set(ev.venueId, [ev]);
    }
    return map;
  }, [data]);

  const areaChips = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, number>();
    const list = mode === 'events' ? data.events : data.venues;
    for (const item of list) {
      if (regionFilter !== 'ALL' && (item.region || 'boston') !== regionFilter) continue;
      counts.set(item.area, (counts.get(item.area) || 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => {
      const ia = AREA_ORDER.indexOf(a[0]);
      const ib = AREA_ORDER.indexOf(b[0]);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return b[1] - a[1];
    });
  }, [data, mode, regionFilter]);

  const availableMethods = useMemo(() => {
    const set = new Set<string>();
    for (const v of data?.venues || []) {
      for (const m of v.collectorMethods) set.add(m);
    }
    return Array.from(set).sort((a, b) => (a === 'none' ? 1 : b === 'none' ? -1 : a.localeCompare(b)));
  }, [data]);

  const availableDays = useMemo(() => {
    const set = new Set<string>();
    for (const ev of data?.events || []) {
      const k = eventDayKey(ev.start);
      if (k !== 'TBD') set.add(k);
    }
    return Array.from(set).sort();
  }, [data]);

  // Filtered Venues (used by both 'venues' and 'attention' modes)
  const filteredVenues = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    const list = data.venues.filter((v) => {
      if (mode === 'attention') {
        const needsAttention =
          v.status === 'Ready (0 Events)' ||
          (v.priority === 'A' && (v.status === 'Not Pulling' || v.status === 'Aggregator Only'));
        if (!needsAttention) return false;
      }
      if (regionFilter !== 'ALL' && (v.region || 'boston') !== regionFilter) return false;
      if (areaFilter !== 'ALL' && v.area !== areaFilter) return false;
      if (statusFilter !== 'ALL' && v.status !== statusFilter) return false;
      if (priorityFilter !== 'ALL' && v.priority !== priorityFilter) return false;
      if (methodFilter !== 'ALL' && !v.collectorMethods.includes(methodFilter)) return false;
      if (q) {
        const hay = `${v.venue} ${v.area} ${v.neighborhood} ${v.vibe} ${v.notes} ${v.address} ${v.collectorMethods.join(' ')} ${v.url}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const sorted = [...list].sort((a, b) => {
      if (venueSortBy === 'events') return b.eventCount - a.eventCount || a.venue.localeCompare(b.venue);
      if (venueSortBy === 'name') return a.venue.localeCompare(b.venue);
      if (venueSortBy === 'area') return a.area.localeCompare(b.area) || PRIO_RANK[a.priority] - PRIO_RANK[b.priority] || a.venue.localeCompare(b.venue);
      if (venueSortBy === 'status') return STATUS_RANK[a.status] - STATUS_RANK[b.status] || PRIO_RANK[a.priority] - PRIO_RANK[b.priority] || b.eventCount - a.eventCount;
      // default 'priority'
      return PRIO_RANK[a.priority] - PRIO_RANK[b.priority] || b.eventCount - a.eventCount || a.venue.localeCompare(b.venue);
    });
    return sorted;
  }, [data, mode, search, regionFilter, areaFilter, statusFilter, priorityFilter, methodFilter, venueSortBy]);

  // Grouped Venues
  const groupedVenues = useMemo(() => {
    if (venueGroupBy === 'none') {
      return [{ key: 'all', label: 'All Matching Venues', items: filteredVenues }];
    }
    const map = new Map<string, DbVenue[]>();
    for (const v of filteredVenues) {
      let key = v.area;
      if (venueGroupBy === 'status') key = v.status;
      else if (venueGroupBy === 'priority') key = v.priority === 'Unranked' ? 'Unranked (Live Feed)' : `Priority ${v.priority}`;
      else if (venueGroupBy === 'method') key = formatMethod(v.primaryMethod);
      else if (venueGroupBy === 'neighborhood') key = `${v.area} · ${v.neighborhood}`;
      const arr = map.get(key);
      if (arr) arr.push(v);
      else map.set(key, [v]);
    }
    const groups = Array.from(map.entries()).map(([label, items]) => ({ key: label, label, items }));
    if (venueGroupBy === 'area') {
      groups.sort((a, b) => {
        const ia = AREA_ORDER.indexOf(a.label);
        const ib = AREA_ORDER.indexOf(b.label);
        if (ia !== -1 && ib !== -1) return ia - ib;
        if (ia !== -1) return -1;
        if (ib !== -1) return 1;
        return b.items.length - a.items.length;
      });
    } else if (venueGroupBy === 'status') {
      groups.sort((a, b) => (STATUS_RANK[a.label] ?? 9) - (STATUS_RANK[b.label] ?? 9));
    } else if (venueGroupBy === 'priority') {
      const order = ['Priority A', 'Priority B', 'Priority C', 'Unranked (Live Feed)'];
      groups.sort((a, b) => order.indexOf(a.label) - order.indexOf(b.label));
    } else {
      groups.sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label));
    }
    return groups;
  }, [filteredVenues, venueGroupBy]);

  // Filtered Events
  const filteredEvents = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return data.events.filter((ev) => {
      if (regionFilter !== 'ALL' && (ev.region || 'boston') !== regionFilter) return false;
      if (areaFilter !== 'ALL' && ev.area !== areaFilter) return false;
      if (categoryFilter !== 'ALL' && ev.category !== categoryFilter) return false;
      if (admissionFilter !== 'ALL') {
        if (admissionFilter === 'free' && ev.admissionType !== 'free') return false;
        if (admissionFilter === 'cover' && ev.admissionType !== 'cover') return false;
        if (admissionFilter === 'ticketed' && ev.admissionType !== 'ticketed') return false;
      }
      if (provenanceFilter !== 'ALL' && ev.provenance !== provenanceFilter) return false;
      if (ratingFilter !== 'ALL') {
        const rating = ev.contentRating || 'PG';
        if (ratingFilter === 'BLOCKED') {
          if (!ev.hotelBlocked && rating !== 'Explicit') return false;
        } else if (rating !== ratingFilter) {
          return false;
        }
      }
      if (dayFilter !== 'ALL' && eventDayKey(ev.start) !== dayFilter) return false;
      if (q) {
        const hay = `${ev.title} ${ev.venue} ${ev.area} ${ev.neighborhood} ${ev.summary} ${ev.safetyReason || ''} ${ev.tags.join(' ')} ${ev.sourceName}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [data, search, regionFilter, areaFilter, categoryFilter, admissionFilter, provenanceFilter, ratingFilter, dayFilter]);

  // Grouped Events
  const groupedEvents = useMemo(() => {
    if (eventGroupBy === 'none') {
      return [{ key: 'all', label: 'All Matching Events', items: filteredEvents }];
    }
    const map = new Map<string, DbEvent[]>();
    for (const ev of filteredEvents) {
      let key = eventDayKey(ev.start);
      if (eventGroupBy === 'venue') key = `${ev.venue} (${ev.area})`;
      else if (eventGroupBy === 'area') key = ev.area;
      else if (eventGroupBy === 'category') key = ev.category;
      else if (eventGroupBy === 'provenance') key = ev.provenance;
      const arr = map.get(key);
      if (arr) arr.push(ev);
      else map.set(key, [ev]);
    }
    const groups = Array.from(map.entries()).map(([k, items]) => ({
      key: k,
      label: eventGroupBy === 'day' ? formatDayHeader(k) : k,
      items,
    }));
    if (eventGroupBy === 'day') {
      groups.sort((a, b) => a.key.localeCompare(b.key));
    } else {
      groups.sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label));
    }
    return groups;
  }, [filteredEvents, eventGroupBy]);

  const selectedVenue = selectedVenueId ? venueMap.get(selectedVenueId) || null : null;
  const selectedVenueEvents = selectedVenue ? eventsByVenueId.get(selectedVenue.id) || [] : [];
  const selectedEvent = useMemo(
    () => (selectedEventId && data ? data.events.find((e) => e.id === selectedEventId) || null : null),
    [selectedEventId, data]
  );

  const hasActiveFilters =
    search.trim() !== '' ||
    regionFilter !== 'ALL' ||
    areaFilter !== 'ALL' ||
    statusFilter !== 'ALL' ||
    priorityFilter !== 'ALL' ||
    methodFilter !== 'ALL' ||
    categoryFilter !== 'ALL' ||
    admissionFilter !== 'ALL' ||
    provenanceFilter !== 'ALL' ||
    ratingFilter !== 'ALL' ||
    dayFilter !== 'ALL';

  function resetFilters() {
    setSearch('');
    setRegionFilter('ALL');
    setAreaFilter('ALL');
    setStatusFilter('ALL');
    setPriorityFilter('ALL');
    setMethodFilter('ALL');
    setCategoryFilter('ALL');
    setAdmissionFilter('ALL');
    setProvenanceFilter('ALL');
    setRatingFilter('ALL');
    setDayFilter('ALL');
  }

  function toggleGroup(groupKey: string) {
    setCollapsedGroups((prev) => ({ ...prev, [groupKey]: !prev[groupKey] }));
  }

  function jumpToKpiStatus(status: VenueStatus | 'ALL') {
    setMode('venues');
    setStatusFilter(status);
    setPriorityFilter('ALL');
    setMethodFilter('ALL');
  }

  return (
    <div className="db-shell">
      <div className="db-backdrop-glow" aria-hidden="true" />

      <div className="db-container">
        {/* TOP STUDIO HEADER */}
        <header className="db-header">
          <div className="db-brand-block">
            <div className="db-brand-row">
              <span className="brand-wordmark">
                HAPPENIN<span>&apos;</span>
              </span>
              <span className="db-studio-pill">DATABASE EXPLORER</span>
            </div>
            <p className="db-subtitle">
              Boston &amp; Seacoast NH venue registry, live 14-day events &amp; Digital Concierges
              {data ? ` · Updated ${formatShortDateTime(data.generatedAt)}` : ''}
            </p>
          </div>

          <div className="db-header-actions">
            <div className="db-mode-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'venues'}
                className={`db-mode-tab${mode === 'venues' ? ' active' : ''}`}
                onClick={() => {
                  setMode('venues');
                  setSelectedEventId(null);
                }}
              >
                Venues
                {data && <span className="db-tab-badge">{data.stats.totalVenues}</span>}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'events'}
                className={`db-mode-tab${mode === 'events' ? ' active' : ''}`}
                onClick={() => {
                  setMode('events');
                  setSelectedVenueId(null);
                }}
              >
                Live Events
                {data && <span className="db-tab-badge">{data.stats.totalEvents}</span>}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'attention'}
                className={`db-mode-tab attention${mode === 'attention' ? ' active' : ''}`}
                onClick={() => {
                  setMode('attention');
                  setStatusFilter('ALL');
                  setPriorityFilter('ALL');
                  setSelectedEventId(null);
                }}
              >
                Attention Queue
                {data && <span className="db-tab-badge">{data.stats.attentionCount}</span>}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'concierges'}
                className={`db-mode-tab${mode === 'concierges' ? ' active' : ''}`}
                onClick={() => {
                  setMode('concierges');
                  setSelectedVenueId(null);
                  setSelectedEventId(null);
                }}
              >
                Concierges
                {data && (
                  <span className="db-tab-badge">{data.concierges?.length ?? 0}</span>
                )}
              </button>
            </div>

            <a className="db-map-link" href="./" target="_blank" rel="noopener noreferrer">
              Open Map ↗
            </a>
          </div>
        </header>

        {loading && <div className="db-state-card">Loading database…</div>}
        {error && <div className="db-state-card error">{error}</div>}

        {data && (
          <>
            {/* INTERACTIVE KPI STRIP */}
            <section className="db-kpi-grid" aria-label="Database coverage overview">
              <button
                type="button"
                className={`db-kpi-card${mode === 'venues' && statusFilter === 'ALL' ? ' selected' : ''}`}
                onClick={() => jumpToKpiStatus('ALL')}
              >
                <span className="db-kpi-label">Master Venues</span>
                <strong className="db-kpi-value">{data.stats.totalVenues}</strong>
                <span className="db-kpi-sub">7 spreadsheets + live feeds</span>
              </button>

              <button
                type="button"
                className={`db-kpi-card accent-live${mode === 'venues' && statusFilter === 'Live (First-Party)' ? ' selected' : ''}`}
                onClick={() => jumpToKpiStatus('Live (First-Party)')}
              >
                <span className="db-kpi-label">Live First-Party</span>
                <strong className="db-kpi-value">{data.stats.statusCounts['Live (First-Party)'] || 0}</strong>
                <span className="db-kpi-sub">Direct API, scraper &amp; rules</span>
              </button>

              <button
                type="button"
                className={`db-kpi-card accent-agg${mode === 'venues' && statusFilter === 'Aggregator Only' ? ' selected' : ''}`}
                onClick={() => jumpToKpiStatus('Aggregator Only')}
              >
                <span className="db-kpi-label">Aggregator Only</span>
                <strong className="db-kpi-value">{data.stats.statusCounts['Aggregator Only'] || 0}</strong>
                <span className="db-kpi-sub">Ticketmaster &amp; POSH</span>
              </button>

              <button
                type="button"
                className={`db-kpi-card accent-ready${mode === 'venues' && statusFilter === 'Ready (0 Events)' ? ' selected' : ''}`}
                onClick={() => jumpToKpiStatus('Ready (0 Events)')}
              >
                <span className="db-kpi-label">Ready (0 Events)</span>
                <strong className="db-kpi-value">{data.stats.statusCounts['Ready (0 Events)'] || 0}</strong>
                <span className="db-kpi-sub">Wired, quiet this window</span>
              </button>

              <button
                type="button"
                className={`db-kpi-card accent-gap${mode === 'venues' && statusFilter === 'Not Pulling' ? ' selected' : ''}`}
                onClick={() => jumpToKpiStatus('Not Pulling')}
              >
                <span className="db-kpi-label">Not Pulling</span>
                <strong className="db-kpi-value">{data.stats.statusCounts['Not Pulling'] || 0}</strong>
                <span className="db-kpi-sub">To investigate / add</span>
              </button>

              <button
                type="button"
                className={`db-kpi-card accent-events${mode === 'events' ? ' selected' : ''}`}
                onClick={() => setMode('events')}
              >
                <span className="db-kpi-label">14-Day Events</span>
                <strong className="db-kpi-value">{data.stats.totalEvents}</strong>
                <span className="db-kpi-sub">Live on Happenin&apos; map</span>
              </button>
            </section>

            {/* STICKY SEARCH, FILTER & GROUP TOOLBAR (Venues / Events / Attention) */}
            {mode !== 'concierges' && (
            <section className="db-toolbar">
              <div className="db-toolbar-top">
                <div className="db-search-wrap">
                  <svg className="db-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
                    <path d="M20 20l-3.8-3.8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <input
                    type="text"
                    className="db-search-input"
                    placeholder={
                      mode === 'events'
                        ? 'Search events, artists, venues, tags, neighborhoods…'
                        : 'Search venues, neighborhoods, vibes, collectors, notes…'
                    }
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                  {search && (
                    <button type="button" className="db-search-clear" onClick={() => setSearch('')} aria-label="Clear search">
                      ✕
                    </button>
                  )}
                </div>

                {mode !== 'events' ? (
                  <div className="db-select-row">
                    <label className="db-select-field">
                      <span>Region</span>
                      <select
                        value={regionFilter}
                        onChange={(e) => {
                          setRegionFilter(e.target.value as 'ALL' | 'boston' | 'seacoast');
                          setAreaFilter('ALL');
                        }}
                      >
                        <option value="ALL">All Regions</option>
                        <option value="boston">Boston</option>
                        <option value="seacoast">Seacoast NH</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Status</span>
                      <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value as VenueStatus | 'ALL')}
                      >
                        <option value="ALL">All Statuses</option>
                        {VENUE_STATUSES.map((st) => (
                          <option key={st} value={st}>
                            {st}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Priority</span>
                      <select
                        value={priorityFilter}
                        onChange={(e) => setPriorityFilter(e.target.value as VenuePriority | 'ALL')}
                      >
                        <option value="ALL">All Priorities</option>
                        {VENUE_PRIORITIES.map((p) => (
                          <option key={p} value={p}>
                            {p === 'Unranked' ? 'Unranked (Live)' : `Priority ${p}`}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Collector</span>
                      <select value={methodFilter} onChange={(e) => setMethodFilter(e.target.value)}>
                        <option value="ALL">All Collectors</option>
                        {availableMethods.map((m) => (
                          <option key={m} value={m}>
                            {formatMethod(m)}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Group By</span>
                      <select
                        value={venueGroupBy}
                        onChange={(e) => {
                          setVenueGroupBy(e.target.value as VenueGroupBy);
                          setCollapsedGroups({});
                        }}
                      >
                        <option value="area">Area / Neighborhood</option>
                        <option value="status">Status</option>
                        <option value="priority">Priority</option>
                        <option value="method">Collector Method</option>
                        <option value="neighborhood">Sub-Neighborhood</option>
                        <option value="none">None (Flat List)</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Sort</span>
                      <select value={venueSortBy} onChange={(e) => setVenueSortBy(e.target.value as VenueSortBy)}>
                        <option value="priority">Priority &amp; Events</option>
                        <option value="events">Most Live Events</option>
                        <option value="name">Name (A–Z)</option>
                        <option value="area">Area</option>
                        <option value="status">Status</option>
                      </select>
                    </label>
                  </div>
                ) : (
                  <div className="db-select-row">
                    <label className="db-select-field">
                      <span>Region</span>
                      <select
                        value={regionFilter}
                        onChange={(e) => {
                          setRegionFilter(e.target.value as 'ALL' | 'boston' | 'seacoast');
                          setAreaFilter('ALL');
                        }}
                      >
                        <option value="ALL">All Regions</option>
                        <option value="boston">Boston</option>
                        <option value="seacoast">Seacoast NH</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Category</span>
                      <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                        <option value="ALL">All Categories</option>
                        <option value="Live Music">Live Music</option>
                        <option value="DJ">DJ</option>
                        <option value="Social">Social</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Admission</span>
                      <select value={admissionFilter} onChange={(e) => setAdmissionFilter(e.target.value)}>
                        <option value="ALL">Any Admission</option>
                        <option value="free">Free</option>
                        <option value="cover">Cover</option>
                        <option value="ticketed">Tickets</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Source</span>
                      <select value={provenanceFilter} onChange={(e) => setProvenanceFilter(e.target.value)}>
                        <option value="ALL">All Sources</option>
                        <option value="First-Party">First-Party Venue</option>
                        <option value="Ticketmaster">Ticketmaster</option>
                        <option value="POSH">POSH</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Rating</span>
                      <select value={ratingFilter} onChange={(e) => setRatingFilter(e.target.value)}>
                        <option value="ALL">All Ratings</option>
                        <option value="PG">PG (Charles &amp; All Hotels)</option>
                        <option value="R">R (Verb &amp; Happenin&apos;)</option>
                        <option value="Explicit">Explicit (Happenin&apos; Only)</option>
                        <option value="BLOCKED">All Hotel-Blocked</option>
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Day</span>
                      <select value={dayFilter} onChange={(e) => setDayFilter(e.target.value)}>
                        <option value="ALL">All 14 Days</option>
                        {availableDays.map((d) => (
                          <option key={d} value={d}>
                            {formatDayHeader(d)}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="db-select-field">
                      <span>Group By</span>
                      <select
                        value={eventGroupBy}
                        onChange={(e) => {
                          setEventGroupBy(e.target.value as EventGroupBy);
                          setCollapsedGroups({});
                        }}
                      >
                        <option value="day">Day</option>
                        <option value="venue">Venue</option>
                        <option value="area">Area / City</option>
                        <option value="category">Category</option>
                        <option value="provenance">Source Type</option>
                        <option value="none">None (Flat List)</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>

              {/* AREA FILTER PILLS */}
              <div className="db-area-bar">
                <button
                  type="button"
                  className={`db-area-pill${areaFilter === 'ALL' ? ' active' : ''}`}
                  onClick={() => setAreaFilter('ALL')}
                >
                  All Areas
                  <span className="db-pill-count">
                    {mode === 'events' ? data.stats.totalEvents : data.stats.totalVenues}
                  </span>
                </button>
                {areaChips.map(([area, count]) => (
                  <button
                    key={area}
                    type="button"
                    className={`db-area-pill${areaFilter === area ? ' active' : ''}`}
                    onClick={() => setAreaFilter(areaFilter === area ? 'ALL' : area)}
                  >
                    {area}
                    <span className="db-pill-count">{count}</span>
                  </button>
                ))}
              </div>

              <div className="db-toolbar-meta">
                <span>
                  Showing{' '}
                  <strong>
                    {mode === 'events' ? filteredEvents.length : filteredVenues.length}
                  </strong>{' '}
                  {mode === 'events' ? 'live events' : 'venues'}
                  {mode === 'attention' ? ' needing review (Priority A gaps & 0-event collectors)' : ''}
                </span>
                {hasActiveFilters && (
                  <button type="button" className="db-reset-btn" onClick={resetFilters}>
                    Reset Filters
                  </button>
                )}
              </div>
            </section>
            )}

            {/* MAIN CONTENT: CONCIERGES, VENUES / ATTENTION, OR EVENTS */}
            {mode === 'concierges' ? (
              <section className="db-concierge-section">
                <div className="db-quick-maps-bar">
                  <div className="db-quick-maps-label">Happenin&apos; Public Maps</div>
                  <div className="db-quick-maps-links">
                    <a className="db-launch-pill" href="./" target="_blank" rel="noopener noreferrer">
                      Location Picker ↗
                    </a>
                    <a className="db-launch-pill" href="./?region=boston" target="_blank" rel="noopener noreferrer">
                      Boston Map ↗
                    </a>
                    <a className="db-launch-pill" href="./?region=seacoast" target="_blank" rel="noopener noreferrer">
                      Seacoast NH Map ↗
                    </a>
                  </div>
                </div>

                <div className="db-concierge-grid">
                  {(data.concierges || []).map((h) => (
                    <article key={h.id} className="db-concierge-card">
                      <div
                        className="db-concierge-banner"
                        style={{
                          background: `linear-gradient(135deg, ${h.bg} 0%, ${h.accent}44 100%)`,
                          borderBottom: `2px solid ${h.accent}`,
                        }}
                      >
                        <div className="db-concierge-banner-top">
                          <span
                            className="db-concierge-swatch"
                            style={{ backgroundColor: h.accent }}
                            aria-hidden="true"
                          />
                          <span className="db-concierge-region">
                            {h.region === 'seacoast' ? 'Seacoast NH' : 'Boston'}
                          </span>
                          <span className={`db-rating-pill rating-${h.maxRating.toLowerCase()}`}>
                            {h.maxRating} Policy
                          </span>
                          <span className="db-concierge-style">
                            {h.mapStyle === 'light' ? 'Light Map' : 'Dark Map'}
                          </span>
                        </div>
                        <h3 className="db-concierge-name">{h.name}</h3>
                        <p className="db-concierge-addr">{h.address}</p>
                      </div>

                      <div className="db-concierge-body">
                        <div className="db-concierge-metrics">
                          <div className="db-concierge-metric">
                            <strong>{h.diningCount}</strong>
                            <span>Dining</span>
                          </div>
                          <div className="db-concierge-metric">
                            <strong>{h.sightsCount}</strong>
                            <span>Sights</span>
                          </div>
                          <div className="db-concierge-metric">
                            <strong>{h.eligibleEventCount}</strong>
                            <span>Live Events</span>
                          </div>
                        </div>

                        <div className="db-concierge-actions">
                          <a
                            className="db-concierge-btn primary"
                            href={`./?hotel=${encodeURIComponent(h.id)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Guest View ↗
                          </a>
                          <a
                            className="db-concierge-btn secondary"
                            href={`./?hotel=${encodeURIComponent(h.id)}&desk=1`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            ★ Concierge Desk ↗
                          </a>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : mode !== 'events' ? (
              <section className="db-groups">
                {groupedVenues.length === 0 || filteredVenues.length === 0 ? (
                  <div className="db-state-card">No venues match the current filters.</div>
                ) : (
                  groupedVenues.map((group) => {
                    const isCollapsed = !!collapsedGroups[group.key];
                    const liveInGroup = group.items.filter((v) => v.eventCount > 0).length;
                    const eventsInGroup = group.items.reduce((acc, v) => acc + v.eventCount, 0);
                    return (
                      <div key={group.key} className="db-group-card">
                        {venueGroupBy !== 'none' && (
                          <button
                            type="button"
                            className="db-group-header"
                            onClick={() => toggleGroup(group.key)}
                          >
                            <div className="db-group-title-wrap">
                              <span className={`db-chevron${isCollapsed ? ' collapsed' : ''}`}>▾</span>
                              <h2 className="db-group-title">{group.label}</h2>
                              <span className="db-group-count">{group.items.length} venues</span>
                            </div>
                            <div className="db-group-stats">
                              <span className="db-group-stat live">{liveInGroup} active</span>
                              <span className="db-group-stat events">{eventsInGroup} events</span>
                            </div>
                          </button>
                        )}

                        {!isCollapsed && (
                          <div className="db-table-wrap">
                            <table className="db-table">
                              <thead>
                                <tr>
                                  <th>Venue</th>
                                  <th>Area / Neighborhood</th>
                                  <th>Prio</th>
                                  <th>Status</th>
                                  <th>Collector</th>
                                  <th className="num">14d Events</th>
                                  <th>Vibe / Notes</th>
                                </tr>
                              </thead>
                              <tbody>
                                {group.items.map((v) => {
                                  const isSelected = selectedVenueId === v.id;
                                  return (
                                    <tr
                                      key={v.id}
                                      className={`db-row${isSelected ? ' selected' : ''}`}
                                      onClick={() => {
                                        setSelectedEventId(null);
                                        setSelectedVenueId(v.id);
                                      }}
                                    >
                                      <td className="db-cell-venue">
                                        <div className="db-venue-name">{v.venue}</div>
                                        {v.address && <div className="db-venue-addr">{v.address}</div>}
                                      </td>
                                      <td>
                                        <div className="db-cell-area">{v.area}</div>
                                        {v.neighborhood && v.neighborhood !== v.area && (
                                          <div className="db-cell-sub">{v.neighborhood}</div>
                                        )}
                                      </td>
                                      <td>
                                        <span className={`db-prio-badge prio-${v.priority.toLowerCase()}`}>
                                          {v.priority === 'Unranked' ? '—' : v.priority}
                                        </span>
                                      </td>
                                      <td>
                                        <span className={`db-status-pill st-${statusSlug(v.status)}`}>
                                          {v.status}
                                        </span>
                                      </td>
                                      <td>
                                        <div className="db-method-list">
                                          {v.collectorMethods.slice(0, 2).map((m) => (
                                            <span key={m} className={`db-method-chip method-${m}`}>
                                              {formatMethod(m)}
                                            </span>
                                          ))}
                                        </div>
                                      </td>
                                      <td className="num">
                                        <span className={`db-event-num${v.eventCount > 0 ? ' has-events' : ''}`}>
                                          {v.eventCount}
                                        </span>
                                      </td>
                                      <td className="db-cell-vibe">
                                        <span>{v.vibe || v.notes || '—'}</span>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </section>
            ) : (
              <section className="db-groups">
                {groupedEvents.length === 0 || filteredEvents.length === 0 ? (
                  <div className="db-state-card">No live events match the current filters.</div>
                ) : (
                  groupedEvents.map((group) => {
                    const isCollapsed = !!collapsedGroups[group.key];
                    return (
                      <div key={group.key} className="db-group-card">
                        {eventGroupBy !== 'none' && (
                          <button
                            type="button"
                            className="db-group-header"
                            onClick={() => toggleGroup(group.key)}
                          >
                            <div className="db-group-title-wrap">
                              <span className={`db-chevron${isCollapsed ? ' collapsed' : ''}`}>▾</span>
                              <h2 className="db-group-title">{group.label}</h2>
                              <span className="db-group-count">{group.items.length} events</span>
                            </div>
                          </button>
                        )}

                        {!isCollapsed && (
                          <div className="db-table-wrap">
                            <table className="db-table">
                              <thead>
                                <tr>
                                  <th>When</th>
                                  <th>Event</th>
                                  <th>Venue &amp; Area</th>
                                  <th>Category</th>
                                  <th>Rating</th>
                                  <th>Admission</th>
                                  <th>Source</th>
                                </tr>
                              </thead>
                              <tbody>
                                {group.items.map((ev) => {
                                  const adm = admissionBadgeLabel(ev.admissionType, ev.price);
                                  const isSelected = selectedEventId === ev.id;
                                  const rating = ev.contentRating || 'PG';
                                  return (
                                    <tr
                                      key={ev.id}
                                      className={`db-row${isSelected ? ' selected' : ''}`}
                                      onClick={() => {
                                        setSelectedVenueId(null);
                                        setSelectedEventId(ev.id);
                                      }}
                                    >
                                      <td className="db-cell-when">
                                        <div className="db-when-day">{formatDayHeader(eventDayKey(ev.start))}</div>
                                        <div className="db-when-time">{formatEventTime(ev.start, ev.end)}</div>
                                      </td>
                                      <td className="db-cell-event-title">
                                        <div className="db-venue-name">{ev.title}</div>
                                        {ev.tags.length > 0 && (
                                          <div className="db-mini-tags">
                                            {ev.tags.slice(0, 3).map((t) => (
                                              <span key={t} className="db-mini-tag">
                                                {t}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                      </td>
                                      <td>
                                        <div className="db-cell-area">{ev.venue}</div>
                                        <div className="db-cell-sub">{ev.area}</div>
                                      </td>
                                      <td>
                                        <span className="db-cat-pill">
                                          <span
                                            className="db-cat-dot"
                                            style={{ background: categoryColor(ev.category) }}
                                          />
                                          {ev.category}
                                        </span>
                                      </td>
                                      <td>
                                        <div className="db-rating-wrap">
                                          <span className={`db-rating-pill rating-${rating.toLowerCase()}`}>
                                            {rating}
                                          </span>
                                          {ev.hotelBlocked && rating !== 'Explicit' && (
                                            <span className="db-rating-pill rating-blocked">No Hotels</span>
                                          )}
                                        </div>
                                      </td>
                                      <td>
                                        {adm ? (
                                          <span className={`admission-pill admission-${adm.kind}`}>{adm.label}</span>
                                        ) : (
                                          <span className="db-cell-sub">—</span>
                                        )}
                                      </td>
                                      <td>
                                        <span className={`db-prov-chip prov-${ev.provenance.toLowerCase()}`}>
                                          {ev.provenance === 'First-Party' ? ev.sourceName : ev.provenance}
                                        </span>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </section>
            )}
          </>
        )}
      </div>

      {/* SLIDE-OVER INSPECTOR DRAWER: VENUE */}
      {selectedVenue && (
        <div
          className="db-drawer-backdrop"
          onClick={() => setSelectedVenueId(null)}
          role="dialog"
          aria-modal="true"
          aria-label={`Inspect ${selectedVenue.venue}`}
        >
          <aside className="db-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="db-drawer-header">
              <div>
                <div className="db-drawer-badges">
                  <span className={`db-prio-badge prio-${selectedVenue.priority.toLowerCase()}`}>
                    {selectedVenue.priority === 'Unranked' ? 'Live Discovery' : `Priority ${selectedVenue.priority}`}
                  </span>
                  <span className={`db-status-pill st-${statusSlug(selectedVenue.status)}`}>
                    {selectedVenue.status}
                  </span>
                </div>
                <h2 className="db-drawer-title">{selectedVenue.venue}</h2>
                <p className="db-drawer-loc">
                  {selectedVenue.area}
                  {selectedVenue.neighborhood && selectedVenue.neighborhood !== selectedVenue.area
                    ? ` · ${selectedVenue.neighborhood}`
                    : ''}
                </p>
              </div>
              <button
                type="button"
                className="close-btn"
                onClick={() => setSelectedVenueId(null)}
                aria-label="Close inspector"
              >
                ✕
              </button>
            </div>

            <div className="db-drawer-body">
              <div className="db-detail-grid">
                <div className="db-detail-box">
                  <span className="db-detail-label">Collector Method</span>
                  <div className="db-method-list">
                    {selectedVenue.collectorMethods.map((m) => (
                      <span key={m} className={`db-method-chip method-${m}`}>
                        {formatMethod(m)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="db-detail-box">
                  <span className="db-detail-label">14-Day Live Events</span>
                  <strong className="db-detail-big">{selectedVenue.eventCount}</strong>
                </div>
              </div>

              {selectedVenue.address && (
                <div className="db-section">
                  <span className="db-detail-label">Address &amp; Map Pin</span>
                  <p className="db-detail-text">
                    {selectedVenue.address}
                    {selectedVenue.latitude !== null && selectedVenue.longitude !== null && (
                      <span className="db-coords">
                        {' '}
                        ({selectedVenue.latitude.toFixed(5)}, {selectedVenue.longitude.toFixed(5)})
                      </span>
                    )}
                  </p>
                </div>
              )}

              {selectedVenue.vibe && (
                <div className="db-section">
                  <span className="db-detail-label">Target Vibe / Programming</span>
                  <p className="db-detail-text">{selectedVenue.vibe}</p>
                </div>
              )}

              {selectedVenue.notes && (
                <div className="db-section">
                  <span className="db-detail-label">Notes &amp; Status Context</span>
                  <p className="db-detail-text">{selectedVenue.notes}</p>
                </div>
              )}

              <div className="db-drawer-actions">
                {selectedVenue.url && (
                  <a className="btn-primary" href={selectedVenue.url} target="_blank" rel="noreferrer">
                    Open Venue Calendar ↗
                  </a>
                )}
                {selectedVenue.latitude !== null && selectedVenue.longitude !== null && (
                  <a
                    className="btn-secondary"
                    href={`https://www.google.com/maps/search/?api=1&query=${selectedVenue.latitude},${selectedVenue.longitude}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Google Maps
                  </a>
                )}
              </div>

              {selectedVenue.recurringRules.length > 0 && (
                <div className="db-section">
                  <span className="db-detail-label">
                    Configured Weekly Recurring Rules ({selectedVenue.recurringRules.length})
                  </span>
                  <div className="db-rule-list">
                    {selectedVenue.recurringRules.map((r, idx) => (
                      <div key={`${r.title}-${idx}`} className="db-rule-card">
                        <div className="db-rule-top">
                          <strong>{r.title}</strong>
                          <span className="db-rule-days">{r.weekdays.join(', ')}</span>
                        </div>
                        <div className="db-rule-time">
                          {formatRuleTime(r.start_time)}
                          {r.end_time ? ` – ${formatRuleTime(r.end_time)}` : ''}
                        </div>
                        {r.description && <p className="db-rule-desc">{r.description}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="db-section">
                <span className="db-detail-label">
                  Upcoming Live Events ({selectedVenueEvents.length})
                </span>
                {selectedVenueEvents.length === 0 ? (
                  <div className="db-empty-mini">
                    No upcoming events currently in the 14-day live feed.
                  </div>
                ) : (
                  <div className="db-event-cards">
                    {selectedVenueEvents.map((ev) => {
                      const adm = admissionBadgeLabel(ev.admissionType, ev.price);
                      return (
                        <button
                          key={ev.id}
                          type="button"
                          className="db-mini-event-card"
                          onClick={() => {
                            setSelectedVenueId(null);
                            setSelectedEventId(ev.id);
                          }}
                        >
                          <div className="db-mini-event-top">
                            <span className="db-cat-pill">
                              <span className="db-cat-dot" style={{ background: categoryColor(ev.category) }} />
                              {ev.category}
                            </span>
                            {adm && <span className={`admission-pill admission-${adm.kind}`}>{adm.label}</span>}
                          </div>
                          <div className="db-mini-event-title">{ev.title}</div>
                          <div className="db-mini-event-time">
                            {formatDayHeader(eventDayKey(ev.start))} · {formatEventTime(ev.start, ev.end)}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="db-drawer-foot">
                <span>Sources: {selectedVenue.sourceSheets.join(', ')}</span>
                <span className="db-v2-hint">Read-only Explorer · Inline editing ready for v2</span>
              </div>
            </div>
          </aside>
        </div>
      )}

      {/* SLIDE-OVER INSPECTOR DRAWER: EVENT */}
      {selectedEvent && (
        <div
          className="db-drawer-backdrop"
          onClick={() => setSelectedEventId(null)}
          role="dialog"
          aria-modal="true"
          aria-label={`Inspect ${selectedEvent.title}`}
        >
          <aside className="db-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="db-drawer-header">
              <div>
                <div className="db-drawer-badges">
                  <span
                    className="category-badge"
                    style={{ background: categoryColor(selectedEvent.category) }}
                  >
                    {selectedEvent.category}
                  </span>
                  {(() => {
                    const adm = admissionBadgeLabel(selectedEvent.admissionType, selectedEvent.price);
                    return adm ? <span className={`admission-pill admission-${adm.kind}`}>{adm.label}</span> : null;
                  })()}
                  <span className={`db-prov-chip prov-${selectedEvent.provenance.toLowerCase()}`}>
                    {selectedEvent.provenance}
                  </span>
                  <span
                    className={`db-rating-pill rating-${(selectedEvent.contentRating || 'PG').toLowerCase()}`}
                  >
                    {selectedEvent.contentRating || 'PG'}
                  </span>
                  {selectedEvent.hotelBlocked && selectedEvent.contentRating !== 'Explicit' && (
                    <span className="db-rating-pill rating-blocked">No Hotels</span>
                  )}
                </div>
                <h2 className="db-drawer-title">{selectedEvent.title}</h2>
                <p className="db-drawer-loc">
                  {selectedEvent.venue} · {selectedEvent.area}
                </p>
              </div>
              <button
                type="button"
                className="close-btn"
                onClick={() => setSelectedEventId(null)}
                aria-label="Close inspector"
              >
                ✕
              </button>
            </div>

            <div className="db-drawer-body">
              {selectedEvent.safetyReason && (
                <div className="db-section">
                  <span className="db-detail-label">Content Safety Note</span>
                  <p className="db-detail-text">{selectedEvent.safetyReason}</p>
                </div>
              )}

              <div className="db-section">
                <span className="db-detail-label">Date &amp; Time</span>
                <p className="db-detail-text highlight">
                  {formatDayHeader(eventDayKey(selectedEvent.start))} ·{' '}
                  {formatEventTime(selectedEvent.start, selectedEvent.end)}
                </p>
              </div>

              {selectedEvent.tags.length > 0 && (
                <div className="db-section">
                  <span className="db-detail-label">AI Vibe Tags</span>
                  <div className="tag-row">
                    {selectedEvent.tags.map((t) => (
                      <span key={t} className="tag-pill">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {selectedEvent.summary && (
                <div className="db-section">
                  <span className="db-detail-label">Summary</span>
                  <p className="db-detail-text">{selectedEvent.summary}</p>
                </div>
              )}

              {selectedEvent.description && selectedEvent.description !== selectedEvent.summary && (
                <div className="db-section">
                  <span className="db-detail-label">Raw Source Description</span>
                  <p className="db-detail-text muted">{selectedEvent.description}</p>
                </div>
              )}

              {selectedEvent.address && (
                <div className="db-section">
                  <span className="db-detail-label">Location</span>
                  <p className="db-detail-text">{selectedEvent.address}</p>
                </div>
              )}

              <div className="db-drawer-actions">
                {selectedEvent.venueId && venueMap.has(selectedEvent.venueId) && (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      const vid = selectedEvent.venueId;
                      setSelectedEventId(null);
                      setSelectedVenueId(vid);
                    }}
                  >
                    View Venue Profile →
                  </button>
                )}
                {selectedEvent.sourceUrl && (
                  <a className="btn-primary" href={selectedEvent.sourceUrl} target="_blank" rel="noreferrer">
                    Source / Tickets ↗
                  </a>
                )}
              </div>

              <div className="db-drawer-foot">
                <span>Source: {selectedEvent.sourceName}</span>
                <span>ID: {selectedEvent.id}</span>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
