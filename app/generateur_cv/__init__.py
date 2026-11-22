"""Intègre le CV Builder historique de CVFlash (fichier cvflash.html, inchangé)
dans TalentConnect.

La page CVFlash est affichée dans un cadre (iframe) à l'intérieur d'une vraie page
TalentConnect (barre de navigation en haut). Dans ce cadre :
  - sur ordinateur, les outils de modification forment une barre latérale à gauche ;
  - sur téléphone, ils restent en haut comme dans l'ancienne version.
Le thème est terracotta, le profil est pré-chargé et le bouton « Enregistrer dans
mon profil » synchronise le CV avec le serveur."""
import json
import os

from flask import url_for
from markupsafe import escape

from ..langues import t

_PATH = os.path.join(os.path.dirname(__file__), "cvflash.html")

TERRACOTTA = "terracotta:{ink:'#3B1A0E',ink2:'#5A2C19',accent:'#D86730',soft:'#FDF0E6',border:'#F5D9C3'},"

ICON_SAVE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
             '<path d="M17 21v-8H7v8M7 3v5h8"/></svg>')
ICON_USER = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M19 8v6M22 11h-6"/></svg>')

ICON_COPY = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>')

# Mise en page « barre latérale » (ordinateur) appliquée à l'intérieur du cadre
EMBED_CSS = """
<style id="tc-embed">
  html,body{font-family:'Inter',system-ui,sans-serif}
  .btn{font-family:'Inter',system-ui,sans-serif;font-weight:600}
  .tc-label{display:none}
  @media (min-width:1024px){
    body{display:grid;grid-template-columns:272px 1fr;min-height:100vh}
    .toolbar{grid-column:1;grid-row:1/span 20;position:sticky;top:0;height:100vh;overflow-y:auto;
      flex-direction:column;align-items:stretch;flex-wrap:nowrap;gap:8px;padding:18px 14px;
      background:linear-gradient(180deg,#3B1A0E,#5A2C19)!important;box-shadow:none}
    .toolbar .btn{width:100%;justify-content:flex-start;padding:11px 13px;font-size:13.5px}
    .toolbar .spacer{display:none}
    .swatches{flex-wrap:wrap;padding:10px 4px;gap:7px}
    .tc-label{display:block;font:700 10.5px 'Inter',sans-serif;letter-spacing:1.4px;text-transform:uppercase;
      color:rgba(255,255,255,.55);padding:12px 4px 2px}
    .stage{grid-column:2;padding-top:28px}
    .panel.open,.gallery.open{position:fixed;left:272px;top:0;bottom:0;width:440px;max-height:none;overflow:auto;
      z-index:70;box-shadow:12px 0 40px rgba(0,0,0,.25)}
    .toast{left:calc(50% + 136px)}
  }
</style>
"""


def _source():
    with open(_PATH, encoding="utf-8") as f:
        return f.read()


def build_page(cv_data=None, logged_in=False, csrf="", embedded=True):
    html = _source()
    html = html.replace("const THEMES={", "const THEMES={" + TERRACOTTA, 1)
    html = html.replace("theme:'bleu', template", "theme:'terracotta', template", 1)
    html = html.replace("<title>Générateur de CV — Modèle</title>", "<title>CV Builder · TalentConnect</title>", 1)
    html = html.replace("background:#0f1a2e;color:#fff;box-shadow", "background:linear-gradient(100deg,#3B1A0E,#5A2C19);color:#fff;box-shadow", 1)
    html = html.replace("background:#132038;color:#dfe7f3", "background:#4A2414;color:#f6e6d8", 1)
    html = html.replace(".photo{position:relative;border-radius:50%;background:#22344f", ".photo{position:relative;border-radius:50%;background:#4A2414", 1)
    html = html.replace("loadSaved();\n", "loadSaved();if(window.TC_CV){Object.assign(state,window.TC_CV);}\n", 1)
    html = html.replace("</head>", '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">'
                        + EMBED_CSS + "</head>", 1)
    # Liens éventuels : s'ouvrent dans la page TalentConnect, pas dans le cadre
    html = html.replace("<head>", '<head><base target="_top">', 1)

    # Intitulés de sections dans la barre latérale (visibles uniquement sur ordinateur)
    html = html.replace('<div class="toolbar">',
                        f'<div class="toolbar"><span class="tc-label">{escape(t("Modèle et contenu"))}</span>', 1)
    html = html.replace('<div class="swatches" id="swatches"></div>',
                        f'<span class="tc-label">{escape(t("Couleur"))}</span><div class="swatches" id="swatches"></div>'
                        f'<span class="tc-label">{escape(t("Actions"))}</span>', 1)

    if logged_in:
        save_btn = (f'<button class="btn" id="tcSaveBtn" style="background:#D86730">{ICON_SAVE}{escape(t("Enregistrer dans mon profil"))}</button>'
                    f'<button class="btn" id="tcVersionBtn">{ICON_COPY}{escape(t("Enregistrer comme version"))}</button>')
    else:
        save_btn = (f'<a class="btn" style="background:#D86730;text-decoration:none" target="_top" '
                    f'href="{url_for("auth.register", role="candidate")}">{ICON_USER}{escape(t("Créer un compte pour sauvegarder"))}</a>')
    html = html.replace('<button class="btn primary" id="pdfBtn">', save_btn + '<button class="btn primary" id="pdfBtn">', 1)

    data_js = json.dumps(cv_data).replace("</", "<\\/") if cv_data else "null"
    pre = f"<script>window.TC_CV={data_js};</script>\n"
    html = html.replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas',
                        pre + '<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas', 1)

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
      if (manual) showToast(j.ok ? {json.dumps(t('CV enregistré : votre profil est à jour'))} : {json.dumps(t('Erreur lors de l’enregistrement'))});
    }} catch(e) {{ if (manual) showToast({json.dumps(t('Connexion impossible, réessayez'))}); }}
  }}
  document.getElementById('tcSaveBtn').addEventListener('click', () => sync(true));
  const _ps = persistSoon;
  persistSoon = function(){{ _ps(); clearTimeout(syncTimer); syncTimer = setTimeout(() => sync(false), 4000); }};
  document.getElementById('tcVersionBtn').addEventListener('click', async () => {{
    const name = prompt({json.dumps(t("Nom de cette version (ex. : CV Data Analyst — Québec)"))});
    if (!name) return;
    try {{ const j = await window.tcSaveVersion(name); showToast(j.ok ? {json.dumps(t("Version enregistrée : vous pouvez l'associer à une candidature"))} : {json.dumps(t("Erreur lors de l’enregistrement"))}); }}
    catch(e) {{ showToast({json.dumps(t("Connexion impossible, réessayez"))}); }}
  }});
  window.tcSaveVersion = async function(name){{
    const r = await fetch({json.dumps(url_for('api.save_cv_version'))}, {{method:'POST', headers:{{'Content-Type':'application/json','X-CSRFToken':CSRF}},
      body: JSON.stringify({{name: name, data: state}})}});
    return r.json();
  }};
}})();
</script>"""
        html = html.replace("</body>", bridge + "\n</body>", 1)
    return html
