// Lucide-style 1.5px stroke line icons. Uses currentColor stroke.
// Paths are Lucide-compatible; names match the design spec (lbb-icons.jsx).

import React from 'react'

const PATHS: Record<string, string> = {
  // Nav
  home:        "M3 11l9-8 9 8M5 10v10h4v-6h6v6h4V10",
  pipeline:    "M3 7h6m6 0h6 M3 7l4-4 M3 7l4 4 M9 17h6m6 0h-6 M21 17l-4-4 M21 17l-4 4",
  verify:      "M12 3l8 3v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3z M9 12l2 2 4-4",
  lookup:      "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M21 21l-5-5",
  rename:      "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z M14.06 6.19l3.75 3.75",
  lbdir:       "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6z M14 3v6h6 M8 13h8 M8 17h8 M8 9h2",
  library:     "M4 19V5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-2zm0 0a2 2 0 0 1 2-2h12",
  collection:  "M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z",
  search:      "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M21 21l-5-5",
  bootlegs:    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M12 12h.01",
  attachments: "M21 12l-9 9a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.7 3.7 0 0 1 5.24 5.24L9.41 18.41a1.85 1.85 0 0 1-2.62-2.62l8.49-8.49",
  spectro:     "M3 12h2 M7 6v12 M11 9v6 M15 4v16 M19 8v8 M23 11v2",
  map:         "M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3V6z M9 3v15 M15 6v15",
  // Curator
  dbeditor:    "M4 7c0-2 4-3 8-3s8 1 8 3v10c0 2-4 3-8 3s-8-1-8-3V7z M4 7c0 2 4 3 8 3s8-1 8-3 M4 12c0 2 4 3 8 3s8-1 8-3",
  scraper:     "M12 3v12 M7 10l5 5 5-5 M3 20h18",
  // Settings
  setup:       "M12 3v3 M12 18v3 M5.6 5.6l2.1 2.1 M16.3 16.3l2.1 2.1 M3 12h3 M18 12h3 M5.6 18.4l2.1-2.1 M16.3 7.7l2.1-2.1 M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  mounts:      "M2 12h20 M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z M6 16h.01 M10 16h.01",
  themes:      "M12 22a10 10 0 1 1 0-20 6 6 0 0 1 0 12h-2.5a2 2 0 1 0 0 4c0 2.2 2 4 4.5 4z M7.5 12a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M12 7.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M16.5 12a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  // Actions
  star:        "M12 3l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 18l-5.9 3 1.2-6.5L2.5 9.9 9.1 9z",
  starFill:    "M12 3l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 18l-5.9 3 1.2-6.5L2.5 9.9 9.1 9z",
  plus:        "M12 5v14 M5 12h14",
  chevDown:    "M6 9l6 6 6-6",
  chevRight:   "M9 6l6 6-6 6",
  chevLeft:    "M15 6l-6 6 6 6",
  chevUp:      "M6 15l6-6 6 6",
  more:        "M5 12h.01 M12 12h.01 M19 12h.01",
  check:       "M5 12l5 5L20 7",
  x:           "M6 6l12 12 M18 6l-12 12",
  download:    "M12 3v13 M7 11l5 5 5-5 M5 21h14",
  upload:      "M12 21V8 M7 13l5-5 5 5 M5 3h14",
  folder:      "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z",
  folderPlus:  "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z M12 11v6 M9 14h6",
  drop:        "M12 3v14 M7 12l5 5 5-5 M4 21h16",
  play:        "M6 4l14 8-14 8V4z",
  pause:       "M6 4h4v16H6V4z M14 4h4v16h-4V4z",
  refresh:     "M21 12a9 9 0 1 1-3-6.7 M21 4v5h-5",
  filter:      "M3 5h18l-7 9v6l-4-2v-4L3 5z",
  bell:        "M6 9a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9z M10 21a2 2 0 0 0 4 0",
  cmd:         "M9 9V6a3 3 0 1 1 3 3H9zm0 0v6m0-6h6m-6 6H6a3 3 0 1 0 3 3v-3zm6-6v6m0-6h3a3 3 0 1 0-3-3v3zm0 6h3a3 3 0 1 1-3 3v-3z",
  reveal:      "M14 3h7v7 M21 3l-9 9 M10 7H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5",
  user:        "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21c0-4 4-7 8-7s8 3 8 7",
  shield:      "M12 3l8 3v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3z",
  alert:       "M12 3l10 17H2L12 3z M12 10v5 M12 18h.01",
  info:        "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 8h.01 M11 12h1v5h1",
  trash:       "M4 7h16 M9 7V4h6v3 M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13 M10 11v6 M14 11v6",
  copy:        "M9 9h10v10H9V9z M15 5H5v10",
  link:        "M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1 M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 1 0 5.66 5.66l1-1",
  globe:       "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M3 12h18 M12 3a13 13 0 0 1 0 18 M12 3a13 13 0 0 0 0 18",
  trading:     "M16 3l4 4-4 4 M20 7H4 M8 21l-4-4 4-4 M4 17h16",
  share:       "M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8 M16 6l-4-4-4 4 M12 2v13",
  tapematch:   "M3 9a2 2 0 0 1 2-2h2l2-4 4 8 2-4 2 4h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z",
  songs:       "M9 18V5l12-2v13 M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
}

export type IconName = keyof typeof PATHS

export interface IconProps {
  name: IconName | string
  size?: number
  stroke?: number
  fill?: string
  style?: React.CSSProperties
  className?: string
}

export function Icon({ name, size = 16, stroke = 1.5, fill, style, className }: IconProps): React.JSX.Element | null {
  const d = PATHS[name]
  if (!d) return null
  const filled = name.endsWith('Fill')
  // Split on " M" to support multi-path strings from the design spec
  const segments = d.split(' M')
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={filled ? 'currentColor' : (fill ?? 'none')}
      stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flex: '0 0 auto', verticalAlign: 'middle', ...style }}
      className={className}
    >
      {segments.map((seg, i) => (
        <path key={i} d={i === 0 ? seg : `M${seg}`} />
      ))}
    </svg>
  )
}
