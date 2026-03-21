/**
 * Custom SVG icons for artifact types in the Scholar theme.
 * Designed to match Lucide's 24×24 viewBox and 1.5px stroke convention.
 */

import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

export function QuizIcon({ size = 24, className, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <circle cx="12" cy="11" r="3" />
      <path d="M12 14v1.5" />
      <circle cx="12" cy="17.5" r="0.5" fill="currentColor" stroke="none" />
      <path d="M8 3v2" />
      <path d="M16 3v2" />
    </svg>
  );
}

export function FlashcardsIcon({ size = 24, className, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <rect x="2" y="6" width="16" height="12" rx="2" />
      <path d="M6 6V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2" />
      <line x1="6" y1="10" x2="14" y2="10" />
      <line x1="6" y1="13" x2="11" y2="13" />
    </svg>
  );
}

export function SummaryIcon({ size = 24, className, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
      <line x1="8" y1="12" x2="16" y2="12" />
      <line x1="8" y1="15" x2="14" y2="15" />
      <line x1="8" y1="18" x2="12" y2="18" />
    </svg>
  );
}

export function NotesIcon({ size = 24, className, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <path d="M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z" />
      <path d="M15 3v4a1 1 0 0 0 1 1h4" />
      <path d="M7 12h5" />
      <path d="M7 15h8" />
      <path d="M7 18h3" />
    </svg>
  );
}

export function RevisionPlanIcon({ size = 24, className, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <path d="M4 4h16v16H4z" rx="2" />
      <path d="M4 9h16" />
      <path d="M9 4v16" />
      <circle cx="6.5" cy="6.5" r="0.5" fill="currentColor" stroke="none" />
      <path d="M12 13h5" />
      <path d="M12 16h3" />
    </svg>
  );
}
