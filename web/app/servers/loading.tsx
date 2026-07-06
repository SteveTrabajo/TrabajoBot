export default function Loading() {
  return (
    <div className="mx-auto max-w-5xl animate-pulse px-4 py-12">
      <div className="h-9 w-56 rounded-md bg-white/10" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-[72px] rounded-xl border border-white/10 bg-white/[0.03]" />
        ))}
      </div>
    </div>
  );
}
