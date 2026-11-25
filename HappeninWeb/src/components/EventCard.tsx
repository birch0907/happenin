import { useState, useEffect } from 'react';
import {
  CATEGORY_COLORS,
  VenueCluster,
  directionsUrl,
  formatEventTime,
} from '../data/events';

type EventCardProps = {
  cluster: VenueCluster;
  onClose: () => void;
};

export function EventCard({ cluster, onClose }: EventCardProps) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    setActiveIndex(0);
  }, [cluster.key]);

  const event = cluster.events[activeIndex] || cluster.events[0];
  if (!event) return null;

  const badgeColor = CATEGORY_COLORS[event.category];

  return (
    <section className="event-card" aria-label={event.title}>
      {cluster.events.length > 1 && (
        <div className="venue-switcher" role="tablist" aria-label="Events at this venue">
          {cluster.events.map((item, idx) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={idx === activeIndex}
              className={`venue-tab${idx === activeIndex ? ' active' : ''}`}
              onClick={() => setActiveIndex(idx)}
            >
              {formatEventTime(item.start)} · {item.title.slice(0, 22)}
              {item.title.length > 22 ? '…' : ''}
            </button>
          ))}
        </div>
      )}

      <div className="card-header">
        <div className="badge-row">
          <span className="category-badge" style={{ backgroundColor: badgeColor }}>
            {event.category}
          </span>
          {event.admissionLabel && (
            <span className={`admission-pill admission-${event.admissionType || 'cover'}`}>
              {event.admissionLabel}
            </span>
          )}
          {event.tags.map((tag) => (
            <span key={tag} className="tag-pill">
              {tag}
            </span>
          ))}
        </div>

        <button
          type="button"
          className="close-btn"
          onClick={onClose}
          aria-label="Close event details"
        >
          ✕
        </button>
      </div>

      <h2 className="event-title">{event.title}</h2>

      <div className="event-meta">
        <span className="event-venue">
          {event.venue}
          {event.city ? ` · ${event.city}` : ''}
        </span>
        <span className="event-time">
          {formatEventTime(event.start)}
          {event.end ? ` – ${formatEventTime(event.end)}` : ''}
        </span>
      </div>

      {event.description && (
        <div className="card-body">
          <p className="event-description">{event.description}</p>
        </div>
      )}

      <div className="card-actions">
        {event.url && (
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary"
          >
            {event.admissionType === 'ticketed' ? 'Get Tickets ↗' : 'Event Info ↗'}
          </a>
        )}
        <a
          href={directionsUrl(event)}
          target="_blank"
          rel="noopener noreferrer"
          className={event.url ? 'btn-secondary' : 'btn-primary'}
        >
          Directions
        </a>
      </div>
    </section>
  );
}
