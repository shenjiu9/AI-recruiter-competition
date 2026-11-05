import { useEffect, useRef } from 'react';
import type { Resume } from '@recruiter/domain';

/** 简历原文：R 编号在左侧；activeRefs 变化时滚动到第一段并用荧光笔高亮 */
export function ResumeViewer({ resume, activeRefs = [] }: { resume: Resume; activeRefs?: string[] }) {
  const container = useRef<HTMLDivElement>(null);
  const key = activeRefs.join(',');
  useEffect(() => {
    const first = activeRefs[0];
    if (!first) return;
    const el = container.current?.querySelector<HTMLElement>(`[data-ref="${first}"]`);
    el?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
    // key 已包含 activeRefs 的全部信息
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return (
    <div className="rc-resume" ref={container} aria-label={`简历原文：${resume.fileName}`}>
      {resume.paragraphs.map((p) => (
        <div key={p.ref} className={`rc-para${activeRefs.includes(p.ref) ? ' on' : ''}`} data-ref={p.ref}>
          <span className="r">{p.ref}</span>
          <span className="t">{p.text}</span>
        </div>
      ))}
    </div>
  );
}
