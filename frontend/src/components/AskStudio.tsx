// Ask the studio (docs/ASK.md): one short question, or a suggested chip, answered
// by the server from the stats engine as of the match clock. The answer is
// plain text from a template; the numbers behind it are shown as evidence and
// each cited moment opens its claim audit ("how we know", components/ClaimAudit).
import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, MessageCircleQuestion, Search, Volume2 } from 'lucide-react';
import { ASK_CHIPS, ASK_MAX_CHARS, type AskAnswer, type AskChip, type AskFailure } from '../api/contract';
import { useI18n } from '../i18n';
import { useReadAloud } from '../lib/speech';
import type { MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { factValue } from './BroadcastOverlay';
import { AuditDrawer } from './ClaimAudit';
import { Badge, Panel, cx } from './ui';

const MAX_LINKS = 3;

type Result = { answer: AskAnswer } | { failure: AskFailure };

export const AskStudio: React.FC<{ match: MatchViewState; actions: MatchActions; compact?: boolean }> = ({ match, actions, compact }) => {
  const i18n = useI18n();
  const { t } = i18n;
  const [text, setText] = useState('');
  const [pending, setPending] = useState<AskChip | 'text' | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [auditId, setAuditId] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const speech = useReadAloud();
  const seq = useRef(0);
  const inputId = useRef(`ask-${Math.random().toString(36).slice(2, 8)}`).current;
  const chips = ASK_CHIPS.filter((c) => match.profile.spoilers || c !== 'score');

  const run = async (input: { question: string } | { chip: AskChip }, kind: AskChip | 'text') => {
    const mine = ++seq.current;
    setPending(kind);
    const res = await actions.ask(input);
    if (mine !== seq.current) return; // a newer question replaced this one
    setPending(null);
    setResult(res.ok ? { answer: res.answer } : { failure: res.failure });
    if (res.ok) speech.speak(res.answer.answer, res.answer.text_language);
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
    if (!q || pending) return;
    void run({ question: q.slice(0, ASK_MAX_CHARS) }, 'text');
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
          maxLength={ASK_MAX_CHARS}
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, ASK_MAX_CHARS))}
          placeholder={t('ask.placeholder')}
          aria-describedby={`${inputId}-count`}
          className="min-h-[44px] min-w-0 flex-1 border border-pp-line bg-pp-deep px-3 text-sm text-pp-chalk placeholder:text-pp-mute focus:border-pp-signal focus:outline-none"
        />
        <button
          type="submit"
          disabled={!text.trim() || !!pending}
          aria-busy={pending === 'text'}
          className="flex min-h-[44px] items-center gap-1.5 bg-pp-pulse px-4 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-white hover:bg-pp-chalk hover:text-pp-night disabled:opacity-50"
        >
          <Search className="h-4 w-4" aria-hidden />
          {pending === 'text' ? t('ask.sending') : t('ask.send')}
        </button>
      </form>
      <p id={`${inputId}-count`} className="ltr-nums mt-1 text-end text-[10px] text-pp-mute">
        {t('ask.count', { n: text.length, max: ASK_MAX_CHARS })}
      </p>

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
                  'min-h-[36px] rounded-full border px-3 text-xs transition disabled:opacity-60',
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
}> = ({ answer, match, onHowWeKnow, onSpeak }) => {
  const i18n = useI18n();
  const { t } = i18n;
  const answered = answer.status === 'answered' || answer.status === 'not_yet';
  const tone = answered ? 'border-pp-signal' : answer.status === 'hidden' ? 'border-pp-gold' : 'border-pp-line';
  const links = answer.moment_ids.slice(-MAX_LINKS);
  const bookmark = (id: string) => match.bookmarks.find((b) => b.moment_id === id);

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
      {links.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {links.map((id) => {
            const b = bookmark(id);
            return (
              <button key={id} type="button" aria-haspopup="dialog" onClick={(e) => onHowWeKnow(id, e.currentTarget)} className="min-h-[32px] text-pp-signal underline decoration-dotted underline-offset-2 hover:text-pp-chalk">
                {t('ask.howWeKnow')}
                {b ? <span className="ltr-nums"> · {b.match_clock}</span> : null}
              </button>
            );
          })}
        </div>
      )}
    </article>
  );
};
