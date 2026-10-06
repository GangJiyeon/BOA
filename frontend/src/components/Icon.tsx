export type IconName = 'home' | 'skin' | 'hair' | 'results' | 'user' | 'kiosk' | 'sparkles' | 'upload' | 'camera' | 'arrow' | 'check' | 'close' | 'info'
const paths: Record<IconName, string> = {
  home: 'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
  skin: 'M12 3C9 7 5 11 5 15a7 7 0 0 0 14 0c0-4-4-8-7-12ZM8 15a4 4 0 0 0 4 4',
  hair: 'M7 13c-4-3-3-10 5-10s9 7 5 10M7 9v6a5 5 0 0 0 10 0V9M5 8c3 1 6-1 7-3 1 2 4 4 7 3M8 20l-3 1M16 20l3 1',
  results: 'M6 3h12v18H6ZM9 7h6M9 11h6M9 15h3',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  kiosk: 'M4 3h16v14H4ZM9 17v4m6-4v4M7 21h10M8 7h8M8 10h5',
  sparkles: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  camera: 'M8 5l2-2h4l2 2h5v15H3V5ZM16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  arrow: 'M4 12h16m-6-6 6 6-6 6', check: 'm5 12 4 4L19 6', close: 'm6 6 12 12M6 18 18 6',
  info: 'M12 11v6m0-10h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
}
export default function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
