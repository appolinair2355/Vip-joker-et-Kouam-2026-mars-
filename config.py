"""
Configuration du bot Baccarat AI
Toutes les valeurs sont lues depuis les variables d'environnement.
Sur Render.com : définir ces variables dans Dashboard > Environment.
"""

import os

# ============================================================================
# TELEGRAM API CREDENTIALS
# ============================================================================

API_ID   = int(os.environ.get("API_ID") or 29177661)
API_HASH  = os.environ.get("API_HASH")  or "a8639172fa8d35dbfd8ea46286d349ab"
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU"

# ============================================================================
# ADMIN ET CANAUX
# ============================================================================

ADMIN_ID             = int(os.environ.get("ADMIN_ID")             or 1190237801)
PREDICTION_CHANNEL_ID = int(os.environ.get("PREDICTION_CHANNEL_ID") or -1003329818758)

# ============================================================================
# PARAMÈTRES DU SERVEUR WEB
# PORT              : 10000 par défaut (valeur attendue par Render.com)
# RENDER_EXTERNAL_URL : URL publique du service sur Render.com (pour le keep-alive)
# ============================================================================

PORT               = int(os.environ.get("PORT") or 10000)
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

COMPTEUR2_SEUIL_B_DEFAULT = 2
COMPTEUR2_ACTIVE_DEFAULT  = True

# ============================================================================
# PARAMÈTRES DE SÉCURITÉ
# ============================================================================

FORCE_RESTART_THRESHOLD   = 20
RESET_AT_GAME_NUMBER      = 1440
PREDICTION_TIMEOUT_MINUTES = 10

# Durée (minutes) sans résultat API avant d'alerter l'admin
API_SILENCE_ALERT_MINUTES = 5

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL") or "INFO"
