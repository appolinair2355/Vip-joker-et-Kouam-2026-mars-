"""
Configuration du bot Baccarat AI
=================================
Toutes les valeurs ont des FALLBACKS intégrés → le bot fonctionne sans aucune
variable d'environnement, SAUF une :

  ┌─────────────────────────────────────────────────────────────────┐
  │  SEULE VARIABLE OBLIGATOIRE SUR RENDER.COM                      │
  │  TELEGRAM_SESSION  →  chaîne de session Telethon (StringSession) │
  │  À générer une fois avec : python generate_session.py           │
  └─────────────────────────────────────────────────────────────────┘

Toutes les autres variables ci-dessous ont des valeurs par défaut codées.
Elles peuvent être surchargées via des variables d'environnement si besoin.
"""

import os

# ============================================================================
# TELEGRAM API CREDENTIALS
# Fallbacks intégrés — pas besoin de les définir sur Render
# ============================================================================

API_ID    = int(os.environ.get("API_ID")    or 29177661)
API_HASH  = os.environ.get("API_HASH")      or "a8639172fa8d35dbfd8ea46286d349ab"
BOT_TOKEN = os.environ.get("BOT_TOKEN")     or "8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU"

# NOTE : TELEGRAM_SESSION est lue directement dans main.py via os.getenv('TELEGRAM_SESSION', '')
#        C'est la seule variable qui N'A PAS de fallback → obligatoire sur Render.

# ============================================================================
# ADMIN ET CANAUX
# Fallbacks intégrés — pas besoin de les définir sur Render
# ============================================================================

ADMIN_ID              = int(os.environ.get("ADMIN_ID")              or 1190237801)
PREDICTION_CHANNEL_ID = int(os.environ.get("PREDICTION_CHANNEL_ID") or -1003329818758)

# ============================================================================
# PARAMÈTRES DU SERVEUR WEB
# PORT : Render.com l'injecte automatiquement → pas besoin de le définir
# RENDER_EXTERNAL_URL : URL publique pour le keep-alive
# ============================================================================

PORT                = int(os.environ.get("PORT") or 10000)
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL") or "https://vip-joker-et-kouam-2026-mars.onrender.com"

# ============================================================================
# CONFIGURATION COSTUMES
# ============================================================================

ALL_SUITS = ['♠', '♥', '♦', '♣']

SUIT_DISPLAY = {
    '♠': '♠️ Pique',
    '♥': '❤️ Cœur',
    '♦': '♦️ Carreau',
    '♣': '♣️ Trèfle'
}

# ============================================================================
# PARAMÈTRES COMPTEUR2
# ============================================================================

COMPTEUR2_SEUIL_B_DEFAULT = 5
COMPTEUR2_ACTIVE_DEFAULT  = True

# ============================================================================
# PARAMÈTRE DF — DÉCALAGE DE PRÉDICTION
# Quand le jeu N se termine → bot prédit le jeu N+df
# df=1 par défaut (prédit le jeu suivant immédiatement après la fin du jeu N)
# ============================================================================

PREDICTION_DF_DEFAULT = 1

# ============================================================================
# COMPTEUR9 — ACCUMULATION PAR HEURE + PRÉDICTION SUR ÉCART (SS)
# Compte les cartes joueur (carte à carte) depuis le dernier reset horaire.
# Quand count_A - count_B >= SS → prédit le costume B (le plus faible).
# Reset automatique à chaque heure pile (HH:00:00).
# ============================================================================

COMPTEUR9_SS_DEFAULT = 7

# ============================================================================
# COMPTEUR8 — ABSENCES CONSÉCUTIVES
# Même logique que C7 : C7 compte les présences ≥5, C8 les absences ≥5
# ============================================================================

COMPTEUR8_THRESHOLD = 5
COMPTEUR8_DATA_FILE = 'compteur8_data.json'

# ============================================================================
# COMPTEUR9 — PRÉDICTIONS SILENCIEUSES (persistance)
# ============================================================================

COMPTEUR9_DATA_FILE = 'compteur9_data.json'

# ============================================================================
# PARAMÈTRES DE SÉCURITÉ
# ============================================================================

FORCE_RESTART_THRESHOLD    = 20
RESET_AT_GAME_NUMBER       = 1440
PREDICTION_TIMEOUT_MINUTES = 10

# Durée (minutes) sans résultat API avant d'alerter l'admin
API_SILENCE_ALERT_MINUTES = 5

# ============================================================================
# BASE DE DONNÉES POSTGRESQL (Render.com)
#
# Sur Render (service déployé) :
#   → Render injecte DATABASE_URL automatiquement avec l'URL INTERNE
#     postgresql://...@dpg-d72p2h3uibrs73a8tojg-a/prediction_baccara
#     (pas de SSL requis pour les connexions internes Render)
#   → Le code lit DATABASE_URL en priorité (env var Render) → URL interne utilisée
#
# Sur Replit (développement) :
#   → Pas de variable DATABASE_URL → fallback vers l'URL EXTERNE ci-dessous
#     (SSL requis avec vérification désactivée pour les connexions cloud externes)
#
# ============================================================================

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or "postgresql://prediction_baccara_user:GAd3ljzVMfK3BUld9w7hHjYeQQGixTUG@dpg-d72p2h3uibrs73a8tojg-a.oregon-postgres.render.com/prediction_baccara"
)

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL") or "INFO"
