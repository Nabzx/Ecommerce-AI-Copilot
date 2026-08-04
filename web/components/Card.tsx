/** The box everything on the dashboard sits in. */
export default function Card({
  title,
  action,
  children,
  className = '',
}: {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-card border border-line bg-surface p-5 sm:p-6 ${className}`}
    >
      {title && (
        <header className="mb-5 flex items-center justify-between gap-3">
          <h2 className="label">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
