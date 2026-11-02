"""Internationalisation légère : les textes sources sont en français,
chaque langue a un fichier JSON {"texte français": "traduction"} dans app/translations/.
Ajouter une langue = ajouter un fichier JSON (ou `flask translate <code>` avec une clé IA)."""
import json
import os

from flask import g, request, session
from flask_login import current_user

TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), "translations")

LANGUAGES = {
    "fr": {"name": "Français", "flag": "🇫🇷", "dir": "ltr"},
    "en": {"name": "English", "flag": "🇬🇧", "dir": "ltr"},
    "es": {"name": "Español", "flag": "🇪🇸", "dir": "ltr"},
    "pt": {"name": "Português", "flag": "🇵🇹", "dir": "ltr"},
}

_cache = {}


def _load(lang):
    if lang not in _cache:
        path = os.path.join(TRANSLATIONS_DIR, f"{lang}.json")
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            # les textes extraits du code contiennent « \n » littéral : on les convertit en vrais retours à la ligne
            _cache[lang] = {k.replace("\\n", "\n"): v.replace("\\n", "\n") for k, v in raw.items()}
        except FileNotFoundError:
            _cache[lang] = {}
    return _cache[lang]


def available_languages():
    langs = dict(LANGUAGES)
    if os.path.isdir(TRANSLATIONS_DIR):
        for fn in os.listdir(TRANSLATIONS_DIR):
            code = fn.rsplit(".", 1)[0]
            if fn.endswith(".json") and code not in langs:
                langs[code] = {"name": code.upper(), "flag": "🌐", "dir": "rtl" if code in ("ar", "he", "fa") else "ltr"}
    return langs


def get_locale():
    langs = available_languages()
    lang = request.args.get("lang")
    if lang in langs:
        session["lang"] = lang
        return lang
    if current_user.is_authenticated and current_user.language in langs:
        return current_user.language
    if session.get("lang") in langs:
        return session["lang"]
    best = request.accept_languages.best_match(list(langs.keys()))
    return best or "fr"


def t(text, **kwargs):
    lang = getattr(g, "lang", "fr")
    out = text if lang == "fr" else _load(lang).get(text, text)
    if kwargs:
        try:
            out = out.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return out


def reload():
    _cache.clear()
