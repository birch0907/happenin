import { CustomPin } from '../data/customPins';
import { HotelConfig, formatWalkLabel, walkingDirectionsUrl } from '../data/hotels';

type CustomPinCardProps = {
  pin: CustomPin;
  hotel: HotelConfig;
  canDelete: boolean;
  onDelete: (id: string) => void;
  onShare?: () => void;
  onClose: () => void;
};

export function CustomPinCard({
  pin,
  hotel,
  canDelete,
  onDelete,
  onShare,
  onClose,
}: CustomPinCardProps) {
  const walkLabel = formatWalkLabel(hotel, pin.latitude, pin.longitude);
  const isConcierge = pin.origin === 'concierge';

  return (
    <section className="event-card custom-pin-card" aria-label={pin.name}>
      <div className="card-header">
        <div className="badge-row">
          <span className="category-badge custom-pin-badge">
            {isConcierge ? '★ Concierge Pick' : '★ Saved Pin'}
          </span>
          <span className="walk-pill">{walkLabel}</span>
        </div>

        <button
          type="button"
          className="close-btn"
          onClick={onClose}
          aria-label="Close pin details"
        >
          ✕
        </button>
      </div>

      <h2 className="event-title">{pin.name}</h2>

      {pin.address && (
        <div className="event-meta">
          <span className="event-time">{pin.address}</span>
        </div>
      )}

      {pin.note && (
        <div className="card-body">
          <p className="event-description custom-pin-note">
            {isConcierge ? `“${pin.note}”` : pin.note}
          </p>
        </div>
      )}

      <div className="card-actions">
        <a
          href={walkingDirectionsUrl(hotel, pin.latitude, pin.longitude)}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary"
        >
          Walking Directions ↗
        </a>
        {onShare && (
          <button type="button" className="btn-secondary" onClick={onShare}>
            Share / QR
          </button>
        )}
        {canDelete && (
          <button
            type="button"
            className="btn-secondary btn-pin-delete"
            onClick={() => onDelete(pin.id)}
            aria-label={`Remove ${pin.name}`}
            title="Remove pin"
          >
            Remove
          </button>
        )}
      </div>
    </section>
  );
}
