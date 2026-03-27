"""
Générateur de TELEGRAM_SESSION pour bot Telethon
==================================================
Lance ce script UNE SEULE FOIS depuis ton terminal :

    python generate_session.py

Il va se connecter avec ton BOT_TOKEN et afficher la chaîne
TELEGRAM_SESSION à copier sur Render.com.

Aucun numéro de téléphone ni code SMS requis — c'est une session BOT.
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# ── Identifiants (mêmes que dans config.py) ───────────────────────────────────
API_ID    = 29177661
API_HASH  = "a8639172fa8d35dbfd8ea46286d349ab"
BOT_TOKEN = "8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU"
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "="*60)
    print("  GÉNÉRATEUR DE SESSION BOT — BACCARAT AI")
    print("="*60)
    print("\nConnexion en cours avec le BOT_TOKEN...")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)
    session_str = client.session.save()
    await client.disconnect()

    print("\n" + "="*60)
    print("  ✅  SESSION GÉNÉRÉE AVEC SUCCÈS")
    print("="*60)
    print("\nCopie la chaîne ci-dessous et colle-la sur Render.com")
    print("dans : Environment → TELEGRAM_SESSION\n")
    print("─"*60)
    print(session_str)
    print("─"*60)
    print("\n⚠️  Ne partage jamais cette chaîne avec quelqu'un d'autre.")
    print()

if __name__ == "__main__":
    asyncio.run(main())
