import {
  HotelConfig,
  HotelPlace,
  PLACE_TAB_COLORS,
  formatWalkLabel,
  walkingDirectionsUrl,
} from '../data/hotels';

type PlaceCardProps = {
  place: HotelPlace;
  hotel: HotelConfig;
  onClose: () => void;
};

export function PlaceCard({ place, hotel, onClose }: PlaceCardProps) {
  const walkLabel = formatWalkLabel(hotel, place.latitude, place.longitude, place.onProperty);
  const badgeColor = PLACE_TAB_COLORS[place.tab];

  return (
    <section className="event-card" aria-label={place.name}>
      <div className="card-header">
        <div className="badge-row">
          <span className="category-badge" style={{ backgroundColor: badgeColor }}>
            {place.onProperty ? 'On Property' : place.tab}
          </span>
          <span className="walk-pill">{walkLabel}</span>
          {place.priceTier && <span className="tag-pill">{place.priceTier}</span>}
        </div>

        <button
          type="button"
          className="close-btn"
          onClick={onClose}
          aria-label="Close place details"
        >
          ✕
        </button>
      </div>

      <h2 className="event-title">{place.name}</h2>

      <div className="event-meta">
        <span className="event-venue">{place.tagline}</span>
        {place.address && <span className="event-time">{place.address}</span>}
      </div>

      <div className="card-body">
        <p className="event-description">{place.description}</p>
      </div>

      <div className="card-actions">
        {place.menuUrl && (
          <a
            href={place.menuUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary"
          >
            Menu ↗
          </a>
        )}
        {place.reserveUrl && (
          <a
            href={place.reserveUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={place.menuUrl ? 'btn-secondary' : 'btn-primary'}
          >
            Reserve ↗
          </a>
        )}
        {!place.menuUrl && !place.reserveUrl && place.websiteUrl && (
          <a
            href={place.websiteUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary"
          >
            Details ↗
          </a>
        )}
        <a
          href={walkingDirectionsUrl(hotel, place.latitude, place.longitude)}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary"
        >
          Directions
        </a>
      </div>
    </section>
  );
}
