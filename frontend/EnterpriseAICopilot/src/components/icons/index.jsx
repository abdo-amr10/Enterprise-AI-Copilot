// Drawn to match lucide-react's icon spec (24x24, stroke=currentColor,
// strokeWidth 1.8, round caps/joins) so they're a drop-in visual match if
// this project adopts `lucide-react` later — just swap the import.
const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export function IconMail(props) {
  return (
    <svg {...base} {...props}>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 6-10 7L2 6" />
    </svg>
  );
}

export function IconLock(props) {
  return (
    <svg {...base} {...props}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

export function IconEye(props) {
  return (
    <svg {...base} {...props}>
      <path d="M1.5 12S5 5 12 5s10.5 7 10.5 7-3.5 7-10.5 7S1.5 12 1.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function IconEyeOff(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9.9 4.24A10.9 10.9 0 0 1 12 4c7 0 10.5 8 10.5 8a13.2 13.2 0 0 1-3.06 4.2M6.6 6.6A13.5 13.5 0 0 0 1.5 12s3.5 8 10.5 8a10.7 10.7 0 0 0 5.4-1.5" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <path d="M1 1l22 22" />
    </svg>
  );
}

export function IconAlertCircle(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12.5" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

export function IconLoader(props) {
  return (
    <svg {...base} {...props}>
      <line x1="12" y1="2" x2="12" y2="6" />
      <line x1="12" y1="18" x2="12" y2="22" />
      <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
      <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
      <line x1="2" y1="12" x2="6" y2="12" />
      <line x1="18" y1="12" x2="22" y2="12" />
      <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
      <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
    </svg>
  );
}

export function IconSparkles(props) {
  return <svg {...base} {...props}><path d="m12 3-1.25 4.75L6 9l4.75 1.25L12 15l1.25-4.75L18 9l-4.75-1.25L12 3Z" /><path d="m19 15-.7 2.3L16 18l2.3.7L19 21l.7-2.3L22 18l-2.3-.7L19 15Z" /><path d="m5 15-.7 2.3L2 18l2.3.7L5 21l.7-2.3L8 18l-2.3-.7L5 15Z" /></svg>;
}

export function IconHistory(props) {
  return <svg {...base} {...props}><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5" /><path d="M12 7v5l3 2" /></svg>;
}

export function IconDashboard(props) {
  return <svg {...base} {...props}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>;
}

export function IconLayers(props) {
  return <svg {...base} {...props}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5" /><path d="m3 16 9 5 9-5" /></svg>;
}

export function IconUsers(props) {
  return <svg {...base} {...props}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>;
}

export function IconShieldCheck(props) {
  return <svg {...base} {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m8.5 12 2.2 2.2 4.8-4.8" /></svg>;
}

export function IconUser(props) {
  return <svg {...base} {...props}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>;
}

export function IconCheck(props) {
  return <svg {...base} {...props}><path d="m5 12 4 4L19 6" /></svg>;
}

export function IconX(props) {
  return <svg {...base} {...props}><path d="m6 6 12 12M18 6 6 18" /></svg>;
}

export function IconSend(props) {
  return <svg {...base} {...props}><path d="m22 2-7 20-4-9-9-4 20-7Z" /><path d="M22 2 11 13" /></svg>;
}

export function IconClock(props) {
  return <svg {...base} {...props}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
}

export function IconArrowLeft(props) {
  return <svg {...base} {...props}><path d="M19 12H5M11 18l-6-6 6-6" /></svg>;
}

export function IconArrowRight(props) {
  return <svg {...base} {...props}><path d="M5 12h14m-6-6 6 6-6 6" /></svg>;
}

export function IconLogOut(props) {
  return <svg {...base} {...props}><path d="M10 17l5-5-5-5" /><path d="M15 12H3" /><path d="M21 19V5a2 2 0 0 0-2-2h-6" /></svg>;
}

export function IconFileText(props) {
  return <svg {...base} {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></svg>;
}

export function IconBookOpen(props) {
  return <svg {...base} {...props}><path d="M2 4.5A2.5 2.5 0 0 1 4.5 2H10v18H4.5A2.5 2.5 0 0 0 2 22V4.5ZM22 4.5A2.5 2.5 0 0 0 19.5 2H14v18h5.5A2.5 2.5 0 0 1 22 22V4.5Z" /></svg>;
}

export function IconTable(props) {
  return <svg {...base} {...props}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10M15 10v10" /></svg>;
}

export function IconDatabase(props) {
  return <svg {...base} {...props}><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12v7c0 1.66 3.58 3 8 3s8-1.34 8-3v-7" /></svg>;
}
export function IconDownload(props) {
  return <svg {...base} {...props}><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M4 21h16" /></svg>;
}

export function IconPrinter(props) {
  return <svg {...base} {...props}><path d="M6 9V3h12v6" /><rect x="4" y="9" width="16" height="8" rx="2" /><path d="M6 17v4h12v-4" /></svg>;
}

export function IconChevronDown(props) {
  return <svg {...base} {...props}><path d="m6 9 6 6 6-6" /></svg>;
}

export function IconSearch(props) {
  return <svg {...base} {...props}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>;
}

export function IconTrash(props) {
  return <svg {...base} {...props}><path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15M10 11v5M14 11v5" /></svg>;
}

export function IconExternalLink(props) {
  return <svg {...base} {...props}><path d="M14 3h7v7M21 3l-9 9" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>;
}
