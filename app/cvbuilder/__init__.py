"""Intègre le CV Builder historique de CVFlash (fichier cvflash.html, inchangé)
dans TalentConnect : thème terracotta, données du profil pré-chargées et
bouton « Enregistrer dans mon profil » qui synchronise le CV avec le serveur."""
import json
import os

from flask import url_for
from markupsafe import escape

from ..i18n import t

_PATH = os.path.join(os.path.dirname(__file__), "cvflash.html")


def _source():
    with open(_PATH, encoding="utf-8") as f:
        return f.read()


TERRACOTTA = "terracotta:{ink:'#3B1A0E',ink2:'#5A2C19',accent:'#D86730',soft:'#FDF0E6',border:'#F5D9C3'},"


def build_page(cv_data=None, logged_in=False, csrf=""):
    html = _source()
    html = html.replace("const THEMES={", "const THEMES={" + TERRACOTTA, 1)
    html = html.replace("theme:'bleu', template", "theme:'terracotta', template", 1)
    html = html.replace("<title>Générateur de CV — Modèle</title>", "<title>CV Builder · TalentConnect</title>", 1)
    # Couleurs de la barre d'outils aux couleurs de TalentConnect
    html = html.replace("background:#0f1a2e;color:#fff;box-shadow", "background:linear-gradient(100deg,#3B1A0E,#5A2C19);color:#fff;box-shadow", 1)
    html = html.replace("background:#132038;color:#dfe7f3", "background:#4A2414;color:#f6e6d8", 1)
    html = html.replace(".photo{position:relative;border-radius:50%;background:#22344f", ".photo{position:relative;border-radius:50%;background:#4A2414", 1)
    html = html.replace("loadSaved();\n", "loadSaved();if(window.TC_CV){Object.assign(state,window.TC_CV);}\n", 1)

    back = url_for("candidate.dashboard") if logged_in else url_for("main.index")
    brand = (f'<a href="{back}" class="btn" style="background:rgba(255,255,255,.14);font-weight:700;text-decoration:none">'
             f'← Talent<span style="color:#FFB48A">Connect</span></a>')
    html = html.replace('<div class="toolbar">', '<div class="toolbar">' + brand, 1)

    if logged_in:
        save_btn = (f'<button class="btn" id="tcSaveBtn" style="background:#D86730">💾 {escape(t("Enregistrer dans mon profil"))}</button>')
    else:
        save_btn = (f'<a class="btn" style="background:#D86730;text-decoration:none" href="{url_for("auth.register", role="candidate")}">'
                    f'✨ {escape(t("Créer un compte pour sauvegarder"))}</a>')
    html = html.replace('<button class="btn primary" id="pdfBtn">', save_btn + '<button class="btn primary" id="pdfBtn">', 1)

    data_js = json.dumps(cv_data).replace("</", "<\\/") if cv_data else "null"
    pre = f"<script>window.TC_CV={data_js};</script>\n"
    html = html.replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas', pre + '<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas', 1)

    if logged_in:
        bridge = f"""
<script>
(function(){{
  const SAVE_URL = {json.dumps(url_for('api.save_cv'))}, CSRF = {json.dumps(csrf)};
  let syncTimer = null;
  async function sync(manual){{
    try {{
      const r = await fetch(SAVE_URL, {{method:'POST', headers:{{'Content-Type':'application/json','X-CSRFToken':CSRF}}, body: JSON.stringify(state)}});
      const j = await r.json();
      if (manual) showToast(j.ok ? {json.dumps(t('CV enregistré — votre profil est à jour ✓'))} : {json.dumps(t('Erreur lors de l’enregistrement'))});
    }} catch(e) {{ if (manual) showToast({json.dumps(t('Connexion impossible, réessayez'))}); }}
  }}
  document.getElementById('tcSaveBtn').addEventListener('click', () => sync(true));
  const _ps = persistSoon;
  persistSoon = function(){{ _ps(); clearTimeout(syncTimer); syncTimer = setTimeout(() => sync(false), 4000); }};
}})();
</script>"""
        html = html.replace("</body>", bridge + "\n</body>", 1)
    return html
