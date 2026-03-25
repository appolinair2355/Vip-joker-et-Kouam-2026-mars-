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
COMPTEUR9_SS_DEFAULT = 8         # Seuil d'écart entre deux costumes pour prédire

# ============================================================================
# COMPTEUR8 — ABSENCES CONSÉCUTIVES (miroir exact du Compteur7 pour les absences)
# Seuil unique : enregistre et notifie quand la série d'absences se TERMINE avec ≥ seuil
# Même logique que C7 : C7 compte les présences ≥5, C8 compte les absences ≥5
# ============================================================================
COMPTEUR8_THRESHOLD = 5          # seuil unique : comme COMPTEUR7_THRESHOLD
COMPTEUR8_DATA_FILE = 'compteur8_data.json'

# ============================================================================
# COMPTEUR9 — PRÉDICTIONS SILENCIEUSES (persistance)
# ============================================================================
COMPTEUR9_DATA_FILE = 'compteur9_data.json'   # historique des prédictions silencieuses

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
