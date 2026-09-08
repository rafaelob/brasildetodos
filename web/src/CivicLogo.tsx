import type { JSX } from 'react';

export interface CivicLogoProps {
  size?: number;
  className?: string;
}

export const CIVIC_COLORS = {
  green: '#12644e',
  yellow: '#f2b705',
  blue: '#0b3b75',
  white: '#ffffff',
} as const;

export function CivicLogo({ size = 36, className = '' }: CivicLogoProps): JSX.Element {
  const classes = ['civic-logo', className].filter(Boolean).join(' ');

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Brasil de Todos"
      className={classes}
    >
      {/* Brazilian Civic Green Field */}
      <rect width="100" height="100" rx="20" fill="#12644e" />

      {/* Brazilian Warm Gold Rhombus / Lozenge */}
      <polygon points="50,14 86,50 50,86 14,50" fill="#f2b705" />

      {/* Brazilian Navy Celestial Sphere */}
      <circle cx="50" cy="50" r="21" fill="#0b3b75" />

      {/* White Citizen Arc — Symbol of Citizen Participation & Democracy */}
      <path
        d="M 32 55 C 42 46 58 46 68 55"
        stroke="#ffffff"
        strokeWidth="3.5"
        strokeLinecap="round"
        fill="none"
      />

      {/* Citizen Beacon / Star of Liberty */}
      <circle cx="50" cy="42" r="2.5" fill="#ffffff" />
    </svg>
  );
}

export default CivicLogo;
