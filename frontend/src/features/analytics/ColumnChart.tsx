import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface Column {
  key: string;
  label: string;
  value: number;
  display: string;
  detail?: string;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Column }[] }) {
  const column = payload?.[0]?.payload;
  if (!active || !column) return null;
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold text-ink">{column.display}</p>
      <p className="text-ink-muted">{column.label}</p>
      {column.detail && <p className="text-ink-muted">{column.detail}</p>}
    </div>
  );
}

const AXIS_TEXT = { fill: "var(--color-ink-subtle)", fontSize: 11 };

/** One series over time. Every value also appears in the table beneath it. */
export function ColumnChart({
  data,
  label,
  valueHeading,
}: {
  data: Column[];
  label: string;
  valueHeading: string;
}) {
  return (
    <div>
      <div role="img" aria-label={label} className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: -20 }}>
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis
              dataKey="label"
              tick={AXIS_TEXT}
              tickLine={false}
              axisLine={{ stroke: "var(--color-line)" }}
              interval="preserveStartEnd"
              minTickGap={18}
            />
            <YAxis tick={AXIS_TEXT} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--color-raised)", fillOpacity: 0.5 }} />
            <Bar dataKey="value" fill="var(--color-brand)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-xs text-ink-muted">
        <summary className="w-fit cursor-pointer hover:text-ink">View as table</summary>
        <table className="mt-2 w-full text-left">
          <caption className="sr-only">{label}</caption>
          <thead>
            <tr className="text-ink-subtle">
              <th scope="col" className="py-1 font-medium">
                Period
              </th>
              <th scope="col" className="py-1 font-medium">
                {valueHeading}
              </th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {data.map((column) => (
              <tr key={column.key} className="border-t border-line">
                <td className="py-1">{column.label}</td>
                <td className="py-1">
                  {column.display}
                  {column.detail ? `, ${column.detail}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
