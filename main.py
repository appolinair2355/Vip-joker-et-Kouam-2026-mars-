import os
import asyncio
import re
import logging
import sys
import io
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple
from datetime import datetime, timedelta
from telethon import TelegramClient, events, utils
from telethon.sessions import StringSession
from telethon.errors import ChatWriteForbiddenError, UserBannedInChannelError
from aiohttp import web
from fpdf import FPDF

from config import (
    API_ID, API_HASH, BOT_TOKEN, ADMIN_ID,
    PREDICTION_CHANNEL_ID, PORT,
    ALL_SUITS, SUIT_DISPLAY
)
from api_utils import get_latest_results
from parole import get_parole

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

if not API_ID or API_ID == 0:
    logger.error("API_ID manquant")
    exit(1)
if not API_HASH:
    logger.error("API_HASH manquant")
    exit(1)
if not BOT_TOKEN:
    logger.error("BOT_TOKEN manquant")
    exit(1)

# ============================================================================
# VARIABLES GLOBALES
# ============================================================================

pending_predictions: Dict[int, dict] = {}
current_game_number = 0
last_prediction_time: Optional[datetime] = None
prediction_channel_ok = False
client = None
suit_block_until: Dict[str, datetime] = {}

# Historique API des jeux
game_history: Dict[int, dict] = {}

# Cache live : stocke TOUS les jeux (en cours + terminés) tels que retournés par l'API.
# Mis à jour à chaque poll ; sert de filet de sécurité pour les rattrapages.
# Nettoyé automatiquement après vérification ou quand le cache dépasse 200 entrées.
game_result_cache: Dict[int, dict] = {}

processed_games: Set[int] = set()  # Jeux déjà comptabilisés (compteur2, compteur4)
prediction_checked_games: Set[int] = set()  # Jeux dont les prédictions ont été vérifiées

# Compteur2 - Gestion des costumes manquants
compteur2_trackers: Dict[str, 'Compteur2Tracker'] = {}
compteur2_seuil_B = 2                        # B défini par l'admin (référence de base)
compteur2_seuil_B_per_suit: Dict[str, int] = {s: 2 for s in ('♠', '♥', '♦', '♣')}  # B dynamique par costume (démarre au B admin)
compteur2_active = True

# Événements PERDU — pour PDF analyse horaire
perdu_events: List[Dict] = []
perdu_pdf_msg_id: Optional[int] = None

# Bilan automatique vers le canal de prédiction
bilan_interval_minutes: int = 60  # Actif par défaut — envoie à chaque heure pile
bilan_task: Optional[asyncio.Task] = None
bilan_1440_sent: bool = False  # Évite le double envoi au jeu #1440

# Mode d'emploi automatique vers le canal de prédiction
MODE_EMPLOI_DEFAULT = """📌 *MODE D'EMPLOI DU BOT DE PRÉDICTION – BACCARAT (CARTES ENSEIGNES)*

🎯 *Principe de fonctionnement*
Le bot a pour vocation de prédire les cartes suivantes :
♠️ (Pique), ♦️ (Carreau), ♣️ (Trèfle), ❤️ (Cœur).

🕹️ *Procédure d'utilisation*
*Identification du numéro de jeu*
Le bot affiche, en tête, un numéro correspondant à une manche spécifique.
Il convient de se rendre sur votre plateforme de jeu (bookmaker), dans la section Baccarat, afin de retrouver ce numéro.

*Exécution de la prédiction*
Sélectionnez l'option :
👉 « Le joueur reçoit une carte enseigne »
Puis, choisissez la carte indiquée par le bot.

🔁 *Conduite à tenir en cas d'échec*
Dans l'éventualité où la prédiction ne se réalise pas, il est recommandé de :
👉 Se référer immédiatement au numéro suivant, affiché en bas des prédictions, et de rejouer en conséquence.

⚠️ *Recommandations stratégiques*
Il est fortement conseillé d'attendre que le bot enregistre une première perte avant d'entamer toute mise.
Toutefois, les utilisateurs les plus confiants peuvent intervenir dès la première prédiction.
Le bot émet quatre prédictions consécutives, suivies d'une pause.
Cette interruption permet de distinguer clairement les séries de prédictions et d'optimiser leur suivi.

💰 *Plan de mise (progression recommandée)*
Il est impératif de respecter la séquence de mises suivante :
• 500 FCFA
• 1 200 FCFA
• 2 500 FCFA
• 5 500 FCFA
• 12 000 FCFA
• 25 000 FCFA
👉 En cas de gain, il convient de revenir à la mise initiale.

🧠 *Conseils essentiels*
• Respectez rigoureusement le plan de mise établi.
• Évitez toute prise de décision impulsive ou non stratégique.
• Limitez-vous à un maximum de quatre prédictions par jour.
• Ne dépassez en aucun cas les six niveaux de mise définis."""

mode_emploi_text: str = MODE_EMPLOI_DEFAULT        # Texte modifiable par l'admin
mode_emploi_interval_hours: int = 4               # Intervalle en heures (0 = désactivé)

# Compteur1 - Gestion des costumes présents consécutifs
compteur1_trackers: Dict[str, 'Compteur1Tracker'] = {}
compteur1_history: List[Dict] = []
MIN_CONSECUTIVE_FOR_STATS = 3

# Gestion des écarts entre prédictions
MIN_GAP_BETWEEN_PREDICTIONS = 4
last_prediction_number_sent = 0

# Historiques
finalized_messages_history: List[Dict] = []
MAX_HISTORY_SIZE = 50
prediction_history: List[Dict] = []

# File d'attente de prédictions
prediction_queue: List[Dict] = []
PREDICTION_SEND_AHEAD = 2

# Tâches d'animation en cours (original_game → asyncio.Task)
animation_tasks: Dict[int, asyncio.Task] = {}

# Canaux secondaires
DISTRIBUTION_CHANNEL_ID = None
COMPTEUR2_CHANNEL_ID = None

# ============================================================================
# SYSTÈME DE RESTRICTION HORAIRE
# ============================================================================

# Liste de fenêtres (start_hour, end_hour) pendant lesquelles les prédictions sont AUTORISÉES
# Si la liste est vide: pas de restriction
PREDICTION_HOURS: List[Tuple[int, int]] = []

def is_prediction_time_allowed() -> bool:
    """Retourne True si les prédictions sont autorisées à l'heure actuelle."""
    if not PREDICTION_HOURS:
        return True
    now = datetime.now()
    current_min = now.hour * 60 + now.minute
    for (start_h, end_h) in PREDICTION_HOURS:
        start_min = start_h * 60
        end_min = end_h * 60
        if start_min == end_min:
            return True  # Fenêtre nulle = toujours autorisé
        if start_min < end_min:
            if start_min <= current_min < end_min:
                return True
        else:
            # Fenêtre qui passe minuit (ex: 23-0 ou 18-17)
            if current_min >= start_min or current_min < end_min:
                return True
    return False

def format_hours_config() -> str:
    if not PREDICTION_HOURS:
        return "✅ Aucune restriction (prédictions 24h/24)"
    lines = []
    for i, (s, e) in enumerate(PREDICTION_HOURS, 1):
        lines.append(f"  {i}. {s:02d}h00 → {e:02d}h00")
    return "\n".join(lines)

# ============================================================================
# SYSTÈME COMPTEUR4 - ÉCARTS DE 10+
# ============================================================================

COMPTEUR4_THRESHOLD = 10  # Seuil d'absences consécutives
COMPTEUR4_DATA_FILE  = 'compteur4_data.json'  # Persistant entre resets (comme C7)
compteur4_trackers: Dict[str, int] = {'♠': 0, '♥': 0, '♦': 0, '♣': 0}
compteur4_events: List[Dict] = []  # Événements terminés persistants
compteur4_pdf_msg_id: Optional[int] = None  # ID du message PDF envoyé à l'admin

# État courant de la série d'absences (pour suivre debut_game, comme C7)
compteur4_current: Dict[str, dict] = {
    suit: {'count': 0, 'start_game': None, 'start_time': None, 'alerted': False}
    for suit in ('♠', '♥', '♦', '♣')
}

# ============================================================================
# SYSTÈME COMPTEUR5 - PRÉSENCES CONSÉCUTIVES DE 10+
# ============================================================================
COMPTEUR5_THRESHOLD = 10  # Seuil de présences consécutives
compteur5_trackers: Dict[str, int] = {'♠': 0, '♥': 0, '♦': 0, '♣': 0}
compteur5_events: List[Dict] = []  # Événements enregistrés
compteur5_pdf_msg_id: Optional[int] = None  # ID du message PDF envoyé à l'admin

# ============================================================================
# SYSTÈME COMPTEUR6 - FILTRE DE PRÉDICTION PAR PAIRES INVERSES
# ============================================================================
# Paires inverses : ❤️ ↔ ♦️  et  ♣️ ↔ ♠️
# Logique : avant de prédire X, on vérifie si PAIR[X] est apparu Wj fois.
#           Oui → confirmer X | Non → prédire PAIR[X] à la place
compteur6_seuil_Wj: int = 2                      # Seuil Wj (modifiable par admin)
compteur6_trackers: Dict[str, int] = {           # Compteur d'apparitions par costume
    '♠': 0, '♥': 0, '♦': 0, '♣': 0
}
COMPTEUR6_PAIRS: Dict[str, str] = {             # Paires inverses
    '♦': '♠', '♠': '♦',
    '♣': '♥', '♥': '♣',
}

# ============================================================================
# SYSTÈME COMPTEUR7 — SÉRIES CONSÉCUTIVES (MIN 5) — PERSISTANT ENTRE RESETS
# ============================================================================
COMPTEUR7_THRESHOLD = 5                          # Seuil minimum de présences consécutives
COMPTEUR7_DATA_FILE = 'compteur7_data.json'      # Fichier persistant (survit aux resets)
HOURLY_DATA_FILE    = 'hourly_suit_data.json'    # Données horaires pour /comparaison

# État courant : pour chaque costume, série en cours
compteur7_current: Dict[str, dict] = {
    suit: {'count': 0, 'start_game': None, 'start_time': None}
    for suit in ('♠', '♥', '♦', '♣')
}
compteur7_completed: List[Dict] = []             # Séries terminées (≥ seuil), persistantes
compteur7_pdf_msg_id: Optional[int] = None       # ID du dernier PDF envoyé à l'admin

# Données horaires cumulées pour /comparaison (heure→costume→nb)
hourly_suit_data:  Dict[int, Dict[str, int]] = {h: {'♠': 0, '♥': 0, '♦': 0, '♣': 0} for h in range(24)}
hourly_game_count: Dict[int, int]            = {h: 0 for h in range(24)}

def generate_compteur4_pdf(events_list: List[Dict]) -> bytes:
    """Génère un PDF avec le tableau des écarts Compteur4 (format série comme C7)."""
    suit_names_map = {'♠': 'Pique', '♥': 'Coeur', '♦': 'Carreau', '♣': 'Trefle'}
    suit_colors = {
        '♠': (30, 30, 30),
        '♥': (180, 0, 0),
        '♦': (0, 80, 180),
        '♣': (0, 120, 0),
    }

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_fill_color(120, 30, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, 'BACCARAT AI - Absences Consecutives Compteur 4', ln=True, align='C', fill=True)
    pdf.ln(4)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6,
        f'Seuil: {COMPTEUR4_THRESHOLD} absences consecutives | '
        f'Genere le {datetime.now().strftime("%d/%m/%Y %H:%M")} | '
        f'Total: {len(events_list)} serie(s) | PERSISTANT',
        ln=True, align='C'
    )
    pdf.ln(6)

    col_widths = [32, 22, 22, 32, 32, 26]
    headers    = ['Date', 'Heure', 'Costume', 'Debut', 'Fin', 'Nb fois']

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_fill_color(120, 30, 0)
    pdf.set_text_color(255, 255, 255)
    for header, width in zip(headers, col_widths):
        pdf.cell(width, 9, header, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 11)
    alt = False
    for ev in events_list:
        suit      = ev.get('suit', '')
        r, g, b   = suit_colors.get(suit, (0, 0, 0))
        date_str  = ev['end_time'].strftime('%d/%m/%Y')
        time_str  = ev['end_time'].strftime('%Hh%M')
        suit_name = suit_names_map.get(suit, suit)
        start_str = f"#{ev['start_game']}"
        end_str   = f"#{ev['end_game']}"
        count_str = f"{ev['count']}x"

        bg = (255, 240, 235) if alt else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.set_text_color(0, 0, 0)

        pdf.cell(col_widths[0], 9, date_str, border=1, fill=alt, align='C')
        pdf.cell(col_widths[1], 9, time_str, border=1, fill=alt, align='C')

        pdf.set_text_color(r, g, b)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(col_widths[2], 9, suit_name, border=1, fill=alt, align='C')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(0, 0, 0)

        pdf.cell(col_widths[3], 9, start_str, border=1, fill=alt, align='C')
        pdf.cell(col_widths[4], 9, end_str,   border=1, fill=alt, align='C')

        pdf.set_text_color(r, g, b)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(col_widths[5], 9, count_str, border=1, fill=alt, align='C')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(0, 0, 0)

        pdf.ln()
        alt = not alt

    if not events_list:
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, 'Aucune serie d absence enregistree', border=1, align='C')
        pdf.ln()

    pdf.ln(8)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_fill_color(120, 30, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, 'Resume par costume', ln=True, fill=True, align='C')
    pdf.ln(3)
    from collections import Counter
    suit_counts = Counter(ev.get('suit', '') for ev in events_list)
    for suit in ['♠', '♥', '♦', '♣']:
        r, g, b = suit_colors.get(suit, (0, 0, 0))
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(r, g, b)
        name = suit_names_map.get(suit, suit)
        cnt  = suit_counts.get(suit, 0)
        pdf.cell(0, 8, f'  {name} : {cnt} serie(s) de {COMPTEUR4_THRESHOLD}+ absences', ln=True)

    pdf.ln(5)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6,
        f'BACCARAT AI - PERSISTANT - Reset #1440 ne supprime PAS ce fichier - '
        f'{datetime.now().strftime("%d/%m/%Y %H:%M")}',
        ln=True, align='C'
    )
    return bytes(pdf.output())

async def send_compteur4_threshold_alert(suit: str, game_number: int, start_game: int):
    """Envoie une alerte immédiate à l'admin quand le seuil de 10 absences est atteint (série en cours)."""
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    suit_emoji_map = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}
    suit_names_map = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
    try:
        admin_entity = await client.get_entity(ADMIN_ID)
        now   = datetime.now()
        emoji = suit_emoji_map.get(suit, suit)
        name  = suit_names_map.get(suit, suit)
        msg = (
            f"🚨 **COMPTEUR 4 — SEUIL ATTEINT**\n\n"
            f"{now.strftime('%d/%m/%Y')} à {now.strftime('%Hh%M')} "
            f"{emoji} **{COMPTEUR4_THRESHOLD} fois absent** — numéro **{start_game}_{game_number}**\n\n"
            f"_{name} absent depuis le jeu #{start_game}. La série continue…_"
        )
        await client.send_message(admin_entity, msg, parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Erreur send_compteur4_threshold_alert: {e}")


async def send_compteur4_series_alert(series: Dict):
    """Envoie la notification finale quand une série d'absences Compteur4 se termine."""
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    suit_emoji_map = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}
    suit_names_map = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
    try:
        admin_entity = await client.get_entity(ADMIN_ID)
        suit     = series['suit']
        emoji    = suit_emoji_map.get(suit, suit)
        name     = suit_names_map.get(suit, suit)
        end_time = series['end_time']
        msg = (
            f"🔴 **COMPTEUR 4 — SÉRIE TERMINÉE**\n\n"
            f"{end_time.strftime('%d/%m/%Y')} à {end_time.strftime('%Hh%M')} "
            f"{emoji} **{series['count']} fois** du numéro "
            f"**{series['start_game']}_{series['end_game']}**\n\n"
            f"_{name} absent {series['count']} fois consécutives._\n\n"
            f"📄 PDF mis à jour ci-dessous."
        )
        await client.send_message(admin_entity, msg, parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Erreur send_compteur4_series_alert: {e}")


async def send_compteur4_pdf():
    """Génère et envoie (ou remplace) le PDF Compteur4 à l'admin."""
    global compteur4_pdf_msg_id

    if not ADMIN_ID or ADMIN_ID == 0:
        logger.warning("⚠️ ADMIN_ID non configuré, PDF non envoyé")
        return

    try:
        pdf_bytes = generate_compteur4_pdf(compteur4_events)
        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.name = "compteur4_ecarts.pdf"

        admin_entity = await client.get_entity(ADMIN_ID)

        # Supprimer l'ancien message PDF si il existe
        if compteur4_pdf_msg_id:
            try:
                await client.delete_messages(admin_entity, [compteur4_pdf_msg_id])
                logger.info(f"🗑️ Ancien PDF supprimé (msg {compteur4_pdf_msg_id})")
            except Exception as e:
                logger.warning(f"⚠️ Impossible de supprimer ancien PDF: {e}")
            compteur4_pdf_msg_id = None

        caption = (
            f"🔴 **COMPTEUR4 — PDF mis à jour**\n\n"
            f"Total séries d'absences enregistrées : **{len(compteur4_events)}**\n"
            f"Seuil : **≥ {COMPTEUR4_THRESHOLD}** absences consécutives\n"
            f"⚠️ Ce PDF persiste entre tous les resets\n"
            f"Mis à jour : {datetime.now().strftime('%d/%m/%Y %Hh%M')}"
        )

        sent = await client.send_file(
            admin_entity,
            pdf_buffer,
            caption=caption,
            parse_mode='markdown',
            attributes=[],
            file_name="compteur4_absences.pdf"
        )
        compteur4_pdf_msg_id = sent.id
        logger.info(f"✅ PDF Compteur4 envoyé à l'admin (msg {compteur4_pdf_msg_id})")

    except Exception as e:
        logger.error(f"❌ Erreur envoi PDF: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ============================================================================
# COMPTEUR5 — PRÉSENCES CONSÉCUTIVES
# ============================================================================

def generate_compteur5_pdf(events_list: List[Dict]) -> bytes:
    """Génère un PDF avec le tableau des présences consécutives Compteur5."""
    suit_names_map = {'♠': 'Pique', '♥': 'Coeur', '♦': 'Carreau', '♣': 'Trefle'}
    suit_colors = {
        '♠': (30, 30, 30),
        '♥': (180, 0, 0),
        '♦': (0, 80, 180),
        '♣': (0, 120, 0),
    }

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_fill_color(0, 100, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, 'BACCARAT AI - Presences Consecutives Compteur 5', ln=True, align='C', fill=True)
    pdf.ln(4)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6,
        f'Seuil: {COMPTEUR5_THRESHOLD} presences consecutives | '
        f'Genere le {datetime.now().strftime("%d/%m/%Y %H:%M")} | '
        f'Total: {len(events_list)} evenement(s)',
        ln=True, align='C'
    )
    pdf.ln(6)

    col_widths = [38, 22, 32, 42, 56]
    headers    = ['Date', 'Heure', 'Numero jeu', 'Costume present', 'Autres cartes']

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_fill_color(0, 100, 50)
    pdf.set_text_color(255, 255, 255)
    for header, width in zip(headers, col_widths):
        pdf.cell(width, 9, header, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 11)
    alt = False
    for ev in events_list:
        present_suit = ev.get('suit', '')
        r, g, b = suit_colors.get(present_suit, (0, 0, 0))

        date_str  = ev['datetime'].strftime('%d/%m/%Y')
        time_str  = ev['datetime'].strftime('%Hh%M')
        game_str  = str(ev['game_number'])
        suit_name = suit_names_map.get(present_suit, present_suit)
        others    = ' | '.join(
            suit_names_map.get(s, s)
            for s in ev.get('player_suits', [])
            if s != present_suit
        ) or '-'

        pdf.set_fill_color(*(240, 255, 240) if alt else (255, 255, 255))
        pdf.set_text_color(0, 0, 0)
        pdf.cell(col_widths[0], 9, date_str, border=1, fill=alt, align='C')
        pdf.cell(col_widths[1], 9, time_str, border=1, fill=alt, align='C')
        pdf.cell(col_widths[2], 9, game_str, border=1, fill=alt, align='C')

        pdf.set_text_color(r, g, b)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(col_widths[3], 9, suit_name, border=1, fill=alt, align='C')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(col_widths[4], 9, others, border=1, fill=alt, align='C')
        pdf.ln()
        alt = not alt

    if not events_list:
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, 'Aucune presence consecutive enregistree', border=1, align='C')
        pdf.ln()

    # Résumé par costume
    pdf.ln(8)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_fill_color(0, 100, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, 'Resume par costume', ln=True, fill=True, align='C')
    pdf.ln(3)
    from collections import Counter as _Counter
    suit_counts = _Counter(ev.get('suit', '') for ev in events_list)
    for suit in ['♠', '♥', '♦', '♣']:
        r, g, b = suit_colors.get(suit, (0, 0, 0))
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(r, g, b)
        name = suit_names_map.get(suit, suit)
        cnt  = suit_counts.get(suit, 0)
        pdf.cell(0, 8, f'  {name} : {cnt} fois le seuil de {COMPTEUR5_THRESHOLD} atteint', ln=True)

    pdf.ln(5)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6, f'BACCARAT AI - CONFIDENTIEL - {datetime.now().strftime("%d/%m/%Y %H:%M")}', ln=True, align='C')

    return bytes(pdf.output())


async def send_compteur5_alert(triggered_suits: List[str], game_number: int):
    """Envoie une notification texte immédiate à l'admin quand le seuil C5 est atteint."""
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    suit_emoji_map = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}
    suit_names_map = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
    try:
        admin_entity = await client.get_entity(ADMIN_ID)
        now = datetime.now()
        lines = ["✅ **COMPTEUR 5 — PRÉSENT 10 FOIS**", ""]
        for suit in triggered_suits:
            emoji = suit_emoji_map.get(suit, suit)
            lines.append(
                f"Le {now.strftime('%d/%m/%Y')} A {now.strftime('%Hh%M')} "
                f"{emoji} Numéro {game_number}"
            )
        lines += [
            "",
            f"_{suit_names_map.get(triggered_suits[0], triggered_suits[0])} "
            f"présent **{COMPTEUR5_THRESHOLD} fois consécutives**._",
            "",
            "📄 PDF mis à jour ci-dessous."
        ]
        await client.send_message(admin_entity, "\n".join(lines), parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Erreur send_compteur5_alert: {e}")


async def send_compteur5_pdf():
    """Génère et envoie (ou remplace) le PDF Compteur5 à l'admin."""
    global compteur5_pdf_msg_id
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    try:
        pdf_bytes = generate_compteur5_pdf(compteur5_events)
        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.name = "compteur5_presences.pdf"
        admin_entity = await client.get_entity(ADMIN_ID)

        if compteur5_pdf_msg_id:
            try:
                await client.delete_messages(admin_entity, [compteur5_pdf_msg_id])
            except Exception as e:
                logger.debug(f"Suppression ancien PDF C5 ignorée: {e}")
            compteur5_pdf_msg_id = None

        caption = (
            f"✅ **COMPTEUR5 — PDF mis à jour**\n\n"
            f"Total présences consécutives enregistrées : **{len(compteur5_events)}**\n"
            f"Seuil actuel : **{COMPTEUR5_THRESHOLD}** présences consécutives\n"
            f"Mis à jour : {datetime.now().strftime('%d/%m/%Y %Hh%M')}"
        )
        sent = await client.send_file(
            admin_entity, pdf_buffer,
            caption=caption, parse_mode='markdown',
            attributes=[], file_name="compteur5_presences.pdf"
        )
        compteur5_pdf_msg_id = sent.id
        logger.info(f"✅ PDF Compteur5 envoyé à l'admin")
    except Exception as e:
        logger.error(f"❌ Erreur send_compteur5_pdf: {e}")
        import traceback; logger.error(traceback.format_exc())


# ============================================================================
# PDF PERDU + ANALYSE HORAIRE + ANALYSE CROISÉE PAR DATE
# ============================================================================

def _group_hours_into_ranges(sorted_hours: List[int]) -> List[Tuple[int, int]]:
    """Regroupe une liste d'heures triées en plages consécutives."""
    if not sorted_hours:
        return []
    ranges = []
    start = end = sorted_hours[0]
    for h in sorted_hours[1:]:
        if h == end + 1:
            end = h
        else:
            ranges.append((start, end))
            start = end = h
    ranges.append((start, end))
    return ranges


def _analyse_perdu_heures(events: List[Dict]) -> List[str]:
    """Analyse les heures de perte et retourne des conseils (plages à éviter)."""
    from collections import Counter
    if not events:
        return []
    hour_counts = Counter(ev['time'].hour for ev in events)
    total = len(events)
    danger_hours = sorted(
        [h for h, c in hour_counts.items() if c >= 2 or (total > 0 and c / total >= 0.2)],
        key=lambda h: -hour_counts[h]
    )
    if not danger_hours:
        return []
    ranges = _group_hours_into_ranges(sorted(danger_hours))
    conseils = []
    for s, e in ranges:
        label = f"{s:02d}h-{e+1:02d}h" if s != e else f"{s:02d}h-{s+1:02d}h"
        count = sum(hour_counts[h] for h in range(s, e + 1))
        conseils.append(f"De {label} : {count} perte(s) enregistree(s)")
    return conseils


def _analyse_perdu_dates(events: List[Dict]) -> Dict:
    """
    Analyse croisée des pertes par date ET par heure.
    Retourne un dict avec :
      - by_date         : {date_str: [hours]}
      - by_day_of_week  : {weekday_name: count}
      - hour_freq       : {hour: nb_dates_differentes_où_cette_heure_est_mauvaise}
      - danger_hours    : heures mauvaises sur >= 2 dates différentes
      - safe_hours      : plages horaires recommandées (sans danger)
      - recommendation  : texte de recommandation final
      - dates_analysees : liste des dates impliquées
    """
    from collections import defaultdict, Counter
    DAYS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    if not events:
        return {
            'by_date': {}, 'by_day_of_week': {}, 'hour_freq': {},
            'danger_hours': [], 'safe_hours': [], 'recommendation': '',
            'dates_analysees': []
        }

    # Regrouper par date
    by_date: Dict[str, List[int]] = defaultdict(list)
    by_day_of_week: Counter = Counter()
    for ev in events:
        d = ev['time'].strftime('%d/%m/%Y')
        h = ev['time'].hour
        by_date[d].append(h)
        by_day_of_week[DAYS_FR[ev['time'].weekday()]] += 1

    dates_analysees = sorted(by_date.keys())

    # Pour chaque heure, compter sur combien de dates distinctes elle apparaît
    hour_date_set: Dict[int, set] = defaultdict(set)
    for d, hours in by_date.items():
        for h in hours:
            hour_date_set[h].add(d)

    hour_freq = {h: len(dates) for h, dates in hour_date_set.items()}
    nb_dates = len(by_date)

    # Heures dangereuses : présentes sur >= 2 dates OU >= 50% des dates
    danger_hours = sorted([
        h for h, cnt in hour_freq.items()
        if cnt >= 2 or (nb_dates >= 2 and cnt / nb_dates >= 0.5)
    ])

    # Heures sûres = toutes les heures de 0 à 23 sauf les dangereuses
    danger_set = set(danger_hours)
    safe_all = [h for h in range(24) if h not in danger_set]
    safe_ranges = _group_hours_into_ranges(safe_all)

    # Construire la recommandation texte
    if danger_hours:
        danger_ranges = _group_hours_into_ranges(danger_hours)
        danger_labels = []
        for s, e in danger_ranges:
            nb = max(hour_freq.get(h, 0) for h in range(s, e + 1))
            label = f"{s:02d}h-{e+1:02d}h ({nb} date(s))" if s != e else f"{s:02d}h-{s+1:02d}h ({nb} date(s))"
            danger_labels.append(label)

        if safe_ranges:
            safe_labels = [
                f"{s:02d}h00 - {e+1:02d}h00" if s != e else f"{s:02d}h00 - {s+1:02d}h00"
                for s, e in safe_ranges
            ]
            rec = (
                f"D'apres mes analyses sur {nb_dates} date(s) ({', '.join(dates_analysees)}), "
                f"les plages a risque sont : {', '.join(danger_labels)}. "
                f"Je vous conseille de programmer les predictions uniquement sur : "
                f"{' | '.join(safe_labels)}."
            )
        else:
            rec = (
                f"D'apres mes analyses sur {nb_dates} date(s) ({', '.join(dates_analysees)}), "
                f"des pertes ont ete detectees a presque toutes les heures. "
                f"Aucune plage vraiment sure n'a pu etre identifiee. "
                f"Reduisez la frequence des predictions."
            )
    else:
        rec = (
            f"Analyse sur {nb_dates} date(s) : aucun pattern horaire repetitif detecte. "
            f"Les pertes sont bien distribuees sur la journee — pas de plage a eviter en particulier."
        )

    return {
        'by_date': dict(by_date),
        'by_day_of_week': dict(by_day_of_week),
        'hour_freq': hour_freq,
        'danger_hours': danger_hours,
        'safe_ranges': safe_ranges,
        'recommendation': rec,
        'dates_analysees': dates_analysees,
    }


def _build_admin_notification(events: List[Dict], date_analysis: Dict) -> str:
    """Génère le message texte de notification admin avec recommandation horaire."""
    total = len(events)
    if total == 0:
        return "📊 Aucune perte enregistrée pour le moment."

    nb_dates = len(date_analysis['dates_analysees'])
    danger_hours = date_analysis['danger_hours']
    safe_ranges = date_analysis.get('safe_ranges', [])

    lines = [
        "⚠️ **ANALYSE DES PERTES — RECOMMANDATION HORAIRE**",
        "",
        f"📅 Dates analysées ({nb_dates}) : {', '.join(date_analysis['dates_analysees'])}",
        f"📉 Total pertes : **{total}**",
        "",
    ]

    if danger_hours:
        danger_ranges = _group_hours_into_ranges(danger_hours)
        lines.append("🔴 **Plages à risque élevé (répétitives sur plusieurs dates) :**")
        for s, e in danger_ranges:
            nb = max(date_analysis['hour_freq'].get(h, 0) for h in range(s, e + 1))
            label = f"{s:02d}h00–{e+1:02d}h00" if s != e else f"{s:02d}h00–{s+1:02d}h00"
            lines.append(f"  • {label} → pertes détectées sur {nb} date(s)")
        lines.append("")

    if safe_ranges:
        lines.append("✅ **Plages recommandées (faibles risques) :**")
        for s, e in safe_ranges:
            label = f"{s:02d}h00 → {e+1:02d}h00" if s != e else f"{s:02d}h00 → {s+1:02d}h00"
            lines.append(f"  • {label}")
        lines.append("")
        safe_labels = [
            f"{s:02d}h-{e+1:02d}h" if s != e else f"{s:02d}h-{s+1:02d}h"
            for s, e in safe_ranges
        ]
        lines.append(
            f"💡 **Conseil** : La plupart des heures analysées ne sont pas favorables. "
            f"Je vous conseille de programmer vos prédictions en définissant "
            f"**{' | '.join(safe_labels)}** d'après mes analyses des dates : "
            f"{', '.join(date_analysis['dates_analysees'])}."
        )
    else:
        lines.append("⚠️ Aucune plage sûre identifiable — réduisez la fréquence des prédictions.")

    lines.append("")
    lines.append("_📄 Voir le PDF ci-dessous pour l'analyse complète par date._")
    return "\n".join(lines)


def generate_perdu_pdf(events: List[Dict]) -> bytes:
    """Génère le PDF des pertes avec analyse horaire, analyse croisée par date et recommandation."""
    date_analysis = _analyse_perdu_dates(events)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    suit_names = {'♠': 'Pique', '♥': 'Coeur', '♦': 'Carreau', '♣': 'Trefle'}
    DAYS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    def section_header(title: str, r: int, g: int, b: int):
        pdf.ln(8)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, title, ln=True, fill=True, align='C')
        pdf.ln(3)
        pdf.set_text_color(0, 0, 0)

    # ── Titre principal ──────────────────────────────────────────────────────
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_fill_color(139, 0, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, 'BACCARAT AI - Analyse Complete des Pertes', ln=True, align='C', fill=True)
    pdf.ln(4)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6,
        f'Genere le {datetime.now().strftime("%d/%m/%Y %H:%M")} | '
        f'Total: {len(events)} perte(s) | '
        f'Dates analysees: {len(date_analysis["dates_analysees"])}',
        ln=True, align='C'
    )
    pdf.ln(6)

    # ── Tableau historique des pertes ────────────────────────────────────────
    section_header('Historique des Pertes', 50, 50, 50)
    col_w = [32, 22, 24, 26, 14, 14, 58]
    hdrs = ['Date', 'Heure', 'Jeu #', 'Costume', 'Ratt.', 'B avant', 'B apres']
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    for h, w in zip(hdrs, col_w):
        pdf.cell(w, 9, h, border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_font('Helvetica', '', 10)
    alt = False
    for ev in events:
        pdf.set_fill_color(*(245, 230, 230) if alt else (255, 255, 255))
        pdf.set_text_color(0, 0, 0)
        row = [
            ev['time'].strftime('%d/%m/%Y'),
            ev['time'].strftime('%H:%M'),
            str(ev['game']),
            suit_names.get(ev['suit'], ev['suit']),
            f"R{ev['rattrapage']}",
            str(ev['b_before']),
            str(ev['b_after'])
        ]
        for d, w in zip(row, col_w):
            pdf.cell(w, 8, d, border=1, fill=alt, align='C')
        pdf.ln()
        alt = not alt
    if not events:
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, 'Aucune perte enregistree', border=1, align='C')
        pdf.ln()

    # ── Analyse par date ─────────────────────────────────────────────────────
    section_header('Comparaison des Pertes par Date', 20, 80, 160)
    if date_analysis['by_date']:
        col_date = 50
        col_hours = 100
        col_nb = 40
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_fill_color(20, 80, 160)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(col_date, 9, 'Date', border=1, fill=True, align='C')
        pdf.cell(col_hours, 9, 'Heures de perte', border=1, fill=True, align='C')
        pdf.cell(col_nb, 9, 'Nb pertes', border=1, fill=True, align='C')
        pdf.ln()
        pdf.set_font('Helvetica', '', 10)
        alt = False
        for date_str in date_analysis['dates_analysees']:
            hours = sorted(date_analysis['by_date'][date_str])
            hours_label = ', '.join(f'{h:02d}h' for h in hours)
            pdf.set_fill_color(*(220, 235, 255) if alt else (255, 255, 255))
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_date, 8, date_str, border=1, fill=alt, align='C')
            pdf.cell(col_hours, 8, hours_label, border=1, fill=alt, align='C')
            pdf.cell(col_nb, 8, str(len(hours)), border=1, fill=alt, align='C')
            pdf.ln()
            alt = not alt
    else:
        pdf.set_text_color(150, 150, 150)
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 8, 'Pas encore assez de donnees par date.', ln=True)

    # ── Analyse par heure (fréquence cross-dates) ────────────────────────────
    section_header('Frequence des Heures de Perte (toutes dates confondues)', 100, 50, 0)
    if date_analysis['hour_freq']:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_fill_color(100, 50, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(40, 9, 'Heure', border=1, fill=True, align='C')
        pdf.cell(60, 9, 'Nb dates concernees', border=1, fill=True, align='C')
        pdf.cell(90, 9, 'Niveau de risque', border=1, fill=True, align='C')
        pdf.ln()
        pdf.set_font('Helvetica', '', 10)
        nb_dates_total = len(date_analysis['dates_analysees'])
        for hour in sorted(date_analysis['hour_freq'].keys()):
            cnt = date_analysis['hour_freq'][hour]
            pct = cnt / nb_dates_total * 100 if nb_dates_total else 0
            if hour in date_analysis['danger_hours']:
                risk = 'RISQUE ELEVE'
                pdf.set_text_color(180, 0, 0)
                pdf.set_fill_color(255, 220, 220)
                do_fill = True
            else:
                risk = 'Acceptable'
                pdf.set_text_color(0, 0, 0)
                pdf.set_fill_color(255, 255, 255)
                do_fill = False
            pdf.cell(40, 8, f'{hour:02d}h00', border=1, fill=do_fill, align='C')
            pdf.cell(60, 8, f'{cnt}/{nb_dates_total} ({pct:.0f}%)', border=1, fill=do_fill, align='C')
            pdf.cell(90, 8, risk, border=1, fill=do_fill, align='C')
            pdf.ln()
            pdf.set_text_color(0, 0, 0)
    else:
        pdf.set_text_color(150, 150, 150)
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 8, 'Aucune donnee disponible.', ln=True)

    # ── Analyse par jour de la semaine ───────────────────────────────────────
    section_header('Pertes par Jour de la Semaine', 80, 0, 120)
    if date_analysis['by_day_of_week']:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_fill_color(80, 0, 120)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(80, 9, 'Jour', border=1, fill=True, align='C')
        pdf.cell(60, 9, 'Nb pertes', border=1, fill=True, align='C')
        pdf.ln()
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(0, 0, 0)
        for day, cnt in sorted(date_analysis['by_day_of_week'].items(),
                               key=lambda x: -x[1]):
            pdf.cell(80, 8, day, border=1, align='C')
            pdf.cell(60, 8, str(cnt), border=1, align='C')
            pdf.ln()
    else:
        pdf.set_text_color(150, 150, 150)
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 8, 'Aucune donnee disponible.', ln=True)

    # ── Seuils B par costume ─────────────────────────────────────────────────
    section_header('Seuils B actuels par Costume', 70, 70, 70)
    pdf.set_font('Helvetica', '', 11)
    pdf.set_text_color(0, 0, 0)
    for suit in ['♠', '♥', '♦', '♣']:
        b_val = compteur2_seuil_B_per_suit.get(suit, compteur2_seuil_B)
        pdf.cell(0, 8, f'  {suit_names.get(suit, suit)}: B = {b_val}', ln=True)

    # ── Recommandation finale ────────────────────────────────────────────────
    section_header('RECOMMANDATION - Plages Horaires Conseilees', 0, 100, 0)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(0, 0, 0)
    if date_analysis['danger_hours']:
        danger_ranges = _group_hours_into_ranges(date_analysis['danger_hours'])
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(180, 0, 0)
        pdf.cell(0, 8, '  Plages a EVITER :', ln=True)
        pdf.set_font('Helvetica', '', 10)
        for s, e in danger_ranges:
            nb = max(date_analysis['hour_freq'].get(h, 0) for h in range(s, e + 1))
            label = f'{s:02d}h00 - {e+1:02d}h00' if s != e else f'{s:02d}h00 - {s+1:02d}h00'
            pdf.cell(0, 8, f'    X  {label}  (pertes sur {nb} date(s))', ln=True)
        pdf.ln(3)

    if date_analysis.get('safe_ranges'):
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(0, 120, 0)
        pdf.cell(0, 8, '  Plages RECOMMANDEES :', ln=True)
        pdf.set_font('Helvetica', '', 10)
        for s, e in date_analysis['safe_ranges']:
            label = f'{s:02d}h00 - {e+1:02d}h00' if s != e else f'{s:02d}h00 - {s+1:02d}h00'
            pdf.cell(0, 8, f'    OK  {label}', ln=True)
        pdf.ln(4)

    pdf.set_font('Helvetica', 'I', 10)
    pdf.set_text_color(50, 50, 50)
    rec_clean = date_analysis['recommendation'].replace('\u2019', "'")
    pdf.multi_cell(0, 7, f'  Synthese : {rec_clean}')

    # ── Pied de page ─────────────────────────────────────────────────────────
    pdf.ln(5)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 6, "Ce PDF est envoye uniquement a l'administrateur - CONFIDENTIEL", ln=True, align='C')

    return bytes(pdf.output())


async def send_perdu_pdf():
    """Envoie la notification texte + le PDF de comparaison à l'admin."""
    global perdu_pdf_msg_id
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    try:
        date_analysis = _analyse_perdu_dates(perdu_events)
        notif_text = _build_admin_notification(perdu_events, date_analysis)

        pdf_bytes = generate_perdu_pdf(perdu_events)
        buf = io.BytesIO(pdf_bytes)
        buf.name = "perdu_analyse_complete.pdf"

        admin_entity = await client.get_entity(ADMIN_ID)

        # Supprimer l'ancien PDF s'il existe
        if perdu_pdf_msg_id:
            try:
                await client.delete_messages(admin_entity, [perdu_pdf_msg_id])
            except Exception as e:
                logger.debug(f"Suppression ancien PDF Perdus ignorée: {e}")
            perdu_pdf_msg_id = None

        # 1. Envoyer la notification texte en premier
        await client.send_message(admin_entity, notif_text, parse_mode='markdown')

        # 2. Envoyer le PDF de comparaison
        caption = (
            f"📊 **ANALYSE COMPLÈTE DES PERTES**\n\n"
            f"Total pertes: **{len(perdu_events)}**\n"
            f"Dates analysées: **{len(date_analysis['dates_analysees'])}**\n"
            f"Mis à jour: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"_Comparaison croisée heures × dates incluse._"
        )
        sent = await client.send_file(
            admin_entity, buf,
            caption=caption,
            parse_mode='markdown',
            file_name="perdu_analyse_complete.pdf"
        )
        perdu_pdf_msg_id = sent.id
        logger.info(f"✅ Notification + PDF comparaison envoyés à l'admin")
    except Exception as e:
        logger.error(f"❌ Erreur send_perdu_pdf: {e}")

# ============================================================================
# BILAN AUTOMATIQUE
# ============================================================================

def _number_to_big(n: int) -> str:
    """Convertit un nombre en gros chiffres unicode."""
    digit_map = {'0':'0️⃣','1':'1️⃣','2':'2️⃣','3':'3️⃣','4':'4️⃣',
                 '5':'5️⃣','6':'6️⃣','7':'7️⃣','8':'8️⃣','9':'9️⃣'}
    return ''.join(digit_map.get(c, c) for c in str(n))


def get_bilan_text() -> str:
    """Génère le texte du bilan des prédictions avec taux de réussite."""
    counts = {'r0': 0, 'r1': 0, 'r2': 0, 'r3': 0, 'perdu': 0}
    for pred in prediction_history:
        st = pred.get('status', '')
        rl = pred.get('rattrapage_level', 0)
        if 'gagne' in st:
            key = f'r{rl}' if rl <= 3 else 'r3'
            counts[key] += 1
        elif st == 'perdu':
            counts['perdu'] += 1

    total = sum(counts.values())
    if total == 0:
        return "📊 **BILAN** — Aucune prédiction finalisée pour le moment."

    total_gagnes = counts['r0'] + counts['r1'] + counts['r2'] + counts['r3']
    taux_reussite = total_gagnes / total * 100
    taux_perdu = counts['perdu'] / total * 100

    def pct(n): return f"{n/total*100:.1f}%"

    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    total_big = _number_to_big(total)
    lines = [
        "╔══════════════════════════════╗",
        f"║  📊 TOTAL PRÉDICTIONS        ║",
        f"║       {total_big}",
        "╚══════════════════════════════╝",
        f"",
        f"📈 **BILAN DES PRÉDICTIONS**",
        f"🕒 {now}",
        "━" * 30,
        f"✅0️⃣ GAGNÉ DIRECT : **{counts['r0']}** ({pct(counts['r0'])})",
        f"✅1️⃣ GAGNÉ R1     : **{counts['r1']}** ({pct(counts['r1'])})",
        f"✅2️⃣ GAGNÉ R2     : **{counts['r2']}** ({pct(counts['r2'])})",
        f"✅3️⃣ GAGNÉ R3     : **{counts['r3']}** ({pct(counts['r3'])})",
        "━" * 30,
        f"❌ PERDU          : **{counts['perdu']}** ({pct(counts['perdu'])})",
        "━" * 30,
        f"🏆 Taux de réussite : **{taux_reussite:.1f}%** ({total_gagnes} gagnées)",
        f"💔 Taux de perte   : **{taux_perdu:.1f}%** ({counts['perdu']} perdues)",
    ]
    return "\n".join(lines)

async def bilan_loop():
    """Envoie le bilan à chaque heure pile (HH:00:00), si non désactivé."""
    global bilan_interval_minutes
    while True:
        try:
            now = datetime.now()
            # Calcul des secondes jusqu'à la prochaine heure pile
            seconds_until_next_hour = 3600 - (now.minute * 60 + now.second)
            await asyncio.sleep(seconds_until_next_hour)

            if bilan_interval_minutes == 0:
                # Désactivé manuellement via /bilan 0
                continue

            entity = await resolve_channel(PREDICTION_CHANNEL_ID)
            if entity:
                heure = datetime.now().strftime('%H:%M')
                await client.send_message(entity, get_bilan_text(), parse_mode='markdown')
                logger.info(f"📊 Bilan horaire envoyé ({heure})")
        except Exception as e:
            logger.error(f"❌ Erreur bilan horaire: {e}")
            await asyncio.sleep(60)

def update_compteur4(game_number: int, player_suits: Set[str], player_cards_raw: list) -> tuple:
    """
    Met à jour Compteur4 — logique série complète (comme Compteur7 pour les absences).
    - Quand un costume est absent, la série monte.
    - À l'atteinte du seuil, une alerte immédiate est envoyée (série toujours en cours).
    - Quand le costume réapparaît et que la série était >= seuil, la série est enregistrée.
    Retourne : (threshold_alerts, completed_series)
      - threshold_alerts : liste de suits ayant JUSTE atteint le seuil (alerte immédiate)
      - completed_series : liste de dicts de séries terminées (enregistrer dans PDF)
    """
    global compteur4_trackers, compteur4_current, compteur4_events

    threshold_alerts  = []
    completed_series  = []
    now = datetime.now()

    for suit in ALL_SUITS:
        cur = compteur4_current[suit]
        if suit in player_suits:
            # Costume présent → fin de série d'absence si série >= seuil
            if cur['count'] >= COMPTEUR4_THRESHOLD:
                series = {
                    'suit':       suit,
                    'count':      cur['count'],
                    'start_game': cur['start_game'],
                    'end_game':   game_number - 1,
                    'start_time': cur['start_time'],
                    'end_time':   now,
                }
                compteur4_events.append(series)
                completed_series.append(series)
                save_compteur4_data()
                logger.info(
                    f"🔴 C4: {suit} série d'absence terminée "
                    f"{series['count']}x (#{series['start_game']}→#{series['end_game']})"
                )
            # Reset
            cur['count']      = 0
            cur['start_game'] = None
            cur['start_time'] = None
            cur['alerted']    = False
            compteur4_trackers[suit] = 0
        else:
            # Costume absent → incrémenter la série
            if cur['count'] == 0:
                cur['start_game'] = game_number
                cur['start_time'] = now
            cur['count'] += 1
            compteur4_trackers[suit] = cur['count']

            # Alerte immédiate quand on atteint exactement le seuil
            if cur['count'] == COMPTEUR4_THRESHOLD and not cur['alerted']:
                cur['alerted'] = True
                threshold_alerts.append(suit)
                logger.info(f"🚨 C4: {suit} absent {COMPTEUR4_THRESHOLD} fois! (série continue…)")

    return threshold_alerts, completed_series


def update_compteur5(game_number: int, player_suits: Set[str], player_cards_raw: list) -> List[str]:
    """Met à jour Compteur5 (présences consécutives). Retourne les costumes ayant atteint le seuil."""
    global compteur5_trackers, compteur5_events
    triggered = []
    for suit in ALL_SUITS:
        if suit in player_suits:
            compteur5_trackers[suit] += 1
            if compteur5_trackers[suit] == COMPTEUR5_THRESHOLD:
                ev = {
                    'datetime': datetime.now(),
                    'game_number': game_number,
                    'suit': suit,
                    'player_suits': list(player_suits),
                }
                compteur5_events.append(ev)
                triggered.append(suit)
                logger.info(f"✅ Compteur5: {suit} présent {COMPTEUR5_THRESHOLD} fois! (jeu #{game_number})")
        else:
            compteur5_trackers[suit] = 0
    return triggered

# ============================================================================
# COMPTEUR6 - FILTRE PRÉDICTION PAR PAIRES INVERSES
# ============================================================================

def update_compteur6(player_suits: Set[str]):
    """Incrémente le compteur d'apparitions Compteur6 pour chaque costume présent.
    Le compteur est plafonné à Wj pour ne jamais dépasser le seuil affiché."""
    global compteur6_trackers
    for suit in player_suits:
        if suit in compteur6_trackers:
            new_val = compteur6_trackers[suit] + 1
            # Plafond : on ne dépasse jamais Wj (le seuil de déclenchement)
            compteur6_trackers[suit] = min(new_val, compteur6_seuil_Wj)
            if new_val >= compteur6_seuil_Wj:
                logger.info(
                    f"📊 C6 {suit}: {new_val}x → seuil Wj={compteur6_seuil_Wj} atteint"
                )

def apply_compteur6(suit: str) -> str:
    """
    Filtre Compteur6 : avant de prédire `suit`, vérifie si son inverse a atteint Wj.
    - Inverse atteint Wj → confirmer la prédiction originale (retourne suit)
                          → RESET du compteur opposé à 0 (cycle consommé)
    - Inverse pas encore à Wj → prédire l'inverse à la place
    Paires : ❤️ ↔ ♦️  |  ♣️ ↔ ♠️
    """
    opposite = COMPTEUR6_PAIRS.get(suit)
    if opposite is None:
        return suit
    count_opposite = compteur6_trackers.get(opposite, 0)
    if count_opposite >= compteur6_seuil_Wj:
        # Consommer le cycle : remettre l'opposé à 0
        compteur6_trackers[opposite] = 0
        logger.info(
            f"🔵 C6: prédit {suit} confirmé — {opposite} apparu {count_opposite}x ≥ Wj={compteur6_seuil_Wj} → reset {opposite}=0"
        )
        return suit
    else:
        logger.info(
            f"🔄 C6: prédit {suit} → redirigé vers {opposite} "
            f"({opposite} apparu seulement {count_opposite}x < Wj={compteur6_seuil_Wj})"
        )
        return opposite

# ============================================================================
# COMPTEUR4 — PERSISTANCE (séries d'absences — survit aux resets)
# ============================================================================

def load_compteur4_data():
    """Charge les séries d'absences Compteur4 depuis le fichier persistant."""
    global compteur4_events
    try:
        if os.path.exists(COMPTEUR4_DATA_FILE):
            with open(COMPTEUR4_DATA_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            compteur4_events = []
            for item in raw:
                item['start_time'] = datetime.fromisoformat(item['start_time'])
                item['end_time']   = datetime.fromisoformat(item['end_time'])
                compteur4_events.append(item)
            logger.info(f"📂 C4: {len(compteur4_events)} séries chargées depuis disque")
    except Exception as e:
        logger.error(f"❌ Chargement C4 échoué: {e}")
        compteur4_events = []


def save_compteur4_data():
    """Sauvegarde les séries d'absences Compteur4 sur disque (persistance entre resets)."""
    try:
        data = []
        for item in compteur4_events:
            row = dict(item)
            row['start_time'] = item['start_time'].isoformat()
            row['end_time']   = item['end_time'].isoformat()
            data.append(row)
        with open(COMPTEUR4_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Sauvegarde C4 échouée: {e}")


# ============================================================================
# COMPTEUR7 — SÉRIES CONSÉCUTIVES PERSISTANTES
# ============================================================================

def load_compteur7_data():
    """Charge les séries Compteur7 depuis le fichier persistant (survit aux resets)."""
    global compteur7_completed
    try:
        if os.path.exists(COMPTEUR7_DATA_FILE):
            with open(COMPTEUR7_DATA_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            compteur7_completed = []
            for item in raw:
                item['start_time'] = datetime.fromisoformat(item['start_time'])
                item['end_time']   = datetime.fromisoformat(item['end_time'])
                compteur7_completed.append(item)
            logger.info(f"📂 C7: {len(compteur7_completed)} séries chargées depuis disque")
    except Exception as e:
        logger.error(f"❌ Chargement C7 échoué: {e}")
        compteur7_completed = []


def save_compteur7_data():
    """Sauvegarde les séries Compteur7 sur disque (persistance entre resets)."""
    try:
        data = []
        for item in compteur7_completed:
            row = dict(item)
            row['start_time'] = item['start_time'].isoformat()
            row['end_time']   = item['end_time'].isoformat()
            data.append(row)
        with open(COMPTEUR7_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Sauvegarde C7 échouée: {e}")


def load_hourly_data():
    """Charge les données horaires depuis le fichier persistant."""
    global hourly_suit_data, hourly_game_count
    try:
        if os.path.exists(HOURLY_DATA_FILE):
            with open(HOURLY_DATA_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for h_str, suits in saved.get('suits', {}).items():
                h = int(h_str)
                if 0 <= h <= 23:
                    for suit, cnt in suits.items():
                        if suit in hourly_suit_data[h]:
                            hourly_suit_data[h][suit] = cnt
            for h_str, cnt in saved.get('totals', {}).items():
                h = int(h_str)
                if 0 <= h <= 23:
                    hourly_game_count[h] = cnt
            logger.info("📂 Données horaires chargées depuis disque")
    except Exception as e:
        logger.error(f"❌ Chargement données horaires: {e}")


def save_hourly_data():
    """Sauvegarde les données horaires sur disque."""
    try:
        data = {
            'suits':  {str(h): dict(suits) for h, suits in hourly_suit_data.items()},
            'totals': {str(h): cnt for h, cnt in hourly_game_count.items()},
        }
        with open(HOURLY_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Sauvegarde données horaires: {e}")


def update_compteur7(game_number: int, player_suits: Set[str]) -> List[Dict]:
    """Met à jour Compteur7. Retourne les séries terminées (≥ seuil) dans ce jeu."""
    global compteur7_current, compteur7_completed
    newly_completed = []
    now = datetime.now()

    for suit in ALL_SUITS:
        current = compteur7_current[suit]
        if suit in player_suits:
            # Costume présent → incrémenter
            if current['count'] == 0:
                current['start_game'] = game_number
                current['start_time'] = now
            current['count'] += 1
        else:
            # Costume absent → vérifier si série terminée
            if current['count'] >= COMPTEUR7_THRESHOLD:
                series = {
                    'suit':       suit,
                    'count':      current['count'],
                    'start_game': current['start_game'],
                    'end_game':   game_number - 1,
                    'start_time': current['start_time'],
                    'end_time':   now,
                }
                compteur7_completed.append(series)
                newly_completed.append(series)
                save_compteur7_data()
                logger.info(
                    f"📊 C7: {suit} série terminée "
                    f"{series['count']}x (#{series['start_game']}→#{series['end_game']})"
                )
            # Reset le compteur
            current['count']      = 0
            current['start_game'] = None
            current['start_time'] = None

    return newly_completed


def update_hourly_data(player_suits: Set[str]):
    """Met à jour les compteurs horaires (pour /comparaison)."""
    h = datetime.now().hour
    hourly_game_count[h] += 1
    for suit in player_suits:
        if suit in hourly_suit_data[h]:
            hourly_suit_data[h][suit] += 1
    # Sauvegarde toutes les 10 parties pour ne pas surcharger le disque
    if hourly_game_count[h] % 10 == 0:
        save_hourly_data()


def generate_compteur7_pdf() -> bytes:
    """Génère un PDF avec le tableau des séries consécutives Compteur7."""
    suit_names_map = {'♠': 'Pique', '♥': 'Coeur', '♦': 'Carreau', '♣': 'Trefle'}
    suit_colors    = {'♠': (30, 30, 30), '♥': (180, 0, 0), '♦': (0, 80, 180), '♣': (0, 120, 0)}
    events_list    = compteur7_completed

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Titre
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_fill_color(90, 0, 160)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, 'BACCARAT AI - Series Consecutives Compteur 7', ln=True, align='C', fill=True)
    pdf.ln(4)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6,
        f'Seuil minimum: {COMPTEUR7_THRESHOLD}x | '
        f'Genere le {datetime.now().strftime("%d/%m/%Y %H:%M")} | '
        f'Total: {len(events_list)} serie(s) | PERSISTANT',
        ln=True, align='C'
    )
    pdf.ln(6)

    col_widths = [32, 22, 22, 32, 32, 26]
    headers    = ['Date', 'Heure', 'Costume', 'Debut', 'Fin', 'Nb fois']

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_fill_color(90, 0, 160)
    pdf.set_text_color(255, 255, 255)
    for header, width in zip(headers, col_widths):
        pdf.cell(width, 9, header, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 11)
    alt = False
    for ev in events_list:
        suit       = ev.get('suit', '')
        r, g, b    = suit_colors.get(suit, (0, 0, 0))
        date_str   = ev['end_time'].strftime('%d/%m/%Y')
        time_str   = ev['end_time'].strftime('%Hh%M')
        suit_name  = suit_names_map.get(suit, suit)
        start_str  = f"#{ev['start_game']}"
        end_str    = f"#{ev['end_game']}"
        count_str  = f"{ev['count']}x"

        bg = (245, 245, 245) if alt else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.set_text_color(0, 0, 0)

        pdf.cell(col_widths[0], 9, date_str, border=1, fill=alt, align='C')
        pdf.cell(col_widths[1], 9, time_str, border=1, fill=alt, align='C')

        pdf.set_text_color(r, g, b)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(col_widths[2], 9, suit_name, border=1, fill=alt, align='C')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(0, 0, 0)

        pdf.cell(col_widths[3], 9, start_str, border=1, fill=alt, align='C')
        pdf.cell(col_widths[4], 9, end_str,   border=1, fill=alt, align='C')

        pdf.set_text_color(r, g, b)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(col_widths[5], 9, count_str, border=1, fill=alt, align='C')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(0, 0, 0)

        pdf.ln()
        alt = not alt

    if not events_list:
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 8, 'Aucune serie enregistree', border=1, align='C')
        pdf.ln()

    # Résumé par costume
    pdf.ln(8)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_fill_color(90, 0, 160)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, 'Resume par costume', ln=True, fill=True, align='C')
    pdf.ln(3)

    from collections import Counter as _Counter
    suit_counts = _Counter(ev.get('suit', '') for ev in events_list)
    for suit in ['♠', '♥', '♦', '♣']:
        r, g, b = suit_colors.get(suit, (0, 0, 0))
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(r, g, b)
        name = suit_names_map.get(suit, suit)
        cnt  = suit_counts.get(suit, 0)
        pdf.cell(0, 8, f'  {name} : {cnt} serie(s) de {COMPTEUR7_THRESHOLD}+ consecutives', ln=True)

    pdf.ln(5)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6,
        f'BACCARAT AI - PERSISTANT - Reset #1440 ne supprime PAS ce fichier - '
        f'{datetime.now().strftime("%d/%m/%Y %H:%M")}',
        ln=True, align='C'
    )
    return bytes(pdf.output())


async def send_compteur7_alert(series: Dict):
    """Envoie une notification à l'admin quand une série Compteur7 se termine."""
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    suit_emoji_map = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}
    suit_names_map = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
    try:
        admin_entity = await client.get_entity(ADMIN_ID)
        suit     = series['suit']
        emoji    = suit_emoji_map.get(suit, suit)
        end_time = series['end_time']
        msg = (
            f"📊 **COMPTEUR 7 — SÉRIE TERMINÉE**\n\n"
            f"{end_time.strftime('%d/%m/%Y')} à {end_time.strftime('%Hh%M')} "
            f"{emoji} **{series['count']} fois** du numéro "
            f"**{series['start_game']}_{series['end_game']}**\n\n"
            f"_{suit_names_map.get(suit, suit)} présent {series['count']} fois consécutives._\n\n"
            f"📄 PDF mis à jour ci-dessous."
        )
        await client.send_message(admin_entity, msg, parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Erreur send_compteur7_alert: {e}")


async def send_compteur7_pdf():
    """Génère et envoie (ou remplace) le PDF Compteur7 à l'admin."""
    global compteur7_pdf_msg_id
    if not ADMIN_ID or ADMIN_ID == 0:
        return
    try:
        pdf_bytes  = generate_compteur7_pdf()
        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.name = "compteur7_series.pdf"
        admin_entity = await client.get_entity(ADMIN_ID)

        if compteur7_pdf_msg_id:
            try:
                await client.delete_messages(admin_entity, [compteur7_pdf_msg_id])
            except Exception:
                pass
            compteur7_pdf_msg_id = None

        caption = (
            f"📊 **COMPTEUR7 — PDF mis à jour**\n\n"
            f"Total séries enregistrées : **{len(compteur7_completed)}**\n"
            f"Seuil : **≥ {COMPTEUR7_THRESHOLD}** présences consécutives\n"
            f"⚠️ Ce PDF persiste entre tous les resets\n"
            f"Mis à jour : {datetime.now().strftime('%d/%m/%Y %Hh%M')}"
        )
        sent = await client.send_file(
            admin_entity, pdf_buffer,
            caption=caption, parse_mode='markdown',
            attributes=[], file_name="compteur7_series.pdf"
        )
        compteur7_pdf_msg_id = sent.id
        logger.info(f"✅ PDF Compteur7 envoyé à l'admin")
    except Exception as e:
        logger.error(f"❌ Erreur send_compteur7_pdf: {e}")
        import traceback; logger.error(traceback.format_exc())


# ============================================================================
# NORMALISATION DES COSTUMES
# ============================================================================

def normalize_suit(s: str) -> str:
    """Normalise un costume API vers le format interne ('♠', '♥', '♦', '♣')."""
    s = s.strip()
    s = s.replace('\ufe0f', '')  # Retirer le variation selector
    s = s.replace('❤', '♥')
    return s

def get_player_suits(player_cards: list) -> Set[str]:
    """Extrait les costumes normalisés des cartes joueur."""
    suits = set()
    for card in player_cards:
        raw = card.get('S', '')
        normalized = normalize_suit(raw)
        if normalized in ALL_SUITS:
            suits.add(normalized)
    return suits

# ============================================================================
# CLASSES TRACKERS
# ============================================================================

@dataclass
class Compteur2Tracker:
    """Tracker pour le compteur2 (costumes manquants)."""
    suit: str
    counter: int = 0
    last_increment_game: int = 0

    def get_display_name(self) -> str:
        return SUIT_DISPLAY.get(self.suit, self.suit)

    def increment(self, game_number: int):
        self.counter += 1
        self.last_increment_game = game_number
        logger.info(f"📊 Compteur2 {self.suit}: {self.counter} (jeu #{game_number})")

    def reset(self, game_number: int):
        if self.counter > 0:
            logger.info(f"🔄 Compteur2 {self.suit}: reset {self.counter}→0 (jeu #{game_number})")
        self.counter = 0
        self.last_increment_game = 0

    def check_threshold(self, seuil_B: int) -> bool:
        return self.counter >= seuil_B


@dataclass
class Compteur1Tracker:
    """Tracker pour le compteur1 (costumes présents consécutivement)."""
    suit: str
    counter: int = 0
    start_game: int = 0
    last_game: int = 0

    def get_display_name(self) -> str:
        return SUIT_DISPLAY.get(self.suit, self.suit)

    def increment(self, game_number: int):
        if self.counter == 0:
            self.start_game = game_number
        self.counter += 1
        self.last_game = game_number

    def reset(self, game_number: int):
        if self.counter >= MIN_CONSECUTIVE_FOR_STATS:
            save_compteur1_series(self.suit, self.counter, self.start_game, self.last_game)
        self.counter = 0
        self.start_game = 0
        self.last_game = 0

    def get_status(self) -> str:
        if self.counter == 0:
            return "0"
        return f"{self.counter} (depuis #{self.start_game})"

# ============================================================================
# FONCTIONS COMPTEUR1
# ============================================================================

def save_compteur1_series(suit: str, count: int, start_game: int, end_game: int):
    global compteur1_history
    entry = {
        'suit': suit,
        'count': count,
        'start_game': start_game,
        'end_game': end_game,
        'timestamp': datetime.now()
    }
    compteur1_history.insert(0, entry)
    if len(compteur1_history) > 100:
        compteur1_history = compteur1_history[:100]

def get_compteur1_record(suit: str) -> int:
    max_count = 0
    for entry in compteur1_history:
        if entry['suit'] == suit and entry['count'] > max_count:
            max_count = entry['count']
    return max_count

def update_compteur1(game_number: int, player_suits: Set[str]):
    global compteur1_trackers
    for suit in ALL_SUITS:
        tracker = compteur1_trackers[suit]
        if suit in player_suits:
            tracker.increment(game_number)
        else:
            tracker.reset(game_number)

# ============================================================================
# FONCTIONS D'HISTORIQUE
# ============================================================================

def add_to_history(game_number: int, player_suits: Set[str]):
    global finalized_messages_history
    entry = {
        'timestamp': datetime.now(),
        'game_number': game_number,
        'player_suits': list(player_suits),
        'predictions_verified': []
    }
    finalized_messages_history.insert(0, entry)
    if len(finalized_messages_history) > MAX_HISTORY_SIZE:
        finalized_messages_history = finalized_messages_history[:MAX_HISTORY_SIZE]

def add_prediction_to_history(game_number: int, suit: str, verification_games: List[int], prediction_type: str = 'standard', reason: str = ''):
    global prediction_history
    prediction_history.insert(0, {
        'predicted_game': game_number,
        'suit': suit,
        'predicted_at': datetime.now(),
        'verification_games': verification_games,
        'status': 'en_cours',
        'verified_at': None,
        'verified_by_game': None,
        'rattrapage_level': 0,
        'type': prediction_type,
        'reason': reason
    })
    if len(prediction_history) > MAX_HISTORY_SIZE:
        prediction_history = prediction_history[:MAX_HISTORY_SIZE]

def update_prediction_in_history(game_number: int, suit: str, verified_by_game: int, rattrapage_level: int, final_status: str):
    global prediction_history
    for pred in prediction_history:
        if pred['predicted_game'] == game_number and pred['suit'] == suit:
            pred['status'] = final_status
            pred['verified_at'] = datetime.now()
            pred['verified_by_game'] = verified_by_game
            pred['rattrapage_level'] = rattrapage_level
            break

# ============================================================================
# INITIALISATION
# ============================================================================

def initialize_trackers():
    global compteur2_trackers, compteur1_trackers, compteur4_trackers, compteur5_trackers, compteur6_trackers
    for suit in ALL_SUITS:
        compteur2_trackers[suit] = Compteur2Tracker(suit=suit)
        compteur1_trackers[suit] = Compteur1Tracker(suit=suit)
        compteur4_trackers[suit] = 0
        compteur5_trackers[suit] = 0
        compteur6_trackers[suit] = 0
    logger.info("📊 Trackers initialisés (Compteur1, Compteur2, Compteur4, Compteur5, Compteur6)")

# ============================================================================
# UTILITAIRES CANAL
# ============================================================================

def normalize_channel_id(channel_id) -> int:
    if not channel_id:
        return None
    channel_str = str(channel_id)
    if channel_str.startswith('-100'):
        return int(channel_str)
    if channel_str.startswith('-'):
        return int(channel_str)
    return int(f"-100{channel_str}")

# Cache pour resolve_channel : évite de spammer l'API Telegram à chaque polling
_channel_cache: Dict[int, object] = {}          # entity_id → entity
_channel_cache_failed: Dict[int, datetime] = {} # entity_id → heure d'échec
_CHANNEL_CACHE_TTL   = 300   # Succès : re-résoudre après 5 min
_CHANNEL_CACHE_FAIL  = 60    # Échec  : ne pas réessayer avant 60s

async def resolve_channel(entity_id):
    if not entity_id:
        return None
    # Échec récent → ne pas réessayer
    fail_time = _channel_cache_failed.get(entity_id)
    if fail_time and (datetime.now() - fail_time).total_seconds() < _CHANNEL_CACHE_FAIL:
        return None
    # Cache valide
    cached = _channel_cache.get(entity_id)
    if cached is not None:
        return cached
    try:
        normalized_id = normalize_channel_id(entity_id)
        entity = await client.get_entity(normalized_id)
        _channel_cache[entity_id] = entity
        _channel_cache_failed.pop(entity_id, None)
        return entity
    except Exception as e:
        logger.error(f"❌ Impossible de résoudre le canal {entity_id}: {e}")
        _channel_cache_failed[entity_id] = datetime.now()
        _channel_cache.pop(entity_id, None)
        return None

def block_suit(suit: str, minutes: int = 5):
    suit_block_until[suit] = datetime.now() + timedelta(minutes=minutes)
    logger.info(f"🔒 {suit} bloqué {minutes}min")

# ============================================================================
# SYSTÈME D'ANIMATION (BARRE DE CHARGEMENT)
# ============================================================================

BAR_SIZE = 10          # Taille totale de la barre
ANIM_INTERVAL = 5.0    # Secondes entre chaque frame — 5s réduit les flood waits Telegram

# Amplitude max totale par rattrapage: R0=2, R1=4, R2=7, R3=10
BAR_MAX_BY_RATTRAPAGE = [2, 4, 7, 10]

# Couleur et taille INCREMENTAL par niveau (la partie mobile)
# R0→2 blocs, R1→2 blocs supplémentaires, R2→3, R3→3
LEVEL_COLORS = ['🟦', '🟩', '🟨', '🟥']
LEVEL_SIZES  = [2, 2, 3, 3]

def build_anim_bar(rattrapage: int, frame: int) -> str:
    """Construit la barre multicolore.
    - Niveaux passés : blocs figés dans leur couleur
    - Niveau actuel  : ping-pong dans sa couleur
    """
    R = min(rattrapage, 3)

    # Partie figée (niveaux précédents)
    frozen = ''
    frozen_count = 0
    for lvl in range(R):
        count = LEVEL_SIZES[lvl]
        frozen += LEVEL_COLORS[lvl] * count
        frozen_count += count

    # Partie mobile (niveau actuel) — ping-pong 0 → LEVEL_SIZES[R]
    cur_size = LEVEL_SIZES[R]
    period   = cur_size * 2
    pos      = frame % max(period, 1)
    moving_count = pos if pos <= cur_size else period - pos
    moving = LEVEL_COLORS[R] * moving_count

    # Cases vides
    used  = frozen_count + moving_count
    empty = '⬜' * max(0, BAR_SIZE - used)

    return frozen + moving + empty


async def _run_animation(original_game: int, check_game: int, start_frame: int = 0):
    """Boucle d'animation: barre multicolore dont la couleur change selon le rattrapage."""
    global pending_predictions, animation_tasks

    try:
        prediction_entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if not prediction_entity:
            return

        frame = start_frame
        while True:
            pred = pending_predictions.get(original_game)
            if not pred or pred.get('status') != 'en_cours':
                break

            msg_id = pred.get('message_id')
            if not msg_id:
                break

            suit = pred['suit']
            suit_display = SUIT_DISPLAY.get(suit, suit)
            rattrapage = pred.get('rattrapage', 0)

            bar = build_anim_bar(rattrapage, frame)

            # Légende du niveau actuel
            level_labels = ['🟦 R0', '🟩 R1', '🟨 R2', '🟥 R3']
            level_label  = level_labels[min(rattrapage, 3)]

            # Petits points animés
            dots = '.' * ((frame % 3) + 1)

            msg = (
                f"🎰 **PRÉDICTION #{original_game}**\n"
                f"🎯 Couleur: {suit_display}\n\n"
                f"🔍 Vérification jeu **#{check_game}** — {level_label}\n"
                f"`{bar}`\n"
                f"⏳ _Analyse{dots}_"
            )

            try:
                await client.edit_message(
                    prediction_entity, msg_id, msg, parse_mode='markdown'
                )
            except Exception as e:
                err = str(e).lower()
                if 'not modified' not in err and 'message_id_invalid' not in err:
                    logger.debug(f"🎬 Edit anim #{original_game}: {e}")

            frame += 1
            await asyncio.sleep(ANIM_INTERVAL)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug(f"🎬 Erreur animation #{original_game}: {e}")
    finally:
        animation_tasks.pop(original_game, None)


def start_animation(original_game: int, check_game: int, start_frame: int = 0):
    """Démarre (ou redémarre) l'animation pour une prédiction."""
    stop_animation(original_game)
    task = asyncio.create_task(_run_animation(original_game, check_game, start_frame))
    animation_tasks[original_game] = task
    logger.info(f"🎬 Animation démarrée #{original_game} → vérifie #{check_game} (frame={start_frame})")


def stop_animation(original_game: int):
    """Arrête l'animation d'une prédiction."""
    task = animation_tasks.pop(original_game, None)
    if task and not task.done():
        task.cancel()


def stop_all_animations():
    """Arrête toutes les animations en cours."""
    for game_num in list(animation_tasks.keys()):
        stop_animation(game_num)


# ============================================================================
# GESTION DES PRÉDICTIONS
# ============================================================================

def format_prediction_message(game_number: int, suit: str, status: str = 'en_cours',
                              current_check: int = None, verified_games: List[int] = None,
                              rattrapage: int = 0) -> str:
    suit_display = SUIT_DISPLAY.get(suit, suit)

    if status == 'en_cours':
        verif_parts = []
        for i in range(4):
            check_num = game_number + i
            if current_check == check_num:
                verif_parts.append(f"🔵#{check_num}")
            elif verified_games and check_num in verified_games:
                continue
            else:
                verif_parts.append(f"⬜#{check_num}")
        verif_line = " | ".join(verif_parts)
        return (
            f"🎰 PRÉDICTION #{game_number}\n"
            f"🎯 Couleur: {suit_display}\n"
            f"📊 Statut: En cours ⏳\n"
            f"🔍 Vérification: {verif_line}"
        )

    elif status == 'gagne':
        num_emoji = ['0️⃣', '1️⃣', '2️⃣', '3️⃣']
        badge = num_emoji[rattrapage] if rattrapage < len(num_emoji) else f'{rattrapage}️⃣'
        return (
            f"🏆 **PRÉDICTION #{game_number}**\n\n"
            f"🎯 **Couleur:** {suit_display}\n"
            f"✅ **Statut:** ✅{badge} GAGNÉ"
        )

    elif status == 'perdu':
        return (
            f"💔 **PRÉDICTION #{game_number}**\n\n"
            f"🎯 **Couleur:** {suit_display}\n"
            f"❌ **Statut:** PERDU 😭"
        )

    elif status == 'expirée_api':
        return (
            f"⚠️ **PRÉDICTION #{game_number}**\n\n"
            f"🎯 **Couleur:** {suit_display}\n"
            f"🔌 **Statut:** EXPIRÉ — jeu sauté par l'API"
        )

    return ""

async def send_prediction_to_channel(channel_id: int, game_number: int, suit: str,
                                     prediction_type: str, is_secondary: bool = False) -> Optional[int]:
    try:
        if not is_secondary and suit in suit_block_until and datetime.now() < suit_block_until[suit]:
            logger.info(f"🔒 {suit} bloqué, prédiction annulée")
            return None
        if not channel_id:
            return None
        channel_entity = await resolve_channel(channel_id)
        if not channel_entity:
            logger.error(f"❌ Canal {channel_id} inaccessible")
            return None
        msg = format_prediction_message(game_number, suit, 'en_cours', game_number, [])
        sent = await client.send_message(channel_entity, msg, parse_mode='markdown')
        return sent.id
    except ChatWriteForbiddenError:
        logger.error(f"❌ Pas de permission dans {channel_id}")
        return None
    except UserBannedInChannelError:
        logger.error(f"❌ Bot banni de {channel_id}")
        return None
    except Exception as e:
        logger.error(f"❌ Erreur envoi à {channel_id}: {e}")
        return None

async def send_prediction_multi_channel(game_number: int, suit: str, prediction_type: str = 'standard') -> bool:
    global last_prediction_time, last_prediction_number_sent, DISTRIBUTION_CHANNEL_ID, COMPTEUR2_CHANNEL_ID

    # Vérification restriction horaire
    if not is_prediction_time_allowed():
        logger.info(f"⏰ Heure non autorisée, prédiction #{game_number} bloquée")
        return False

    # ── Filtre Compteur6 : redirection par paires inverses ──────────────────
    suit_original = suit
    suit = apply_compteur6(suit)
    if suit != suit_original:
        logger.info(f"🔄 C6: prédiction #{game_number} redirigée {suit_original} → {suit}")

    success = False

    if PREDICTION_CHANNEL_ID:
        if game_number in pending_predictions:
            logger.warning(f"⚠️ #{game_number} déjà dans pending")
            return False

        old_last = last_prediction_number_sent
        last_prediction_number_sent = game_number

        # Chercher la raison dans la file d'attente
        queued_reason = ''
        for qp in prediction_queue:
            if qp['game_number'] == game_number and qp['suit'] == suit:
                queued_reason = qp.get('reason', '')
                break

        pending_predictions[game_number] = {
            'suit': suit,
            'message_id': None,
            'status': 'sending',
            'type': prediction_type,
            'sent_time': datetime.now(),
            'verification_games': [game_number, game_number + 1, game_number + 2],
            'verified_games': [],
            'found_at': None,
            'rattrapage': 0,
            'current_check': game_number,
            'reason': queued_reason
        }

        msg_id = await send_prediction_to_channel(
            PREDICTION_CHANNEL_ID, game_number, suit, prediction_type, is_secondary=False
        )

        if msg_id:
            last_prediction_time = datetime.now()
            pending_predictions[game_number]['message_id'] = msg_id
            pending_predictions[game_number]['status'] = 'en_cours'
            add_prediction_to_history(game_number, suit, [game_number, game_number + 1, game_number + 2], prediction_type, queued_reason)
            success = True
            logger.info(f"✅ Prédiction #{game_number} {suit} envoyée ({prediction_type})")
            # Démarrer l'animation dès l'envoi
            start_animation(game_number, game_number)

            secondary_channel_id = None
            if prediction_type == 'distribution' and DISTRIBUTION_CHANNEL_ID:
                secondary_channel_id = DISTRIBUTION_CHANNEL_ID
            elif prediction_type == 'compteur2' and COMPTEUR2_CHANNEL_ID:
                secondary_channel_id = COMPTEUR2_CHANNEL_ID

            if secondary_channel_id:
                sec_msg_id = await send_prediction_to_channel(
                    secondary_channel_id, game_number, suit, prediction_type, is_secondary=True
                )
                if sec_msg_id:
                    pending_predictions[game_number]['secondary_message_id'] = sec_msg_id
                    pending_predictions[game_number]['secondary_channel_id'] = secondary_channel_id
        else:
            if game_number in pending_predictions and pending_predictions[game_number]['status'] == 'sending':
                del pending_predictions[game_number]
            last_prediction_number_sent = old_last

    return success

async def notify_b_augmente(suit: str, old_b: int, new_b: int, game_number: int, rattrapage: int):
    """Envoie une notification privée à l'admin quand le B d'un costume augmente."""
    try:
        if not ADMIN_ID or ADMIN_ID == 0:
            return
        suit_emoji = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}.get(suit, suit)
        suit_display = SUIT_DISPLAY.get(suit, suit)
        r_label = f"R{rattrapage}" if rattrapage > 0 else "Direct"
        msg = (
            f"📈 **B augmenté — {suit_emoji} {suit_display}**\n"
            f"Jeu **#{game_number}** → PERDU ({r_label})\n"
            f"B : **{old_b}** → **{new_b}**"
        )
        admin_entity = await client.get_entity(ADMIN_ID)
        await client.send_message(admin_entity, msg, parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Notif B augmenté: {e}")

async def send_parole_auto_delete(statut_key: str, game_number: int):
    """Envoie une parole biblique sur le canal et la supprime automatiquement après 60s."""
    try:
        entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if not entity:
            return
        texte = get_parole(statut_key, game_number, count=1)
        msg = await client.send_message(entity, texte, parse_mode='markdown')
        await asyncio.sleep(30)
        try:
            await client.delete_messages(entity, [msg.id])
        except Exception as e:
            logger.debug(f"Suppression parole #{game_number} ignorée: {e}")
    except Exception as e:
        logger.debug(f"send_parole_auto_delete #{game_number}: {e}")


async def update_prediction_message(game_number: int, status: str, rattrapage: int = 0):
    if game_number not in pending_predictions:
        return

    pred = pending_predictions[game_number]
    suit = pred['suit']
    msg_id = pred['message_id']
    new_msg = format_prediction_message(game_number, suit, status, rattrapage=rattrapage)

    # Déterminer la clé de parole selon le statut
    parole_key = None
    if 'gagne' in status:
        logger.info(f"✅ Gagné: #{game_number} (R{rattrapage})")
        parole_key = f'gagne_r{rattrapage}'
    elif status == 'expirée_api':
        logger.warning(f"🔌 Prédiction #{game_number} expirée — jeu sauté par l'API (R{rattrapage})")
    else:
        logger.info(f"❌ Perdu: #{game_number}")
        parole_key = 'perdu'
        block_suit(suit, 5)
        # Enregistrer l'événement PERDU
        old_b = compteur2_seuil_B_per_suit.get(suit, compteur2_seuil_B)
        new_b = old_b + 1
        compteur2_seuil_B_per_suit[suit] = new_b
        perdu_events.append({
            'game': game_number,
            'suit': suit,
            'time': datetime.now(),
            'rattrapage': rattrapage,
            'b_before': old_b,
            'b_after': new_b
        })
        logger.info(f"📈 B({suit}) augmenté: {old_b} → {new_b} après PERDU #{game_number}")
        asyncio.create_task(send_perdu_pdf())
        asyncio.create_task(notify_b_augmente(suit, old_b, new_b, game_number, rattrapage))

    # Arrêter l'animation AVANT d'éditer le résultat final
    stop_animation(game_number)
    del pending_predictions[game_number]

    try:
        prediction_entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if prediction_entity and msg_id:
            await client.edit_message(prediction_entity, msg_id, new_msg, parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Erreur édition message #{game_number}: {e}")

    sec_msg_id = pred.get('secondary_message_id')
    sec_channel_id = pred.get('secondary_channel_id')
    if sec_msg_id and sec_channel_id:
        try:
            sec_entity = await resolve_channel(sec_channel_id)
            if sec_entity:
                await client.edit_message(sec_entity, sec_msg_id, new_msg, parse_mode='markdown')
        except Exception as e:
            logger.error(f"❌ Erreur édition canal secondaire #{game_number}: {e}")

    # Envoyer la parole biblique (auto-supprimée après 60s)
    if parole_key:
        asyncio.create_task(send_parole_auto_delete(parole_key, game_number))

async def update_prediction_progress(game_number: int, current_check: int):
    if game_number not in pending_predictions:
        return
    pred = pending_predictions[game_number]
    suit = pred['suit']
    msg_id = pred['message_id']
    verified_games = pred.get('verified_games', [])
    pred['current_check'] = current_check
    # Relancer l'animation depuis le max précédent pour la continuité visuelle
    new_rattrapage = pred.get('rattrapage', 0)
    prev_rattrapage = max(0, new_rattrapage - 1)
    start_frame = BAR_MAX_BY_RATTRAPAGE[min(prev_rattrapage, len(BAR_MAX_BY_RATTRAPAGE) - 1)]
    start_animation(game_number, current_check, start_frame)
    msg = format_prediction_message(game_number, suit, 'en_cours', current_check, verified_games)
    try:
        prediction_entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if prediction_entity:
            await client.edit_message(prediction_entity, msg_id, msg, parse_mode='markdown')
    except Exception as e:
        logger.error(f"❌ Erreur update progress: {e}")

    sec_msg_id = pred.get('secondary_message_id')
    sec_channel_id = pred.get('secondary_channel_id')
    if sec_msg_id and sec_channel_id:
        try:
            sec_entity = await resolve_channel(sec_channel_id)
            if sec_entity:
                await client.edit_message(sec_entity, sec_msg_id, msg, parse_mode='markdown')
        except Exception as e:
            logger.error(f"❌ Erreur update progress canal secondaire: {e}")

async def check_prediction_result(game_number: int, player_suits: Set[str], is_finished: bool = False) -> bool:
    """
    Vérifie les prédictions en attente contre les cartes joueur.
    - Victoire immédiate si le costume est trouvé (même partie non finie).
    - Échec (rattrapage) uniquement quand la partie est terminée (is_finished=True).
    - Catch-up : si le jeu attendu a été sauté par l'API, on récupère depuis l'historique.
    """
    found = False

    # ─── Vérification directe (rattrapage=0, game_number == numéro prédit) ───
    if game_number in pending_predictions:
        pred = pending_predictions[game_number]
        if pred['status'] == 'en_cours':
            target_suit = pred['suit']

            if game_number not in pred['verified_games']:
                logger.info(f"🔍 Vérif #{game_number} (fini={is_finished}): {target_suit} dans {player_suits}?")

                if target_suit in player_suits:
                    # ✅ Costume trouvé → victoire immédiate
                    pred['verified_games'].append(game_number)
                    await update_prediction_message(game_number, 'gagne', 0)
                    update_prediction_in_history(game_number, target_suit, game_number, 0, 'gagne_r0')
                    found = True
                elif is_finished:
                    # ❌ Partie terminée sans le costume → passer au rattrapage R1
                    pred['verified_games'].append(game_number)
                    pred['rattrapage'] = 1
                    next_check = game_number + 1
                    logger.info(f"❌ #{game_number} terminé sans {target_suit}, attente R1 #{next_check}")
                    await update_prediction_progress(game_number, next_check)
                else:
                    # ⏳ Partie en cours, costume pas encore là → re-vérifier au prochain poll
                    logger.debug(f"⏳ #{game_number} en cours, {target_suit} pas encore là")

    # ─── Vérification rattrapage (R1/R2/R3) ──────────────────────────────────
    for original_game, pred in list(pending_predictions.items()):
        if pred['status'] != 'en_cours':
            continue
        rattrapage = pred.get('rattrapage', 0)
        if rattrapage == 0:
            continue  # Géré dans la section directe ci-dessus

        target_suit  = pred['suit']
        expected_game = original_game + rattrapage

        # Ignorer les jeux antérieurs au jeu attendu
        if game_number < expected_game:
            continue

        # ── Catch-up : le jeu attendu a peut-être été sauté par l'API ──
        # On cherche d'abord dans game_result_cache (cache live), puis game_history (terminés).
        check_game       = expected_game
        check_suits      = player_suits
        check_finished   = is_finished
        api_skipped      = False   # True si le jeu attendu est introuvable dans les deux caches

        if game_number > expected_game and expected_game not in pred['verified_games']:
            # 1. Cache live (game_result_cache) — priorité maximale
            cached = game_result_cache.get(expected_game)
            if cached and cached.get('is_finished', False):
                check_suits    = get_player_suits(cached.get('player_cards', []))
                check_finished = True
                logger.info(f"🔁 Catch-up R{rattrapage}: #{expected_game} récupéré depuis cache live")
            else:
                # 2. Historique terminés (game_history)
                hist = game_history.get(expected_game)
                if hist and hist.get('is_finished', False):
                    check_suits    = get_player_suits(hist.get('player_cards', []))
                    check_finished = True
                    logger.info(f"🔁 Catch-up R{rattrapage}: #{expected_game} récupéré depuis historique")
                else:
                    # Jeu introuvable dans les deux caches → API a sauté ce jeu
                    api_skipped = True
                    logger.warning(f"🔌 Catch-up R{rattrapage}: #{expected_game} introuvable — API sautée")

        # Ne pas re-traiter si ce jeu de vérification est déjà enregistré
        if check_game in pred['verified_games']:
            continue

        # ── Jeu sauté par l'API : marquer EXPIRÉ et passer à la suite ──────
        if api_skipped:
            pred['verified_games'].append(expected_game)
            await update_prediction_message(original_game, 'expirée_api', rattrapage)
            update_prediction_in_history(original_game, target_suit, expected_game, rattrapage, 'expirée_api')
            # Nettoyer les entrées de cache devenues inutiles
            game_result_cache.pop(expected_game, None)
            found = True
            continue

        logger.info(f"🔍 Vérif R{rattrapage} #{check_game} (fini={check_finished}): {target_suit} dans {check_suits}?")

        if target_suit in check_suits:
            # ✅ Statut final : GAGNÉ → nettoyer le cache de ce jeu
            pred['verified_games'].append(check_game)
            await update_prediction_message(original_game, 'gagne', rattrapage)
            update_prediction_in_history(original_game, target_suit, check_game, rattrapage, f'gagne_r{rattrapage}')
            game_result_cache.pop(check_game, None)   # nettoyage cache — statut final trouvé
            found = True

        elif check_finished:
            pred['verified_games'].append(check_game)
            if rattrapage < 3:
                # Intermédiaire : passage au rattrapage suivant — cache conservé
                pred['rattrapage'] = rattrapage + 1
                next_check = original_game + rattrapage + 1
                logger.info(f"❌ R{rattrapage} terminé sans {target_suit}, attente R{rattrapage+1} #{next_check}")
                await update_prediction_progress(original_game, next_check)
            else:
                # ❌ Statut final : PERDU R3 → nettoyer le cache de ce jeu
                logger.info(f"❌ R3 terminé sans {target_suit}, prédiction PERDUE #{original_game}")
                await update_prediction_message(original_game, 'perdu', 3)
                update_prediction_in_history(original_game, target_suit, check_game, 3, 'perdu')
                game_result_cache.pop(check_game, None)   # nettoyage cache — statut final trouvé
                found = True

        else:
            # ⏳ Partie en cours, costume pas encore là → re-vérifier au prochain poll
            logger.debug(f"⏳ R{rattrapage} #{check_game} en cours, {target_suit} pas encore là")

    return found

# ============================================================================
# GESTION DE LA FILE D'ATTENTE
# ============================================================================

def can_accept_prediction(pred_number: int) -> bool:
    global prediction_queue, pending_predictions, last_prediction_number_sent, MIN_GAP_BETWEEN_PREDICTIONS

    # Règle 1 : jamais de nouvelle prédiction si une est en cours de vérification
    if pending_predictions:
        logger.debug(f"🚫 #{pred_number} ignoré — prédiction en attente de vérification")
        return False

    # Règle 2 : intervalle minimum de {MIN_GAP} jeux entre numéros de prédiction
    if last_prediction_number_sent > 0:
        gap = pred_number - last_prediction_number_sent
        if gap < MIN_GAP_BETWEEN_PREDICTIONS:
            logger.debug(f"🚫 #{pred_number} ignoré — écart {gap} < {MIN_GAP_BETWEEN_PREDICTIONS} (dernière #{last_prediction_number_sent})")
            return False

    for queued_pred in prediction_queue:
        existing_num = queued_pred['game_number']
        gap = abs(pred_number - existing_num)
        if gap < MIN_GAP_BETWEEN_PREDICTIONS:
            return False

    return True

def add_to_prediction_queue(game_number: int, suit: str, prediction_type: str, reason: str = '') -> bool:
    global prediction_queue

    for pred in prediction_queue:
        if pred['game_number'] == game_number:
            return False

    if not can_accept_prediction(game_number):
        return False

    prediction_queue.append({
        'game_number': game_number,
        'suit': suit,
        'type': prediction_type,
        'reason': reason,
        'added_at': datetime.now()
    })
    prediction_queue.sort(key=lambda x: x['game_number'])
    logger.info(f"📥 #{game_number} ({suit}) en file. Total: {len(prediction_queue)}")
    return True

async def process_prediction_queue(current_game: int):
    global prediction_queue, pending_predictions

    if pending_predictions:
        return

    to_remove = []
    to_send = None

    for pred in list(prediction_queue):
        pred_number = pred['game_number']

        if current_game > pred_number - PREDICTION_SEND_AHEAD:
            logger.warning(f"⏰ #{pred_number} EXPIRÉ (canal #{current_game})")
            to_remove.append(pred)
            continue

        if current_game == pred_number - PREDICTION_SEND_AHEAD:
            to_send = pred
            break

    for pred in to_remove:
        prediction_queue.remove(pred)

    if to_send:
        if pending_predictions:
            return
        pred_number = to_send['game_number']
        suit = to_send['suit']
        pred_type = to_send['type']
        logger.info(f"📤 Envoi depuis file: #{pred_number}")
        success = await send_prediction_multi_channel(pred_number, suit, pred_type)
        if success:
            prediction_queue.remove(to_send)

# ============================================================================
# MISE À JOUR COMPTEUR2
# ============================================================================

def update_compteur2(game_number: int, player_suits: Set[str]):
    global compteur2_trackers
    for suit in ALL_SUITS:
        tracker = compteur2_trackers[suit]
        if suit in player_suits:
            tracker.reset(game_number)
        else:
            tracker.increment(game_number)

def get_compteur2_ready_predictions(current_game: int) -> List[tuple]:
    global compteur2_trackers, compteur2_seuil_B_per_suit
    ready = []
    for suit in ALL_SUITS:
        tracker = compteur2_trackers[suit]
        b = compteur2_seuil_B_per_suit.get(suit, compteur2_seuil_B)
        if tracker.check_threshold(b):
            pred_number = current_game + 2
            start_game = tracker.last_increment_game - (tracker.counter - 1)
            suit_display = SUIT_DISPLAY.get(suit, suit)
            reason = (
                f"Du jeu #{start_game} au jeu #{tracker.last_increment_game}, "
                f"{suit_display} etait absent {tracker.counter} fois de suite "
                f"(seuil B={b}). Prediction lancee pour le jeu #{pred_number}."
            )
            ready.append((suit, pred_number, reason))
            tracker.reset(current_game)
    return ready

# ============================================================================
# TRAITEMENT DES JEUX (API)
# ============================================================================

async def send_bilan_and_reset_at_1440():
    """
    Fin de cycle jeu #1440 — séquence exacte :
      1. Bilan général → admin (chat privé)
      2. PDF Compteur4, Compteur5, Perdus → admin (avant tout reset)
      3. Attente 20 secondes
      4. Reset du stock de données (prédictions, historiques, compteurs)
         — Les perdu_events ne sont JAMAIS effacés (comparaison inter-journées)
         — Les B par costume sont remis à la valeur B admin
         — Toutes les configurations admin sont préservées
      5. Notification de reset → admin (chat privé)
    """
    global prediction_history, bilan_1440_sent
    global pending_predictions, prediction_queue, finalized_messages_history
    global processed_games, prediction_checked_games, perdu_pdf_msg_id
    global compteur4_trackers, compteur4_events, compteur4_pdf_msg_id
    global compteur5_trackers, compteur5_events, compteur5_pdf_msg_id
    global compteur2_trackers, compteur2_seuil_B_per_suit
    global compteur1_trackers, compteur1_history
    global last_prediction_time, last_prediction_number_sent, suit_block_until
    global animation_tasks

    bilan_1440_sent = True

    # ── ÉTAPE 1 : Bilan → admin uniquement ──────────────────────────────────
    txt = get_bilan_text()
    total_finalized = sum(
        1 for p in prediction_history
        if p.get('status', '') not in ('en_cours', '')
    )
    header = (
        f"🔔 **FIN DE CYCLE — JEU #1440**\n"
        f"Bilan sur **{total_finalized}** prédiction(s) finalisées.\n"
        f"Le bot repart à neuf dans 20 secondes.\n\n"
    )
    # Envoi du bilan dans le canal de prédiction
    try:
        canal_entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if canal_entity:
            await client.send_message(canal_entity, header + txt, parse_mode='markdown')
            logger.info("📊 Bilan #1440 envoyé dans le canal de prédiction.")
    except Exception as e:
        logger.error(f"❌ Erreur envoi bilan #1440 canal: {e}")

    # Envoi du bilan également à l'administrateur (chat privé)
    if ADMIN_ID and ADMIN_ID != 0:
        try:
            admin_entity = await client.get_entity(ADMIN_ID)
            await client.send_message(admin_entity, header + txt, parse_mode='markdown')
            logger.info("📊 Bilan #1440 envoyé à l'administrateur (chat privé).")
        except Exception as e:
            logger.error(f"❌ Erreur envoi bilan #1440 admin: {e}")

    # ── ÉTAPE 2 : Envoi de tous les PDFs AVANT le reset ─────────────────────
    logger.info("📄 Envoi des PDFs avant reset #1440...")

    # PDF Compteur4 (snapshot — données persistantes, NON effacées au reset)
    try:
        if compteur4_events:
            pdf4 = generate_compteur4_pdf(compteur4_events)
            buf4 = io.BytesIO(pdf4)
            buf4.name = "compteur4_absences_cycle.pdf"
            admin_entity = await client.get_entity(ADMIN_ID)
            await client.send_file(
                admin_entity, buf4,
                caption=(
                    f"🔴 **COMPTEUR4 — SNAPSHOT FIN DE CYCLE**\n"
                    f"Total séries d'absences : **{len(compteur4_events)}**\n"
                    f"⚠️ Ces données sont persistantes — elles ne seront PAS effacées au reset"
                ),
                parse_mode='markdown',
                file_name="compteur4_absences_cycle.pdf"
            )
            logger.info("✅ PDF Compteur4 snapshot envoyé avant reset")
    except Exception as e:
        logger.error(f"❌ PDF Compteur4 avant reset: {e}")

    # PDF Compteur5
    try:
        if compteur5_events:
            pdf5 = generate_compteur5_pdf(compteur5_events)
            buf5 = io.BytesIO(pdf5)
            buf5.name = "compteur5_presences_final.pdf"
            admin_entity = await client.get_entity(ADMIN_ID)
            await client.send_file(
                admin_entity, buf5,
                caption=(
                    f"✅ **COMPTEUR5 — PDF FINAL DU CYCLE**\n"
                    f"Total présences : **{len(compteur5_events)}**\n"
                    f"_(Sauvegarde avant reset)_"
                ),
                parse_mode='markdown',
                file_name="compteur5_presences_final.pdf"
            )
            logger.info("✅ PDF Compteur5 final envoyé avant reset")
    except Exception as e:
        logger.error(f"❌ PDF Compteur5 avant reset: {e}")

    # PDF Perdus (perdu_events ne sera JAMAIS effacé — comparaison inter-journées)
    try:
        if perdu_events:
            await send_perdu_pdf()
            logger.info("✅ PDF Perdus final envoyé avant reset")
    except Exception as e:
        logger.error(f"❌ PDF Perdus avant reset: {e}")

    # ── ÉTAPE 3 : Attente 20 secondes ───────────────────────────────────────
    logger.info("⏳ Attente 20 secondes avant reset #1440...")
    await asyncio.sleep(20)

    # ── ÉTAPE 4 : Reset du stock de données ─────────────────────────────────
    nb_pending = len(pending_predictions)
    nb_queue   = len(prediction_queue)
    nb_history = len(prediction_history)
    nb_c4      = len(compteur4_events)
    nb_c5      = len(compteur5_events)
    nb_perdu   = len(perdu_events)     # conservé, juste pour le rapport

    stop_all_animations()

    # Prédictions
    pending_predictions.clear()
    prediction_queue.clear()
    prediction_history.clear()
    finalized_messages_history.clear()
    processed_games.clear()
    prediction_checked_games.clear()
    suit_block_until.clear()
    last_prediction_time        = None
    last_prediction_number_sent = 0
    perdu_pdf_msg_id            = None

    # Événements Compteur5 (vidés — PDF déjà envoyé)
    compteur5_events.clear()
    compteur5_pdf_msg_id = None
    # ⚠️ compteur4_events N'EST PAS EFFACÉ — persistant entre cycles (comme C7)
    compteur4_pdf_msg_id = None

    # Compteurs remis à 0
    for suit in ALL_SUITS:
        compteur4_trackers[suit] = 0
        compteur5_trackers[suit] = 0
        # Reset de la série d'absence courante (l'historique persistant reste intact)
        compteur4_current[suit] = {'count': 0, 'start_game': None, 'start_time': None, 'alerted': False}

    for tracker in compteur2_trackers.values():
        tracker.counter = 0
        tracker.last_increment_game = 0

    for tracker in compteur1_trackers.values():
        tracker.counter    = 0
        tracker.start_game = 0
        tracker.last_game  = 0
    compteur1_history.clear()

    # B par costume remis à la valeur B admin (les hausses du cycle sont effacées)
    for suit in ALL_SUITS:
        compteur2_seuil_B_per_suit[suit] = compteur2_seuil_B
    logger.info(f"🔄 B par costume remis à B admin ({compteur2_seuil_B}) pour tous les costumes")

    # Compteur6 : compteurs d'apparitions remis à 0 (le seuil Wj admin est préservé)
    for suit in ALL_SUITS:
        compteur6_trackers[suit] = 0
    logger.info(f"🔄 Compteur6 remis à 0 (Wj={compteur6_seuil_Wj} préservé)")

    # ⚠️ perdu_events N'EST JAMAIS EFFACÉ — comparaison inter-journées préservée

    logger.info("🔄 Reset complet du stock #1440 — configs admin et perdu_events préservés.")

    # ── ÉTAPE 5 : Notification de reset → admin ──────────────────────────────
    if ADMIN_ID and ADMIN_ID != 0:
        try:
            admin_entity = await client.get_entity(ADMIN_ID)
            msg = (
                f"♻️ **RESET EFFECTUÉ — FIN DU CYCLE #1440**\n\n"
                f"**Données effacées :**\n"
                f"  • {nb_pending} prédiction(s) en attente\n"
                f"  • {nb_queue} prédiction(s) en file\n"
                f"  • {nb_history} entrées d'historique\n"
                f"  • {nb_c5} événement(s) Compteur5\n"
                f"  • B par costume remis à B admin ({compteur2_seuil_B})\n\n"
                f"**Préservé (persistant entre cycles) :**\n"
                f"  • {nb_perdu} pertes historiques (inter-journées)\n"
                f"  • {len(compteur4_events)} séries Compteur4 (absences persistantes)\n"
                f"  • Séries Compteur7 (présences persistantes)\n"
                f"  • B admin : {compteur2_seuil_B}\n"
                f"  • Seuil Compteur4 : {COMPTEUR4_THRESHOLD}\n"
                f"  • Seuil Compteur5 : {COMPTEUR5_THRESHOLD}\n"
                f"  • Restriction horaire : {'Active' if PREDICTION_HOURS else 'Inactive'}\n"
                f"  • Toutes les configurations admin\n\n"
                f"✅ Le bot est neuf et prêt pour le prochain cycle."
            )
            await client.send_message(admin_entity, msg, parse_mode='markdown')
        except Exception as e:
            logger.error(f"❌ Erreur notif admin #1440: {e}")


async def process_game_result(game_number: int, player_suits: Set[str], player_cards_raw: list, is_finished: bool = False):
    """Traite un résultat de jeu venant de l'API 1xBet."""
    global current_game_number, processed_games, bilan_1440_sent

    if game_number > current_game_number:
        current_game_number = game_number

    # Vérification dynamique des prédictions
    # Victoire immédiate si costume trouvé, échec seulement si partie terminée
    await check_prediction_result(game_number, player_suits, is_finished)

    # Traiter la file d'attente
    await process_prediction_queue(game_number)

    # Comptabilisation (une seule fois par jeu)
    if game_number not in processed_games:
        processed_games.add(game_number)

        add_to_history(game_number, player_suits)
        update_compteur1(game_number, player_suits)
        update_compteur2(game_number, player_suits)

        # Compteur4: séries d'absences (seuil + série complète, persistant)
        threshold4, completed4 = update_compteur4(game_number, player_suits, player_cards_raw)
        for suit in threshold4:
            cur4 = compteur4_current[suit]
            asyncio.create_task(send_compteur4_threshold_alert(suit, game_number, cur4['start_game']))
        for series4 in completed4:
            asyncio.create_task(send_compteur4_series_alert(series4))
            asyncio.create_task(send_compteur4_pdf())

        # Compteur5: détecter les présences consécutives de 10
        triggered5 = update_compteur5(game_number, player_suits, player_cards_raw)
        if triggered5:
            asyncio.create_task(send_compteur5_alert(triggered5, game_number))
            asyncio.create_task(send_compteur5_pdf())

        # Compteur6: mettre à jour le compteur d'apparitions par costume
        update_compteur6(player_suits)

        # Compteur7: séries consécutives (min 5) — persistant entre resets
        completed7 = update_compteur7(game_number, player_suits)
        for series in completed7:
            asyncio.create_task(send_compteur7_alert(series))
            asyncio.create_task(send_compteur7_pdf())

        # Données horaires pour /comparaison
        update_hourly_data(player_suits)

        # Prédictions Compteur2
        if compteur2_active:
            compteur2_preds = get_compteur2_ready_predictions(game_number)
            for suit, pred_num, reason in compteur2_preds:
                added = add_to_prediction_queue(pred_num, suit, 'compteur2', reason)
                if added:
                    logger.info(f"📊 Compteur2: #{pred_num} {suit} en file")

        logger.info(f"📊 Jeu #{game_number}: joueur {player_suits} | C4={dict(compteur4_trackers)}")

    # Fin de cycle : jeu #1440 terminé → bilan envoyé + reset historique
    if game_number == 1440 and is_finished and not bilan_1440_sent:
        asyncio.create_task(send_bilan_and_reset_at_1440())

    # Nouveau cycle détecté (jeu #1 ou #2) → réarmer le flag pour le prochain #1440
    if game_number <= 2 and bilan_1440_sent:
        bilan_1440_sent = False
        logger.info("🔄 Nouveau cycle détecté — bilan_1440 réarmé")

# ============================================================================
# BOUCLE DE POLLING API
# ============================================================================

async def api_polling_loop():
    """Boucle principale: interroge l'API 1xBet et traite les résultats."""
    global game_history, game_result_cache

    logger.info("🔄 Démarrage boucle de polling API (toutes les 4s)...")
    loop = asyncio.get_event_loop()

    while True:
        try:
            results = await loop.run_in_executor(None, get_latest_results)

            if results:
                for result in results:
                    game_number = result['game_number']
                    player_cards = result.get('player_cards', [])

                    if not player_cards:
                        continue

                    player_suits = get_player_suits(player_cards)
                    if not player_suits:
                        continue

                    is_finished = result.get('is_finished', False)

                    # Mettre à jour l'historique (jeux terminés uniquement)
                    game_history[game_number] = result

                    # ── Cache live : stocker TOUS les jeux (en cours + terminés) ──
                    # Un jeu terminé ne régresse jamais → on ne remplace pas is_finished=True
                    existing = game_result_cache.get(game_number, {})
                    if not existing.get('is_finished', False):
                        game_result_cache[game_number] = {
                            'player_cards': player_cards,
                            'player_suits': player_suits,
                            'is_finished': is_finished,
                        }

                    # Victoire immédiate si costume trouvé, échec seulement si partie terminée
                    await process_game_result(game_number, player_suits, player_cards, is_finished)

                # ── Nettoyage du cache live : conserver au max 200 entrées ──
                if len(game_result_cache) > 200:
                    cutoff = sorted(game_result_cache.keys())[:-150]  # garder les 150 plus récents
                    for k in cutoff:
                        game_result_cache.pop(k, None)

                # Garder l'historique propre (max 500 jeux)
                if len(game_history) > 500:
                    oldest = sorted(game_history.keys())[:100]
                    for k in oldest:
                        game_history.pop(k, None)
            else:
                logger.debug("🔄 API: aucun résultat")

        except Exception as e:
            logger.error(f"❌ Erreur polling API: {e}")

        await asyncio.sleep(4)

# ============================================================================
# RESET ET NETTOYAGE
# ============================================================================

async def cleanup_stale_predictions():
    global pending_predictions
    from config import PREDICTION_TIMEOUT_MINUTES
    now = datetime.now()
    stale = []

    for game_number, pred in list(pending_predictions.items()):
        sent_time = pred.get('sent_time')
        if sent_time:
            age_minutes = (now - sent_time).total_seconds() / 60
            if age_minutes >= PREDICTION_TIMEOUT_MINUTES:
                stale.append(game_number)
        else:
            # BUG FIX : sent_time=None → prédiction jamais nettoyée → bot bloqué.
            # Fallback : utiliser l'heure actuelle comme référence — on la retire immédiatement.
            logger.warning(f"🧹 #{game_number} sans sent_time — forcé en timeout")
            stale.append(game_number)

    for game_number in stale:
        pred = pending_predictions.get(game_number)
        if pred:
            suit = pred.get('suit', '?')
            logger.warning(f"🧹 #{game_number} ({suit}) expiré (timeout)")
            stop_animation(game_number)
            try:
                prediction_entity = await resolve_channel(PREDICTION_CHANNEL_ID)
                if prediction_entity and pred.get('message_id'):
                    suit_display = SUIT_DISPLAY.get(suit, suit)
                    expired_msg = f"⏰ **PRÉDICTION #{game_number}**\n🎯 {suit_display}\n⌛ **EXPIRÉE**"
                    await client.edit_message(prediction_entity, pred['message_id'], expired_msg, parse_mode='markdown')
            except Exception as e:
                logger.debug(f"Édition message expiré #{game_number} ignorée: {e}")
            del pending_predictions[game_number]

async def auto_reset_system():
    """Vérifie toutes les 30s les prédictions en attente et supprime celles expirées (>10min)."""
    while True:
        try:
            await asyncio.sleep(30)
            if pending_predictions:
                await cleanup_stale_predictions()
        except Exception as e:
            logger.error(f"❌ Erreur auto_reset: {e}")
            await asyncio.sleep(30)

# ─── Watchdog global : déblocage automatique ────────────────────────────────

_api_polling_task: Optional[asyncio.Task] = None

async def _api_polling_guardian():
    """Lance api_polling_loop et la redémarre automatiquement si elle s'arrête."""
    global _api_polling_task
    while True:
        try:
            logger.info("🔄 Démarrage/redémarrage api_polling_loop via guardian")
            _api_polling_task = asyncio.create_task(api_polling_loop())
            await _api_polling_task
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ Guardian: api_polling_loop crash inattendu: {e}")
        logger.warning("⚠️ api_polling_loop terminée — redémarrage dans 5s")
        await asyncio.sleep(5)

async def auto_watchdog_task():
    """
    Watchdog global — s'exécute toutes les 60s.
    Détecte et débloque automatiquement :
      1. Prédictions bloquées au-delà de 15 min (sécurité post-timeout)
      2. Tous les costumes bloqués simultanément (suit_block_until)
      3. Notifie l'admin à chaque déblocage automatique
    """
    global pending_predictions, suit_block_until, prediction_queue
    from config import PREDICTION_TIMEOUT_MINUTES, FORCE_RESTART_THRESHOLD

    HARD_TIMEOUT = max(PREDICTION_TIMEOUT_MINUTES + 5, 15)  # 15 min minimum

    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now()
            actions = []

            # ── 1. Prédictions bloquées au-delà du hard timeout ─────────────
            hard_stale = []
            for game_number, pred in list(pending_predictions.items()):
                sent_time = pred.get('sent_time')
                if sent_time is None or (now - sent_time).total_seconds() / 60 >= HARD_TIMEOUT:
                    hard_stale.append(game_number)

            if hard_stale:
                for gn in hard_stale:
                    pred = pending_predictions.pop(gn, None)
                    if pred:
                        stop_animation(gn)
                        suit = pred.get('suit', '?')
                        actions.append(f"🧹 Prédiction #{gn} ({suit}) forcée hors mémoire")
                        try:
                            entity = await resolve_channel(PREDICTION_CHANNEL_ID)
                            if entity and pred.get('message_id'):
                                sd = SUIT_DISPLAY.get(suit, suit)
                                await client.edit_message(
                                    entity, pred['message_id'],
                                    f"⏰ **PRÉDICTION #{gn}**\n🎯 {sd}\n⌛ **EXPIRÉE (watchdog)**",
                                    parse_mode='markdown')
                        except Exception:
                            pass

            # ── 2. Tous les costumes simultanément bloqués ──────────────────
            blocked_suits = [s for s in ALL_SUITS if s in suit_block_until and now < suit_block_until[s]]
            if len(blocked_suits) == len(ALL_SUITS):
                suit_block_until.clear()
                actions.append("🔓 Tous les costumes étaient bloqués — déblocage forcé")
                logger.warning("⚠️ Watchdog: tous les costumes bloqués → déblocage automatique")

            # ── 3. Notification admin ────────────────────────────────────────
            if actions and ADMIN_ID:
                try:
                    admin_entity = await client.get_entity(ADMIN_ID)
                    msg = "🤖 **WATCHDOG — Déblocage automatique**\n\n" + "\n".join(actions)
                    await client.send_message(admin_entity, msg, parse_mode='markdown')
                except Exception as e:
                    logger.warning(f"Watchdog: impossible de notifier admin: {e}")

        except Exception as e:
            logger.error(f"❌ Erreur watchdog: {e}")

async def perform_full_reset(reason: str):
    global pending_predictions, last_prediction_time
    global last_prediction_number_sent, compteur2_trackers, prediction_queue
    global compteur1_trackers, compteur1_history, processed_games, prediction_checked_games
    global compteur2_seuil_B_per_suit, compteur2_seuil_B, game_result_cache

    stats = len(pending_predictions)
    queue_stats = len(prediction_queue)

    for tracker in compteur1_trackers.values():
        if tracker.counter >= MIN_CONSECUTIVE_FOR_STATS:
            save_compteur1_series(tracker.suit, tracker.counter, tracker.start_game, tracker.last_game)

    for tracker in compteur2_trackers.values():
        tracker.counter = 0
        tracker.last_increment_game = 0

    for tracker in compteur1_trackers.values():
        tracker.counter = 0
        tracker.start_game = 0
        tracker.last_game = 0

    for suit in ALL_SUITS:
        compteur4_trackers[suit] = 0
        compteur4_current[suit] = {'count': 0, 'start_game': None, 'start_time': None, 'alerted': False}

    stop_all_animations()
    pending_predictions.clear()
    prediction_queue.clear()
    processed_games.clear()
    prediction_checked_games.clear()
    game_result_cache.clear()
    last_prediction_time = None
    last_prediction_number_sent = 0
    suit_block_until.clear()

    # Remettre les B dynamiques par costume à la valeur initiale
    for suit in ALL_SUITS:
        compteur2_seuil_B_per_suit[suit] = compteur2_seuil_B
    logger.info(f"🔄 B par costume réinitialisé à {compteur2_seuil_B} pour tous les costumes")

    logger.info(f"🔄 {reason} - {stats} actives, {queue_stats} file cleared")

    if ADMIN_ID and ADMIN_ID != 0:
        try:
            admin_entity = await client.get_entity(ADMIN_ID)
            msg = (
                f"🔄 **RESET SYSTÈME**\n\n"
                f"{reason}\n\n"
                f"✅ {stats} prédictions actives effacées\n"
                f"✅ {queue_stats} prédictions en file effacées\n"
                f"✅ Compteurs remis à zéro\n\n"
                f"🤖 Baccarat AI"
            )
            await client.send_message(admin_entity, msg, parse_mode='markdown')
        except Exception as e:
            logger.error(f"❌ Impossible de notifier l'admin: {e}")

# ============================================================================
# COMMANDES ADMIN
# ============================================================================

async def cmd_heures(event):
    """Gestion des plages horaires de prédiction."""
    global PREDICTION_HOURS

    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return

    try:
        parts = event.message.message.split()

        if len(parts) == 1:
            now = datetime.now()
            allowed = "✅ OUI" if is_prediction_time_allowed() else "❌ NON"
            await event.respond(
                f"⏰ **RESTRICTION HORAIRE**\n\n"
                f"Heure actuelle: **{now.strftime('%H:%M')}**\n"
                f"Prédictions autorisées: {allowed}\n\n"
                f"**Plages actives:**\n{format_hours_config()}\n\n"
                f"**Usage:**\n"
                f"`/heures add HH-HH` — Ajouter une plage\n"
                f"`/heures del HH-HH` — Supprimer une plage\n"
                f"`/heures clear` — Supprimer toutes les plages (24h/24)"
            )
            return

        sub = parts[1].lower()

        if sub == 'clear':
            PREDICTION_HOURS.clear()
            await event.respond("✅ **Toutes les restrictions horaires supprimées** — prédictions 24h/24")
            return

        if sub == 'add' and len(parts) >= 3:
            raw = parts[2]
            if '-' not in raw:
                await event.respond("❌ Format: HH-HH (ex: `/heures add 18-17`)")
                return
            s_str, e_str = raw.split('-', 1)
            s_h, e_h = int(s_str.strip()), int(e_str.strip())
            if not (0 <= s_h <= 23 and 0 <= e_h <= 23):
                await event.respond("❌ Heures entre 0 et 23")
                return
            PREDICTION_HOURS.append((s_h, e_h))
            await event.respond(
                f"✅ **Plage ajoutée:** {s_h:02d}h00 → {e_h:02d}h00\n\n"
                f"**Plages actives:**\n{format_hours_config()}"
            )
            return

        if sub == 'del' and len(parts) >= 3:
            raw = parts[2]
            if '-' not in raw:
                await event.respond("❌ Format: HH-HH")
                return
            s_str, e_str = raw.split('-', 1)
            s_h, e_h = int(s_str.strip()), int(e_str.strip())
            if (s_h, e_h) in PREDICTION_HOURS:
                PREDICTION_HOURS.remove((s_h, e_h))
                await event.respond(f"✅ **Plage supprimée:** {s_h:02d}h00 → {e_h:02d}h00")
            else:
                await event.respond(f"❌ Plage {s_h:02d}h-{e_h:02d}h introuvable")
            return

        await event.respond(
            "❌ Usage:\n"
            "`/heures` — Voir config\n"
            "`/heures add HH-HH` — Ajouter plage\n"
            "`/heures del HH-HH` — Supprimer plage\n"
            "`/heures clear` — Tout supprimer"
        )

    except ValueError:
        await event.respond("❌ Format invalide. Utilisez des entiers (ex: `/heures add 18-17`)")
    except Exception as e:
        logger.error(f"Erreur cmd_heures: {e}")
        await event.respond(f"❌ Erreur: {e}")


async def cmd_compteur4(event):
    """Affiche le statut du Compteur4 et envoie le PDF des écarts."""
    global compteur4_trackers, compteur4_events, COMPTEUR4_THRESHOLD

    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return

    try:
        parts = event.message.message.split()

        if len(parts) >= 2:
            sub = parts[1].lower()

            if sub == 'seuil' and len(parts) >= 3:
                try:
                    val = int(parts[2])
                    if not 5 <= val <= 50:
                        await event.respond("❌ Seuil entre 5 et 50")
                        return
                    old = COMPTEUR4_THRESHOLD
                    COMPTEUR4_THRESHOLD = val
                    await event.respond(f"✅ **Seuil Compteur4:** {old} → {val}")
                    return
                except ValueError:
                    await event.respond("❌ Usage: `/compteur4 seuil 10`")
                    return

            if sub == 'pdf':
                await event.respond("📄 Génération du PDF en cours...")
                await send_compteur4_pdf()
                return

            if sub == 'reset':
                for suit in ALL_SUITS:
                    compteur4_trackers[suit] = 0
                    compteur4_current[suit] = {'count': 0, 'start_game': None, 'start_time': None, 'alerted': False}
                compteur4_events.clear()
                save_compteur4_data()
                await event.respond("🔄 **Compteur4 reset** — Compteurs, séries courantes et historique effacés")
                return

        # Affichage statut
        suit_names  = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
        suit_emoji  = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}
        lines = [
            f"🔴 **COMPTEUR4** — Absences consécutives (seuil ≥ {COMPTEUR4_THRESHOLD})\n",
            "**En cours :**",
        ]

        any_active = False
        for suit in ALL_SUITS:
            cur   = compteur4_current[suit]
            count = cur['count']
            name  = SUIT_DISPLAY.get(suit, suit)
            if count > 0:
                any_active = True
                bar = "█" * min(count, 12) + ("…" if count > 12 else "")
                alert = " 🚨" if count >= COMPTEUR4_THRESHOLD else ""
                lines.append(f"  {name}: [{bar}] {count}x (depuis #{cur['start_game']}){alert}")
            else:
                lines.append(f"  {name}: —")

        if not any_active:
            lines.append("  _(aucune série en cours)_")

        total = len(compteur4_events)
        lines.append(f"\n**Séries terminées enregistrées :** {total}")
        if total > 0:
            for s in compteur4_events[-5:]:
                emo = suit_emoji.get(s['suit'], s['suit'])
                end_date = s['end_time'].strftime('%d/%m %Hh%M')
                lines.append(
                    f"  • {end_date} — {emo} **{s['count']}x** "
                    f"(#{s['start_game']}→#{s['end_game']})"
                )
            lines.append("_(5 dernières — /compteur4 pdf pour le tableau complet)_")

        lines.append(f"\nUsage: `/compteur4` `pdf` `seuil N` `reset`")
        await event.respond("\n".join(lines), parse_mode='markdown')

    except Exception as e:
        logger.error(f"Erreur cmd_compteur4: {e}")
        await event.respond(f"❌ Erreur: {e}")


async def cmd_compteur5(event):
    """Affiche le statut du Compteur5 et envoie le PDF des présences consécutives."""
    global compteur5_trackers, compteur5_events, COMPTEUR5_THRESHOLD
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        raw   = event.message.message.strip()
        parts = raw.split()
        sub   = parts[1].lower() if len(parts) > 1 else ''

        if sub == 'pdf':
            await send_compteur5_pdf()
            await event.respond("✅ PDF Compteur5 envoyé.")
            return

        if sub == 'seuil' and len(parts) > 2:
            try:
                val = int(parts[2])
                if val < 1:
                    await event.respond("❌ Seuil minimum : 1")
                    return
                old = COMPTEUR5_THRESHOLD
                COMPTEUR5_THRESHOLD = val
                await event.respond(f"✅ **Seuil Compteur5:** {old} → {val}")
            except ValueError:
                await event.respond("❌ Usage: `/compteur5 seuil 10`")
            return

        if sub == 'reset':
            for suit in ALL_SUITS:
                compteur5_trackers[suit] = 0
            compteur5_events.clear()
            await event.respond("🔄 **Compteur5 reset** — Compteurs et historique effacés")
            return

        # Affichage du statut
        suit_emoji_map = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}
        lines = [f"✅ **COMPTEUR5 — PRÉSENCES CONSÉCUTIVES** (seuil: {COMPTEUR5_THRESHOLD})", ""]
        for suit in ALL_SUITS:
            count   = compteur5_trackers.get(suit, 0)
            name    = SUIT_DISPLAY.get(suit, suit)
            bar_len = min(count, COMPTEUR5_THRESHOLD)
            bar     = "█" * bar_len + "░" * (COMPTEUR5_THRESHOLD - bar_len)
            pct     = f"{count}/{COMPTEUR5_THRESHOLD}"
            alert   = " 🔥" if count >= COMPTEUR5_THRESHOLD else ""
            lines.append(f"{name}: [{bar}] {pct}{alert}")

        lines.append(f"\n**Événements enregistrés:** {len(compteur5_events)}")

        if compteur5_events:
            lines.append(f"\n**Derniers enregistrements :**")
            for ev in compteur5_events[-5:][::-1]:
                emoji = suit_emoji_map.get(ev['suit'], ev['suit'])
                dt    = ev['datetime']
                lines.append(
                    f"  • Le {dt.strftime('%d/%m/%Y')} A {dt.strftime('%Hh%M')} "
                    f"{emoji} Numéro {ev['game_number']}"
                )

        lines.append(
            f"\n**Usage:**\n`/compteur5 pdf` — Envoyer le PDF\n"
            f"`/compteur5 seuil N` — Changer le seuil (actuel: {COMPTEUR5_THRESHOLD})\n"
            f"`/compteur5 reset` — Réinitialiser"
        )
        await event.respond("\n".join(lines))

    except Exception as e:
        logger.error(f"Erreur cmd_compteur5: {e}")
        await event.respond(f"❌ Erreur: {e}")


async def cmd_compteur6(event):
    """Affiche le statut du Compteur6 et permet de régler le seuil Wj."""
    global compteur6_seuil_Wj, compteur6_trackers
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        raw   = event.message.message.strip()
        parts = raw.split()
        sub   = parts[1].lower() if len(parts) > 1 else ''

        # /compteur6 wj N  — changer le seuil Wj
        if sub in ('wj', 'seuil') and len(parts) > 2:
            try:
                val = int(parts[2])
                if val < 1:
                    await event.respond("❌ Valeur minimum : 1")
                    return
                old = compteur6_seuil_Wj
                compteur6_seuil_Wj = val
                await event.respond(
                    f"✅ **Seuil Wj (Compteur6):** {old} → {val}\n"
                    f"Le filtre de prédiction utilisera désormais Wj = **{val}**"
                )
            except ValueError:
                await event.respond("❌ Usage: `/compteur6 wj 3`")
            return

        # /compteur6 reset — remettre les compteurs à 0
        if sub == 'reset':
            for suit in ALL_SUITS:
                compteur6_trackers[suit] = 0
            await event.respond(
                f"🔄 **Compteur6 reset** — Compteurs remis à 0\n"
                f"Seuil Wj préservé : **{compteur6_seuil_Wj}**"
            )
            return

        # Affichage du statut — format identique au Compteur2
        wj = compteur6_seuil_Wj
        lines = [f"📊 **COMPTEUR6** (Apparitions costume)\n"]
        for suit in ALL_SUITS:
            count   = compteur6_trackers.get(suit, 0)
            name    = SUIT_DISPLAY.get(suit, suit)
            filled  = min(count, wj)
            bar     = "█" * filled + "░" * (wj - filled)
            lines.append(f"{name}: [{bar}] {count}/{wj}")

        lines.append(f"\nUsage: /compteur6 [wj N/reset]")
        await event.respond("\n".join(lines), parse_mode='markdown')

    except Exception as e:
        logger.error(f"Erreur cmd_compteur6: {e}")
        await event.respond(f"❌ Erreur: {e}")


async def cmd_compteur7(event):
    """Affiche le statut du Compteur7 (séries consécutives) et permet de l'administrer."""
    global compteur7_current, compteur7_completed, COMPTEUR7_THRESHOLD
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        raw   = event.message.message.strip()
        parts = raw.split()
        sub   = parts[1].lower() if len(parts) > 1 else ''

        # /compteur7 pdf — envoyer le PDF manuellement
        if sub == 'pdf':
            await send_compteur7_pdf()
            await event.respond("📄 PDF Compteur7 envoyé.")
            return

        # /compteur7 seuil N — changer le seuil
        if sub == 'seuil' and len(parts) > 2:
            try:
                val = int(parts[2])
                if val < 2:
                    await event.respond("❌ Seuil minimum : 2")
                    return
                old = COMPTEUR7_THRESHOLD
                COMPTEUR7_THRESHOLD = val
                await event.respond(
                    f"✅ **Seuil Compteur7:** {old} → {val}\n"
                    f"Détection à partir de **{val}** présences consécutives"
                )
            except ValueError:
                await event.respond("❌ Usage: `/compteur7 seuil 5`")
            return

        # /compteur7 reset — effacer l'historique persistant
        if sub == 'reset':
            compteur7_completed.clear()
            for suit in ALL_SUITS:
                compteur7_current[suit] = {'count': 0, 'start_game': None, 'start_time': None}
            save_compteur7_data()
            await event.respond("🔄 **Compteur7 reset** — historique effacé du disque")
            return

        # Affichage statut
        suit_names = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
        lines = [f"📊 **COMPTEUR7** — Séries consécutives (seuil ≥ {COMPTEUR7_THRESHOLD})\n"]

        lines.append("**En cours :**")
        any_active = False
        for suit in ALL_SUITS:
            cur   = compteur7_current[suit]
            count = cur['count']
            name  = SUIT_DISPLAY.get(suit, suit)
            if count > 0:
                any_active = True
                bar = "█" * min(count, 12) + ("…" if count > 12 else "")
                lines.append(f"  {name}: [{bar}] {count}x (depuis #{cur['start_game']})")
            else:
                lines.append(f"  {name}: —")

        if not any_active:
            lines.append("  _(aucune série en cours)_")

        total = len(compteur7_completed)
        lines.append(f"\n**Séries terminées enregistrées :** {total}")
        if total > 0:
            for s in compteur7_completed[-5:]:
                sn       = suit_names.get(s['suit'], s['suit'])
                end_date = s['end_time'].strftime('%d/%m %Hh%M')
                lines.append(
                    f"  • {end_date} — {s['suit']} **{s['count']}x** "
                    f"(#{s['start_game']}→#{s['end_game']})"
                )
            lines.append("_(5 dernières — /compteur7 pdf pour le tableau complet)_")

        lines.append(f"\nUsage: `/compteur7` `pdf` `seuil N` `reset`")
        await event.respond("\n".join(lines), parse_mode='markdown')

    except Exception as e:
        logger.error(f"Erreur cmd_compteur7: {e}")
        await event.respond(f"❌ Erreur: {e}")


async def cmd_comparaison(event):
    """Analyse intelligente et naturelle des apparitions de costumes par heure de la journée."""
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        suit_names = {'♠': 'Pique', '♥': 'Cœur', '♦': 'Carreau', '♣': 'Trèfle'}
        suit_emoji = {'♠': '♠️', '♥': '❤️', '♦': '♦️', '♣': '♣️'}

        # ── Heures ayant assez de données ────────────────────────────────────
        active_hours = sorted([h for h in range(24) if hourly_game_count[h] >= 3])
        total_games  = sum(hourly_game_count[h] for h in active_hours)

        if total_games < 10:
            await event.respond(
                "📊 **COMPARAISON HORAIRE**\n\n"
                "⏳ Pas encore assez de données (minimum 10 parties nécessaires).\n"
                "L'analyse sera disponible après quelques heures de collecte.\n\n"
                f"Parties enregistrées actuellement : **{total_games}**"
            )
            return

        # ── Calcul des taux par heure ─────────────────────────────────────────
        taux: Dict[str, Dict[int, float]] = {}
        for suit in ALL_SUITS:
            taux[suit] = {}
            for h in active_hours:
                cnt   = hourly_suit_data[h].get(suit, 0)
                tot_h = hourly_game_count[h]
                taux[suit][h] = round(cnt / tot_h * 100, 1) if tot_h > 0 else 0.0

        # Taux global
        overall: Dict[str, float] = {}
        for suit in ALL_SUITS:
            ts = sum(hourly_suit_data[h].get(suit, 0) for h in active_hours)
            overall[suit] = round(ts / total_games * 100, 1) if total_games > 0 else 0.0

        suit_order = sorted(ALL_SUITS, key=lambda s: overall[s], reverse=True)

        # ── Fonction utilitaire : grouper des heures consécutives en plages ──
        def group_hours_into_ranges(hours_list: List[int]) -> List[List[int]]:
            """Regroupe [12,13,14,17,18] en [[12,13,14],[17,18]]"""
            if not hours_list:
                return []
            sorted_h = sorted(hours_list)
            groups, grp = [], [sorted_h[0]]
            for h in sorted_h[1:]:
                if h == grp[-1] + 1:
                    grp.append(h)
                else:
                    groups.append(grp)
                    grp = [h]
            groups.append(grp)
            return groups

        def format_range(grp: List[int]) -> str:
            if len(grp) == 1:
                return f"{grp[0]:02d}h"
            return f"{grp[0]:02d}h à {grp[-1] + 1:02d}h"

        # ── Données Compteur7 (séries de présences) par heure ─────────────────
        c7_by_hour: Dict[int, List[Dict]] = {h: [] for h in range(24)}
        for s in compteur7_completed:
            h = s['end_time'].hour
            c7_by_hour[h].append(s)

        # ── Données Compteur4 (séries d'absences) par heure ──────────────────
        c4_by_hour: Dict[int, List[Dict]] = {h: [] for h in range(24)}
        for s in compteur4_events:
            h = s['end_time'].hour
            c4_by_hour[h].append(s)

        # ── En-tête du rapport ────────────────────────────────────────────────
        current_h = datetime.now().hour
        now_str   = datetime.now().strftime('%d/%m/%Y à %Hh%M')
        lines = [
            f"📊 **ANALYSE COMPARAISON INTELLIGENTE**",
            f"📅 {now_str} — {total_games} parties analysées",
            f"⏰ {len(active_hours)} tranches horaires actives\n",
        ]

        # ── Analyse par costume ───────────────────────────────────────────────
        for suit in suit_order:
            name      = suit_names[suit]
            emoji     = suit_emoji[suit]
            avg       = overall[suit]
            ht        = taux[suit]
            threshold_strong = avg + 8
            threshold_weak   = avg - 8

            # Heures fortes et faibles
            strong_hours = sorted([h for h in active_hours if ht.get(h, 0) >= threshold_strong],
                                   key=lambda h: ht[h], reverse=True)
            weak_hours   = sorted([h for h in active_hours if ht.get(h, 0) <= threshold_weak],
                                   key=lambda h: ht[h])

            strong_sorted_asc = sorted(strong_hours)
            weak_sorted_asc   = sorted(weak_hours)

            strong_groups = group_hours_into_ranges(strong_sorted_asc)
            weak_groups   = group_hours_into_ranges(weak_sorted_asc)

            # Meilleure plage forte (la plus longue)
            best_strong_grp = max(strong_groups, key=len) if strong_groups else None
            best_weak_grp   = max(weak_groups,   key=len) if weak_groups   else None

            lines.append(f"━━━━━━━━━━━━━━━")
            lines.append(f"{emoji} **{name}** — moyenne globale : **{avg:.0f}%**")

            # Message principal en langage naturel
            if best_strong_grp and best_weak_grp:
                strong_pct_avg = round(sum(ht.get(h, 0) for h in best_strong_grp) / len(best_strong_grp))
                weak_pct_avg   = round(sum(ht.get(h, 0) for h in best_weak_grp) / len(best_weak_grp))
                lines.append(
                    f"  📌 Aujourd'hui **{name}** apparaît bien de **{format_range(best_strong_grp)}** "
                    f"({strong_pct_avg}%), mais arrivé sur "
                    f"**{format_range(best_weak_grp)}** il a baissé — devient **rare** ({weak_pct_avg}%)"
                )
            elif best_strong_grp:
                strong_pct_avg = round(sum(ht.get(h, 0) for h in best_strong_grp) / len(best_strong_grp))
                lines.append(
                    f"  📌 **{name}** est fort de **{format_range(best_strong_grp)}** "
                    f"({strong_pct_avg}%) — pas de zone faible notable"
                )
            elif best_weak_grp:
                weak_pct_avg = round(sum(ht.get(h, 0) for h in best_weak_grp) / len(best_weak_grp))
                lines.append(
                    f"  📌 **{name}** devient rare de **{format_range(best_weak_grp)}** "
                    f"({weak_pct_avg}%) — pas de zone forte notable"
                )
            else:
                lines.append(f"  📌 **{name}** apparaît de manière régulière toute la journée ({avg:.0f}%)")

            # Toutes les plages fortes
            if strong_groups:
                strong_details = []
                for grp in sorted(strong_groups, key=len, reverse=True)[:3]:
                    avg_t = round(sum(ht.get(h, 0) for h in grp) / len(grp))
                    strong_details.append(f"{format_range(grp)} ({avg_t}%)")
                lines.append(f"  ✅ **Zones favorables :** {' | '.join(strong_details)}")

            # Toutes les plages faibles
            if weak_groups:
                weak_details = []
                for grp in sorted(weak_groups, key=len, reverse=True)[:3]:
                    avg_t = round(sum(ht.get(h, 0) for h in grp) / len(grp))
                    weak_details.append(f"{format_range(grp)} ({avg_t}%)")
                lines.append(f"  ❄️ **Zones rares :** {' | '.join(weak_details)}")

            # Données C7 (séries de présences longues) pour ce costume
            c7_suit = [s for s in compteur7_completed if s['suit'] == suit]
            if c7_suit:
                by_h: Dict[int, int] = {}
                for s7 in c7_suit:
                    h7 = s7['end_time'].hour
                    by_h[h7] = by_h.get(h7, 0) + 1
                top_c7_h = max(by_h, key=by_h.get)
                lines.append(
                    f"  🔥 Séries longues souvent terminées vers **{top_c7_h:02d}h** "
                    f"({by_h[top_c7_h]}x enregistré)"
                )

            # Données C4 (séries d'absences longues) pour ce costume
            c4_suit = [s for s in compteur4_events if s['suit'] == suit]
            if c4_suit:
                by_h4: Dict[int, int] = {}
                for s4 in c4_suit:
                    h4 = s4['end_time'].hour
                    by_h4[h4] = by_h4.get(h4, 0) + 1
                top_c4_h = max(by_h4, key=by_h4.get)
                lines.append(
                    f"  ⚠️ Longues absences souvent terminées vers **{top_c4_h:02d}h** "
                    f"({by_h4[top_c4_h]}x enregistré)"
                )

        # ── Situation en temps réel ───────────────────────────────────────────
        lines.append(f"\n━━━━━━━━━━━━━━━")
        lines.append(f"🕐 **Situation MAINTENANT ({current_h:02d}h)**")
        if current_h in active_hours:
            ranked = sorted(ALL_SUITS, key=lambda s: taux[s].get(current_h, 0), reverse=True)
            best   = ranked[0]
            worst  = ranked[-1]
            best_p = taux[best].get(current_h, 0)
            worst_p= taux[worst].get(current_h, 0)
            trend_lines = []
            for s in ranked:
                p    = taux[s].get(current_h, 0)
                diff = round(p - overall[s], 1)
                sign = "▲" if diff > 2 else ("▼" if diff < -2 else "▶")
                trend_lines.append(
                    f"  {suit_emoji[s]} {suit_names[s]}: **{p:.0f}%** {sign} ({'+' if diff >= 0 else ''}{diff}% vs moy.)"
                )
            lines.extend(trend_lines)
            lines.append(
                f"\n  🏆 Le plus favorable maintenant : {suit_emoji[best]} **{suit_names[best]}** ({best_p:.0f}%)"
            )
            lines.append(
                f"  ⛔ Le plus rare maintenant : {suit_emoji[worst]} **{suit_names[worst]}** ({worst_p:.0f}%)"
            )

            # Prévision heure suivante
            next_h = (current_h + 1) % 24
            if next_h in active_hours:
                best_next = max(ALL_SUITS, key=lambda s: taux[s].get(next_h, 0))
                lines.append(
                    f"\n  📈 Dans 1h ({next_h:02d}h) : favorable pour "
                    f"{suit_emoji[best_next]} **{suit_names[best_next]}** "
                    f"({taux[best_next].get(next_h, 0):.0f}%)"
                )
        else:
            lines.append(f"  ℹ️ Pas encore assez de données pour {current_h:02d}h")

        # ── Conseils globaux du jour ──────────────────────────────────────────
        lines.append(f"\n━━━━━━━━━━━━━━━")
        lines.append(f"💡 **CONSEILS STRATÉGIQUES DU JOUR**")
        for suit in suit_order:
            name  = suit_names[suit]
            emoji = suit_emoji[suit]
            ht    = taux[suit]
            if not active_hours:
                continue
            sorted_desc = sorted(active_hours, key=lambda h: ht.get(h, 0), reverse=True)
            top_h   = sorted_desc[0]
            top_t   = ht.get(top_h, 0)
            low_h   = sorted_desc[-1]
            low_t   = ht.get(low_h, 0)
            delta   = round(top_t - low_t)

            # Phrase conseil
            if delta >= 20:
                conseil = f"Forte variation — privilégier **{top_h:02d}h** ({top_t:.0f}%), éviter **{low_h:02d}h** ({low_t:.0f}%)"
            elif delta >= 10:
                conseil = f"Variation modérée — meilleur créneau **{top_h:02d}h** ({top_t:.0f}%)"
            else:
                conseil = f"Comportement stable — peut être joué à tout moment"

            lines.append(f"  {emoji} **{name}** : {conseil}")

        await event.respond("\n".join(lines), parse_mode='markdown')

    except Exception as e:
        logger.error(f"Erreur cmd_comparaison: {e}")
        import traceback; logger.error(traceback.format_exc())
        await event.respond(f"❌ Erreur: {e}")


async def cmd_plus(event):
    global PREDICTION_SEND_AHEAD
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        parts = event.message.message.split()
        if len(parts) == 1:
            await event.respond(f"➕ **PRÉDICTION SEND AHEAD**\n\nValeur actuelle: **{PREDICTION_SEND_AHEAD}**\n\n**Usage:** `/plus [1-5]`")
            return
        val = int(parts[1])
        if not 1 <= val <= 5:
            await event.respond("❌ La valeur doit être entre 1 et 5")
            return
        old = PREDICTION_SEND_AHEAD
        PREDICTION_SEND_AHEAD = val
        await event.respond(f"✅ **Send ahead modifié: {old} → {val}**")
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_gap(event):
    global MIN_GAP_BETWEEN_PREDICTIONS
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        parts = event.message.message.split()
        if len(parts) == 1:
            await event.respond(f"📏 **ÉCART MINIMUM**\n\nValeur actuelle: **{MIN_GAP_BETWEEN_PREDICTIONS}**\n\n**Usage:** `/gap [2-10]`")
            return
        val = int(parts[1])
        if not 2 <= val <= 10:
            await event.respond("❌ L'écart doit être entre 2 et 10")
            return
        old = MIN_GAP_BETWEEN_PREDICTIONS
        MIN_GAP_BETWEEN_PREDICTIONS = val
        await event.respond(f"✅ **Écart modifié: {old} → {val}**")
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_compteur1(event):
    global compteur1_trackers
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        lines = ["🎯 **COMPTEUR1** (Présences consécutives du joueur)", ""]
        for suit in ALL_SUITS:
            tracker = compteur1_trackers.get(suit)
            if tracker:
                if tracker.counter > 0:
                    lines.append(f"{tracker.get_display_name()}: **{tracker.counter}** consécutifs (depuis #{tracker.start_game})")
                else:
                    lines.append(f"{tracker.get_display_name()}: 0")
        await event.respond("\n".join(lines))
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_stats(event):
    global compteur1_history, compteur1_trackers
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        lines = ["📊 **STATISTIQUES COMPTEUR1**", "Séries de présences consécutives (joueur, min 3)", ""]

        for tracker in compteur1_trackers.values():
            if tracker.counter >= MIN_CONSECUTIVE_FOR_STATS:
                already_saved = any(
                    e['suit'] == tracker.suit and e['count'] == tracker.counter and e['end_game'] == tracker.last_game
                    for e in compteur1_history[:5]
                )
                if not already_saved:
                    save_compteur1_series(tracker.suit, tracker.counter, tracker.start_game, tracker.last_game)

        stats_by_suit = {'♥': [], '♠': [], '♦': [], '♣': []}
        for entry in compteur1_history:
            suit = entry['suit']
            if suit in stats_by_suit:
                stats_by_suit[suit].append(entry)

        has_data = False
        for suit in ['♥', '♠', '♦', '♣']:
            entries = stats_by_suit[suit]
            if not entries:
                continue
            has_data = True
            record = get_compteur1_record(suit)
            lines.append(f"**{SUIT_DISPLAY.get(suit, suit)}** (Record: {record})")
            for i, entry in enumerate(entries[:5], 1):
                count = entry['count']
                start = entry['start_game']
                end = entry['end_game']
                star = "⭐" if count == record else ""
                lines.append(f"  {i}. {count} fois (#{start}-#{end}) {star}")
            lines.append("")

        if not has_data:
            lines.append("❌ Aucune série ≥3 enregistrée")

        await event.respond("\n".join(lines))
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_compteur2(event):
    global compteur2_seuil_B, compteur2_active, compteur2_trackers
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        parts = event.message.message.split()
        if len(parts) == 1:
            status_str = "✅ ON" if compteur2_active else "❌ OFF"
            lines = [f"📊 **COMPTEUR2** (Absences joueur)", f"Statut: {status_str} | Seuil B défaut: {compteur2_seuil_B}", "", "Progression (B dynamique par costume):"]
            for suit in ALL_SUITS:
                tracker = compteur2_trackers.get(suit)
                if tracker:
                    b = compteur2_seuil_B_per_suit.get(suit, compteur2_seuil_B)
                    progress = min(tracker.counter, b)
                    bar = f"[{'█' * progress}{'░' * max(0, b - progress)}]"
                    status = "🔮 PRÊT" if tracker.counter >= b else f"{tracker.counter}/{b}"
                    b_marker = f" (B={b})" if b != compteur2_seuil_B else ""
                    lines.append(f"{tracker.get_display_name()}: {bar} {status}{b_marker}")
            lines.append(f"\n**Usage:** `/compteur2 [B/on/off/reset]`")
            await event.respond("\n".join(lines))
            return

        arg = parts[1].lower()
        if arg == 'off':
            compteur2_active = False
            await event.respond("❌ **Compteur2 OFF**")
        elif arg == 'on':
            compteur2_active = True
            await event.respond("✅ **Compteur2 ON**")
        elif arg == 'reset':
            for tracker in compteur2_trackers.values():
                tracker.counter = 0
            await event.respond("🔄 **Compteur2 reset**")
        else:
            b_val = int(arg)
            if not 2 <= b_val <= 10:
                await event.respond("❌ B entre 2 et 10")
                return
            old_b = compteur2_seuil_B
            compteur2_seuil_B = b_val
            # Mettre à jour les B par costume :
            # - Les costumes au niveau admin précédent → passent au nouveau niveau admin
            # - Les costumes élevés par des pertes → ajustés par le même delta
            delta = b_val - old_b
            for s in ALL_SUITS:
                cur = compteur2_seuil_B_per_suit.get(s, old_b)
                excess = cur - old_b  # Nombre de pertes accumulées pour ce costume
                compteur2_seuil_B_per_suit[s] = b_val + max(0, excess)
            lines = [f"✅ **Seuil B admin = {b_val}** (ancien: {old_b})\n", "B par costume mis à jour:"]
            for s in ALL_SUITS:
                sd = SUIT_DISPLAY.get(s, s)
                new_val = compteur2_seuil_B_per_suit[s]
                losses = new_val - b_val
                suffix = f" (+{losses} perte(s))" if losses > 0 else " ✅"
                lines.append(f"  {sd}: **{new_val}**{suffix}")
            await event.respond("\n".join(lines), parse_mode='markdown')
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_canal_distribution(event):
    global DISTRIBUTION_CHANNEL_ID
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        parts = event.message.message.split()
        if len(parts) == 1:
            status = f"✅ Actif: `{DISTRIBUTION_CHANNEL_ID}`" if DISTRIBUTION_CHANNEL_ID else "❌ Inactif"
            await event.respond(f"🎯 **CANAL SECONDAIRE COMPTEUR2**\n\n{status}\n\n**Usage:** `/canaldistribution [ID]` ou `/canaldistribution off`")
            return
        arg = parts[1].lower()
        if arg == 'off':
            old = DISTRIBUTION_CHANNEL_ID
            DISTRIBUTION_CHANNEL_ID = None
            await event.respond(f"❌ **Canal secondaire désactivé** (était: `{old}`)")
            return
        new_id = int(arg)
        channel_entity = await resolve_channel(new_id)
        if not channel_entity:
            await event.respond(f"❌ Canal `{new_id}` inaccessible")
            return
        old = DISTRIBUTION_CHANNEL_ID
        DISTRIBUTION_CHANNEL_ID = new_id
        await event.respond(f"✅ **Canal secondaire: {old} → {new_id}**")
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_canal_compteur2(event):
    global COMPTEUR2_CHANNEL_ID
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        parts = event.message.message.split()
        if len(parts) == 1:
            status = f"✅ Actif: `{COMPTEUR2_CHANNEL_ID}`" if COMPTEUR2_CHANNEL_ID else "❌ Inactif"
            await event.respond(f"📊 **CANAL COMPTEUR2**\n\n{status}\n\n**Usage:** `/canalcompteur2 [ID]` ou `/canalcompteur2 off`")
            return
        arg = parts[1].lower()
        if arg == 'off':
            old = COMPTEUR2_CHANNEL_ID
            COMPTEUR2_CHANNEL_ID = None
            await event.respond(f"❌ **Canal Compteur2 désactivé** (était: `{old}`)")
            return
        new_id = int(arg)
        channel_entity = await resolve_channel(new_id)
        if not channel_entity:
            await event.respond(f"❌ Canal `{new_id}` inaccessible")
            return
        old = COMPTEUR2_CHANNEL_ID
        COMPTEUR2_CHANNEL_ID = new_id
        await event.respond(f"✅ **Canal Compteur2: {old} → {new_id}**")
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_canaux(event):
    global DISTRIBUTION_CHANNEL_ID, COMPTEUR2_CHANNEL_ID, PREDICTION_CHANNEL_ID
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    lines = [
        "📡 **CONFIGURATION DES CANAUX**",
        "",
        f"📤 **Principal:** `{PREDICTION_CHANNEL_ID}`",
        f"🎯 **Secondaire Compteur2:** {f'`{DISTRIBUTION_CHANNEL_ID}`' if DISTRIBUTION_CHANNEL_ID else '❌'}",
        f"📊 **Canal Compteur2:** {f'`{COMPTEUR2_CHANNEL_ID}`' if COMPTEUR2_CHANNEL_ID else '❌'}",
    ]
    await event.respond("\n".join(lines))


async def cmd_queue(event):
    global prediction_queue, current_game_number, MIN_GAP_BETWEEN_PREDICTIONS, PREDICTION_SEND_AHEAD
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    try:
        lines = [
            "📋 **FILE D'ATTENTE**",
            f"Écart: {MIN_GAP_BETWEEN_PREDICTIONS} | Envoi: N-{PREDICTION_SEND_AHEAD}",
            "",
        ]
        if not prediction_queue:
            lines.append("❌ Vide")
        else:
            lines.append(f"**{len(prediction_queue)} prédictions:**\n")
            for i, pred in enumerate(prediction_queue, 1):
                suit = SUIT_DISPLAY.get(pred['suit'], pred['suit'])
                pred_type = pred['type']
                pred_num = pred['game_number']
                type_str = "📊C2" if pred_type == 'compteur2' else "🤖"
                send_threshold = pred_num - PREDICTION_SEND_AHEAD
                if current_game_number >= send_threshold:
                    status = "🟢 PRÊT" if not pending_predictions else "⏳ Attente"
                else:
                    wait_num = send_threshold - current_game_number
                    status = f"⏳ Dans {wait_num}"
                lines.append(f"{i}. #{pred_num} {suit} | {type_str} | {status}")
        lines.append(f"\n🎮 Jeu API actuel: #{current_game_number}")
        await event.respond("\n".join(lines))
    except Exception as e:
        await event.respond(f"❌ Erreur: {str(e)}")


async def cmd_pending(event):
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    from config import PREDICTION_TIMEOUT_MINUTES
    now = datetime.now()
    try:
        if not pending_predictions:
            await event.respond("✅ **Aucune prédiction en cours**")
            return
        lines = [f"🔍 **PRÉDICTIONS EN COURS** ({len(pending_predictions)})", ""]
        for game_number, pred in pending_predictions.items():
            suit = pred.get('suit', '?')
            suit_display = SUIT_DISPLAY.get(suit, suit)
            rattrapage = pred.get('rattrapage', 0)
            current_check = pred.get('current_check', game_number)
            verified_games = pred.get('verified_games', [])
            sent_time = pred.get('sent_time')
            pred_type = pred.get('type', 'standard')
            type_str = "📊C2" if pred_type == 'compteur2' else "🤖"
            age_str = ""
            if sent_time:
                age_sec = int((now - sent_time).total_seconds())
                age_str = f"{age_sec // 60}m{age_sec % 60:02d}s"
            verif_parts = []
            for i in range(3):
                check_num = game_number + i
                if current_check == check_num:
                    verif_parts.append(f"🔵#{check_num}")
                elif check_num in verified_games:
                    verif_parts.append(f"❌#{check_num}")
                else:
                    verif_parts.append(f"⬜#{check_num}")
            lines.append(f"**#{game_number}** {suit_display} | {type_str} | R{rattrapage}")
            lines.append(f"  🔍 {' | '.join(verif_parts)}")
            lines.append(f"  ⏱️ Il y a {age_str}")
            lines.append("")
        lines.append(f"🎮 Jeu API actuel: #{current_game_number}")
        await event.respond("\n".join(lines))
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")


async def cmd_history(event):
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    lines = ["📜 **HISTORIQUE PRÉDICTIONS**", ""]
    recent = prediction_history[:10]
    if not recent:
        lines.append("❌ Aucune prédiction")
    else:
        for i, pred in enumerate(recent, 1):
            suit = SUIT_DISPLAY.get(pred['suit'], pred['suit'])
            status = pred['status']
            pred_time = pred['predicted_at'].strftime('%H:%M:%S')
            rule = "📊C2" if pred.get('type') == 'compteur2' else "🤖"
            emoji = {'en_cours': '🎰', 'gagne_r0': '🏆', 'gagne_r1': '🏆', 'gagne_r2': '🏆', 'perdu': '💔'}.get(status, '❓')
            lines.append(f"{i}. {emoji} #{pred['predicted_game']} {suit} | {rule} | {status}")
            lines.append(f"   🕐 {pred_time}")
    await event.respond("\n".join(lines))


async def cmd_status(event):
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return

    compteur2_str = "✅ ON" if compteur2_active else "❌ OFF"
    now = datetime.now()
    allowed = "✅" if is_prediction_time_allowed() else "❌"

    lines = [
        "📊 **STATUT COMPLET**",
        "",
        f"🎮 Jeu API actuel: #{current_game_number}",
        f"📊 Compteur2: {compteur2_str} (B={compteur2_seuil_B})",
        f"📏 Écart: {MIN_GAP_BETWEEN_PREDICTIONS}",
        f"⏰ Prédictions autorisées: {allowed} ({now.strftime('%H:%M')})",
        f"📋 File: {len(prediction_queue)} | Actives: {len(pending_predictions)}",
        f"📊 Écarts C4: {len(compteur4_events)}",
        "",
        f"**Plages horaires:**\n{format_hours_config()}",
        "",
        f"**Compteur4 (absences):**",
    ]

    for suit in ALL_SUITS:
        count = compteur4_trackers.get(suit, 0)
        name = SUIT_DISPLAY.get(suit, suit)
        lines.append(f"  {name}: {count}/{COMPTEUR4_THRESHOLD}")

    if pending_predictions:
        lines.append("")
        lines.append("🔍 **En vérification:**")
        for game_number, pred in pending_predictions.items():
            suit_display = SUIT_DISPLAY.get(pred['suit'], pred['suit'])
            rattrapage = pred.get('rattrapage', 0)
            sent_time = pred.get('sent_time')
            age_str = ""
            if sent_time:
                age_sec = int((now - sent_time).total_seconds())
                age_str = f" ({age_sec // 60}m{age_sec % 60:02d}s)"
            lines.append(f"  • #{game_number} {suit_display} — R{rattrapage}{age_str}")

    await event.respond("\n".join(lines))


async def cmd_help(event):
    if event.is_group or event.is_channel:
        return

    help_text = (
        f"📖 **BACCARAT AI - COMMANDES**\n\n"
        f"**⚙️ Configuration:**\n"
        f"`/plus [1-5]` — Envoi en avance (actuel: {PREDICTION_SEND_AHEAD})\n"
        f"`/gap [2-10]` — Écart min entre prédictions ({MIN_GAP_BETWEEN_PREDICTIONS})\n\n"
        f"**⏰ Restriction horaire:**\n"
        f"`/heures` — Voir/gérer les plages\n"
        f"`/heures add HH-HH` — Ajouter une plage\n"
        f"`/heures del HH-HH` — Supprimer une plage\n"
        f"`/heures clear` — 24h/24 sans restriction\n\n"
        f"**📊 Compteurs:**\n"
        f"`/compteur1` — Présences consécutives (joueur)\n"
        f"`/compteur2 [B/on/off/reset]` — Absences consécutives\n"
        f"`/stats` — Historique séries Compteur1\n"
        f"`/compteur4` — Écarts 10+ (avec PDF)\n"
        f"`/compteur4 pdf` — Envoyer le PDF maintenant\n"
        f"`/compteur4 seuil N` — Changer le seuil (actuel: {COMPTEUR4_THRESHOLD})\n\n"
        f"**📡 Canaux:**\n"
        f"`/canaldistribution [ID/off]`\n"
        f"`/canalcompteur2 [ID/off]`\n"
        f"`/canaux` — Voir config\n\n"
        f"**📋 Gestion:**\n"
        f"`/pending` — Prédictions en vérification\n"
        f"`/queue` — File d'attente\n"
        f"`/status` — Statut complet\n"
        f"`/history` — Historique\n"
        f"`/reset` — Reset manuel\n"
        f"`/debloquer` — 🔓 Déblocage d'urgence (prédictions/costumes bloqués)\n\n"
        f"🤖 Baccarat AI | Source: 1xBet API"
    )
    await event.respond(help_text)


async def cmd_reset(event):
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    await event.respond("🔄 Reset en cours...")
    await perform_full_reset("Reset manuel")
    await event.respond("✅ Reset effectué!")


async def cmd_debloquer(event):
    """Déblocage d'urgence : vide pending_predictions, suit_block_until et prediction_queue."""
    global pending_predictions, suit_block_until, prediction_queue
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return

    lines = []

    nb_pending = len(pending_predictions)
    if nb_pending:
        for gn, pred in list(pending_predictions.items()):
            stop_animation(gn)
        pending_predictions.clear()
        lines.append(f"🧹 {nb_pending} prédiction(s) bloquée(s) supprimée(s)")

    nb_blocked = len([s for s in suit_block_until if datetime.now() < suit_block_until[s]])
    if nb_blocked:
        suit_block_until.clear()
        lines.append(f"🔓 {nb_blocked} costume(s) débloqué(s)")

    nb_queue = len(prediction_queue)
    if nb_queue:
        prediction_queue.clear()
        lines.append(f"🗑️ {nb_queue} prédiction(s) en file supprimée(s)")

    if lines:
        rapport = "✅ **DÉBLOCAGE D'URGENCE**\n\n" + "\n".join(lines) + "\n\n🟢 Bot actif et prêt."
    else:
        rapport = "✅ Rien à débloquer — bot déjà actif."

    logger.warning(f"🔓 Déblocage manuel: {'; '.join(lines) if lines else 'rien'}")
    await event.respond(rapport, parse_mode='markdown')


# ============================================================================
# COMMANDES : POURQUOI / PERDUS / BILAN
# ============================================================================

async def cmd_pourquoi(event):
    """Explique pourquoi une prédiction a été faite."""
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    parts = event.message.message.strip().split()
    target = None
    if len(parts) >= 2:
        try:
            target = int(parts[1])
        except ValueError:
            pass
    if target is None:
        await event.respond("❌ Usage: `/pourquoi [numéro_jeu]`\nEx: `/pourquoi 794`")
        return
    found = None
    for pred in prediction_history:
        if pred['predicted_game'] == target:
            found = pred
            break
    if not found:
        await event.respond(f"❌ Aucune prédiction trouvée pour le jeu #{target}")
        return
    suit_display = SUIT_DISPLAY.get(found['suit'], found['suit'])
    reason = found.get('reason', '')
    status = found.get('status', 'inconnu')
    pred_at = found['predicted_at'].strftime('%d/%m/%Y %H:%M')
    status_map = {
        'gagne_r0': '✅0️⃣ GAGNÉ DIRECT', 'gagne_r1': '✅1️⃣ GAGNÉ R1',
        'gagne_r2': '✅2️⃣ GAGNÉ R2', 'gagne_r3': '✅3️⃣ GAGNÉ R3',
        'perdu': '❌ PERDU', 'en_cours': '⏳ EN COURS'
    }
    status_str = status_map.get(status, status)
    b_val = compteur2_seuil_B_per_suit.get(found['suit'], compteur2_seuil_B)
    msg = (
        f"🔎 **POURQUOI #{target} ?**\n\n"
        f"🎯 Couleur prédite: {suit_display}\n"
        f"📅 Prédit le: {pred_at}\n"
        f"📊 Statut: {status_str}\n"
        f"📏 Seuil B actuel ({found['suit']}): **{b_val}**\n\n"
        f"📖 **Raison:**\n_{reason if reason else 'Raison non enregistrée (ancienne prédiction).'}_ "
    )
    await event.respond(msg, parse_mode='markdown')


async def cmd_perdus(event):
    """Envoie le PDF des pertes avec analyse horaire à l'admin."""
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    if not perdu_events:
        await event.respond("📊 Aucune perte enregistrée pour le moment.")
        return
    await event.respond("📉 Génération du rapport de pertes...")
    await send_perdu_pdf()


async def cmd_bilan(event):
    """Gère le bilan automatique : /bilan [intervalle_minutes] ou /bilan now."""
    global bilan_interval_minutes
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return
    parts = event.message.message.strip().split()
    if len(parts) == 1:
        now = datetime.now()
        minutes_left = 60 - now.minute
        status = f"✅ Actif — prochain envoi dans **{minutes_left} min** (à {(now.hour + 1) % 24:02d}:00)" \
                 if bilan_interval_minutes > 0 else "🔕 Désactivé"
        await event.respond(
            f"📊 **BILAN AUTOMATIQUE**\n\n"
            f"Statut: **{status}**\n"
            f"Fréquence: toutes les heures pile (HH:00)\n\n"
            f"**Usage:**\n"
            f"`/bilan now` — Envoyer le bilan immédiatement dans le canal\n"
            f"`/bilan 0` — Désactiver l'envoi automatique\n"
            f"`/bilan on` — Réactiver l'envoi automatique\n\n"
            + get_bilan_text(),
            parse_mode='markdown'
        )
        return
    arg = parts[1].strip()
    if arg == 'now':
        txt = get_bilan_text()
        entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if entity:
            await client.send_message(entity, txt, parse_mode='markdown')
        await event.respond("✅ Bilan envoyé dans le canal.")
        return
    if arg == 'on':
        bilan_interval_minutes = 60
        now = datetime.now()
        minutes_left = 60 - now.minute
        await event.respond(f"✅ Bilan automatique réactivé — prochain envoi dans **{minutes_left} min**.")
        return
    if arg == '0':
        bilan_interval_minutes = 0
        await event.respond("🔕 Bilan automatique désactivé.")
        return
    await event.respond(
        "❌ Commande inconnue.\n"
        "`/bilan now` — Envoyer maintenant\n"
        "`/bilan on` — Activer\n"
        "`/bilan 0` — Désactiver"
    )


# ============================================================================
# MODE D'EMPLOI AUTOMATIQUE
# ============================================================================

async def mode_emploi_loop():
    """Envoie le mode d'emploi dans le canal à chaque intervalle défini, à l'heure pile."""
    global mode_emploi_interval_hours, mode_emploi_text
    while True:
        try:
            interval = mode_emploi_interval_hours
            if interval <= 0:
                await asyncio.sleep(60)
                continue

            now = datetime.now()
            # Trouver la prochaine heure pile alignée sur l'intervalle
            # Ex : intervalle=4h → 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
            current_hour = now.hour
            hours_since_last = current_hour % interval
            hours_until_next = interval - hours_since_last
            seconds_until_next = hours_until_next * 3600 - (now.minute * 60 + now.second)
            if seconds_until_next <= 0:
                seconds_until_next += interval * 3600

            await asyncio.sleep(seconds_until_next)

            if mode_emploi_interval_hours <= 0:
                continue

            entity = await resolve_channel(PREDICTION_CHANNEL_ID)
            if entity:
                await client.send_message(entity, mode_emploi_text, parse_mode='markdown')
                logger.info(f"📋 Mode d'emploi envoyé ({datetime.now().strftime('%H:%M')})")
        except Exception as e:
            logger.error(f"❌ Erreur mode_emploi_loop: {e}")
            await asyncio.sleep(60)


async def cmd_emploi(event):
    """Commande /emploi — gère le mode d'emploi automatique."""
    global mode_emploi_text, mode_emploi_interval_hours
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return

    raw = event.message.message.strip()
    parts = raw.split(None, 1)  # max 2 parties : commande + reste

    # ── /emploi seul : affiche le statut et le texte actuel ─────────────────
    if len(parts) == 1:
        interval = mode_emploi_interval_hours
        now = datetime.now()
        if interval > 0:
            hours_since_last = now.hour % interval
            hours_until_next = interval - hours_since_last
            next_heure = (now.hour + hours_until_next) % 24
            status = f"✅ Actif — toutes les {interval}h (prochain: {next_heure:02d}:00)"
        else:
            status = "🔕 Désactivé"

        await event.respond(
            f"📋 **MODE D'EMPLOI AUTOMATIQUE**\n\n"
            f"Statut: {status}\n\n"
            f"**Commandes:**\n"
            f"`/emploi now` — Envoyer maintenant dans le canal\n"
            f"`/emploi interval 4` — Changer l'intervalle (ex: 4h)\n"
            f"`/emploi interval 0` — Désactiver\n"
            f"`/emploi set [texte]` — Remplacer le texte\n"
            f"`/emploi reset` — Restaurer le texte par défaut\n\n"
            f"**Texte actuel (aperçu) :**\n"
            f"_{mode_emploi_text[:300]}{'…' if len(mode_emploi_text) > 300 else ''}_",
            parse_mode='markdown'
        )
        return

    sub = parts[1].strip()

    # ── /emploi now ──────────────────────────────────────────────────────────
    if sub.lower() == 'now':
        entity = await resolve_channel(PREDICTION_CHANNEL_ID)
        if entity:
            await client.send_message(entity, mode_emploi_text, parse_mode='markdown')
        await event.respond("✅ Mode d'emploi envoyé dans le canal.")
        return

    # ── /emploi reset ─────────────────────────────────────────────────────────
    if sub.lower() == 'reset':
        mode_emploi_text = MODE_EMPLOI_DEFAULT
        await event.respond("🔄 Mode d'emploi réinitialisé au texte par défaut.")
        return

    # ── /emploi interval [N] ──────────────────────────────────────────────────
    if sub.lower().startswith('interval'):
        sub_parts = sub.split()
        if len(sub_parts) < 2:
            await event.respond("❌ Usage: `/emploi interval [1-24]` ou `/emploi interval 0` pour désactiver")
            return
        try:
            val = int(sub_parts[1])
            if val < 0 or val > 24:
                await event.respond("❌ Intervalle entre 0 et 24 heures.")
                return
            mode_emploi_interval_hours = val
            if val == 0:
                await event.respond("🔕 Mode d'emploi automatique désactivé.")
            else:
                now = datetime.now()
                hours_until_next = val - (now.hour % val) if val > 0 else 0
                next_h = (now.hour + hours_until_next) % 24
                await event.respond(
                    f"✅ Mode d'emploi toutes les **{val}h**.\n"
                    f"Prochain envoi: **{next_h:02d}:00**"
                )
        except ValueError:
            await event.respond("❌ Valeur invalide. Exemple: `/emploi interval 4`")
        return

    # ── /emploi set [texte] ───────────────────────────────────────────────────
    if sub.lower().startswith('set '):
        new_text = sub[4:].strip()
        if len(new_text) < 10:
            await event.respond("❌ Texte trop court (minimum 10 caractères).")
            return
        mode_emploi_text = new_text
        await event.respond(
            f"✅ Nouveau texte enregistré ({len(new_text)} caractères).\n"
            f"Utilisez `/emploi now` pour l'envoyer immédiatement."
        )
        return

    await event.respond(
        "❌ Commande inconnue.\n"
        "`/emploi` — Voir statut\n"
        "`/emploi now` — Envoyer maintenant\n"
        "`/emploi interval 4` — Toutes les 4h\n"
        "`/emploi set [texte]` — Changer le texte\n"
        "`/emploi reset` — Texte par défaut"
    )


# ============================================================================
# COMMANDE /b — GESTION DU B DYNAMIQUE PAR COSTUME
# ============================================================================

# Historique des changements de B par costume : [(suit, old_b, new_b, datetime, raison)]
b_change_history: List[tuple] = []

# Costumes dont le reset a été planifié (jeu auto-analyse) : {suit: scheduled_datetime}
b_reset_scheduled: Dict[str, datetime] = {}


async def _execute_b_reset(suit: str, new_b: int, raison: str):
    """Réinitialise le B d'un costume et notifie l'admin."""
    global compteur2_seuil_B_per_suit
    old_b = compteur2_seuil_B_per_suit.get(suit, compteur2_seuil_B)
    compteur2_seuil_B_per_suit[suit] = new_b
    b_change_history.append((suit, old_b, new_b, datetime.now(), raison))
    b_reset_scheduled.pop(suit, None)
    suit_display = SUIT_DISPLAY.get(suit, suit)
    logger.info(f"🔄 B({suit}) réinitialisé: {old_b} → {new_b} ({raison})")
    if ADMIN_ID:
        try:
            admin = await client.get_entity(ADMIN_ID)
            await client.send_message(
                admin,
                f"✅ **B réinitialisé — {suit_display}**\n\n"
                f"Ancien B : **{old_b}**\n"
                f"Nouveau B : **{new_b}** (= B admin)\n"
                f"Raison : _{raison}_",
                parse_mode='markdown'
            )
        except Exception as e:
            logger.error(f"❌ Notif reset B: {e}")


async def _scheduled_b_reset(suit: str, delay_seconds: int, raison: str):
    """Reset différé du B d'un costume après délai."""
    await asyncio.sleep(delay_seconds)
    if suit in b_reset_scheduled:  # Vérifie que le reset n'a pas été annulé
        await _execute_b_reset(suit, compteur2_seuil_B, raison)


def _analyse_b_suit(suit: str, window: int = 100) -> dict:
    """
    Analyse si le B initial serait suffisant pour le costume donné.
    Retourne: {'would_trigger': bool, 'max_absence': int, 'initial_b': int, 'current_b': int}
    """
    initial_b = compteur2_seuil_B
    current_b  = compteur2_seuil_B_per_suit.get(suit, initial_b)

    # Récupérer les derniers jeux connus
    recent_games = sorted(game_history.keys())[-window:]
    if not recent_games:
        return {'would_trigger': False, 'max_absence': 0,
                'initial_b': initial_b, 'current_b': current_b}

    # Calculer la plus longue séquence d'absence consécutive
    max_streak = 0
    streak = 0
    example_start = 0
    example_end   = 0
    for gn in recent_games:
        result = game_history.get(gn, {})
        player_cards = result.get('player_cards', [])
        suits_in_game = set()
        for c in player_cards:
            s = c.get('suit') or c.get('color') or ''
            if s in ALL_SUITS:
                suits_in_game.add(s)
        if suit not in suits_in_game:
            if streak == 0:
                example_start = gn
            streak += 1
            example_end = gn
            if streak > max_streak:
                max_streak = streak
        else:
            streak = 0

    would_trigger = max_streak >= initial_b
    return {
        'would_trigger': would_trigger,
        'max_absence': max_streak,
        'initial_b': initial_b,
        'current_b': current_b,
        'example_start': example_start,
        'example_end': example_end,
    }


async def cmd_b(event):
    """Commande /b — affiche et gère le B dynamique par costume."""
    global compteur2_seuil_B_per_suit
    if event.is_group or event.is_channel:
        return
    if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
        await event.respond("🔒 Admin uniquement")
        return

    parts = event.message.message.strip().split()

    # ── /b seul : tableau des B actuels + historique ────────────────────────
    if len(parts) == 1:
        lines = [f"📏 **SEUILS B PAR COSTUME**", f"B admin (base) : **{compteur2_seuil_B}**\n"]
        for suit in ALL_SUITS:
            sd  = SUIT_DISPLAY.get(suit, suit)
            cur = compteur2_seuil_B_per_suit.get(suit, compteur2_seuil_B)
            ini = compteur2_seuil_B
            delta = cur - ini
            marker = f" (+{delta} après {delta} perte(s))" if delta > 0 else " ✅ égal au B admin"
            sched  = f"\n   ⏰ Reset prévu: {b_reset_scheduled[suit].strftime('%H:%M')}" \
                     if suit in b_reset_scheduled else ""
            lines.append(f"{sd} : B admin={ini} → actuel = **{cur}**{marker}{sched}")

        if b_change_history:
            lines.append("\n📜 **Historique des changements:**")
            for suit, old, new, dt, raison in b_change_history[-6:]:
                sd = SUIT_DISPLAY.get(suit, suit)
                lines.append(f"• {dt.strftime('%d/%m %H:%M')} {sd}: {old}→{new} ({raison})")

        lines.append(
            "\n**Commandes:**\n"
            "`/b reset ♠` — Remettre ♠ au B admin\n"
            "`/b reset all` — Remettre tous les costumes au B admin\n"
            "`/b analyse` — Analyser et proposer un reset automatique\n"
            "`/b cancel ♠` — Annuler un reset planifié"
        )
        await event.respond("\n".join(lines), parse_mode='markdown')
        return

    arg = parts[1].lower()

    # ── /b reset all ─────────────────────────────────────────────────────────
    if arg == 'reset' and len(parts) >= 3 and parts[2].lower() == 'all':
        for s in ALL_SUITS:
            if compteur2_seuil_B_per_suit.get(s, compteur2_seuil_B) != compteur2_seuil_B:
                await _execute_b_reset(s, compteur2_seuil_B, "Reset manuel (all)")
        await event.respond(f"✅ Tous les B remis à **{compteur2_seuil_B}** (valeur initiale).")
        return

    # ── /b reset ♠ ───────────────────────────────────────────────────────────
    if arg == 'reset' and len(parts) >= 3:
        suit_input = parts[2]
        # Cherche le costume correspondant
        target = None
        for s in ALL_SUITS:
            if suit_input in (s, SUIT_DISPLAY.get(s, ''), s.strip()):
                target = s
                break
        if not target:
            await event.respond(f"❌ Costume inconnu: `{suit_input}`\nUtilisez ♠ ♥ ♦ ♣")
            return
        old_b = compteur2_seuil_B_per_suit.get(target, compteur2_seuil_B)
        if old_b == compteur2_seuil_B:
            await event.respond(f"ℹ️ {SUIT_DISPLAY.get(target, target)} est déjà à B={compteur2_seuil_B}.")
            return
        await _execute_b_reset(target, compteur2_seuil_B, "Reset manuel admin")
        return

    # ── /b cancel ♠ ──────────────────────────────────────────────────────────
    if arg == 'cancel' and len(parts) >= 3:
        suit_input = parts[2]
        target = None
        for s in ALL_SUITS:
            if suit_input in (s, SUIT_DISPLAY.get(s, ''), s.strip()):
                target = s
                break
        if not target or target not in b_reset_scheduled:
            await event.respond(f"❌ Aucun reset planifié pour `{suit_input}`.")
            return
        b_reset_scheduled.pop(target)
        await event.respond(f"🚫 Reset planifié pour {SUIT_DISPLAY.get(target, target)} annulé.")
        return

    # ── /b analyse ───────────────────────────────────────────────────────────
    if arg == 'analyse':
        await event.respond("🔬 Analyse en cours…")
        lines = [f"🔬 **ANALYSE DES SEUILS B**\n_B admin actuel = {compteur2_seuil_B}_\n"]
        proposed = []
        for suit in ALL_SUITS:
            sd  = SUIT_DISPLAY.get(suit, suit)
            res = _analyse_b_suit(suit)
            cur = res['current_b']
            ini = res['initial_b']  # = compteur2_seuil_B (admin)
            if cur <= ini:
                lines.append(f"{sd}: B={cur} (= B admin) — aucun reset nécessaire")
                continue
            if res['would_trigger']:
                lines.append(
                    f"{sd}: B actuel={cur} | B admin={ini}\n"
                    f"   ✅ Le B admin **aurait déclenché** une prédiction "
                    f"(absence max = {res['max_absence']} sur 100 jeux, "
                    f"jeux #{res.get('example_start','')}→#{res.get('example_end','')})\n"
                    f"   → **Reset vers B admin recommandé dans 1h**"
                )
                proposed.append(suit)
            else:
                lines.append(
                    f"{sd}: B actuel={cur} | B admin={ini}\n"
                    f"   ⚠️ Le B admin n'atteint pas encore le seuil "
                    f"(absence max = {res['max_absence']}/{ini}) — reset non recommandé"
                )

        if proposed:
            lines.append(f"\n🕐 Reset automatique vers B admin ({compteur2_seuil_B}) dans **1 heure** pour: "
                         + " ".join(SUIT_DISPLAY.get(s, s) for s in proposed))
            for suit in proposed:
                if suit not in b_reset_scheduled:
                    b_reset_scheduled[suit] = datetime.now() + timedelta(hours=1)
                    snap = _analyse_b_suit(suit)
                    asyncio.create_task(
                        _scheduled_b_reset(suit, 3600,
                                           f"Auto-analyse: B admin suffisant "
                                           f"(absence max={snap['max_absence']})")
                    )
        else:
            lines.append("\n✅ Aucun reset recommandé pour le moment.")

        await event.respond("\n".join(lines), parse_mode='markdown')
        return

    await event.respond(
        "❌ Commande inconnue.\n"
        "`/b` — Voir tous les B\n"
        "`/b reset ♠` — Reset immédiat\n"
        "`/b reset all` — Reset tout\n"
        "`/b analyse` — Analyse automatique\n"
        "`/b cancel ♠` — Annuler un reset planifié"
    )


# ============================================================================
# SETUP ET DÉMARRAGE
# ============================================================================

def setup_handlers():
    client.add_event_handler(cmd_heures, events.NewMessage(pattern=r'^/heures'))
    client.add_event_handler(cmd_compteur4, events.NewMessage(pattern=r'^/compteur4'))
    client.add_event_handler(cmd_plus, events.NewMessage(pattern=r'^/plus'))
    client.add_event_handler(cmd_gap, events.NewMessage(pattern=r'^/gap'))
    client.add_event_handler(cmd_canal_distribution, events.NewMessage(pattern=r'^/canaldistribution'))
    client.add_event_handler(cmd_canal_compteur2, events.NewMessage(pattern=r'^/canalcompteur2'))
    client.add_event_handler(cmd_canaux, events.NewMessage(pattern=r'^/canaux$'))
    client.add_event_handler(cmd_compteur1, events.NewMessage(pattern=r'^/compteur1$'))
    client.add_event_handler(cmd_stats, events.NewMessage(pattern=r'^/stats$'))
    client.add_event_handler(cmd_queue, events.NewMessage(pattern=r'^/queue$'))
    client.add_event_handler(cmd_pending, events.NewMessage(pattern=r'^/pending$'))
    client.add_event_handler(cmd_compteur2, events.NewMessage(pattern=r'^/compteur2'))
    client.add_event_handler(cmd_status, events.NewMessage(pattern=r'^/status$'))
    client.add_event_handler(cmd_history, events.NewMessage(pattern=r'^/history$'))
    client.add_event_handler(cmd_reset, events.NewMessage(pattern=r'^/reset$'))
    client.add_event_handler(cmd_debloquer, events.NewMessage(pattern=r'^/debloquer$'))
    client.add_event_handler(cmd_help, events.NewMessage(pattern=r'^/help$'))
    client.add_event_handler(cmd_pourquoi, events.NewMessage(pattern=r'^/pourquoi'))
    client.add_event_handler(cmd_perdus, events.NewMessage(pattern=r'^/perdus$'))
    client.add_event_handler(cmd_bilan, events.NewMessage(pattern=r'^/bilan'))
    client.add_event_handler(cmd_b, events.NewMessage(pattern=r'^/b($|\s)'))
    client.add_event_handler(cmd_emploi, events.NewMessage(pattern=r'^/emploi'))
    client.add_event_handler(cmd_compteur5, events.NewMessage(pattern=r'^/compteur5'))
    client.add_event_handler(cmd_compteur6, events.NewMessage(pattern=r'^/compteur6'))
    client.add_event_handler(cmd_compteur7, events.NewMessage(pattern=r'^/compteur7'))
    client.add_event_handler(cmd_comparaison, events.NewMessage(pattern=r'^/comparaison'))


async def start_bot():
    global client, prediction_channel_ok

    session = os.getenv('TELEGRAM_SESSION', '')
    client = TelegramClient(StringSession(session), API_ID, API_HASH)

    try:
        await client.start(bot_token=BOT_TOKEN)
        setup_handlers()
        initialize_trackers()

        # Charger données persistantes Compteur4, Compteur7 et données horaires
        load_compteur4_data()
        load_compteur7_data()
        load_hourly_data()

        if PREDICTION_CHANNEL_ID:
            try:
                pred_entity = await resolve_channel(PREDICTION_CHANNEL_ID)
                if pred_entity:
                    prediction_channel_ok = True
                    logger.info(f"✅ Canal prédiction OK")
            except Exception as e:
                logger.error(f"❌ Erreur canal prédiction: {e}")

        logger.info("🤖 Bot démarré")
        return True

    except Exception as e:
        logger.error(f"❌ Erreur démarrage: {e}")
        return False


async def main():
    # ── Démarrage du serveur web (une seule fois) ──
    app = web.Application()
    app.router.add_get('/health', lambda r: web.Response(text="OK"))
    app.router.add_get('/', lambda r: web.Response(text="BACCARAT AI 🤖 Running | Source: 1xBet API"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server port {PORT}")

    # ── Boucle de reconnexion automatique ──
    background_started = False
    retry_delay = 5
    while True:
        try:
            if not await start_bot():
                logger.error("❌ start_bot() a échoué — nouvelle tentative dans 30s")
                await asyncio.sleep(30)
                continue

            # Tâches de fond : démarrées UNE SEULE FOIS après le premier start_bot réussi
            if not background_started:
                asyncio.create_task(auto_reset_system())
                asyncio.create_task(_api_polling_guardian())   # guardian redémarre si crash
                asyncio.create_task(auto_watchdog_task())      # watchdog déblocage automatique
                asyncio.create_task(bilan_loop())
                asyncio.create_task(mode_emploi_loop())
                background_started = True

            logger.info(f"📏 Écart: {MIN_GAP_BETWEEN_PREDICTIONS}")
            logger.info(f"📡 Source: 1xBet API (polling toutes les 4s)")
            logger.info(f"📊 Compteur4 seuil: {COMPTEUR4_THRESHOLD}")
            logger.info(f"⏰ Restriction horaire: {'ACTIVE' if PREDICTION_HOURS else 'INACTIVE (24h/24)'}")

            retry_delay = 5   # reset après connexion réussie
            await client.run_until_disconnected()
            logger.warning("⚠️ Telegram déconnecté — reconnexion dans 5s...")

        except KeyboardInterrupt:
            logger.info("Arrêt manuel demandé.")
            break
        except Exception as e:
            logger.error(f"❌ Erreur boucle principale: {e} — reconnexion dans {retry_delay}s")

        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 120)   # backoff exponentiel max 2 min

        try:
            if client and client.is_connected():
                await client.disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêté")
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)
