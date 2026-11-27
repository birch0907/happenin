import { useEffect, useState } from 'react';
import {
  PlaceSearchResult,
  searchNearbyPlaces,
} from '../data/customPins';
import { HotelConfig } from '../data/hotels';

export type DraftPinLocation = {
  latitude: number;
  longitude: number;
  suggestedName?: string;
  address?: string;
};

type PinDropSheetProps = {
  hotel: HotelConfig;
  isDeskMode: boolean;
  draftLocation: DraftPinLocation | null;
  onSelectSearchResult: (result: PlaceSearchResult) => void;
  onSavePin: (pin: { name: string; note: string; address?: string; latitude: number; longitude: number }) => void;
  onCancel: () => void;
};

export function PinDropSheet({
  hotel,
  isDeskMode,
  draftLocation,
  onSelectSearchResult,
  onSavePin,
  onCancel,
}: PinDropSheetProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlaceSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [address, setAddress] = useState('');

  // Sync suggested name/address when user taps the map or clicks a search result
  useEffect(() => {
    if (!draftLocation) return;
    if (draftLocation.suggestedName) {
      setName(draftLocation.suggestedName);
    }
    if (draftLocation.address) {
      setAddress(draftLocation.address);
    }
  }, [draftLocation]);

  // Debounced nearby place search via Photon (OpenStreetMap)
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchNearbyPlaces(q, hotel.latitude, hotel.longitude, controller.signal)
        .then((hits) => {
          setResults(hits);
          setSearching(false);
        })
        .catch(() => {
          setSearching(false);
        });
    }, 280);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, hotel.latitude, hotel.longitude]);

  const canSave = Boolean(draftLocation && name.trim().length > 0);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draftLocation || !name.trim()) return;
    onSavePin({
      name: name.trim(),
      note: note.trim(),
      address: address.trim() || undefined,
      latitude: draftLocation.latitude,
      longitude: draftLocation.longitude,
    });
  }

  return (
    <section className="event-card pin-drop-sheet" aria-label="Drop a custom pin">
      <div className="card-header">
        <div className="badge-row">
          <span className="category-badge custom-pin-badge">
            {isDeskMode ? '★ Concierge Pin Drop' : '★ Drop a Pin'}
          </span>
          <span className="pin-drop-hint-inline">
            {draftLocation ? 'Pin placed ✓' : 'Search or tap the map'}
          </span>
        </div>
        <button
          type="button"
          className="close-btn"
          onClick={onCancel}
          aria-label="Cancel pin drop"
        >
          ✕
        </button>
      </div>

      <div className="pin-search-box">
        <input
          type="search"
          className="pin-input"
          placeholder="Search a spot or address (e.g. ramen, vinyl shop)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {searching && <span className="pin-search-status">Searching…</span>}
        {results.length > 0 && (
          <ul className="pin-search-results" role="listbox" aria-label="Search suggestions">
            {results.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className="pin-search-item"
                  onClick={() => {
                    onSelectSearchResult(r);
                    setName(r.name);
                    setAddress(r.address);
                    setQuery('');
                    setResults([]);
                  }}
                >
                  <span className="pin-search-name">{r.name}</span>
                  {r.address && <span className="pin-search-addr">{r.address}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form className="pin-drop-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="pin-input"
          placeholder="Place name *"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          required
        />
        <textarea
          className="pin-textarea"
          rows={2}
          placeholder={
            isDeskMode
              ? 'Personal concierge note (e.g. "Ask for the corner booth — cash only!")'
              : 'Optional note (e.g. "Concierge recommended for late-night ramen")'
          }
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={220}
        />

        {!draftLocation && (
          <p className="pin-tap-prompt">
            Tap anywhere on the map above — or pick a search result — to place the pin.
          </p>
        )}

        <div className="card-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={!canSave}>
            {isDeskMode ? 'Add Concierge Pick' : 'Save Pin'}
          </button>
        </div>
      </form>
    </section>
  );
}
