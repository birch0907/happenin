import { useId } from 'react';

type HappeninLogoProps = {
  size?: 'header' | 'modal';
  neon?: boolean;
};

export function HappeninLogo({ size = 'header', neon = true }: HappeninLogoProps) {
  const uid = useId().replace(/:/g, '');
  const gradId = `hap-grad-${uid}`;
  const sweepId = `hap-sweep-${uid}`;
  const glowId = `hap-glow-${uid}`;
  const isModal = size === 'modal';
  const iconSize = isModal ? 42 : 28;

  return (
    <span className={`hap-logo hap-logo-${size}${neon ? ' hap-logo-neon' : ''}`}>
      <svg
        className="hap-logo-pin"
        width={iconSize}
        height={iconSize}
        viewBox="0 0 48 48"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={gradId} x1="4" y1="24" x2="44" y2="24" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FF3EA5" />
            <stop offset="52%" stopColor="#B64CFF" />
            <stop offset="100%" stopColor="#2FE6E6" />
          </linearGradient>
          <linearGradient id={sweepId} x1="24" y1="6" x2="36" y2="18" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#2FE6E6" stopOpacity="0.48" />
            <stop offset="100%" stopColor="#2FE6E6" stopOpacity="0" />
          </linearGradient>
          <filter id={glowId} x="-25%" y="-25%" width="150%" height="150%">
            <feGaussianBlur stdDeviation="1.6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g filter={neon ? `url(#${glowId})` : undefined}>
          {/* Subtle upper-right radar sweep sector */}
          <path d="M24 19 L24 7.5 A11.5 11.5 0 0 1 35.5 19 Z" fill={`url(#${sweepId})`} />

          {/* Outer map-pin outline */}
          <path
            d="M24 44.5 C24 44.5 8 30.5 8 19 A16 16 0 1 1 40 19 C40 30.5 24 44.5 24 44.5 Z"
            stroke={`url(#${gradId})`}
            strokeWidth="2.3"
            strokeLinejoin="round"
          />

          {/* Outer concentric radar arcs */}
          <path
            d="M12.2 17 A12 12 0 0 1 22.2 7.2 M25.8 7.2 A12 12 0 0 1 35.8 17 M35.4 22.5 A12 12 0 0 1 24 31 A12 12 0 0 1 12.6 22.5"
            stroke={`url(#${gradId})`}
            strokeWidth="1.6"
            strokeLinecap="round"
            opacity="0.9"
          />

          {/* Inner concentric radar ring */}
          <circle
            cx="24"
            cy="19"
            r="7.6"
            stroke={`url(#${gradId})`}
            strokeWidth="1.5"
            opacity="0.88"
          />

          {/* Live soundwave / ECG pulse */}
          <path
            d="M3 19 H14.2 L16.8 14.5 L19.4 23.2 L22.2 10.5 L25.3 26.8 L28.2 14.2 L30.8 19 H45"
            stroke={`url(#${gradId})`}
            strokeWidth="2.1"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      </svg>

      <span className="hap-logo-wordmark">
        <span className="hap-word-left">HAPP</span>
        <span className="hap-word-right">ENIN</span>
        <svg
          className="hap-logo-apostrophe"
          width={isModal ? 14 : 10}
          height={isModal ? 18 : 13}
          viewBox="0 0 14 18"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M7.5 1.2 C4.2 3.2 2 5.9 2 8.9 C2 11.4 3.6 13.1 5.6 13.7 C5.3 15.1 4.4 16.3 3.4 17 C6.9 16.3 11.8 12.9 11.8 8.3 C11.8 5.2 9.8 2.8 7.5 1.2 Z"
            fill="#4CF6F6"
          />
          <circle cx="6.8" cy="8.2" r="2.1" fill="#0D0822" />
        </svg>
      </span>
    </span>
  );
}
