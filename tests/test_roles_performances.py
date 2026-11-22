"""Vérifie l'isolation des rôles et mesure le temps de traitement serveur des pages principales.

Prérequis : base de démonstration (flask --app run.py seed-demo).
Usage : python tests/test_roles_performances.py
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402

app = create_app()
app.config["WTF_CSRF_ENABLED"] = False


def client(email=None, pw="Demo1234!"):
    c = app.test_client()
    if email:
        c.post("/auth/connexion", data={"email": email, "password": pw})
    return c


cand, rec, anon = client("aicha.kone@demo.tc"), client("awa.traore@demo.tc"), client()
CHECKS = [
    ("candidat -> /admin/", cand, "/admin/", 403), ("candidat -> /recruteur/", cand, "/recruteur/", 403),
    ("recruteur -> /candidat/", rec, "/candidat/", 403), ("recruteur -> /admin/paiements", rec, "/admin/paiements", 403),
    ("anonyme -> /candidat/ (redirigé vers la connexion)", anon, "/candidat/", 302),
    ("anonyme -> /admin/ (redirigé vers la connexion)", anon, "/admin/", 302),
]
ok = 0
print("Isolation des rôles")
for name, c, url, expected in CHECKS:
    status = c.get(url).status_code
    ok += status == expected
    print(f"  {name:52s} {status}  {'OK' if status == expected else 'ÉCHEC'}")
print(f"  -> {ok}/{len(CHECKS)} contrôles réussis\n")

print("Temps de traitement serveur (médiane de 5 mesures, hors réseau)")
for c, url in [(anon, "/"), (cand, "/candidat/"), (cand, "/candidat/offres"), (cand, "/candidat/offres/3"),
               (cand, "/candidat/suivi/"), (rec, "/recruteur/"), (rec, "/recruteur/offres/3/tri")]:
    times = []
    for _ in range(5):
        t = time.perf_counter()
        c.get(url)
        times.append((time.perf_counter() - t) * 1000)
    print(f"  {url:28s} {statistics.median(times):6.0f} ms")
