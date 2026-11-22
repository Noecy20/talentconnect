"""Test de personnalité basé sur l'Ennéagramme (9 types).

Déroulé : choix du genre (accords grammaticaux uniquement), instructions, 90 affirmations
présentées par pages de 5 dans un ordre « tourniquet » (T1-1, T2-1 … T9-1, T1-2 …),
échelle de 0 (pas du tout d'accord) à 4 (tout à fait d'accord), puis rapport.

Le calcul est fait ici, côté serveur, sans IA : il est transparent et reproductible.
Ce test est un outil de connaissance de soi, pas un diagnostic.
"""
import re
from collections import Counter

ECHELLE = [(0, "Pas du tout d'accord"), (1, "Pas d'accord"), (2, "Neutre"), (3, "D'accord"), (4, "Tout à fait d'accord")]

# --------------------------------------------------------------------------- banque d'affirmations (10 par type)
AFFIRMATIONS = {
    1: ["Je ne me sens tranquille qu'une fois qu'un travail est fait correctement, dans les moindres détails.",
        "Je repère vite ce qui cloche dans un document, un plan ou une organisation.",
        "Je relis plusieurs fois avant de rendre quelque chose.",
        "Je me sens responsable d'améliorer ce qui pourrait mieux fonctionner.",
        "J'ai une petite voix intérieure qui me juge quand je fais une erreur.",
        "Les règles et les standards de qualité comptent beaucoup pour moi.",
        "Le désordre autour de moi me gêne pour me concentrer.",
        "J'ai du mal à laisser passer un travail « à peu près bien ».",
        "Quand je reçois une critique, je veux comprendre exactement ce que je peux corriger.",
        "Mon entourage compte sur moi pour vérifier que tout est juste."],
    2: ["Je devine souvent ce dont les autres ont besoin avant qu'ils le disent.",
        "J'aide volontiers, même quand personne ne me le demande.",
        "Je montre facilement mon affection à ceux que j'aime.",
        "Il m'arrive de passer après tout le monde pour que les autres aillent bien.",
        "Quand mes proches vont mal, mon moral baisse aussi.",
        "On vient souvent me confier ses soucis ou me demander conseil.",
        "Me sentir utile aux autres me rend heureux(se).",
        "J'aime qu'on me voie comme une personne généreuse et attentionnée.",
        "J'ai du mal à dire non quand quelqu'un me demande un service.",
        "Je me sens blessé(e) quand mon aide n'est pas remarquée."],
    3: ["Je me fixe des objectifs précis et je fais tout pour les atteindre.",
        "La réussite est un moteur puissant dans ma vie.",
        "J'apprécie qu'on salue mes résultats.",
        "Je m'adapte facilement à des rôles et des publics très différents.",
        "Je cherche en permanence à faire plus en moins de temps.",
        "L'image que je renvoie aux autres compte beaucoup pour moi.",
        "À peine un objectif atteint, j'en vise déjà un autre.",
        "Je change de méthode sans hésiter si une autre est plus efficace.",
        "Je supporte mal de perdre ou d'échouer devant les autres.",
        "J'ai tendance à mettre mes émotions de côté pour avancer."],
    4: ["Mes émotions nourrissent beaucoup ma créativité.",
        "J'ai besoin que ce que je fais reflète qui je suis vraiment.",
        "Je suis très sensible à la beauté des lieux, des objets et des ambiances.",
        "Je me sens pleinement vivant(e) quand je crée quelque chose d'original.",
        "Ma façon de m'habiller ou de décorer exprime ma personnalité.",
        "Je remarque des détails émouvants ou inspirants que les autres ignorent.",
        "J'ai souvent le sentiment d'être différent(e) des autres.",
        "Je ressens les émotions plus intensément que la plupart des gens.",
        "La mélancolie ne me fait pas peur, elle fait partie de moi.",
        "Je fais confiance à ma vision personnelle, même quand elle est atypique."],
    5: ["J'observe et j'analyse une situation avant d'y entrer.",
        "Je m'appuie sur des faits et des données pour décider.",
        "Les problèmes complexes qui demandent des recherches me passionnent.",
        "Je préfère ne pas donner mon avis tant que je n'ai pas tout examiné.",
        "J'aime approfondir un sujet jusqu'à en devenir expert(e).",
        "Je garde facilement mon calme et mon recul face aux problèmes.",
        "J'aime comprendre les mécanismes qui expliquent comment les choses marchent.",
        "J'ai besoin de moments seul(e) pour recharger mes batteries.",
        "Les idées m'intéressent souvent plus que les mondanités.",
        "Je protège mon temps et mon énergie des sollicitations."],
    6: ["J'anticipe ce qui pourrait mal tourner et je prévois un plan B.",
        "La sécurité et la stabilité sont essentielles pour moi.",
        "Je suis très fidèle envers les personnes et les groupes en qui j'ai confiance.",
        "Avant d'agir, je pèse les risques et les conséquences.",
        "Je travaille mieux quand les règles et les attentes sont claires.",
        "La peur de me tromper me fait parfois hésiter.",
        "Les routines me rassurent.",
        "J'aime avoir l'avis de personnes de confiance avant de me lancer.",
        "Je me méfie des gens tant qu'ils n'ont pas fait leurs preuves.",
        "Je suis prêt(e) à beaucoup donner pour défendre mon groupe."],
    7: ["Le changement m'enthousiasme plus qu'il ne m'inquiète.",
        "Je cherche sans cesse de nouvelles expériences.",
        "Je transforme facilement une tâche banale en quelque chose d'amusant.",
        "La routine m'ennuie très vite.",
        "Je préfère garder de la place pour l'imprévu plutôt que tout planifier.",
        "Je vois presque toujours le bon côté des choses.",
        "J'ai besoin de liberté pour faire mes propres choix.",
        "Je rebondis vite quand un plan tombe à l'eau.",
        "Lancer un projet m'excite davantage que le mener jusqu'au bout.",
        "Voyager, découvrir, goûter à tout : c'est ce qui me fait vibrer."],
    8: ["Je prends les décisions avec assurance.",
        "Je dis ce que je pense, franchement.",
        "Je défends farouchement ceux que j'aime.",
        "Le conflit ne me fait pas peur, je l'affronte.",
        "Dans un groupe, je prends naturellement les commandes.",
        "Les injustices me poussent à réagir immédiatement.",
        "Je respecte les personnes fortes et sûres d'elles.",
        "Je préfère compter sur moi-même que dépendre des autres.",
        "Utiliser mon influence pour faire bouger les choses ne me gêne pas.",
        "Je déteste me sentir contrôlé(e) ou manipulé(e)."],
    9: ["Je fais tout pour garder une bonne ambiance autour de moi.",
        "Je comprends facilement les arguments de chaque camp.",
        "Je préfère éviter une dispute plutôt que régler le problème de front.",
        "Je veille à ce que chacun se sente écouté dans une discussion.",
        "J'aide naturellement les autres à trouver un compromis.",
        "Garder la paix compte plus pour moi que d'avoir raison.",
        "Les décisions qui risquent de fâcher quelqu'un me paralysent.",
        "Je laisse souvent couler pour ne pas faire de vagues.",
        "Je mets parfois mes envies de côté pour l'harmonie du groupe.",
        "Les environnements calmes et sans tension me conviennent le mieux."],
}
NB_QUESTIONS = sum(len(v) for v in AFFIRMATIONS.values())   # 90
PAR_PAGE = 5

# Flèches de l'Ennéagramme : type -> (direction de stress, direction de croissance)
FLECHES = {1: (4, 7), 2: (8, 4), 3: (9, 6), 4: (2, 1), 5: (7, 8), 6: (3, 9), 7: (1, 5), 8: (5, 2), 9: (6, 3)}


def ordre():
    """Ordre « tourniquet » : T1-1, T2-1 … T9-1, T1-2 … ; renvoie [(code, type, texte)]."""
    out = []
    for i in range(10):
        for typ in range(1, 10):
            out.append((f"T{typ}-{i + 1}", typ, AFFIRMATIONS[typ][i]))
    return out


# --------------------------------------------------------------------------- accords selon le genre
_ACCORD = re.compile(r"(\w+)\((e|se|ve|ne|le|rice|ère|fe)\)")


def accorder(texte, genre):
    """« prêt(e) » -> « prêt » (H) ou « prête » (F) ; « heureux(se) » -> « heureuse » ;
    « constructif(ve) » -> « constructive » ; « formateur(rice) » -> « formatrice » ;
    « développeur(se) » -> « développeuse » ; « conseiller(ère) » -> « conseillère »."""
    def f(m):
        mot, suffixe = m.group(1), m.group(2)
        if genre != "F":
            return mot
        if suffixe == "se" and mot.endswith("x"):
            return mot[:-1] + "se"
        if suffixe == "se" and mot.endswith("eur"):
            return mot[:-1] + "se"
        if suffixe == "ve" and mot.endswith("f"):
            return mot[:-1] + "ve"
        if suffixe == "rice" and mot.endswith("teur"):
            return mot[:-4] + "trice"
        if suffixe == "ère" and mot.endswith("er"):
            return mot[:-2] + "ère"
        return mot + suffixe
    return _ACCORD.sub(f, texte or "")


# --------------------------------------------------------------------------- calcul
def calculer(reponses, genre="F"):
    """`reponses` : {"T1-1": 0..4, …}. Renvoie le résultat complet (JSON enregistrable)."""
    brut = {t: sum(int(reponses.get(f"T{t}-{i}", 0)) for i in range(1, 11)) for t in range(1, 10)}
    pct = {t: round(brut[t] / 40 * 100) for t in brut}
    quatres = {t: sum(1 for i in range(1, 11) if int(reponses.get(f"T{t}-{i}", 0)) == 4) for t in brut}
    classes = sorted(brut, key=lambda t: (-pct[t], -quatres[t], t))
    dominant, second = classes[0], classes[1]
    mixte = pct[dominant] == pct[second] and quatres[dominant] == quatres[second]

    voisins = (9 if dominant == 1 else dominant - 1, 1 if dominant == 9 else dominant + 1)
    aile = max(voisins, key=lambda v: (pct[v], quatres[v]))

    valeurs = [int(v) for v in reponses.values()]
    plus_frequent = Counter(valeurs).most_common(1)[0][1] if valeurs else 0
    return {
        "genre": "F" if genre == "F" else "H",
        "reponses": {k: int(v) for k, v in reponses.items()},
        "scores_pct": {str(t): pct[t] for t in range(1, 10)},
        "classement": classes,
        "type_dominant": dominant,
        "aile": aile,
        "code": f"{dominant}w{aile}",
        "profil_mixte": [dominant, second] if mixte else None,
        "second": second,
        "profil_nuance": (pct[dominant] - pct[second]) < 5,
        "fiable": not (valeurs and plus_frequent / len(valeurs) > 0.8),
    }


def reponses_valides(form):
    """Lit les 90 réponses d'un formulaire ; None s'il en manque une ou si une valeur est hors échelle."""
    out = {}
    for code, _, _ in ordre():
        v = form.get(code)
        if v not in ("0", "1", "2", "3", "4"):
            return None
        out[code] = int(v)
    return out


# --------------------------------------------------------------------------- contenu du rapport
TYPES = {
    1: dict(
        nom="Le Perfectionniste", motivation="Faire les choses bien, être intègre",
        portrait="Exigeant(e) et droit(e), vous voulez que les choses soient faites correctement et vous élevez le niveau de tout ce que vous touchez.",
        qui="Votre moteur profond est le besoin d'agir de façon juste et d'améliorer le monde qui vous entoure. "
            "Votre peur de base est d'être dans l'erreur, imparfait(e) ou de mal faire ; votre désir de base est d'être "
            "intègre et en accord avec vos principes. Vous avez un sens aigu de ce qui « devrait être » et vous mettez "
            "beaucoup d'énergie à rapprocher la réalité de cet idéal.",
        forces=["Rigueur et souci du détail : on peut vous confier un travail sensible.",
                "Fiabilité : vous tenez vos engagements et vos délais.",
                "Sens de l'éthique et de la justice très développé.",
                "Capacité à organiser, structurer et améliorer les méthodes.",
                "Exemplarité : vous inspirez le sérieux autour de vous."],
        vigilance=["Votre exigence peut devenir de l'autocritique : vous avez le droit à l'erreur.",
                   "Vous pouvez paraître rigide quand d'autres façons de faire sont aussi valables.",
                   "Le perfectionnisme peut retarder la livraison d'un travail déjà très bon.",
                   "La colère retenue finit par se voir : exprimez plus tôt ce qui vous gêne."],
        environnement="Un cadre clair, des standards de qualité reconnus et du temps pour bien faire.",
        collaboration="Méthodique et constructif(ve) : vous proposez des améliorations concrètes et vous aimez que chacun tienne son rôle.",
        metiers=["Auditeur(rice) ou contrôleur(se) de gestion", "Responsable qualité / conformité", "Juriste ou comptable"],
        apporte="La loyauté, la constance et le souci de bien faire les choses pour l'autre.",
        besoin="Être reconnu(e) pour vos efforts et sentir que l'autre partage vos valeurs.",
        tension="Vos remarques, même bien intentionnées, peuvent être vécues comme des critiques.",
        stress="vous devenez plus sombre, vous vous sentez incompris(e) et vous ruminez ce qui ne va pas, comme un Type 4 en difficulté",
        croissance="vous vous détendez, retrouvez la spontanéité et le plaisir, et acceptez que « assez bien » soit parfois parfait, comme un Type 7 épanoui",
        defis=["Rendez un travail sans le relire une troisième fois.",
               "Notez trois choses qui se sont bien passées aujourd'hui, même imparfaites.",
               "Exprimez calmement une petite contrariété au moment où elle arrive.",
               "Laissez quelqu'un faire une tâche à sa façon, sans corriger.",
               "Accordez-vous 30 minutes de loisir sans objectif.",
               "Remplacez une critique par un encouragement concret.",
               "Pardonnez-vous une erreur de la semaine et écrivez ce qu'elle vous a appris."]),
    2: dict(
        nom="L'Altruiste", motivation="Être aimé(e) en étant utile",
        portrait="Chaleureux(se) et attentionné(e), vous savez ce dont les autres ont besoin et vous êtes là pour eux.",
        qui="Votre moteur profond est le lien avec les autres : vous vous sentez bien quand vous êtes utile et apprécié(e). "
            "Votre peur de base est de ne pas être aimé(e) ou d'être indésirable ; votre désir de base est d'être aimé(e) "
            "pour ce que vous êtes. Vous lisez finement les émotions et vous donnez beaucoup, parfois au détriment de vos propres besoins.",
        forces=["Empathie et grande écoute.",
                "Générosité et disponibilité pour les autres.",
                "Talent pour créer des liens et souder une équipe.",
                "Intuition des besoins avant qu'ils ne soient exprimés.",
                "Chaleur humaine qui met les gens en confiance."],
        vigilance=["Vous oubliez parfois vos propres besoins : ils comptent autant que ceux des autres.",
                   "Dire non est aussi une façon de prendre soin de la relation.",
                   "Attendre de la reconnaissance en retour peut créer de la déception.",
                   "Aider sans qu'on vous le demande peut être vécu comme envahissant."],
        environnement="Une ambiance humaine, où l'on travaille en équipe et où l'on sert directement des personnes.",
        collaboration="Soutenant(e) et fédérateur(rice) : vous facilitez la vie de l'équipe et veillez au moral de chacun.",
        metiers=["Chargé(e) des ressources humaines", "Conseiller(ère) clientèle ou en insertion", "Infirmier(ère) ou travailleur(se) social(e)"],
        apporte="L'attention, la tendresse et une présence fiable dans les moments difficiles.",
        besoin="Recevoir de l'affection et de la gratitude, sans avoir à la demander.",
        tension="Le sentiment de donner plus que vous ne recevez.",
        stress="vous pouvez devenir exigeant(e) et dominateur(rice), en reprochant aux autres leur ingratitude, comme un Type 8 sous tension",
        croissance="vous vous reconnectez à vos propres émotions et besoins et vous vous accordez de l'attention, comme un Type 4 épanoui",
        defis=["Dites non à une demande qui ne vous convient pas, poliment.",
               "Demandez de l'aide pour une petite chose.",
               "Notez un besoin personnel et satisfaites-le aujourd'hui.",
               "Aidez quelqu'un seulement s'il vous le demande.",
               "Passez une heure rien que pour vous.",
               "Recevez un compliment par un simple « merci ».",
               "Faites le point : qui prend soin de vous ? Remerciez cette personne."]),
    3: dict(
        nom="Le Battant", motivation="Réussir, être reconnu(e)",
        portrait="Énergique et efficace, vous vous fixez des objectifs ambitieux et vous savez les atteindre.",
        qui="Votre moteur profond est la réussite et la reconnaissance de votre valeur à travers ce que vous accomplissez. "
            "Votre peur de base est d'être sans valeur ou de passer pour un échec ; votre désir de base est de vous sentir "
            "précieux(se) et accompli(e). Vous savez vous adapter, motiver les autres et trouver le chemin le plus rapide vers le résultat.",
        forces=["Sens de l'objectif et du résultat.",
                "Grande capacité de travail et d'organisation.",
                "Adaptabilité aux situations et aux publics.",
                "Charisme et aisance pour présenter, convaincre, motiver.",
                "Esprit d'initiative et goût du défi."],
        vigilance=["Votre valeur ne se résume pas à vos résultats.",
                   "Le rythme effréné peut vous couper de vos émotions et de vos proches.",
                   "Soigner l'image peut faire passer l'authenticité au second plan.",
                   "La peur de l'échec peut vous pousser à éviter les situations où vous n'êtes pas sûr(e) de briller."],
        environnement="Un cadre dynamique avec des objectifs mesurables, de la reconnaissance et des perspectives d'évolution.",
        collaboration="Moteur(rice) et orienté(e) solutions : vous donnez le cap et vous faites avancer le groupe.",
        metiers=["Commercial(e) ou chargé(e) d'affaires", "Chef(fe) de projet", "Entrepreneur(e) ou responsable marketing"],
        apporte="L'élan, l'optimisme et l'envie de construire ensemble.",
        besoin="Être admiré(e) et soutenu(e) dans vos projets.",
        tension="Le travail qui passe avant le temps partagé.",
        stress="vous vous désengagez, procrastinez et devenez apathique, comme un Type 9 en difficulté",
        croissance="vous devenez plus loyal(e), coopératif(ve) et attentif(ve) aux autres, comme un Type 6 épanoui",
        defis=["Bloquez une soirée sans travail ni écran pro.",
               "Partagez un échec et ce qu'il vous a appris.",
               "Demandez à un proche comment il va vraiment, et écoutez.",
               "Faites une activité où vous n'êtes pas performant(e), juste pour le plaisir.",
               "Notez ce que vous ressentez trois fois dans la journée.",
               "Mettez en avant la réussite d'un(e) collègue.",
               "Écrivez ce qui compte pour vous en dehors de la réussite."]),
    4: dict(
        nom="L'Individualiste", motivation="Être authentique et unique",
        portrait="Sensible et créatif(ve), vous cherchez le sens et la beauté, et vous voulez que votre vie vous ressemble.",
        qui="Votre moteur profond est l'authenticité : exprimer qui vous êtes vraiment. Votre peur de base est de ne pas avoir "
            "d'identité propre ou de signification ; votre désir de base est de trouver qui vous êtes et de le vivre pleinement. "
            "Vous ressentez les émotions avec intensité et vous percevez des nuances que d'autres ne voient pas.",
        forces=["Créativité et sens esthétique.",
                "Profondeur émotionnelle et capacité d'introspection.",
                "Empathie pour la souffrance des autres.",
                "Originalité : vous proposez des idées hors des sentiers battus.",
                "Authenticité dans vos relations."],
        vigilance=["Les émotions intenses peuvent vous submerger : apprenez à les laisser passer.",
                   "Comparer votre vie à celle des autres nourrit le sentiment qu'il vous manque quelque chose.",
                   "Les tâches routinières sont aussi une partie du chemin.",
                   "Le repli sur soi peut être pris pour de la distance."],
        environnement="Un poste qui laisse place à la créativité, à l'expression personnelle et à des projets qui ont du sens.",
        collaboration="Inspirant(e) et sincère : vous apportez une vision et une sensibilité humaine aux projets.",
        metiers=["Designer graphique ou UX", "Rédacteur(rice), communicant(e) ou créateur(rice) de contenu", "Psychologue ou art-thérapeute"],
        apporte="La profondeur, la sincérité et une vraie compréhension des émotions.",
        besoin="Être compris(e) et accepté(e) dans votre singularité.",
        tension="L'impression d'être incompris(e), ou des hauts et des bas émotionnels.",
        stress="vous devenez dépendant(e) des autres et cherchez à être rassuré(e), comme un Type 2 sous tension",
        croissance="vous devenez plus discipliné(e) et objectif(ve), et vous concrétisez vos idées, comme un Type 1 épanoui",
        defis=["Terminez une petite tâche que vous repoussez.",
               "Notez trois choses dont vous êtes reconnaissant(e).",
               "Partagez une création, même imparfaite.",
               "Fixez-vous une routine de 20 minutes pour un projet qui vous tient à cœur.",
               "Écoutez quelqu'un sans ramener la conversation à vous.",
               "Quand une émotion forte arrive, nommez-la puis faites une marche.",
               "Faites une chose ordinaire avec attention et plaisir."]),
    5: dict(
        nom="L'Observateur", motivation="Comprendre, être compétent(e)",
        portrait="Curieux(se) et réfléchi(e), vous cherchez à comprendre en profondeur avant d'agir.",
        qui="Votre moteur profond est la connaissance : comprendre comment le monde fonctionne. Votre peur de base est d'être "
            "incapable, envahi(e) ou dépassé(e) ; votre désir de base est d'être compétent(e) et autonome. Vous observez, analysez "
            "et vous préservez votre énergie pour ce qui vous passionne.",
        forces=["Esprit d'analyse et de synthèse.",
                "Expertise approfondie dans vos domaines.",
                "Calme et objectivité face aux problèmes.",
                "Autonomie et indépendance d'esprit.",
                "Capacité à voir ce que les autres n'ont pas remarqué."],
        vigilance=["Rester en retrait peut vous faire manquer des occasions.",
                   "Vous attendez d'en savoir « assez » pour agir : agir aussi permet d'apprendre.",
                   "Partager vos idées et vos émotions renforce vos liens.",
                   "Protéger votre énergie ne doit pas vous isoler."],
        environnement="Un cadre calme, avec de l'autonomie, du temps pour approfondir et des problèmes complexes à résoudre.",
        collaboration="Expert(e) et posé(e) : on vient vous voir pour un avis éclairé et une analyse solide.",
        metiers=["Data analyst ou data scientist", "Ingénieur(e) ou développeur(se)", "Chercheur(se) ou consultant(e) expert(e)"],
        apporte="La loyauté discrète, la stabilité et une compréhension profonde.",
        besoin="De l'espace personnel et le respect de votre indépendance.",
        tension="Le besoin de solitude qui peut être vécu comme de la distance.",
        stress="vous vous dispersez, devenez impatient(e) et cherchez des distractions, comme un Type 7 sous tension",
        croissance="vous passez à l'action avec assurance et partagez votre savoir, comme un Type 8 épanoui",
        defis=["Donnez votre avis en réunion avant d'avoir tout vérifié.",
               "Lancez une action concrète sur un projet que vous étudiez depuis longtemps.",
               "Partagez une émotion avec un proche.",
               "Proposez un café à un(e) collègue que vous connaissez peu.",
               "Enseignez quelque chose que vous maîtrisez.",
               "Faites une activité physique sans réfléchir à autre chose.",
               "Demandez un retour sur votre travail et accueillez-le."]),
    6: dict(
        nom="Le Loyaliste", motivation="Être en sécurité, soutenu(e)",
        portrait="Fiable et engagé(e), vous anticipez les risques et vous êtes fidèle à ceux qui comptent pour vous.",
        qui="Votre moteur profond est la sécurité : construire un cadre stable et des relations sur lesquelles compter. "
            "Votre peur de base est d'être sans soutien ni repères ; votre désir de base est de vous sentir en sécurité et soutenu(e). "
            "Vous repérez les risques avant les autres et vous êtes d'une loyauté remarquable.",
        forces=["Loyauté et sens des responsabilités.",
                "Anticipation des risques et préparation.",
                "Esprit d'équipe et solidarité.",
                "Travail sérieux, fiable et constant.",
                "Esprit critique : vous posez les bonnes questions."],
        vigilance=["L'inquiétude peut vous faire imaginer le pire : vérifiez les faits.",
                   "Le doute peut retarder les décisions : faites-vous davantage confiance.",
                   "La méfiance initiale peut freiner de belles collaborations.",
                   "Vous n'avez pas besoin de l'avis de tous pour avancer."],
        environnement="Un cadre clair et stable, une équipe soudée et des responsables en qui vous avez confiance.",
        collaboration="Engagé(e) et protecteur(rice) : vous êtes le pilier fiable de l'équipe.",
        metiers=["Gestionnaire des risques ou analyste crédit", "Responsable administratif(ve) ou logistique", "Fonctionnaire, enseignant(e) ou agent de sécurité"],
        apporte="La fidélité, la constance et un soutien sans faille.",
        besoin="Être rassuré(e) et pouvoir compter sur l'autre.",
        tension="Le doute ou les inquiétudes qui reviennent.",
        stress="vous vous lancez dans une suractivité pour prouver votre valeur, comme un Type 3 sous tension",
        croissance="vous vous apaisez, faites confiance à la vie et aux autres, comme un Type 9 épanoui",
        defis=["Prenez une petite décision sans demander d'avis.",
               "Notez une inquiétude puis trois faits qui la relativisent.",
               "Essayez une nouveauté hors de votre routine.",
               "Faites confiance à quelqu'un pour une tâche importante.",
               "Pratiquez 5 minutes de respiration avant une situation stressante.",
               "Rappelez-vous une épreuve que vous avez surmontée.",
               "Dites à une personne de confiance ce que vous appréciez chez elle."]),
    7: dict(
        nom="L'Épicurien", motivation="Être libre, éviter la frustration",
        portrait="Enthousiaste et curieux(se), vous aimez les idées nouvelles, les expériences et la liberté.",
        qui="Votre moteur profond est la liberté et la joie de vivre : profiter de tout ce que la vie offre. Votre peur de base est "
            "d'être privé(e), enfermé(e) ou de souffrir ; votre désir de base est d'être satisfait(e) et comblé(e). "
            "Vous voyez les possibilités partout et votre optimisme est contagieux.",
        forces=["Optimisme et énergie communicative.",
                "Créativité et capacité à imaginer des solutions.",
                "Adaptabilité et rapidité de rebond.",
                "Polyvalence et curiosité.",
                "Talent pour mettre de l'ambiance et motiver."],
        vigilance=["Finir un projet compte autant que le lancer.",
                   "Fuir les émotions difficiles ne les fait pas disparaître.",
                   "Trop d'options peut vous disperser : choisissez.",
                   "Tenir ses engagements renforce la confiance des autres."],
        environnement="Un poste varié, avec de la liberté, de l'innovation et des projets qui changent souvent.",
        collaboration="Créatif(ve) et stimulant(e) : vous lancez les idées et entraînez l'équipe.",
        metiers=["Chargé(e) d'événementiel ou de communication", "Business developer ou entrepreneur(e)", "Guide, animateur(rice) ou métier du tourisme"],
        apporte="La gaieté, la spontanéité et l'envie de vivre de belles choses.",
        besoin="De la liberté et de la nouveauté.",
        tension="L'impression de fuir les sujets sérieux ou les engagements.",
        stress="vous devenez perfectionniste, critique et impatient(e), comme un Type 1 sous tension",
        croissance="vous gagnez en profondeur et en concentration, comme un Type 5 épanoui",
        defis=["Terminez un projet en cours avant d'en commencer un autre.",
               "Restez avec une émotion désagréable 5 minutes, sans distraction.",
               "Planifiez votre journée et tenez le planning.",
               "Approfondissez un seul sujet pendant une heure.",
               "Tenez un engagement pris auprès de quelqu'un.",
               "Passez une soirée simple, sans sortie ni écran.",
               "Écrivez ce qui vous rend vraiment heureux(se), au-delà de la nouveauté."]),
    8: dict(
        nom="Le Protecteur", motivation="Être fort(e), garder le contrôle de sa vie",
        portrait="Direct(e) et déterminé(e), vous prenez les choses en main et vous protégez ceux qui comptent.",
        qui="Votre moteur profond est la force et l'autonomie : rester maître de votre vie. Votre peur de base est d'être "
            "contrôlé(e), blessé(e) ou dépendant(e) ; votre désir de base est de vous protéger et de décider de votre destin. "
            "Vous avez une énergie puissante, un grand sens de la justice et le courage de dire les choses.",
        forces=["Leadership naturel et capacité de décision.",
                "Courage face aux conflits et aux difficultés.",
                "Sens de la justice et protection des plus faibles.",
                "Franchise et clarté.",
                "Énergie pour faire bouger les choses."],
        vigilance=["Votre franchise peut blesser : la forme compte aussi.",
                   "Montrer votre vulnérabilité est aussi une force.",
                   "Vouloir tout contrôler peut épuiser et éloigner les autres.",
                   "Écouter avant de trancher enrichit vos décisions."],
        environnement="Un poste à responsabilités, avec de l'autonomie et des défis à relever.",
        collaboration="Leader et protecteur(rice) : vous donnez une direction claire et vous défendez votre équipe.",
        metiers=["Manager ou directeur(rice) d'équipe", "Avocat(e) ou négociateur(rice)", "Entrepreneur(e) ou chef(fe) de chantier"],
        apporte="La protection, la loyauté et une énergie qui rassure.",
        besoin="La franchise et le respect de votre indépendance.",
        tension="L'intensité de vos réactions ou le besoin de contrôle.",
        stress="vous vous retirez, ruminez et vous isolez, comme un Type 5 sous tension",
        croissance="vous ouvrez votre cœur et mettez votre force au service des autres, comme un Type 2 épanoui",
        defis=["Laissez quelqu'un d'autre prendre une décision à votre place.",
               "Écoutez un désaccord jusqu'au bout avant de répondre.",
               "Confiez une inquiétude à un proche.",
               "Faites un geste de douceur inattendu.",
               "Demandez « qu'en penses-tu ? » au moins trois fois aujourd'hui.",
               "Reformulez une critique de façon bienveillante.",
               "Accordez-vous un vrai temps de repos."]),
    9: dict(
        nom="Le Médiateur", motivation="Préserver la paix intérieure et extérieure",
        portrait="Calme et bienveillant(e), vous rassemblez les gens et vous apaisez les tensions.",
        qui="Votre moteur profond est l'harmonie : être en paix avec vous-même et avec les autres. Votre peur de base est la perte, "
            "la séparation ou le conflit ; votre désir de base est la stabilité et la paix intérieure. Vous comprenez tous les points "
            "de vue et vous créez autour de vous un climat apaisé.",
        forces=["Écoute et ouverture d'esprit.",
                "Talent de médiation et de compromis.",
                "Calme et stabilité dans les moments difficiles.",
                "Bienveillance et acceptation des autres.",
                "Capacité à rassembler une équipe."],
        vigilance=["Éviter les conflits peut laisser les problèmes grandir.",
                   "Vos envies et opinions méritent d'être exprimées.",
                   "La procrastination freine vos projets : avancez pas à pas.",
                   "Dire oui pour la paix peut vous faire oublier vos priorités."],
        environnement="Un cadre serein, coopératif, avec des objectifs clairs et un rythme régulier.",
        collaboration="Fédérateur(rice) et conciliant(e) : vous faites travailler ensemble des personnes très différentes.",
        metiers=["Médiateur(rice) ou chargé(e) de relations sociales", "Conseiller(ère) d'orientation ou formateur(rice)", "Assistant(e) de direction ou coordinateur(rice)"],
        apporte="La douceur, la patience et une présence apaisante.",
        besoin="Un climat serein et le respect de votre rythme.",
        tension="Les non-dits accumulés pour éviter le conflit.",
        stress="vous devenez anxieux(se), méfiant(e) et indécis(e), comme un Type 6 sous tension",
        croissance="vous passez à l'action, affirmez vos objectifs et gagnez en énergie, comme un Type 3 épanoui",
        defis=["Donnez votre avis franchement sur un petit sujet.",
               "Choisissez vous-même le restaurant, le film ou l'activité.",
               "Fixez-vous trois priorités du jour et tenez-les.",
               "Abordez calmement un sujet que vous évitez.",
               "Commencez par la tâche la plus importante, pas la plus facile.",
               "Dites non à une demande qui ne fait pas partie de vos priorités.",
               "Écrivez un objectif personnel pour le mois et la première étape."]),
}


def rapport(resultat):
    """Le contenu du rapport, accordé au genre, prêt à afficher."""
    g = resultat["genre"]
    d = resultat["type_dominant"]
    T = TYPES[d]
    a = lambda x: accorder(x, g)
    stress, croissance = FLECHES[d]
    return {
        "type": d, "nom": T["nom"], "aile": resultat["aile"], "nom_aile": TYPES[resultat["aile"]]["nom"],
        "code": resultat["code"], "motivation": a(T["motivation"]), "portrait": a(T["portrait"]), "qui": a(T["qui"]),
        "forces": [a(x) for x in T["forces"]], "vigilance": [a(x) for x in T["vigilance"]],
        "environnement": a(T["environnement"]), "collaboration": a(T["collaboration"]),
        "metiers": [a(x) for x in T["metiers"]],
        "apporte": a(T["apporte"]), "besoin": a(T["besoin"]), "tension": a(T["tension"]),
        "stress_type": stress, "stress_nom": TYPES[stress]["nom"], "stress": a(T["stress"]),
        "croissance_type": croissance, "croissance_nom": TYPES[croissance]["nom"], "croissance": a(T["croissance"]),
        "defis": [a(x) for x in T["defis"]],
        "scores": [(int(t), TYPES[int(t)]["nom"], p) for t, p in
                   sorted(resultat["scores_pct"].items(), key=lambda kv: -kv[1])],
        "second": resultat["second"], "nom_second": TYPES[resultat["second"]]["nom"],
        "mixte": resultat.get("profil_mixte"), "nuance": resultat["profil_nuance"], "fiable": resultat["fiable"],
    }
