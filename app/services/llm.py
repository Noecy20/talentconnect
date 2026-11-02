"""Accès optionnel à un LLM (Claude). Sans clé API, toutes les fonctions
renvoient None et l'app utilise ses modèles internes (règles + extraction)."""
from flask import current_app


def enabled():
    return bool(current_app.config.get("ANTHROPIC_API_KEY"))


def generate(system, prompt, max_tokens=800):
    if not enabled():
        return None
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
        current_app.logger.warning("LLM indisponible : %s", exc)
        return None
