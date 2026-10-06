import type { ReactNode } from 'react'
export default function PageIntro({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <header className="page-intro"><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{children}</p></header>
}
export function ProgressSteps({ labels, current }: { labels: string[]; current: number }) {
  return <ol className="flow-steps" aria-label="진행 순서">{labels.map((label, index) => <li key={label} className={index < current ? 'complete' : ''} aria-current={index === current ? 'step' : undefined}><span>{index < current ? '✓' : String(index + 1).padStart(2, '0')}</span>{label}</li>)}</ol>
}
