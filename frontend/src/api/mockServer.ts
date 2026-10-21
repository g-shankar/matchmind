// In-browser stand-in for the match server: replays a recorded engine run
// (public/demo/demo-match.json) and answers the same contract messages, so the
// app keeps working when the backend is unreachable. It only re-sends numbers
// that are in the recording; it never computes new stats.
import type {
  Bookmark,
  ClientAction,
  ControlChaosState,
  CrewStatus,
  Evidence,
  FocusMetric,
  Language,
  MatchEvent,
  MatchState,
  MomentKind,
  OverlayCard,
  PersonaType,
  Playback,
  PlayerStats,
  Recap,
  Replay,
  ServerMessage,
  Slot,
  SnapshotData,
  SpeedMultiplier,
  Teams,
  ViewerProfile,
} from './contract';
import type { MatchTransport, MessageHandler } from './transport';
import { metricAlertText } from './mockText';

export interface FixtureTick {
  event: MatchEvent;
  clock: string;
  period: number;
  score: { home: number; away: number };
  state: MatchState;
  control_chaos: ControlChaosState;
  players_changed: PlayerStats[];
}

export interface MomentText {
  headline: string;
  body: string;
  why: string;
}

export interface FixtureMoment {
  moment_id: string;
  kind: MomentKind;
  slot: Slot;
  priority: number;
  show_at_s: number;
  duration_s: number;
  event_id: string;
  match_clock: string;
  team: string | null;
  player_ids: string[];
  evidence: Evidence[];
  tactical_tag: string;
  replay: Replay | null;
  texts: Partial<Record<PersonaType, Partial<Record<Language, MomentText>>>>;
}

export interface DemoFixture {
  fixture_version: number;
  match_id: string;
  source: string;
  teams: Teams;
  crew: CrewStatus;
  ticks: FixtureTick[];
  moments: FixtureMoment[];
  recaps: Partial<Record<PersonaType, Partial<Record<Language, Recap>>>>;
}

export const DEFAULT_PROFILE: ViewerProfile = {
  persona: 'casual',
  language: 'en',
  favourite_team: null,
  focus_player_id: null,
  focus_metric: null,
};

const STEP_MS = 100;
const SPEEDS: SpeedMultiplier[] = [1, 10, 60];
const BOOKMARK_KINDS: MomentKind[] = [
  'goal',
  'card',
  'better_option',
  'unfound_run',
  'big_chance',
  'pressure_spell',
  'momentum_swing',
  'milestone',
];

const textPersona = (p: PersonaType): PersonaType => (p === 'player_spotlight' ? 'casual' : p);

export function pickText(m: FixtureMoment, persona: PersonaType, language: Language): { text: MomentText; language: Language } {
  const byLang = m.texts[textPersona(persona)] ?? m.texts.casual ?? {};
  const text = byLang[language];
  if (text) return { text, language };
  return { text: byLang.en ?? { headline: m.kind, body: '', why: '' }, language: 'en' };
}

export function cardForMoment(m: FixtureMoment, profile: ViewerProfile): OverlayCard | null {
  const focus = profile.focus_player_id;
  const involvesFocus = !!focus && m.player_ids.includes(focus);
  if (profile.persona === 'player_spotlight' && focus && !involvesFocus && m.kind !== 'goal') return null;
  const { text, language } = pickText(m, profile.persona, profile.language);
  const favourite_side = profile.favourite_team ? m.team === profile.favourite_team : null;
  const priority = Math.min(100, m.priority + (favourite_side ? 10 : 0) + (involvesFocus ? 15 : 0));
  return {
    card_id: `${m.moment_id}:${profile.persona}:${language}`,
    moment_id: m.moment_id,
    kind: m.kind,
    slot: m.slot,
    priority,
    show_at_s: m.show_at_s,
    duration_s: m.duration_s,
    persona: profile.persona,
    language,
    rtl: language === 'ar',
    headline: text.headline,
    body: text.body,
    why: text.why,
    tactical_tag: m.tactical_tag,
    evidence: m.evidence,
    player_ids: m.player_ids,
    team: m.team,
    favourite_side,
    produced_by: 'template',
    fallback_reason: null,
    replay: m.replay,
  };
}

// Builds a metric_alert card when this connection's focus metric changes enough to mention.
export function metricAlert(
  metric: FocusMetric,
  prev: FixtureTick | null,
  tick: FixtureTick,
  teams: Teams,
  language: Language,
): OverlayCard | null {
  const s = tick.state;
  const e = tick.event;
  let value: number | null = null;
  let unit: string | null = null;
  let team: string | null = null;
  let player: string | null = null;
  let label: string = metric;

  if (metric === 'pressure') {
    for (const side of ['home', 'away'] as const) {
      const now = s[side].pressure_index;
      const before = prev ? prev.state[side].pressure_index : 0;
      if (now >= 70 && before < 70) {
        value = Math.round(now);
        team = side === 'home' ? s.home_id : s.away_id;
        label = 'pressure_index';
      }
    }
  } else if (metric === 'momentum') {
    const before = prev ? prev.state.momentum : 0;
    if (Math.abs(s.momentum) >= 40 && Math.abs(before) < 40) {
      value = Math.round(s.momentum);
      team = s.momentum > 0 ? s.home_id : s.away_id;
      label = 'momentum';
    }
  } else if (metric === 'xg' && e.type === 'shot' && e.metrics.chance_quality != null) {
    value = e.metrics.chance_quality;
    team = e.team;
    player = e.player_id;
    label = 'chance_quality';
  } else if (metric === 'top_speed' && e.metrics.sprint && e.metrics.player_speed_kmh != null) {
    value = e.metrics.player_speed_kmh;
    unit = 'km/h';
    team = e.team;
    player = e.player_id;
    label = 'player_speed';
  } else if (metric === 'pass_difficulty' && (e.metrics.pass_difficulty ?? 0) >= 60) {
    value = e.metrics.pass_difficulty;
    team = e.team;
    player = e.player_id;
    label = 'pass_difficulty';
  }
  if (value == null) return null;

  const playerName = player ? findPlayerName(teams, player) : null;
  const teamName = team ? (team === teams.home.team_id ? teams.home.short_name : teams.away.short_name) : '';
  const text = metricAlertText(metric, language, { value, team: teamName, player: playerName ?? teamName });
  return {
    card_id: `metric:${metric}:${e.event_id}:${language}`,
    moment_id: `metric:${e.event_id}`,
    kind: metric === 'momentum' ? 'momentum_swing' : metric === 'pressure' ? 'pressure_spell' : metric === 'top_speed' ? 'speed_burst' : metric === 'xg' ? 'big_chance' : 'hard_pass',
    slot: 'metric_alert',
    priority: 50,
    show_at_s: e.clock_s,
    duration_s: 6,
    persona: 'casual',
    language: text.language,
    rtl: text.language === 'ar',
    headline: text.headline,
    body: text.body,
    why: '',
    tactical_tag: metric,
    evidence: [{ label, value, unit, source_event_id: e.event_id }],
    player_ids: player ? [player] : [],
    team,
    favourite_side: null,
    produced_by: 'template',
    fallback_reason: null,
    replay: null,
  };
}

export function findPlayerName(teams: Teams, playerId: string): string | null {
  for (const t of [teams.home, teams.away]) {
    const p = t.players.find((x) => x.player_id === playerId);
    if (p) return p.name;
  }
  return null;
}

// Index of the tick to resume from for a seek target in match-clock seconds.
// Period 2 restarts at 2700 s, so targets from 2700 prefer second-half ticks.
export function seekIndex(ticks: FixtureTick[], clockS: number): number {
  const wantPeriod = clockS >= 2700 ? 2 : 1;
  const idx = ticks.findIndex((t) => t.event.period === wantPeriod && t.event.clock_s >= clockS);
  if (idx >= 0) return idx;
  const any = ticks.findIndex((t) => t.event.clock_s >= clockS && t.event.period >= wantPeriod);
  return any >= 0 ? any : ticks.length;
}

export class MockMatchServer implements MatchTransport {
  readonly kind = 'demo' as const;
  private next = 0; // index of the next tick to play
  private vclock = 0; // virtual seconds since kick-off, monotonic across periods
  private vtimes: number[];
  private running = true;
  private speed: SpeedMultiplier;
  private profile: ViewerProfile;
  private players = new Map<string, PlayerStats>();
  private momentsByEvent = new Map<string, FixtureMoment[]>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private ended = false;

  constructor(
    private readonly fixture: DemoFixture,
    private readonly emit: MessageHandler,
    options: { profile?: Partial<ViewerProfile>; speed?: SpeedMultiplier; autoplay?: boolean } = {},
  ) {
    this.profile = { ...DEFAULT_PROFILE, ...options.profile };
    this.speed = options.speed ?? 10;
    this.running = options.autoplay ?? true;
    let acc = 0;
    this.vtimes = fixture.ticks.map((t, i) => {
      const prev = i > 0 ? fixture.ticks[i - 1].event : null;
      // Half time is not replayed: the clock gap across a period change counts as zero.
      if (prev && prev.period === t.event.period) acc += Math.max(0, t.event.clock_s - prev.clock_s);
      return acc;
    });
    for (const m of fixture.moments) {
      const list = this.momentsByEvent.get(m.event_id) ?? [];
      list.push(m);
      this.momentsByEvent.set(m.event_id, list);
    }
    queueMicrotask(() => {
      this.emit({ type: 'INITIAL_SNAPSHOT', data: this.snapshot() });
      this.timer = setInterval(() => this.step(STEP_MS / 1000), STEP_MS);
    });
  }

  // Advances playback by `seconds` of wall time. Public so tests can drive it.
  step(seconds: number) {
    if (!this.running || this.ended) return;
    this.vclock += seconds * this.speed;
    while (this.next < this.fixture.ticks.length && this.vtimes[this.next] <= this.vclock) {
      this.playTick(this.next);
      this.next += 1;
    }
    if (this.next >= this.fixture.ticks.length && !this.ended) {
      this.ended = true;
      this.running = false;
      this.emit({ type: 'PLAYBACK_CONTROL', data: this.playback() });
      const recap = this.recapFor(this.profile.persona, this.profile.language);
      if (recap) this.emit({ type: 'MATCH_END', data: { recap } });
    }
  }

  send(action: ClientAction) {
    switch (action.action) {
      case 'toggle_pause':
        if (this.ended) return;
        this.running = !this.running;
        this.emit({ type: 'PLAYBACK_CONTROL', data: this.playback() });
        return;
      case 'set_speed':
        if (!SPEEDS.includes(action.speed_multiplier)) {
          this.emit({ type: 'ERROR', data: { message: 'Speed must be 1, 10 or 60.' } });
          return;
        }
        this.speed = action.speed_multiplier;
        this.emit({ type: 'PLAYBACK_CONTROL', data: this.playback() });
        return;
      case 'reset':
        this.emit({ type: 'MATCH_RESET', data: {} });
        this.jumpTo(0);
        this.running = true;
        this.emit({ type: 'INITIAL_SNAPSHOT', data: this.snapshot() });
        return;
      case 'seek':
        this.jumpTo(seekIndex(this.fixture.ticks, Math.max(0, action.clock_s)));
        this.emit({ type: 'INITIAL_SNAPSHOT', data: this.snapshot() });
        return;
      case 'set_persona':
      case 'set_view': {
        const { action: _a, ...changes } = action;
        this.profile = { ...this.profile, ...changes };
        this.emit({ type: 'PROFILE_CHANGED', data: this.profile });
        this.emit({ type: 'PERSONA_CHANGED', data: { persona: this.profile.persona } });
        return;
      }
      default:
        this.emit({ type: 'ERROR', data: { message: 'That action is not supported.' } });
    }
  }

  async getMoment(
    momentId: string,
    persona: PersonaType,
    language: Language,
    favouriteTeam: string | null,
  ): Promise<OverlayCard | null> {
    const m = this.fixture.moments.find((x) => x.moment_id === momentId);
    if (!m) return null;
    return cardForMoment(m, { ...DEFAULT_PROFILE, persona, language, favourite_team: favouriteTeam });
  }

  async getRecap(persona: PersonaType, language: Language): Promise<Recap | null> {
    return this.recapFor(persona, language);
  }

  close() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private recapFor(persona: PersonaType, language: Language): Recap | null {
    const byLang = this.fixture.recaps[textPersona(persona)] ?? this.fixture.recaps.casual;
    return byLang?.[language] ?? byLang?.en ?? null;
  }

  private jumpTo(index: number) {
    this.players.clear();
    for (let i = 0; i < index; i++) this.applyPlayers(this.fixture.ticks[i]);
    this.next = index;
    this.vclock = index > 0 ? this.vtimes[index - 1] : 0;
    this.ended = index >= this.fixture.ticks.length;
    if (this.ended) this.running = false;
  }

  private applyPlayers(tick: FixtureTick) {
    for (const p of tick.players_changed) this.players.set(p.player_id, p);
  }

  private playTick(i: number) {
    const tick = this.fixture.ticks[i];
    this.applyPlayers(tick);
    const cards: OverlayCard[] = [];
    for (const m of this.momentsByEvent.get(tick.event.event_id) ?? []) {
      const card = cardForMoment(m, this.profile);
      if (card) cards.push(card);
    }
    if (this.profile.focus_metric) {
      const alert = metricAlert(
        this.profile.focus_metric,
        i > 0 ? this.fixture.ticks[i - 1] : null,
        tick,
        this.fixture.teams,
        this.profile.language,
      );
      if (alert) cards.push(alert);
    }
    cards.sort((a, b) => b.priority - a.priority);
    this.emit({
      type: 'MATCH_TICK',
      data: {
        event: tick.event,
        clock: tick.clock,
        period: tick.period,
        score: tick.score,
        state: tick.state,
        control_chaos: tick.control_chaos,
        cards,
        players_changed: tick.players_changed,
      },
    });
  }

  private playback(): Playback {
    const last = this.next > 0 ? this.fixture.ticks[this.next - 1] : this.fixture.ticks[0];
    return {
      is_running: this.running,
      speed_multiplier: this.speed,
      clock_s: last.event.clock_s,
      ended: this.ended,
    };
  }

  private snapshot(): SnapshotData {
    const ticks = this.fixture.ticks;
    const last = this.next > 0 ? ticks[this.next - 1] : ticks[0];
    const recent: OverlayCard[] = [];
    const playedIds = new Set(ticks.slice(0, this.next).map((t) => t.event.event_id));
    for (const m of this.fixture.moments) {
      if (m.slot === 'pitch_tag' || !playedIds.has(m.event_id)) continue;
      const card = cardForMoment(m, this.profile);
      if (card) recent.push(card);
    }
    return {
      match_id: this.fixture.match_id,
      clock: last.clock,
      period: last.period,
      home_score: this.next > 0 ? last.score.home : 0,
      away_score: this.next > 0 ? last.score.away : 0,
      teams: this.fixture.teams,
      state: last.state,
      control_chaos: last.control_chaos,
      profile: this.profile,
      playback: this.playback(),
      recent_cards: recent.slice(-8),
      bookmarks: this.bookmarks(),
      players: [...this.players.values()],
      crew: this.fixture.crew,
      auto_eventing: null,
    };
  }

  private bookmarks(): Bookmark[] {
    return this.fixture.moments
      .filter((m) => BOOKMARK_KINDS.includes(m.kind))
      .map((m) => ({
        moment_id: m.moment_id,
        kind: m.kind,
        match_clock: m.match_clock,
        clock_s: m.show_at_s,
        title: pickText(m, this.profile.persona, this.profile.language).text.headline,
      }));
  }
}

export async function loadDemoFixture(url = `${import.meta.env.BASE_URL}demo/demo-match.json`): Promise<DemoFixture> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`demo fixture ${res.status}`);
  return (await res.json()) as DemoFixture;
}

export type { ServerMessage };
