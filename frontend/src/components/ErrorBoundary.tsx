import React from 'react';

// Last line of defence: a plain message instead of a blank page. Shown before
// any translations load, so it carries all five UI languages.
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
        <p lang="es">Algo ha fallado. Recarga la página para reiniciar el partido.</p>
        <p lang="fr">Un problème est survenu. Actualisez la page pour relancer le match.</p>
        <p lang="ar" dir="rtl">حدث خطأ. أعد تحميل الصفحة لإعادة تشغيل المباراة.</p>
        <p lang="ja">問題が発生しました。ページを再読み込みすると試合が最初から始まります。</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-3 rounded-lg bg-pp-pulseFill px-4 py-2 font-bold text-white">
          Refresh
        </button>
      </div>
    );
  }
}
