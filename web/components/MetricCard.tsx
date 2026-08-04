import { changeLabel } from '@/lib/format';

/**
 * One headline figure with its change on the previous period.
 *
 * The change is monochrome on purpose. An arrow already says which way it
 * went, so colouring it too would just add noise to a page that is meant to
 * be quiet.
 */
export default function MetricCard({
  label,
  value,
  change,
  note,
  className = '',
}: {
  label: string;
  value: string;
  change?: number | null;
  note?: string;
  className?: string;
}) {
  const delta = change === undefined ? null : changeLabel(change);

  return (
    <div className={`rounded-card border border-line bg-surface p-5 ${className}`}>
      <p className="label">{label}</p>
      <p className="tnum mt-3 text-[26px] font-semibold leading-none tracking-tight text-ink sm:text-[30px]">
        {value}
      </p>
      <p className="mt-2 h-4 text-xs text-ink-muted">
        {delta && (
          <span className="tnum">
            {delta} <span className="text-ink-faint">vs previous</span>
          </span>
        )}
        {!delta && note && <span className="text-ink-faint">{note}</span>}
      </p>
    </div>
  );
}
