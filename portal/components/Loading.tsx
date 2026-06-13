export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="text-[#8b95a1] text-sm py-8">{label}</div>;
}

export function ErrorState({ error }: { error: any }) {
  return (
    <div className="bg-[#161b22] border border-[#b91c1c] rounded-lg p-4 text-sm">
      <div className="font-semibold text-[#f87171]">Request failed</div>
      <div className="text-[#8b95a1] mt-1">{String(error?.message || error)}</div>
    </div>
  );
}
