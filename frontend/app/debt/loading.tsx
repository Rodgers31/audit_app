export default function DebtLoading() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-emerald-50/30 p-6 animate-pulse">
      {/* Header skeleton */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="h-8 w-64 bg-slate-200 rounded mb-3" />
        <div className="h-4 w-96 bg-slate-100 rounded" />
      </div>

      {/* Stat cards row */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
            <div className="h-4 w-24 bg-slate-200 rounded mb-3" />
            <div className="h-7 w-36 bg-slate-200 rounded mb-2" />
            <div className="h-3 w-20 bg-slate-100 rounded" />
          </div>
        ))}
      </div>

      {/* Chart area */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-100 h-80" />
        <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-100 h-80" />
      </div>
    </div>
  );
}
