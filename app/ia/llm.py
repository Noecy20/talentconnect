"""Accès (facultatif) à une IA générative pour rédiger : retours aux candidats,
lettres de motivation, réponses de l'assistant, traductions.

Deux fournisseurs possibles, dans cet ordre :
  1. OpenRouter (OPENROUTER_API_KEY) : un seul compte pour des dizaines de modèles,
     dont beaucoup de gratuits (ceux dont l'identifiant finit par « :free »).
  2. Claude d'Anthropic (ANTHROPIC_API_KEY).
Sans aucune clé, generate() renvoie None et l'app garde ses modèles internes
(règles + extraction de passages) : rien ne casse.

Bascule automatique avec OpenRouter
-----------------------------------
Un modèle gratuit peut être saturé, limité (« rate limit »), retiré ou en panne.
On tient donc une liste de modèles à essayer :
  - d'abord ceux choisis dans OPENROUTER_MODELES (facultatif, séparés par des virgules),
  - puis tous les modèles gratuits publiés par OpenRouter (liste relue toutes les 6 h).
Quand un modèle renvoie une erreur, on le met « au repos » quelques minutes
(plus longtemps s'il a disparu) et on passe immédiatement au suivant.
Le dernier modèle qui a bien répondu est essayé en premier la fois suivante.
"""
import json
import time
import urllib.error
import urllib.request

from flask import current_app

URL_OPENROUTER = "https://openrouter.ai/api/v1"
ESSAIS_MAX = 6            # nombre de modèles essayés pour une même demande
DELAI_REQUETE = 45        # secondes avant d'abandonner un modèle trop lent

# État partagé par toutes les requêtes du processus
_catalogue = {"quand": 0, "modeles": []}   # modèles gratuits connus
_repos = {}                                 # modèle -> heure à laquelle on peut le réessayer
_dernier_bon = {"modele": None}             # dernier modèle qui a répondu correctement


# --------------------------------------------------------------------------- état
def enabled():
    c = current_app.config
    return bool(c.get("OPENROUTER_API_KEY") or c.get("ANTHROPIC_API_KEY"))


def fournisseur():
    c = current_app.config
    if c.get("OPENROUTER_API_KEY"):
        return "OpenRouter"
    if c.get("ANTHROPIC_API_KEY"):
        return "Anthropic"
    return None


def etat():
    """Résumé pour l'administration et la commande « flask ia-modeles »."""
    maintenant = time.time()
    return {
        "fournisseur": fournisseur(),
        "dernier_modele": _dernier_bon["modele"],
        "modeles": _ordre_des_modeles(),
        "au_repos": {m: round(t - maintenant) for m, t in _repos.items() if t > maintenant},
    }


# --------------------------------------------------------------------------- point d'entrée
def generate(system, prompt, max_tokens=800):
    """Renvoie le texte rédigé, ou None si aucune IA n'est disponible."""
    if current_app.config.get("OPENROUTER_API_KEY"):
        texte = _openrouter(system, prompt, max_tokens)
        if texte:
            return texte
    if current_app.config.get("ANTHROPIC_API_KEY"):
        return _anthropic(system, prompt, max_tokens)
    return None


# --------------------------------------------------------------------------- OpenRouter
def _openrouter(system, prompt, max_tokens):
    essais = 0
    for modele in _ordre_des_modeles():
        if essais >= ESSAIS_MAX:
            break
        if _repos.get(modele, 0) > time.time():
            continue
        essais += 1
        try:
            texte = _appel_openrouter(modele, system, prompt, max_tokens)
        except _ErreurModele as err:
            _mettre_au_repos(modele, err.duree)
            current_app.logger.warning("IA : %s indisponible (%s), on passe au suivant", modele, err)
            continue
        if texte:
            _dernier_bon["modele"] = modele
            return texte
        _mettre_au_repos(modele, 120)   # réponse vide : on lui laisse un peu de temps
    current_app.logger.warning("IA : aucun modèle OpenRouter n'a répondu (%s essai(s))", essais)
    return None


class _ErreurModele(Exception):
    """Erreur d'un modèle, avec la durée pendant laquelle il ne faut plus l'appeler."""
    def __init__(self, message, duree):
        super().__init__(message)
        self.duree = duree


def _appel_openrouter(modele, system, prompt, max_tokens):
    corps = {"model": modele, "max_tokens": max(max_tokens, 400),
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{URL_OPENROUTER}/chat/completions", data=json.dumps(corps).encode(),
                                 headers=_entetes(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=DELAI_REQUETE) as r:
            rep = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 429 : trop de demandes / quota du jour ; 402 : plus de crédit ; 404 : modèle retiré
        duree = {429: 10 * 60, 402: 60 * 60, 404: 6 * 3600, 400: 30 * 60}.get(e.code, 5 * 60)
        raise _ErreurModele(f"HTTP {e.code}", duree)
    except Exception as e:   # délai dépassé, réseau…
        raise _ErreurModele(str(e) or type(e).__name__, 3 * 60)

    # OpenRouter peut aussi renvoyer une erreur dans un corps « 200 »
    if rep.get("error"):
        code = (rep["error"] or {}).get("code")
        raise _ErreurModele(f"erreur {code}", 10 * 60 if code == 429 else 5 * 60)
    choix = rep.get("choices") or []
    if not choix:
        return None
    texte = ((choix[0].get("message") or {}).get("content") or "").strip()
    if choix[0].get("finish_reason") == "length" and len(texte) < 40:
        return None   # le modèle a tout dépensé à « réfléchir » : on passe au suivant
    return texte or None


def _mettre_au_repos(modele, duree):
    _repos[modele] = time.time() + duree
    if _dernier_bon["modele"] == modele:
        _dernier_bon["modele"] = None


def _ordre_des_modeles():
    """Dernier modèle qui a marché, puis les modèles choisis, puis tous les gratuits."""
    choisis = [m.strip() for m in (current_app.config.get("OPENROUTER_MODELES") or "").split(",") if m.strip()]
    ordre = []
    for m in [_dernier_bon["modele"]] + choisis + _modeles_gratuits():
        if m and m not in ordre:
            ordre.append(m)
    return ordre


def _modeles_gratuits():
    """Liste des modèles gratuits d'OpenRouter, relue toutes les 6 heures.
    Les plus grands contextes d'abord (ce sont en général les modèles les plus solides)."""
    if _catalogue["modeles"] and time.time() - _catalogue["quand"] < 6 * 3600:
        return _catalogue["modeles"]
    try:
        req = urllib.request.Request(f"{URL_OPENROUTER}/models", headers=_entetes())
        with urllib.request.urlopen(req, timeout=15) as r:
            donnees = json.loads(r.read().decode("utf-8")).get("data", [])
    except Exception as exc:
        current_app.logger.warning("IA : liste des modèles OpenRouter indisponible (%s)", exc)
        return _catalogue["modeles"]
    gratuits = []
    for m in donnees:
        if _est_gratuit(m) and _ecrit_du_texte(m):
            gratuits.append((m.get("context_length") or 0, m["id"]))
    gratuits.sort(reverse=True)
    _catalogue.update(quand=time.time(), modeles=[i for _, i in gratuits])
    return _catalogue["modeles"]


def _est_gratuit(m):
    prix = m.get("pricing") or {}
    return m.get("id", "").endswith(":free") or (
        str(prix.get("prompt")) in ("0", "0.0") and str(prix.get("completion")) in ("0", "0.0"))


# Modèles qui ne rédigent pas de texte (musique, images, voix, vecteurs) : à écarter
_MOTS_NON_TEXTE = ("lyria", "imagen", "image", "tts", "audio", "music", "embed", "whisper", "veo", "flux", "dall-e")


def _ecrit_du_texte(m):
    """Vrai si le modèle répond par du texte (« text->text », « text+image->text »…)."""
    archi = m.get("architecture") or {}
    sorties = archi.get("output_modalities")
    if sorties is not None:
        if list(sorties) != ["text"]:
            return False
    elif "->" in (archi.get("modality") or ""):
        if archi["modality"].split("->")[1].strip() != "text":
            return False
    return not any(mot in m.get("id", "").lower() for mot in _MOTS_NON_TEXTE)


def _entetes():
    return {"Authorization": f"Bearer {current_app.config['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
            # Facultatifs : font apparaître l'app dans les statistiques d'OpenRouter
            "HTTP-Referer": current_app.config.get("APP_URL") or "https://talentconnect.onrender.com",
            "X-Title": "TalentConnect"}


# --------------------------------------------------------------------------- Anthropic (Claude)
def _anthropic(system, prompt, max_tokens):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=current_app.config["LLM_MODEL"],
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as exc:  # réseau, quota, clé invalide…
        current_app.logger.warning("Claude indisponible : %s", exc)
        return None
