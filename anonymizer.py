import os
import sys
import json
import glob
import re
import random
import string
import pandas as pd

POPULAR_USERNAMES = [
    "Zizou98", "ElTaktiko", "KingKylian", "CoachVahid", "FootixPro",
    "SuperSub", "CapitaineRamos", "TitiHenry", "CR7Legend", "PronoMaster",
    "Maestro10", "SoleilDeMarseille", "MagicGrizou", "MisterProno", "ChapeauBas",
    "CornerDirect", "TikiTaka", "PoloGourcuff", "LesYeuxDansLesBleus", "DimitriPayet",
    "Jorjinho", "VaraneBlock", "TontonEvra", "NicoAnelka", "BielsaLoco",
    "Ronnie50", "Fenomeno", "R10Magic", "MisterAncelotti", "LaDecima",
    "PanenkaKing", "BarcaBoy", "RealFanatik", "RedDevil", "Gunner4Life",
    "BavarianMachine", "Brazuca", "JogaBonito", "GoldenBoy", "BallonDor",
    "CleanSheet", "PetitPont", "LucarneOposee", "CartonRouge", "HorsJeu",
    "TirAuBut", "TacleGlisse", "SurfaceDeReparation", "GrandPont", "PasseDecisive",
    "DoubleTete", "RepriseDeVolee", "CoupDuChapeau", "FiletTremblant", "MainDeDieu",
    "StadeDeFrance", "ParcDesPrinces", "Velodrome", "GeoffroyGuichard", "Bollaert",
    "LaBeaujoire", "RoazhonPark", "GroupamaStadium", "PierreMauroy", "AllianzRiviera",
    "MatmutAtlantique", "KopNord", "Ultras93", "SupporterNum1", "FouDeFoot",
    "MonsieurLArbitre", "VarInutile", "LigneDeTouche", "DirectComment", "JourDeMatch",
    "TroisiemeMitemps", "BucheurDeStats", "RoiDuProno", "ChatonDeLigue1", "PigeonDuProno",
    "ChatNoir", "LaGagne", "NulEtVierge", "VictoireNet", "RemontadaKing",
    "ScoreExacteur", "MrCentPourCent", "LeChatDuComptoir", "TactiqueZero", "Tifosi31",
    "FuriaRoja", "AzzurriFan", "DieMannschaft", "OranjePower", "ThreeLions",
    "SelecaoStar", "Albiceleste", "SkyBlues", "Rossoneri", "ScudettoKing"
]

def build_anonymous_mapping(players_list):
    """
    Crée un dictionnaire déterministe {vrai_pseudo: pseudo_anonyme}
    en piochant dans la liste des 100 pseudos les plus populaires.
    """
    sorted_players = sorted(list(set(players_list)))
    mapping = {}
    for idx, p in enumerate(sorted_players):
        anon_name = POPULAR_USERNAMES[idx % len(POPULAR_USERNAMES)]
        if idx >= len(POPULAR_USERNAMES):
            anon_name += f"_{idx // len(POPULAR_USERNAMES) + 1}"
        mapping[p] = anon_name
    return mapping

def generate_random_league_code(original_code="ABCDEF12"):
    """
    Génère un code de ligue anonymisé déterministe (sur la base d'un seed du code original)
    ayant exactement la même longueur et le même format que le code original.
    Exemple : 'ABCDEF12' (8 chars) -> 'XK92MN7P'
    """
    length = len(original_code) if original_code else 8
    chars = string.ascii_uppercase + string.digits
    rng = random.Random(original_code)
    rand_code = ''.join(rng.choices(chars, k=length))
    return rand_code

def get_anonymized_league_info(original_info=None):
    """
    Retourne des informations de ligue anonymisées.
    """
    return {
        'code': 'LIGUE_ANONYME',
        'name': 'Ligue Anonyme'
    }

def anonymize_dataframe(df, mapping):
    """
    Renomme les colonnes de joueurs dans le DataFrame des points cumulés.
    """
    df_anon = df.copy()
    rename_dict = {p: mapping[p] for p in df_anon.columns if p in mapping}
    return df_anon.rename(columns=rename_dict)

def anonymize_player_pronos(player_pronos, mapping):
    """
    Renomme les clés du dictionnaire des pronostics par participant.
    """
    anon_pronos = {}
    for p, pronos in player_pronos.items():
        anon_p = mapping.get(p, p)
        anon_pronos[anon_p] = pronos
    return anon_pronos

def anonymize_directory(source_dir, dest_dir=None):
    """
    Duplique un dossier de données MPP en anonymisant tous les CSV et JSON.
    """
    source_dir = os.path.abspath(source_dir)
    if dest_dir is None:
        dest_dir = source_dir.rstrip('/\\') + '_anon'
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)

    prono_files = glob.glob(os.path.join(source_dir, 'pronos_*.csv'))
    raw_players = []
    for f in prono_files:
        basename = os.path.basename(f)
        parts = basename.replace('pronos_', '').replace('.csv', '').split('_')
        if len(parts) >= 1:
            raw_players.append(parts[0])

    pts_file = os.path.join(source_dir, 'points_cumules.csv')
    if os.path.exists(pts_file):
        df_pts = pd.read_csv(pts_file)
        raw_players.extend([c for c in df_pts.columns if c not in ['Match_Num', 'Date', 'Match']])

    anon_map = build_anonymous_mapping(raw_players)

    league_info = get_anonymized_league_info()
    with open(os.path.join(dest_dir, 'league_info.json'), 'w', encoding='utf-8') as f:
        json.dump(league_info, f, ensure_ascii=False, indent=2)

    if os.path.exists(pts_file):
        df_pts = pd.read_csv(pts_file)
        df_pts_anon = anonymize_dataframe(df_pts, anon_map)
        df_pts_anon.to_csv(os.path.join(dest_dir, 'points_cumules.csv'), index=False, encoding='utf-8')

    for f in prono_files:
        basename = os.path.basename(f)
        m = re.match(r'pronos_(.+)_(\d+)\.csv', basename)
        if m:
            user_name = m.group(1)
            user_id = m.group(2)
            anon_user = anon_map.get(user_name, user_name)
            dest_filename = f"pronos_{anon_user}_{user_id}.csv"
        else:
            dest_filename = basename

        df_prono = pd.read_csv(f)
        df_prono.to_csv(os.path.join(dest_dir, dest_filename), index=False, encoding='utf-8')

    for b_json in ['bonuses.json', 'bonus_country.json', 'bonus_goals.json']:
        b_path = os.path.join(source_dir, b_json)
        if os.path.exists(b_path):
            try:
                with open(b_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                anon_data = {}
                for k, v in data.items():
                    anon_k = anon_map.get(k, k)
                    anon_data[anon_k] = v
                with open(os.path.join(dest_dir, b_json), 'w', encoding='utf-8') as f:
                    json.dump(anon_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    return dest_dir, anon_map

if __name__ == '__main__':
    if len(sys.argv) > 1:
        target = sys.argv[1]
        out_dir, mapping = anonymize_directory(target)
        print(f"[OK] Dossier anonymisé créé avec succès : {out_dir}")
        print(f"[INFO] Correspondance des pseudos ({len(mapping)} joueurs) :")
        for real_p, anon_p in mapping.items():
            print(f"   • {real_p} -> {anon_p}")
    else:
        print("Usage: python anonymizer.py <dossier_ligue>")
