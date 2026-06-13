export default function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
}) {
  return (
    <div className="bg-[#161b22] border border-[#232a33] rounded-lg p-4">
      <div className="text-[#8b95a1] text-xs uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-[#8b95a1] text-xs mt-1">{sub}</div>}
    </div>
  );
}
