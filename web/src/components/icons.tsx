// Small inline icons (24px grid, stroke = currentColor) and the app logo.
import type { SVGProps } from 'react'

function Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    />
  )
}

export const UploadIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M12 16V4M7 9l5-5 5 5" />
    <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </Icon>
)

export const FileIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
  </Icon>
)

export const TrashIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M4 7h16M10 11v6M14 11v6" />
    <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
  </Icon>
)

export const InfoIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </Icon>
)

export const ClockIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
)

export const BoltIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M13 3L5 14h6l-1 7 8-11h-6z" />
  </Icon>
)

export const MenuIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </Icon>
)

export const PlusIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
)

export const SearchIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </Icon>
)

export const SendIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M21 3L10 14" />
    <path d="M21 3l-7 18-4-7-7-4z" />
  </Icon>
)

export const StopIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
  </Icon>
)

export const LayersIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M12 3l9 5-9 5-9-5z" />
    <path d="M3 13l9 5 9-5" />
  </Icon>
)

export const CheckCircleIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12l3 3 5-6" />
  </Icon>
)

export const LoaderIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
  </Icon>
)

export const AlertIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M12 4l9 16H3z" />
    <path d="M12 10v4M12 17h.01" />
  </Icon>
)

export const ChatIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
  </Icon>
)

export const SparkIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
    <path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />
  </Icon>
)

/** Corner brackets around text lines: reading a scanned page. */
export const ScanIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" />
    <path d="M8 10h8M8 14h5" />
  </Icon>
)

/** Two stacked pages. */
export const PagesIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}>
    <rect x="8" y="3" width="12" height="15" rx="2" />
    <path d="M16 21H6a2 2 0 0 1-2-2V7" />
  </Icon>
)

/** Harf (حرف, "letter"): the letter noon ن, a bowl with a diamond nuqta, on an indigo tile. */
export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="Harf">
      <rect width="40" height="40" rx="11" fill="#4338ca" />
      <path d="M10.5 17.5C10.5 25 15 30 20 30s9.5-5 9.5-12.5" fill="none" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
      <path d="M20 10.5l3.2 3.2-3.2 3.2-3.2-3.2z" fill="#fff" />
    </svg>
  )
}
