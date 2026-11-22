"""Point d'entrée : python run.py (développement) ou gunicorn run:app (production)."""
import os

from flask_migrate import upgrade

from app import create_app

app = create_app()

with app.app_context():
    # Applique automatiquement les migrations (crée les tables au premier lancement)
    upgrade(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations"))
    from app.commandes import _bootstrap
    _bootstrap(app)

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
