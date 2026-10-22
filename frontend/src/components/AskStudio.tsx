// Ask the studio (docs/ASK.md): one short question, or a suggested chip, answered
// by the server from the stats engine as of the match clock. The answer is
// plain text from a template; the numbers behind it are shown as evidence and
// each cited moment opens its claim audit ("how we know", components/ClaimAudit).
import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, MessageCircleQuestion, Play, Search, Volume2 } from 'lucide-react';
import { ASK_CHIPS, ASK_MAX_CHARS, type AskAnswer, type AskChip, type AskFailure, type Bookmark } from '../api/contract';
import { compareMoments } from './MomentsList';
import { useI18n } from '../i18n';
import { useReadAloud } from '../lib/speech';
import type { MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { factValue } from '../lib/facts';
import { LazyAuditDrawer as AuditDrawer } from './ShowWorking';
import { Badge, Panel, cx } from './ui';

const MAX_LINKS = 3;

const isSpecialBookmark = (match: MatchViewState, id: string) => {
  const kind = match.bookmarks.find((b) => b.moment_id === id)?.kind;
  return kind === 'better_option' || kind === 'unfound_run';
};

type Result = { answer: AskAnswer } | { failure: AskFailure };

// A long paste is kept (up to this cap) so the counter shows its real length and the box
// says it is too long, instead of cutting it silently; only questions within ASK_MAX_CHARS
// are sent. A paste past the cap is cut, and the counter says so ("10000+").
export const TYPED_CAP = 10_000;

/** The first "should he have passed?" moment still to come after `asOf`, from the public
 * jump list (special moments are listed spoiler-free before they happen). */
export function nextBetterOption(bookmarks: Bookmark[], asOf: { clock_s: number; period: number }): Bookmark | null {
  const later = bookmarks.filter((b) => b.kind === 'better_option' && compareMoments(b, asOf) > 0).sort(compareMoments);
  return later[0] ?? null;
}

export const AskStudio: React.FC<{
  match: MatchViewState;
  actions: MatchActions;
  compact?: boolean;
  /** Opens the replay of a "should he have passed?" or unfound-run moment the answer cites. */
  onOpenReplay?: (momentId: string) => void;
  /** Jumps the match to a moment from the jump list (the first "should he have passed?"). */
  onJump?: (b: Bookmark) => void;
}> = ({ match, actions, compact, onOpenReplay, onJump }) => {
  const i18n = useI18n();
  const { t } = i18n;
  const [text, setText] = useState('');
  const [clipped, setClipped] = useState(false);
  const [pending, setPending] = useState<AskChip | 'text' | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [hint, setHint] = useState<'empty' | null>(null);
  const [auditId, setAuditId] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const speech = useReadAloud();
  const seq = useRef(0);
  const inputId = useRef(`ask-${Math.random().toString(36).slice(2, 8)}`).current;
  const chips = ASK_CHIPS.filter((c) => match.profile.spoilers || c !== 'score');
  const tooLong = text.trim().length > ASK_MAX_CHARS;

  const run = async (input: { question: string } | { chip: AskChip }, kind: AskChip | 'text') => {
    const mine = ++seq.current;
    setPending(kind);
    const res = await actions.ask(input);
    if (mine !== seq.current) return; // a newer question replaced this one
    setPending(null);
    setResult(res.ok ? { answer: res.answer } : { failure: res.failure });
    if (res.ok) speech.speak(res.answer.answer, res.answer.text_language);
    // "Should he have passed?" is best answered by the replay itself: open it straight away.
    if (res.ok && kind === 'better_option' && onOpenReplay) {
      const special = res.answer.moment_ids.slice().reverse().find((id) => isSpecialBookmark(match, id));
      if (special) onOpenReplay(special);
    }
  };

  // A language or catch-up switch makes the answer on screen stale: clear it.
  useEffect(() => {
    seq.current += 1;
    setPending(null);
    setResult(null);
  }, [match.profile.language, match.profile.spoilers]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (pending) return;
    if (!q) {
      setHint('empty');
      return;
    }
    if (q.length > ASK_MAX_CHARS) return; // the counter already says it is too long
    setHint(null);
    void run({ question: q }, 'text');
  };

  const howWeKnow = (momentId: string, from: HTMLElement) => {
    opener.current = from;
    setAuditId(momentId);
  };

  return (
    <Panel
      title={
        <>
          <MessageCircleQuestion className="me-1.5 h-4 w-4" aria-hidden />
          {t('ask.title')}
        </>
      }
      className={compact ? undefined : 'min-h-0'}
    >
      <p className="mb-3 text-xs text-pp-mute">{t('ask.subtitle')}</p>
      <form onSubmit={submit} className="flex items-stretch gap-2" role="search">
        <label htmlFor={inputId} className="sr-only">
          {t('ask.label')}
        </label>
        <input
          id={inputId}
          type="text"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          value={text}
          onChange={(e) => {
            const raw = e.target.value;
            setClipped(raw.length > TYPED_CAP);
            setText(raw.slice(0, TYPED_CAP));
            if (hint) setHint(null);
          }}
          aria-invalid={tooLong || hint === 'empty' ? true : undefined}
          placeholder={t('ask.placeholder')}
          aria-describedby={`${inputId}-count`}
          className="min-h-[44px] min-w-0 flex-1 border border-pp-line bg-pp-deep px-3 text-sm text-pp-chalk placeholder:text-pp-mute focus:border-pp-signal focus:outline-none"
        />
        <button
          type="submit"
          disabled={!!pending || tooLong}
          aria-busy={pending === 'text'}
          className="flex min-h-[44px] items-center gap-1.5 bg-pp-pulse px-4 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-white hover:bg-pp-chalk hover:text-pp-night disabled:opacity-50"
        >
          <Search className="h-4 w-4" aria-hidden />
          {pending === 'text' ? t('ask.sending') : t('ask.send')}
        </button>
      </form>
      <p id={`${inputId}-count`} className={cx('ltr-nums mt-1 text-end text-[11px]', tooLong ? 'font-semibold text-pp-gold' : 'text-pp-mute')}>
        {t('ask.count', { n: clipped ? t('guide.counter.over', { n: TYPED_CAP }) : text.length, max: ASK_MAX_CHARS })}
      </p>
      {(tooLong || hint === 'empty') && (
        <p role="alert" data-testid="ask-hint" className="mt-1 border-s-4 border-pp-gold bg-pp-gold/10 px-3 py-1.5 text-xs text-pp-gold">
          {tooLong ? t('visit.ask.tooLong', { n: text.length, max: ASK_MAX_CHARS }) : t('visit.ask.empty')}
        </p>
      )}

      <div className="mt-2" role="group" aria-label={t('ask.suggested')}>
        <ul className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <li key={chip}>
              <button
                type="button"
                onClick={() => void run({ chip }, chip)}
                disabled={!!pending}
                aria-busy={pending === chip}
                className={cx(
                  'min-h-[44px] rounded-full border px-3 text-xs transition disabled:opacity-60',
                  pending === chip ? 'border-pp-signal bg-pp-signal/15 text-pp-signal' : 'border-pp-line bg-pp-raised text-slate-200 hover:border-pp-signal',
                )}
              >
                {pending === chip ? t('ask.sending') : t(`ask.chip.${chip}`)}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div aria-live="polite" className="mt-3">
        {result && 'failure' in result && (
          <p role="alert" className="border-s-4 border-pp-gold bg-pp-gold/10 px-3 py-2 text-sm text-pp-gold">
            {t(`ask.fail.${result.failure}`)}
          </p>
        )}
        {result && 'answer' in result && (
          <AnswerCard
            answer={result.answer}
            match={match}
            onHowWeKnow={howWeKnow}
            onOpenReplay={onOpenReplay}
            onJump={onJump}
            onSpeak={speech.enabled ? () => speech.speak(result.answer.answer, result.answer.text_language) : undefined}
          />
        )}
      </div>
      {auditId && (
        <AuditDrawer
          momentId={auditId}
          persona={match.profile.persona}
          language={match.profile.language}
          onClose={() => {
            setAuditId(null);
            opener.current?.focus();
          }}
        />
      )}
    </Panel>
  );
};

const AnswerCard: React.FC<{
  answer: AskAnswer;
  match: MatchViewState;
  onHowWeKnow: (momentId: string, from: HTMLElement) => void;
  onSpeak?: () => void;
  onOpenReplay?: (momentId: string) => void;
  onJump?: (b: Bookmark) => void;
}> = ({ answer, match, onHowWeKnow, onSpeak, onOpenReplay, onJump }) => {
  const i18n = useI18n();
  const { t } = i18n;
  const answered = answer.status === 'answered' || answer.status === 'not_yet';
  const tone = answered ? 'border-pp-signal' : answer.status === 'hidden' ? 'border-pp-gold' : 'border-pp-line';
  const links = answer.moment_ids.slice(-MAX_LINKS);
  const bookmark = (id: string) => match.bookmarks.find((b) => b.moment_id === id);
  // "Should he have passed?" before the first one: say when it comes and offer to jump there.
  const upcoming =
    answer.status === 'answered' && answer.intent?.kind === 'better_option' && !links.some((id) => isSpecialBookmark(match, id))
      ? nextBetterOption(match.bookmarks, answer.as_of)
      : null;

  return (
    <article data-testid="ask-answer" className={cx('border-s-4 bg-pp-deep/70 px-3 py-3', tone)}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px]">
        <span className="ltr-nums font-bold uppercase tracking-widest text-pp-signal">{t('ask.asOf', { clock: `⁦${answer.as_of.clock}⁩` })}</span>
        {answer.status === 'refused' && <Badge tone="mute">{t('ask.refused')}</Badge>}
        {answer.status === 'hidden' && <Badge tone="gold">{t('ask.hidden')}</Badge>}
        {answer.status === 'clarify' && <Badge tone="gold">{t('ask.clarify')}</Badge>}
        {answered && answer.fact_check.ok && (
          <span className="inline-flex items-center gap-1 text-pp-mute">
            <CheckCircle2 className="h-3.5 w-3.5 text-pp-signal" aria-hidden />
            {t('ask.checked')}
          </span>
        )}
        {onSpeak && (
          <button type="button" onClick={onSpeak} aria-label={t('ask.readAloud')} title={t('ask.readAloud')} className="ms-auto flex h-8 w-8 items-center justify-center text-pp-mute hover:text-pp-chalk">
            <Volume2 className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
      {/* Plain text only: the answer is never rendered as HTML. */}
      <p dir={answer.rtl ? 'rtl' : 'ltr'} lang={answer.text_language} className="text-[15px] leading-snug text-pp-chalk">
        {answer.answer}
      </p>
      {answer.metric && (
        <p className="mt-2 text-xs text-pp-mute" dir="ltr">
          {t('ask.formula', { formula: answer.metric.formula })}
        </p>
      )}
      {answer.evidence.length > 0 && (
        <div className="mt-2">
          <h3 className="sr-only">{t('ask.evidence')}</h3>
          <ul className="flex flex-wrap gap-1.5" aria-label={t('ask.evidence')}>
            {answer.evidence.slice(0, 8).map((e, i) => (
              <li key={`${e.label_key ?? e.label}-${i}`} className="border border-pp-line bg-pp-raised px-2 py-0.5 text-[11px] text-slate-200">
                <span className="text-pp-mute">{e.label}</span>{' '}
                <span className="ltr-nums font-bold text-pp-chalk">
                  {factValue(i18n, e.value)}
                  {e.unit ? ` ${e.unit}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {upcoming && (
        <div data-testid="ask-upcoming" className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span className="text-slate-300">{t('guide.ask.firstAt', { clock: `⁦${upcoming.match_clock}⁩` })}</span>
          {onJump && (
            <button type="button" onClick={() => onJump(upcoming)} className="inline-flex min-h-[44px] items-center gap-1 bg-pp-pulse px-3 text-xs font-bold text-white hover:bg-pp-pulse/85">
              <Play className="h-3.5 w-3.5" aria-hidden />
              <span className="ltr-nums">{t('guide.ask.jumpTo', { clock: upcoming.match_clock })}</span>
            </button>
          )}
        </div>
      )}
      {links.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {links.map((id) => {
            const b = bookmark(id);
            return (
              <React.Fragment key={id}>
              {onOpenReplay && isSpecialBookmark(match, id) && (
                <button type="button" aria-haspopup="dialog" onClick={() => onOpenReplay(id)} className="inline-flex min-h-[44px] items-center gap-1 bg-pp-pulse px-3 text-xs font-bold text-white hover:bg-pp-pulse/85">
                  <Play className="h-3.5 w-3.5" aria-hidden />
                  {t('visit.jump.replay')}
                  {b ? <span className="ltr-nums"> · {b.match_clock}</span> : null}
                </button>
              )}
              <button type="button" aria-haspopup="dialog" onClick={(e) => onHowWeKnow(id, e.currentTarget)} className="min-h-[44px] text-pp-signal underline decoration-dotted underline-offset-2 hover:text-pp-chalk">
                {t('ask.howWeKnow')}
                {b ? <span className="ltr-nums"> · {b.match_clock}</span> : null}
              </button>
              </React.Fragment>
            );
          })}
        </div>
      )}
    </article>
  );
};
