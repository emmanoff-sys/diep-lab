export default function Section({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-[#161b22] border border-[#232a33] rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {right}
      </div>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-xl font-semibold">{title}</h1>
      {subtitle && <div className="text-sm text-[#8b95a1] mt-0.5">{subtitle}</div>}
    </div>
  );
}
