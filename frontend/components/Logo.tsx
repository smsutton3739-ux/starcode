/**
 * The mark: a star over an open scroll — the two things the platform brings together.
 * Inline SVG so it needs no network request and inherits the current colour.
 */
export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      className={className}
      role="img"
      aria-label="Starcode"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="24" cy="24" r="23" className="fill-ink-950 dark:fill-ink-100" />
      <path
        d="M24 8l2.8 8.6h9l-7.3 5.3 2.8 8.6L24 25.2l-7.3 5.3 2.8-8.6-7.3-5.3h9L24 8z"
        className="fill-gold-500"
      />
      <path
        d="M12 34c4-1.6 8-2.4 12-2.4s8 .8 12 2.4v4c-4-1.6-8-2.4-12-2.4s-8 .8-12 2.4v-4z"
        className="fill-ink-100 dark:fill-ink-800"
      />
    </svg>
  );
}
