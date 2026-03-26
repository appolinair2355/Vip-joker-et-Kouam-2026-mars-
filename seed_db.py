"""
Script de seeding — Injecte les données historiques C7 et prediction_history
dans PostgreSQL. À exécuter une seule fois.
"""
import asyncio
import json
import os
from datetime import datetime

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SUIT_MAP = {"Carreau": "♦", "Coeur": "♥", "Pique": "♠", "Trefle": "♣"}

# ============================================================================
# DONNÉES COMPTEUR 7 — 99 séries (extraites du PDF)
# ============================================================================
C7_RAW = [
    ("25/03/2026", "12h30", "Carreau", 745,  750,  6),
    ("25/03/2026", "12h36", "Coeur",   751,  756,  6),
    ("25/03/2026", "12h44", "Coeur",   760,  764,  5),
    ("25/03/2026", "21h00", "Pique",  1256, 1260,  5),
    ("25/03/2026", "21h57", "Carreau",1312, 1317,  6),
    ("25/03/2026", "22h32", "Carreau",1348, 1352,  5),
    ("25/03/2026", "22h39", "Carreau",1355, 1359,  5),
    ("25/03/2026", "22h53", "Coeur",  1365, 1373,  9),
    ("26/03/2026", "00h41", "Coeur",    35,   41,  7),
    ("26/03/2026", "00h45", "Pique",    41,   45,  5),
    ("26/03/2026", "00h51", "Coeur",    47,   51,  5),
    ("26/03/2026", "00h55", "Pique",    51,   55,  5),
    ("26/03/2026", "01h08", "Coeur",    63,   68,  6),
    ("26/03/2026", "01h34", "Trefle",   89,   94,  6),
    ("26/03/2026", "02h01", "Trefle",  116,  121,  6),
    ("26/03/2026", "02h11", "Trefle",  127,  131,  5),
    ("26/03/2026", "02h24", "Carreau", 139,  144,  6),
    ("26/03/2026", "02h31", "Carreau", 147,  151,  5),
    ("26/03/2026", "02h45", "Carreau", 161,  165,  5),
    ("26/03/2026", "03h04", "Carreau", 179,  184,  6),
    ("26/03/2026", "03h05", "Trefle",  181,  185,  5),
    ("26/03/2026", "03h13", "Coeur",   189,  193,  5),
    ("26/03/2026", "03h17", "Carreau", 190,  197,  8),
    ("26/03/2026", "03h38", "Trefle",  213,  218,  6),
    ("26/03/2026", "03h54", "Carreau", 230,  234,  5),
    ("26/03/2026", "04h07", "Pique",   243,  247,  5),
    ("26/03/2026", "04h13", "Carreau", 247,  253,  7),
    ("26/03/2026", "04h31", "Trefle",  267,  271,  5),
    ("26/03/2026", "04h46", "Carreau", 281,  286,  6),
    ("26/03/2026", "05h16", "Trefle",  312,  316,  5),
    ("26/03/2026", "05h50", "Trefle",  346,  350,  5),
    ("26/03/2026", "05h59", "Carreau", 354,  359,  6),
    ("26/03/2026", "06h06", "Carreau", 362,  366,  5),
    ("26/03/2026", "06h27", "Coeur",   381,  387,  7),
    ("26/03/2026", "06h32", "Carreau", 388,  392,  5),
    ("26/03/2026", "06h40", "Carreau", 396,  400,  5),
    ("26/03/2026", "06h46", "Carreau", 402,  406,  5),
    ("26/03/2026", "06h56", "Trefle",  412,  416,  5),
    ("26/03/2026", "07h01", "Carreau", 417,  421,  5),
    ("26/03/2026", "07h14", "Pique",   429,  434,  6),
    ("26/03/2026", "07h27", "Pique",   442,  447,  6),
    ("26/03/2026", "07h36", "Pique",   451,  456,  6),
    ("26/03/2026", "07h41", "Coeur",   456,  461,  6),
    ("26/03/2026", "07h45", "Trefle",  461,  465,  5),
    ("26/03/2026", "07h56", "Trefle",  470,  476,  7),
    ("26/03/2026", "08h00", "Pique",   476,  480,  5),
    ("26/03/2026", "08h17", "Trefle",  493,  497,  5),
    ("26/03/2026", "08h41", "Trefle",  517,  521,  5),
    ("26/03/2026", "08h45", "Carreau", 520,  525,  6),
    ("26/03/2026", "08h57", "Carreau", 532,  537,  6),
    ("26/03/2026", "09h00", "Coeur",   536,  540,  5),
    ("26/03/2026", "09h07", "Pique",   542,  547,  6),
    ("26/03/2026", "09h32", "Coeur",   568,  572,  5),
    ("26/03/2026", "09h50", "Trefle",  586,  590,  5),
    ("26/03/2026", "09h59", "Pique",   593,  599,  7),
    ("26/03/2026", "10h04", "Coeur",   599,  604,  6),
    ("26/03/2026", "10h12", "Pique",   608,  612,  5),
    ("26/03/2026", "10h18", "Pique",   614,  618,  5),
    ("26/03/2026", "10h28", "Trefle",  623,  628,  6),
    ("26/03/2026", "10h38", "Pique",   632,  638,  7),
    ("26/03/2026", "10h44", "Carreau", 640,  644,  5),
    ("26/03/2026", "11h01", "Trefle",  654,  661,  8),
    ("26/03/2026", "11h08", "Trefle",  663,  668,  6),
    ("26/03/2026", "11h14", "Coeur",   669,  674,  6),
    ("26/03/2026", "11h22", "Carreau", 678,  682,  5),
    ("26/03/2026", "11h42", "Trefle",  691,  702, 12),
    ("26/03/2026", "11h43", "Carreau", 699,  703,  5),
    ("26/03/2026", "11h59", "Pique",   714,  719,  6),
    ("26/03/2026", "12h16", "Pique",   732,  736,  5),
    ("26/03/2026", "12h18", "Coeur",   734,  738,  5),
    ("26/03/2026", "12h38", "Pique",   754,  758,  5),
    ("26/03/2026", "12h47", "Carreau", 762,  767,  6),
    ("26/03/2026", "13h27", "Trefle",  803,  807,  5),
    ("26/03/2026", "13h32", "Pique",   808,  812,  5),
    ("26/03/2026", "13h51", "Coeur",   827,  831,  5),
    ("26/03/2026", "14h11", "Trefle",  847,  851,  5),
    ("26/03/2026", "14h18", "Carreau", 851,  858,  8),
    ("26/03/2026", "14h20", "Pique",   855,  860,  6),
    ("26/03/2026", "14h32", "Carreau", 864,  872,  9),
    ("26/03/2026", "14h39", "Pique",   873,  879,  7),
    ("26/03/2026", "15h06", "Carreau", 902,  906,  5),
    ("26/03/2026", "15h31", "Coeur",   926,  931,  6),
    ("26/03/2026", "15h34", "Trefle",  930,  934,  5),
    ("26/03/2026", "15h39", "Carreau", 935,  939,  5),
    ("26/03/2026", "16h33", "Pique",   987,  993,  7),
    ("26/03/2026", "16h38", "Coeur",   994,  998,  5),
    ("26/03/2026", "16h52", "Coeur",  1008, 1012,  5),
    ("26/03/2026", "17h24", "Pique",  1039, 1044,  6),
    ("26/03/2026", "17h27", "Trefle", 1043, 1047,  5),
    ("26/03/2026", "17h56", "Trefle", 1072, 1076,  5),
    ("26/03/2026", "18h20", "Carreau",1096, 1100,  5),
    ("26/03/2026", "18h27", "Trefle", 1103, 1107,  5),
    ("26/03/2026", "19h08", "Pique",  1144, 1148,  5),
    ("26/03/2026", "19h13", "Carreau",1148, 1153,  6),
    ("26/03/2026", "19h24", "Trefle", 1157, 1164,  8),
    ("26/03/2026", "19h40", "Coeur",  1172, 1180,  9),
    ("26/03/2026", "19h51", "Pique",  1187, 1191,  5),
    ("26/03/2026", "19h57", "Trefle", 1193, 1197,  5),
    ("26/03/2026", "20h11", "Carreau",1207, 1211,  5),
]

# ============================================================================
# DONNÉES PREDICTION HISTORY — 50 prédictions (extraites du PDF rapport)
# ============================================================================
PRED_RAW = [
    ("26/03/2026","02:06:41",128,"Carreau","C2","Du jeu #123 au jeu #127, Carreau etait absent 5 fois de suite (seuil B=5).","win",1,129),
    ("26/03/2026","02:26:14",148,"Coeur","C2","-","win",3,151),
    ("26/03/2026","02:30:38",152,"Pique","C2","Du jeu #147 au jeu #151, Pique etait absent 5 fois de suite (seuil B=5).","win",3,155),
    ("26/03/2026","03:09:08",191,"Trefle","C2","Du jeu #186 au jeu #190, Trefle etait absent 5 fois de suite (seuil B=5).","loss",3,194),
    ("26/03/2026","03:15:43",197,"Coeur","C2","-","win",0,197),
    ("26/03/2026","03:31:34",213,"Pique","C2","Du jeu #208 au jeu #212, Pique etait absent 5 fois de suite (seuil B=5).","win",0,213),
    ("26/03/2026","03:38:37",220,"Pique","C2","Du jeu #215 au jeu #219, Pique etait absent 5 fois de suite (seuil B=5).","win",0,220),
    ("26/03/2026","04:30:35",272,"Coeur","C2","Du jeu #267 au jeu #271, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,272),
    ("26/03/2026","04:56:07",298,"Coeur","C2","Du jeu #293 au jeu #297, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,298),
    ("26/03/2026","05:15:15",317,"Coeur","C2","Du jeu #312 au jeu #316, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,317),
    ("26/03/2026","05:54:40",356,"Pique","C2","Du jeu #351 au jeu #355, Pique etait absent 5 fois de suite (seuil B=5).","win",0,356),
    ("26/03/2026","06:05:37",367,"Coeur","C2","Du jeu #362 au jeu #366, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,367),
    ("26/03/2026","06:38:33",400,"Pique","C2","Du jeu #395 au jeu #399, Pique etait absent 5 fois de suite (seuil B=5).","win",3,403),
    ("26/03/2026","06:46:41",408,"Coeur","C2","Du jeu #403 au jeu #407, Coeur etait absent 5 fois de suite (seuil B=5).","win",1,409),
    ("26/03/2026","06:58:33",420,"Coeur","C2","Du jeu #415 au jeu #419, Coeur etait absent 5 fois de suite (seuil B=5).","win",2,422),
    ("26/03/2026","07:29:16",451,"Coeur","C2","Du jeu #446 au jeu #450, Coeur etait absent 5 fois de suite (seuil B=5).","win",1,452),
    ("26/03/2026","08:11:36",493,"Trefle","C2","Du jeu #487 au jeu #492, Trefle etait absent 6 fois de suite (seuil B=6).","win",0,493),
    ("26/03/2026","08:17:38",499,"Pique","C2","Du jeu #494 au jeu #498, Pique etait absent 5 fois de suite (seuil B=5).","win",0,499),
    ("26/03/2026","08:39:35",521,"Coeur","C2","Du jeu #516 au jeu #520, Coeur etait absent 5 fois de suite (seuil B=5).","win",1,522),
    ("26/03/2026","08:56:11",538,"Pique","C2","Du jeu #533 au jeu #537, Pique etait absent 5 fois de suite (seuil B=5).","win",2,540),
    ("26/03/2026","09:19:40",561,"Pique","C2","Du jeu #556 au jeu #560, Pique etait absent 5 fois de suite (seuil B=5).","win",2,563),
    ("26/03/2026","09:40:40",582,"Coeur","C2","Du jeu #577 au jeu #581, Coeur etait absent 5 fois de suite (seuil B=5).","win",1,583),
    ("26/03/2026","09:57:36",599,"Carreau","C2","Du jeu #594 au jeu #598, Carreau etait absent 5 fois de suite (seuil B=5).","win",1,600),
    ("26/03/2026","10:03:35",605,"Pique","C2","Du jeu #600 au jeu #604, Pique etait absent 5 fois de suite (seuil B=5).","win",3,608),
    ("26/03/2026","10:19:10",621,"Coeur","C2","Du jeu #616 au jeu #620, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,621),
    ("26/03/2026","10:26:18",628,"Pique","C2","Du jeu #623 au jeu #627, Pique etait absent 5 fois de suite (seuil B=5).","win",1,629),
    ("26/03/2026","11:08:08",670,"Carreau","C2","Du jeu #665 au jeu #669, Carreau etait absent 5 fois de suite (seuil B=5).","win",1,671),
    ("26/03/2026","11:26:11",688,"Trefle","C2","Du jeu #682 au jeu #687, Trefle etait absent 6 fois de suite (seuil B=6).","win",1,689),
    ("26/03/2026","11:34:38",696,"Coeur","C2","Du jeu #691 au jeu #695, Coeur etait absent 5 fois de suite (seuil B=5).","win",1,697),
    ("26/03/2026","11:54:39",716,"Carreau","C2","Du jeu #711 au jeu #715, Carreau etait absent 5 fois de suite (seuil B=5).","win",2,718),
    ("26/03/2026","12:05:38",727,"Pique","C2","Du jeu #722 au jeu #726, Pique etait absent 5 fois de suite (seuil B=5).","win",0,727),
    ("26/03/2026","12:17:38",739,"Carreau","C2","Du jeu #734 au jeu #738, Carreau etait absent 5 fois de suite (seuil B=5).","win",0,739),
    ("26/03/2026","12:44:10",766,"Trefle","C2","Du jeu #760 au jeu #765, Trefle etait absent 6 fois de suite (seuil B=6).","win",0,766),
    ("26/03/2026","12:54:38",776,"Coeur","C2","Du jeu #771 au jeu #775, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,776),
    ("26/03/2026","13:36:12",818,"Pique","C2","Du jeu #813 au jeu #817, Pique etait absent 5 fois de suite (seuil B=5).","win",0,818),
    ("26/03/2026","14:10:35",852,"Pique","C2","Du jeu #847 au jeu #851, Pique etait absent 5 fois de suite (seuil B=5).","win",3,855),
    ("26/03/2026","14:29:12",871,"Pique","C2","Du jeu #866 au jeu #870, Pique etait absent 5 fois de suite (seuil B=5).","win",2,873),
    ("26/03/2026","14:48:41",890,"Pique","C2","Du jeu #885 au jeu #889, Pique etait absent 5 fois de suite (seuil B=5).","win",1,891),
    ("26/03/2026","15:43:15",945,"Carreau","C2","Du jeu #940 au jeu #944, Carreau etait absent 5 fois de suite (seuil B=5).","win",0,945),
    ("26/03/2026","16:38:14",1000,"Carreau","C2","Du jeu #995 au jeu #999, Carreau etait absent 5 fois de suite (seuil B=5).","win",2,1002),
    ("26/03/2026","17:01:32",1023,"Carreau","C2","Du jeu #1018 au jeu #1022, Carreau etait absent 5 fois de suite (seuil B=5).","win",0,1023),
    ("26/03/2026","17:11:41",1033,"Pique","C2","Du jeu #1028 au jeu #1032, Pique etait absent 5 fois de suite (seuil B=5).","win",1,1034),
    ("26/03/2026","17:38:10",1060,"Carreau","C2","Du jeu #1055 au jeu #1059, Carreau etait absent 5 fois de suite (seuil B=5).","loss",3,1063),
    ("26/03/2026","17:55:12",1077,"Pique","C2","Du jeu #1072 au jeu #1076, Pique etait absent 5 fois de suite (seuil B=5).","win",1,1078),
    ("26/03/2026","18:09:38",1091,"Coeur","C2","Du jeu #1086 au jeu #1090, Coeur etait absent 5 fois de suite (seuil B=5).","win",3,1094),
    ("26/03/2026","19:12:41",1154,"Pique","C2","Du jeu #1149 au jeu #1153, Pique etait absent 5 fois de suite (seuil B=5).","win",2,1156),
    ("26/03/2026","19:19:36",1161,"Coeur","C2","Du jeu #1156 au jeu #1160, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,1161),
    ("26/03/2026","19:35:35",1177,"Pique","C2","Du jeu #1172 au jeu #1176, Pique etait absent 5 fois de suite (seuil B=5).","loss",3,1180),
    ("26/03/2026","19:41:17",1183,"Carreau","C2","-","win",0,1183),
    ("26/03/2026","19:53:35",1195,"Coeur","C2","Du jeu #1190 au jeu #1194, Coeur etait absent 5 fois de suite (seuil B=5).","win",0,1195),
]


def parse_dt(date_str, time_str):
    """Convertit date DD/MM/YYYY + heure HH:MM ou HHhMM en datetime."""
    time_str = time_str.replace("h", ":")
    if time_str.endswith(":"):
        time_str += "00"
    return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")


async def seed():
    is_local = (
        'helium'    in DATABASE_URL or
        'localhost' in DATABASE_URL or
        '127.0.0.1' in DATABASE_URL
    )
    is_render_internal = (
        'dpg-' in DATABASE_URL and
        'postgres.render.com' not in DATABASE_URL
    )
    ssl_mode = False if (is_local or is_render_internal) else 'require'

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3, ssl=ssl_mode)

    async with pool.acquire() as conn:
        # ------------------------------------------------------------------
        # 1. COMPTEUR 7 — stocké en kv_store
        # ------------------------------------------------------------------
        print("⏳ Insertion Compteur7...")
        c7_list = []
        for (date_s, heure_s, costume, debut, fin, nb) in C7_RAW:
            dt = parse_dt(date_s, heure_s)
            suit = SUIT_MAP[costume]
            c7_list.append({
                "suit":       suit,
                "start_time": dt.isoformat(),
                "end_time":   dt.isoformat(),
                "count":      nb,
                "start_game": debut,
                "end_game":   fin,
            })

        await conn.execute("""
            INSERT INTO kv_store (key, data, updated_at)
            VALUES ('compteur7', $1::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET data=$1::jsonb, updated_at=NOW()
        """, json.dumps(c7_list))
        print(f"  ✅ {len(c7_list)} séries C7 insérées dans kv_store")

        # ------------------------------------------------------------------
        # 2. PREDICTION HISTORY — stocké dans la table prediction_history
        # ------------------------------------------------------------------
        print("⏳ Insertion prediction_history...")
        inserted = 0
        skipped = 0
        # Normaliser les statuts: 'win' → 'gagne_rN', 'loss' → 'perdu'
        await conn.execute("""
            UPDATE prediction_history
            SET status = CONCAT('gagne_r', rattrapage_level)
            WHERE status = 'win'
        """)
        await conn.execute("""
            UPDATE prediction_history
            SET status = 'perdu'
            WHERE status = 'loss'
        """)

        for (date_s, time_s, game, costume, cpt, reason, status, rattrap, verified_game) in PRED_RAW:
            predicted_at = datetime.strptime(f"{date_s} {time_s}", "%d/%m/%Y %H:%M:%S")
            suit = SUIT_MAP[costume]
            pred_type = "standard"
            # Convertir le statut vers le format interne
            if status == 'win':
                norm_status = f'gagne_r{rattrap}'
            elif status == 'loss':
                norm_status = 'perdu'
            else:
                norm_status = status
            result = await conn.execute("""
                INSERT INTO prediction_history
                    (predicted_game, suit, prediction_type, reason, status,
                     rattrapage_level, predicted_at, verified_at, verified_by_game)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (predicted_game, suit) DO NOTHING
            """,
                game, suit, pred_type, reason if reason != "-" else "", norm_status,
                rattrap, predicted_at, predicted_at, verified_game
            )
            if result == "INSERT 0 1":
                inserted += 1
            else:
                skipped += 1
        print(f"  ✅ {inserted} prédictions insérées | {skipped} déjà présentes")

    await pool.close()
    print("🎉 Seeding terminé.")


if __name__ == "__main__":
    asyncio.run(seed())
