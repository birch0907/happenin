import { useEffect, useMemo, useState } from 'react';
import QRCode from 'qrcode';
import { CustomPin, buildGuestShareUrl } from '../data/customPins';
import { HotelConfig } from '../data/hotels';

type SharePinsModalProps = {
  hotel: HotelConfig;
  pins: CustomPin[];
  isDeskMode: boolean;
  onDeletePin: (id: string) => void;
  onClearAll: () => void;
  onClose: () => void;
};

export function SharePinsModal({
  hotel,
  pins,
  isDeskMode,
  onDeletePin,
  onClearAll,
  onClose,
}: SharePinsModalProps) {
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const shareUrl = useMemo(() => buildGuestShareUrl(hotel.id, pins), [hotel.id, pins]);

  useEffect(() => {
    if (pins.length === 0) {
      setQrDataUrl(null);
      return;
    }
    let cancelled = false;
    QRCode.toDataURL(shareUrl, {
      width: 240,
      margin: 2,
      color: {
        dark: '#111111',
        light: '#FFFFFF',
      },
      errorCorrectionLevel: 'M',
    })
      .then((dataUrl) => {
        if (!cancelled) setQrDataUrl(dataUrl);
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [shareUrl, pins.length]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback copy
      const input = document.createElement('input');
      input.value = shareUrl;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div
      className="share-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Share custom pins"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="share-modal">
        <div className="card-header">
          <div className="badge-row">
            <span className="category-badge custom-pin-badge">
              {isDeskMode ? '★ Share with Guest' : '★ Your Saved Pins'}
            </span>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close share dialog">
            ✕
          </button>
        </div>

        <h2 className="share-modal-title">
          {pins.length === 0
            ? 'No pins yet'
            : `${pins.length} Custom ${pins.length === 1 ? 'Pick' : 'Picks'} for ${hotel.name}`}
        </h2>

        {pins.length === 0 ? (
          <p className="share-modal-sub">
            Drop one or more pins on the map, then open this dialog to generate a scannable QR code and shareable link.
          </p>
        ) : (
          <>
            <p className="share-modal-sub">
              Scan this QR code with a guest&apos;s phone — or copy the link to text it — to open {hotel.name}&apos;s map with these pins highlighted.
            </p>

            {qrDataUrl && (
              <div className="share-qr-box">
                <img src={qrDataUrl} alt="QR code for custom concierge map" width={196} height={196} />
              </div>
            )}

            <ul className="share-pin-list">
              {pins.map((p) => (
                <li key={p.id} className="share-pin-row">
                  <div className="share-pin-info">
                    <span className="share-pin-name">★ {p.name}</span>
                    {p.note && <span className="share-pin-note">{p.note}</span>}
                  </div>
                  <button
                    type="button"
                    className="share-pin-remove"
                    onClick={() => onDeletePin(p.id)}
                    aria-label={`Remove ${p.name}`}
                    title="Remove pin"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>

            <div className="share-actions">
              <button type="button" className="btn-primary" onClick={handleCopy}>
                {copied ? 'Link Copied ✓' : 'Copy Guest Link'}
              </button>
              <a
                href={shareUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary"
              >
                Guest Preview ↗
              </a>
            </div>

            {isDeskMode && (
              <button type="button" className="share-clear-btn" onClick={onClearAll}>
                Clear all pins for next guest
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
