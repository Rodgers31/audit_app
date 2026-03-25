export default function CountiesLoading() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-emerald-50/30 p-6 animate-pulse">
      {/* Header skeleton */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="h-8 w-56 bg-slate-200 rounded mb-3" />
        <div className="h-4 w-80 bg-slate-100 rounded" />
      </div>

      {/* Search and filter bar */}
      <div className="max-w-7xl mx-auto flex gap-3 mb-6">
        <div className="h-10 flex-1 max-w-md bg-slate-200 rounded-lg" />
        <div className="h-10 w-28 bg-slate-200 rounded-lg" />
        <div className="h-10 w-28 bg-slate-200 rounded-lg" />
      </div>

      {/* County cards grid */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-10 w-10 bg-slate-200 rounded-full" />
              <div>
                <div className="h-5 w-32 bg-slate-200 rounded mb-1" />
                <div className="h-3 w-20 bg-slate-100 rounded" />
              </div>
            </div>
            <div className="space-y-2">
              <div className="h-3 w-full bg-slate-100 rounded" />
              <div className="h-3 w-3/4 bg-slate-100 rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
