// Placeholder das abas que ainda não têm backend. Diz o que vai aparecer ali
// em vez de deixar a aba parecer quebrada ou vazia por bug.

export default function ComingSoon({
  emoji,
  title,
  children,
}: {
  emoji: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel">
      <div className="empty">
        <div className="big">{emoji}</div>
        <div style={{ fontWeight: 700, color: "var(--text)", marginBottom: 6 }}>{title}</div>
        <div style={{ maxWidth: 460, margin: "0 auto", lineHeight: 1.6 }}>{children}</div>
      </div>
    </div>
  );
}
