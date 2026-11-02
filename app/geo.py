"""Pays, devises et villes pour une app internationale.
Les noms de pays sont traduits dans la langue de l'utilisateur (Babel) et
la devise suit automatiquement le pays (ex : CI -> XOF, FR -> EUR, CA -> CAD)."""
from functools import lru_cache

from babel import Locale
from babel.numbers import format_currency, format_decimal, get_currency_symbol, get_territory_currencies
import geonamescache

_gc = geonamescache.GeonamesCache()

# Pays mis en avant en tête de liste
PRIORITY = ["CI", "SN", "CM", "BF", "ML", "TG", "BJ", "GN", "NE", "GA", "CG", "CD", "MA", "TN", "DZ",
            "FR", "BE", "CA", "CH", "US", "GB", "DE", "ES", "PT", "GH", "NG", "KE", "RW", "ZA"]


@lru_cache(maxsize=16)
def countries(lang="fr"):
    try:
        names = Locale.parse(lang).territories
    except Exception:
        names = Locale.parse("fr").territories
    codes = [c for c in _gc.get_countries().keys()]
    items = [(c, names.get(c, _gc.get_countries()[c]["name"])) for c in codes]
    pri = [i for c in PRIORITY for i in items if i[0] == c]
    rest = sorted([i for i in items if i[0] not in PRIORITY], key=lambda x: x[1])
    return pri + rest


def country_name(code, lang="fr"):
    if not code:
        return ""
    try:
        return Locale.parse(lang).territories.get(code, code)
    except Exception:
        return code


@lru_cache(maxsize=512)
def currency_for(code):
    try:
        cur = get_territory_currencies(code or "CI")
        return cur[0] if cur else "USD"
    except Exception:
        return "USD"


def money(amount, currency="XOF", lang="fr"):
    if amount is None or amount == "":
        return ""
    try:
        if float(amount).is_integer():
            # Montants entiers : pas de décimales (900 000 F CFA, 3 000 €)
            return f"{format_decimal(int(amount), locale=lang)} {get_currency_symbol(currency, locale=lang)}".replace("\u202f", " ").replace("\xa0", " ")
        return format_currency(amount, currency, locale=lang).replace("\xa0", " ")
    except Exception:
        return f"{amount:,} {currency}".replace(",", " ")


@lru_cache(maxsize=256)
def cities(code, limit=400):
    rows = [c for c in _gc.get_cities().values() if c["countrycode"] == code]
    rows.sort(key=lambda c: -c["population"])
    return [{"name": c["name"], "lat": c["latitude"], "lng": c["longitude"]} for c in rows[:limit]]


def city_coords(code, name):
    if not name:
        return None
    for c in cities(code):
        if c["name"].lower() == name.lower():
            return c["lat"], c["lng"]
    return None
