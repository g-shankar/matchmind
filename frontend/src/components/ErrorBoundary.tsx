import React from 'react';

// Last line of defence: a plain message instead of a blank page. Shown before
// any translations load, so it carries all three UI languages.
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="flex min-h-screen flex-col items-center justify-center gap-2 bg-pp-night p-6 text-center text-slate-200">
        <p className="font-display text-xl">Something went wrong. Refresh the page to restart the match.</p>
        <p>Algo ha fallado. Recarga la página para reiniciar el partido.</p>
        <p dir="rtl">حدث خطأ. أعد تحميل الصفحة لإعادة تشغيل المباراة.</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-3 rounded-lg bg-pp-pulse px-4 py-2 font-bold text-white">
          Refresh
        </button>
      </div>
    );
  }
}
