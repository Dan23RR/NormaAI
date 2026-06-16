'use client';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]" role="alert">
      <div className="bg-surface border border-red-500/20 rounded-xl p-8 max-w-lg text-center">
        <div className="text-red-400 text-4xl mb-4" aria-hidden="true">!</div>
        <h2 className="text-lg font-semibold text-text mb-2">Errore nel caricamento</h2>
        <p className="text-text-muted text-sm mb-6">
          {error.message || 'Si è verificato un errore imprevisto.'}
        </p>
        <button
          onClick={reset}
          className="px-6 py-2.5 bg-accent hover:bg-accent2 text-white rounded-lg text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg"
        >
          Riprova
        </button>
      </div>
    </div>
  );
}
