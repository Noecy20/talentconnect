"""Tout ce qui relève de l'intelligence artificielle dans TalentConnect.

- scores.py        : scores de compatibilité, d'employabilité, d'éligibilité des parrains
                     et probabilité d'être contacté (règles pondérées réglables par l'admin)
- modele_rappel.py : modèle d'apprentissage entraîné sur de vraies candidatures
                     (voir ml/entrainer_modele_rappel.py) ; le modèle est dans modele_rappel.joblib
- orientation.py   : test d'orientation RIASEC et métiers recommandés
- llm.py           : IA générative (facultatif) : OpenRouter avec bascule automatique
                     entre modèles gratuits, ou Claude (clé ANTHROPIC_API_KEY)
- rag.py           : l'assistant qui répond à partir du profil (recherche + génération)
"""
