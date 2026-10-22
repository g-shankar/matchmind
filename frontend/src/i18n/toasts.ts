// Error toasts in the viewer's own language. The match server sends each refusal with a
// stable `code` next to its English text (docs/API-CONTRACT.md, ERROR); the toast shows the
// text for that code in the viewer's content language, so a rate-limit message never
// appears in English on an Arabic or Japanese page. Kept in all five content languages,
// not only the three UI languages, because a toast speaks to the viewer about their match.

export const TOAST_LANGUAGES = ['en', 'es', 'fr', 'ar', 'ja'] as const;
export type ToastLanguage = (typeof TOAST_LANGUAGES)[number];

export const TOAST_CODES = [
  'jump_too_fast',
  'view_too_fast',
  'control_too_fast',
  'too_many_actions',
  'match_finished',
  'bad_speed',
  'bad_time',
  'no_such_half',
  'not_played_yet',
  'after_full_time',
  'unknown_club',
  'unknown_player',
  'loading',
  'oops',
  'load_failed',
  'other',
] as const;
export type ToastCode = (typeof TOAST_CODES)[number];

export const TOASTS: Record<ToastLanguage, Record<ToastCode, string>> = {
  en: {
    jump_too_fast: 'Jumping around too fast. Wait a moment and try again.',
    view_too_fast: 'Changing the view too fast. Wait a moment and try again.',
    control_too_fast: 'Playback was just changed. Wait a moment and try again.',
    too_many_actions: 'Too many taps at once. Wait a moment and try again.',
    match_finished: 'The match has finished. Restart or jump back to watch it again.',
    bad_speed: 'Pick a speed of 1x, 10x or 60x.',
    bad_time: 'Pick a time between kick-off and full time.',
    no_such_half: 'That half is not in this match.',
    not_played_yet: 'That part of the match has not been played yet.',
    after_full_time: 'That time is after full time.',
    unknown_club: 'That club is not in this match.',
    unknown_player: 'That player is not in this match.',
    loading: 'The match is still loading. Try again in a moment.',
    oops: 'Something went wrong on our side. Please try again.',
    load_failed: 'The match could not be loaded. Refresh to try again.',
    other: 'That did not work. Try again.',
  },
  es: {
    jump_too_fast: 'Estás saltando demasiado rápido. Espera un momento y vuelve a intentarlo.',
    view_too_fast: 'Estás cambiando la vista demasiado rápido. Espera un momento y vuelve a intentarlo.',
    control_too_fast: 'La reproducción acaba de cambiar. Espera un momento y vuelve a intentarlo.',
    too_many_actions: 'Demasiados toques a la vez. Espera un momento y vuelve a intentarlo.',
    match_finished: 'El partido ha terminado. Reinícialo o vuelve atrás para verlo otra vez.',
    bad_speed: 'Elige una velocidad de 1x, 10x o 60x.',
    bad_time: 'Elige un momento entre el saque inicial y el final.',
    no_such_half: 'Esa parte no existe en este partido.',
    not_played_yet: 'Esa parte del partido todavía no se ha jugado.',
    after_full_time: 'Ese momento es posterior al final del partido.',
    unknown_club: 'Ese club no juega este partido.',
    unknown_player: 'Ese jugador no está en este partido.',
    loading: 'El partido todavía se está cargando. Inténtalo de nuevo en un momento.',
    oops: 'Algo ha fallado por nuestra parte. Inténtalo de nuevo.',
    load_failed: 'No se pudo cargar el partido. Recarga la página para intentarlo de nuevo.',
    other: 'No ha funcionado. Inténtalo de nuevo.',
  },
  fr: {
    jump_too_fast: 'Vous sautez trop vite. Attendez un instant et réessayez.',
    view_too_fast: 'Vous changez de vue trop vite. Attendez un instant et réessayez.',
    control_too_fast: 'La lecture vient d’être modifiée. Attendez un instant et réessayez.',
    too_many_actions: 'Trop d’actions à la fois. Attendez un instant et réessayez.',
    match_finished: 'Le match est terminé. Relancez-le ou revenez en arrière pour le revoir.',
    bad_speed: 'Choisissez une vitesse de 1x, 10x ou 60x.',
    bad_time: 'Choisissez un moment entre le coup d’envoi et la fin du match.',
    no_such_half: 'Cette période n’existe pas dans ce match.',
    not_played_yet: 'Cette partie du match n’a pas encore été jouée.',
    after_full_time: 'Ce moment est après la fin du match.',
    unknown_club: 'Ce club ne joue pas ce match.',
    unknown_player: 'Ce joueur n’est pas dans ce match.',
    loading: 'Le match est encore en chargement. Réessayez dans un instant.',
    oops: 'Un problème est survenu de notre côté. Veuillez réessayer.',
    load_failed: 'Le match n’a pas pu être chargé. Actualisez la page pour réessayer.',
    other: 'Cela n’a pas fonctionné. Réessayez.',
  },
  ar: {
    jump_too_fast: 'أنت تنتقل بسرعة كبيرة. انتظر لحظة ثم حاول مرة أخرى.',
    view_too_fast: 'أنت تغيّر العرض بسرعة كبيرة. انتظر لحظة ثم حاول مرة أخرى.',
    control_too_fast: 'تم تغيير التشغيل للتو. انتظر لحظة ثم حاول مرة أخرى.',
    too_many_actions: 'نقرات كثيرة في وقت واحد. انتظر لحظة ثم حاول مرة أخرى.',
    match_finished: 'انتهت المباراة. أعد تشغيلها أو ارجع إلى لحظة سابقة لمشاهدتها مجددًا.',
    bad_speed: 'اختر سرعة 1x أو 10x أو 60x.',
    bad_time: 'اختر وقتًا بين صافرة البداية ونهاية المباراة.',
    no_such_half: 'هذا الشوط غير موجود في هذه المباراة.',
    not_played_yet: 'هذا الجزء من المباراة لم يُلعب بعد.',
    after_full_time: 'هذا الوقت بعد نهاية المباراة.',
    unknown_club: 'هذا النادي لا يلعب في هذه المباراة.',
    unknown_player: 'هذا اللاعب ليس في هذه المباراة.',
    loading: 'ما زالت المباراة قيد التحميل. حاول مرة أخرى بعد لحظة.',
    oops: 'حدث خطأ من جهتنا. يرجى المحاولة مرة أخرى.',
    load_failed: 'تعذّر تحميل المباراة. حدّث الصفحة للمحاولة مرة أخرى.',
    other: 'لم ينجح ذلك. حاول مرة أخرى.',
  },
  ja: {
    jump_too_fast: '移動が速すぎます。少し待ってからもう一度お試しください。',
    view_too_fast: '表示の切り替えが速すぎます。少し待ってからもう一度お試しください。',
    control_too_fast: '再生が変更されたばかりです。少し待ってからもう一度お試しください。',
    too_many_actions: '操作が多すぎます。少し待ってからもう一度お試しください。',
    match_finished: '試合は終了しました。最初から再生するか、前の場面に戻ってご覧ください。',
    bad_speed: '速度は 1x、10x、60x から選んでください。',
    bad_time: 'キックオフから試合終了までの時間を選んでください。',
    no_such_half: 'その前後半はこの試合にありません。',
    not_played_yet: 'その場面はまだ行われていません。',
    after_full_time: 'その時間は試合終了後です。',
    unknown_club: 'そのクラブはこの試合に出ていません。',
    unknown_player: 'その選手はこの試合に出ていません。',
    loading: '試合を読み込み中です。少し待ってからもう一度お試しください。',
    oops: 'こちら側で問題が発生しました。もう一度お試しください。',
    load_failed: '試合を読み込めませんでした。ページを再読み込みしてください。',
    other: 'うまくいきませんでした。もう一度お試しください。',
  },
};

const isToastLanguage = (lang: string): lang is ToastLanguage => (TOAST_LANGUAGES as readonly string[]).includes(lang);
const isToastCode = (code: string): code is ToastCode => (TOAST_CODES as readonly string[]).includes(code);

// The English texts the server (and the offline demo) sends, for frames without a code.
const BY_ENGLISH = new Map<string, ToastCode>(
  Object.entries(TOASTS.en).map(([code, text]) => [text, code as ToastCode]),
);
BY_ENGLISH.set('Too many actions at once. Wait a moment and try again.', 'too_many_actions');
BY_ENGLISH.set('The match has finished. Reset or jump back to watch it again.', 'match_finished');
BY_ENGLISH.set('Speed must be 1, 10 or 60.', 'bad_speed');

/** The toast for an error, in the viewer's language. English pages keep the server's own
 * words for anything without a code; other languages get a translated general message
 * rather than English text. */
export function toastText(message: string, code: string | null | undefined, language: string): string {
  const lang: ToastLanguage = isToastLanguage(language) ? language : 'en';
  const known = code && isToastCode(code) && code !== 'other' ? code : BY_ENGLISH.get(message);
  if (known) return TOASTS[lang][known];
  return lang === 'en' ? message : TOASTS[lang].other;
}
