export default function Loading() {
  return (
    <div className="mx-auto max-w-5xl animate-pulse px-4 py-12">
      <div className="h-9 w-64 rounded-md bg-white/10" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <div className="h-32 rounded-xl border border-white/10 bg-white/[0.03]" />
        <div className="h-32 rounded-xl border border-white/10 bg-white/[0.03]" />
        <div className="h-64 rounded-xl border border-white/10 bg-white/[0.03] sm:col-span-2" />
      </div>
    </div>
  );
}
