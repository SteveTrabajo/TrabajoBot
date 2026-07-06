export default function Loading() {
  return (
    <div className="mx-auto max-w-5xl animate-pulse space-y-6 px-4 py-12">
      <div className="h-9 w-56 rounded-md bg-white/10" />
      <div className="h-56 rounded-xl border border-white/10 bg-white/[0.03]" />
      <div className="h-72 rounded-xl border border-white/10 bg-white/[0.03]" />
      <div className="h-56 rounded-xl border border-white/10 bg-white/[0.03]" />
    </div>
  );
}
