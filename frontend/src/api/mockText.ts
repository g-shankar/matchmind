// Template wording for the demo replay's focus-metric alerts. The only numbers
// are the recorded values passed in.
import type { FocusMetric, Language } from './contract';

type Vars = { value: number; team: string; player: string };
type Template = { headline: string; body: string };

const TEMPLATES: Record<'en' | 'es' | 'ar', Record<FocusMetric, Template>> = {
  en: {
    pressure: { headline: '{team} turn up the pressure', body: 'Pressure index hits {value} over the last five minutes.' },
    momentum: { headline: 'Momentum shifts to {team}', body: 'Momentum reading is now {value}.' },
    xg: { headline: 'Chance for {player}', body: 'That shot was worth {value} xG.' },
    top_speed: { headline: '{player} at full sprint', body: 'Clocked at {value} km/h.' },
    pass_difficulty: { headline: 'Hard pass from {player}', body: 'Pass difficulty {value} out of 100.' },
  },
  es: {
    pressure: { headline: '{team} aprieta', body: 'El índice de presión llega a {value} en los últimos cinco minutos.' },
    momentum: { headline: 'La inercia es de {team}', body: 'La inercia marca ahora {value}.' },
    xg: { headline: 'Ocasión para {player}', body: 'Ese disparo valía {value} xG.' },
    top_speed: { headline: '{player} a máxima velocidad', body: 'Cronometrado a {value} km/h.' },
    pass_difficulty: { headline: 'Pase difícil de {player}', body: 'Dificultad del pase: {value} sobre 100.' },
  },
  ar: {
    pressure: { headline: '{team} يرفع الضغط', body: 'مؤشر الضغط يبلغ {value} في آخر خمس دقائق.' },
    momentum: { headline: 'الزخم يتحول إلى {team}', body: 'قراءة الزخم الآن {value}.' },
    xg: { headline: 'فرصة لـ{player}', body: 'قيمة هذه التسديدة {value} من الأهداف المتوقعة (xG).' },
    top_speed: { headline: '{player} بأقصى سرعة', body: 'سُجّلت سرعته عند {value} كم/س.' },
    pass_difficulty: { headline: 'تمريرة صعبة من {player}', body: 'صعوبة التمريرة {value} من 100.' },
  },
};

const fill = (s: string, v: Vars) =>
  s.replace('{value}', String(v.value)).replace('{team}', v.team).replace('{player}', v.player);

export function metricAlertText(metric: FocusMetric, language: Language, vars: Vars) {
  const lang = language === 'es' || language === 'ar' ? language : 'en';
  const t = TEMPLATES[lang][metric];
  return { language: lang as Language, headline: fill(t.headline, vars), body: fill(t.body, vars) };
}
