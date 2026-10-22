"""Filler and football words a match question may carry besides its keywords.

The parser takes every keyword, name and number it recognises out of a question,
then these words. Whatever is left is unknown: a question that carries more than
one unknown word is asking for something else as well ("btw how do I make a
bomb", "answer as a poem") and is refused. The words are in the guard's
normalised form: case-folded, accents stripped, Arabic letters folded (no hamza
on alef, teh marbuta as heh, alef maqsura as yeh), Japanese voiced marks
dropped. Kept one language per block, for review.
"""

# Word lists are kept as long lines for review.
# ruff: noqa: E501

from __future__ import annotations

from .guard import normalise


def _words(text: str) -> frozenset[str]:
    return frozenset(normalise(text).split())


EN = _words(
    """
    a an the is are was were be been being am do does did done doing have has had having will would shall should can
    could may might must of to in on at for from by with about into over after before between during since until up
    down out off so far yet now currently right today tonight this that these those it its they them their theirs he
    she him his her hers we us our you your i me my what whats who whos whom whose which when where why how hows
    many much more most less least fewer than then and or but not no yes any some all each every both either neither
    there here very really just only still already again ever overall total totals stat stats statistic statistics
    number numbers figure figures game match matches team teams side sides club clubs player players guy guys lad man
    pitch field half halves time minute minutes min mins second first last full kickoff start started end period
    stoppage added extra injury give gives giving show showing tell telling let lets see look looking looks know
    please pls plz thanks thank thx hey hi hello ok okay well good bad better best worst worse high higher highest low
    lower lowest big bigger biggest fast faster quick quicker slow slower slowest far further farthest made make
    makes making run ran runs running covered cover covers going go goes gone playing played play plays performing
    performance performances doing compare compared comparison versus vs against difference mean means meaning
    explain define defined definition calculate calculated work works worked out stand standing stands happening
    happen happened happens on top winning won losing lost ahead behind leading lead leads level drawing draw drawn
    attempt attempts attempted attempting complete completed completion create created creating chance chances goal
    goals scored score scoring scores net assist assists assisted card cards booked booking bookings sent var review
    reviewed reviews decision decisions offside handball foul fouls penalty penalties ruled disallowed referee flag
    flagged assistant recently recent lately latest instead option options get gets got getting need needs rate per
    percent percentage accuracy accurate speed pace distance kilometres kilometers km kmh hour pass passes passing
    passed shot shots shooting target tackle tackles tackling interception interceptions touch touches key possession
    momentum pressure pressing press tilt index sprint sprints unfound home away visitors hosts shirt jersey wearing
    wears number one two three four five six seven eight nine ten eleven list so like say said mostly anyone someone
    anybody somebody everyone nobody something anything everything nothing other others another same such own also
    either whose thing things way ways lot lots bit kind sort tonight's today's game's team's player's
    """
)

ES = _words(
    """
    el la los las lo un una unos unas de del al a en y e o u que quien quienes cual cuales como cuanto cuantos cuanta
    cuantas cuando donde por para con sin sobre entre hasta desde es son esta estan estamos era eran fue fueron ser
    sido han ha he hay habia hubo lleva llevan llevado tiene tienen tenido tenia hecho hizo hace hacen va van ido iba
    mas menos muy mejor peor partido partidos juego equipo equipos jugador jugadores ahora hoy ya aun todavia momento
    minuto minutos parte tiempo primera primer segunda segundo dime dinos muestrame dame cuenta se le les su sus mi me
    te tu nos este esto ese esa eso aquel si no numero dorsal estadisticas estadistica datos dato corrido corrio
    corre recorrido rapido rapida veloz gol goles tiro tiros puerta porteria posesion pase pases precision presion
    domina dominando dominado ganando gana ganado perdiendo pierde marcador resultado tarjeta tarjetas amarilla
    amarillas roja rojas local locales visitante visitantes paso pasado sucedido significa significan explica
    explicame definicion calcula calcula calculado favor gracias hola oye bien mal alto alta total totales jugada
    jugadas ocasion ocasiones oportunidad oportunidades entradas entrada intercepciones toques clave asistencias
    asistencia campo cancha club clubes lado
    """
)

FR = _words(
    """
    le la les l un une des de du d a au aux en et ou qui que qu quoi quel quelle quels quelles comment combien quand
    est sont ete etait etaient a ont avait fait faire fais il elle ils elles on c ce cet cette ces se s sa son ses
    leur leurs mon ma mes ton ta tes notre nos votre vos plus moins tres bien mieux meilleur meilleure mal match
    matchs jeu equipe equipes joueur joueurs maintenant aujourd hui jusqu ici instant moment minute minutes mi temps
    premiere premier seconde second deuxieme dis dites donne donnez montre montrez moi nous vous y ne pas n numero
    stats statistiques chiffres couru court rapide vite but buts tir tirs cadre cadres possession passe passes
    precision pression domine dominent gagne gagnent perd score carton cartons jaune jaunes rouge rouges domicile
    exterieur visiteurs passe signifie explique expliquez definition calcule merci bonjour salut svp total totaux
    occasion occasions action actions tacles tacle interceptions ballons touches cles terrain club clubs pour avec
    sans sur dans par entre depuis apres avant cote est-ce qu'est-ce c'est
    """
)

AR = _words(
    """
    من ما ماذا كم كيف هل اي في على عن الى مع و او ثم هو هي هم هما هذا هذه ذلك تلك الذي التي الان حتى منذ بين لديه لديها
    لديهم عند عدد اكثر اقل افضل اسوا فريق الفريق الفريقين اللاعب لاعب اللاعبين لاعبين المباراه مباراه الدقيقه دقيقه
    الدقائق دقائق الشوط شوط الاول الثاني حدث يحدث النتيجه نتيجه سجل سجلت الاهداف اهداف هدف الاحصائيات احصائيات
    الارقام رقم قل لي اخبرني اعطني ارني من فضلك شكرا مرحبا حاليا اليوم الحين هنا هناك كان كانت يكون تكون عليه لها له
    لهم يا الملعب النادي اداء يلعب لعب جيد قطع قطعها اسرع الاسرع ركض جري التسديدات تسديدات تسديده الاستحواذ
    التمريرات تمريرات تمريره البطاقات بطاقات بطاقه صفراء حمراء صفراوات المتوقعه المتوقع مجموع اجمالي حتي ايضا
    يسيطر المسيطر بعد قبل خلال صاحب اكبر اصغر مستوى كيف يلعب يلعبون لعبوا اداء ادى قدم قدمها الحاليه الحالي اخر جميع كل
    بعض اول ثاني ثالث جدا كثيرا قليلا مره مرات نعم لا ليس لم لن قد هناك يوجد توجد كانت اين متى لماذا لمن الذين اللذين
    فيها فيه منها منه عنه عنها بها به لنا لكم انا نحن انت انتم ارجو رجاء الضيوف المضيف المستضيف الفرق نتائج وضع
    """
)

# Japanese has no spaces: these are taken out of each run of kana and kanji, longest first.
_JA_WORDS = """
    です ですか ますか ます でした ました ください 教えて おしえて 何 なに なん 誰 だれ どの どれ どちら いくつ 何本 何枚 何回 何点
    は が を に で と も の か へ や から まで より ね よ な だ ? ？ 今 いま 現在 これまで ここまで 試合 チーム 選手 一番 最も もっとも
    多い 多く 高い 低い 速い 早い 少ない 枚 本 回 点 人 前半 後半 分 ホーム アウェイ 合計 数 いる いますか ある ありますか
    した する しています している 何対何 どう どっち 勝って 勝っている リード 優勢 シュート パス タックル カード 退場 走った
    走行距離 距離 スピード 最速 枠内 キーパス ゴール 得点 得点者 期待 ポゼッション 支配率 プレッシャー 勢い スコア 状況
"""
JA: tuple[str, ...] = tuple(sorted(_words(_JA_WORDS), key=len, reverse=True))

# Arabic attaches "and", "the", "with the", "for the" to the word.
AR_PREFIXES: tuple[str, ...] = ("وال", "بال", "لل", "فال", "كال", "ال", "و", "ب", "ل", "ف")

FILLER: frozenset[str] = EN | ES | FR | AR
