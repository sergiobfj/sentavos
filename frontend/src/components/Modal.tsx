import { useEffect, useRef, type ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

export default function Modal({ title, onClose, children, footer }: ModalProps) {
  const dialog = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const viewport = window.visualViewport;
    const resize = () => {
      if (overlay.current && viewport) {
        overlay.current.style.height = `${viewport.height}px`;
        overlay.current.style.top = `${viewport.offsetTop}px`;
      }
      if (document.activeElement instanceof HTMLElement && dialog.current?.contains(document.activeElement))
        document.activeElement.scrollIntoView({block:"nearest"});
    };
    resize();
    viewport?.addEventListener("resize",resize);
    viewport?.addEventListener("scroll",resize);
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    if (dialog.current && !dialog.current.contains(document.activeElement)) dialog.current.querySelector<HTMLElement>("input,select,button,[tabindex]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      const current = dialog.current;
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (!current || dialogs[dialogs.length - 1] !== current) return;
      if (e.key === "Escape") closeRef.current();
      if (e.key !== "Tab") return;
      const focusable = [...current.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])')].filter(el=>el.getClientRects().length>0);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length-1];
      if (e.shiftKey && document.activeElement===first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement===last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      viewport?.removeEventListener("resize",resize);
      viewport?.removeEventListener("scroll",resize);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = oldOverflow;
      previous?.focus();
    };
  }, []);

  return (
    <div ref={overlay} className="overlay" onMouseDown={onClose}>
      <div ref={dialog} className="modal" onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="m-head">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Fechar">✕</button>
        </div>
        {children}
        {footer && <div className="m-foot">{footer}</div>}
      </div>
    </div>
  );
}
