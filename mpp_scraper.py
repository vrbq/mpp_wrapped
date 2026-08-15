import csv
import glob
import json
import logging
import os
import re
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service

# Configuration du système de logging (console INFO, fichier DEBUG)
logger = logging.getLogger("mpp_scraper")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Fichier log récupérant tous les détails (DEBUG et +)
file_handler = logging.FileHandler("mpp_scraper.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console affichant les étapes importantes (INFO et +)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def parse_pronos_from_dom(html_content):
    """Extrait l'ensemble des pronostics d'une page profil MPP à partir de son DOM HTML."""
    logger.debug(f"Début de l'analyse du DOM HTML (taille: {len(html_content)} caractères)...")
    soup = BeautifulSoup(html_content, "html.parser")
    pronos = []
    DAYS = [
        "lundi",
        "mardi",
        "mercredi",
        "jeudi",
        "vendredi",
        "samedi",
        "dimanche",
    ]
    current_date = "Inconnue"

    # Prétraitement : identifier les card_divs uniques contenant "cote" ou "prono" et ayant un score
    card_divs = {} # id(div) -> div
    for element in soup.find_all(string=True):
        val = element.strip().lower()
        if "cote" in val or "prono" in val:
            curr = element.parent
            while curr:
                if curr.name == "div":
                    strings = list(curr.stripped_strings)
                    # Un bloc de match doit contenir un séparateur de score ":" ou "-" et faire une taille raisonnable
                    if (":" in strings or "-" in strings) and len(strings) < 25:
                        card_divs[id(curr)] = curr
                        break
                curr = curr.parent

    visited_ids = set()

    def traverse(element):
        nonlocal current_date
        if id(element) in visited_ids:
            return
        
        # Si c'est une carte de match identifiée
        if id(element) in card_divs:
            card = card_divs[id(element)]
            strings = list(card.stripped_strings)
            parse_card(strings, current_date)
            # Marquer tous les descendants comme visités
            for desc in card.find_all(True):
                visited_ids.add(id(desc))
            visited_ids.add(id(card))
            return
            
        # Sinon, vérifier si c'est un en-tête de date
        if element.name in ["div", "span", "p"]:
            text = element.get_text(strip=True)
            words = text.lower().split()
            if (
                len(words) >= 3
                and words[0] in DAYS
                and words[1].isdigit()
                and len(text) < 35
                and "match" not in text.lower()
            ):
                current_date = text
                logger.debug(f"Nouvelle date de match détectée : {current_date}")
                
        # Continuer le parcours sur les enfants du tag
        for child in element.children:
            if hasattr(child, "name") and child.name is not None:
                traverse(child)

    def parse_card(strings, date):
        try:
            # 1. Équipes et Score Réel (recherche index du séparateur)
            colon_idx = -1
            for idx, s in enumerate(strings):
                if s == ":" or s == "-":
                    colon_idx = idx
                    break
            
            if colon_idx >= 2 and colon_idx + 2 < len(strings):
                home_team = strings[colon_idx - 2]
                score_home = strings[colon_idx - 1]
                score_away = strings[colon_idx + 1]
                away_team = strings[colon_idx + 2]
                score_reel = f"{score_home} - {score_away}"
            else:
                home_team, away_team, score_reel = "", "", ""
                
            # 2. Détail (Prolongations / Tirs au but)
            detail = ""
            for s in strings:
                if "prolong" in s.lower() or "tab" in s.lower():
                    detail = s
                    break
            
            # 3. Cote
            cote = ""
            cote_idx = -1
            for idx, s in enumerate(strings):
                if "cote" in s.lower():
                    cote_idx = idx
                    break
            if cote_idx != -1 and cote_idx + 1 < len(strings):
                cote = strings[cote_idx + 1]
                
            # 4. Tag de bonus / rareté
            bonus_tag = ""
            for s in strings:
                if (s.startswith("(") and s.endswith(")")) or ("pts" in s and "+" in s):
                    bonus_tag = s
                    break
                    
            # 5. Prono MPP
            prono_mpp = ""
            prono_idx = -1
            for idx, s in enumerate(strings):
                if "prono" in s.lower():
                    prono_idx = idx
                    break
            if prono_idx != -1 and prono_idx + 1 < len(strings):
                prono_mpp = strings[prono_idx + 1]
                
            # 6. Points gagnés
            pts = ""
            pts_idx = -1
            for idx, s in enumerate(strings):
                if s.lower() in ["pts", "pt"]:
                    pts_idx = idx
                    break
            if pts_idx != -1 and pts_idx - 1 >= 0:
                pts = strings[pts_idx - 1]
                
            if home_team and away_team:
                logger.debug(
                    f"Prono parsé : {home_team} [{score_reel}] {away_team} "
                    f"| Cote: {cote} | Prono MPP: {prono_mpp} | Pts gagnés: {pts}"
                )
                pronos.append(
                    {
                        "Date": date,
                        "Equipe_Domicile": home_team,
                        "Score_Reel": score_reel,
                        "Equipe_Exterieur": away_team,
                        "Detail": detail,
                        "Cote": cote,
                        "Bonus_Tag": bonus_tag,
                        "Prono_MPP": prono_mpp,
                        "Points_Gagnes": pts,
                    }
                )
            else:
                logger.debug(f"Bloc de match ignoré (informations manquantes) : {strings}")
        except Exception as e:
            logger.debug(f"Erreur d'extraction d'un bloc prono : {e}", exc_info=True)

    # Lancer le parcours depuis le body (ou la racine du soup)
    body = soup.find("body") or soup
    traverse(body)

    # Dédoublonnage
    unique_pronos = []
    seen = set()
    for p in pronos:
        key = (
            p["Date"],
            p["Equipe_Domicile"],
            p["Equipe_Exterieur"],
            p["Prono_MPP"],
        )
        if key not in seen:
            seen.add(key)
            unique_pronos.append(p)
        else:
            logger.debug(f"Intégration ignorée car doublon : {p}")

    logger.debug(f"Extraction terminée pour le DOM : {len(unique_pronos)} pronos uniques extraits.")
    return unique_pronos


def export_to_csv(filename, pronos_data):
    """Exporte la liste des pronostics au format CSV."""
    fieldnames = [
        "Date",
        "Equipe_Domicile",
        "Score_Reel",
        "Equipe_Exterieur",
        "Detail",
        "Cote",
        "Bonus_Tag",
        "Prono_MPP",
        "Points_Gagnes",
    ]
    logger.debug(f"Tentative d'écriture de {len(pronos_data)} lignes dans {filename}...")
    try:
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(pronos_data)
        logger.debug(f"Fichier {filename} écrit avec succès.")
    except Exception as e:
        logger.error(f"Erreur lors de l'écriture du CSV {filename} : {e}", exc_info=True)


def generate_cumulative_csv(target_dir=None, output_filename="points_cumules.csv"):
    """
    Combine tous les fichiers CSV de pronostics (pronos_*.csv) en un seul fichier CSV.
    En colonnes : les informations du match (Match_Num, Date, Match) puis chaque joueur.
    Sur chaque ligne : les points obtenus pour chaque match en cumulant les points (du 1er match au dernier).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    if target_dir is None:
        saved_dir = os.path.join(base_dir, "saved")
        if os.path.exists(saved_dir):
            target_dir = saved_dir
        else:
            target_dir = base_dir

    logger.info(f"Recherche des CSV de pronostics dans : {target_dir}")
    csv_files = glob.glob(os.path.join(target_dir, "pronos_*.csv"))
    
    if not csv_files and target_dir != base_dir:
        csv_files = glob.glob(os.path.join(base_dir, "pronos_*.csv"))
        target_dir = base_dir

    if not csv_files:
        logger.warning("Aucun fichier pronos_*.csv trouvé pour la transformation cumulée.")
        return None

    # Exclure les fichiers cumulés déjà générés
    csv_files = [
        f for f in csv_files 
        if not os.path.basename(f).startswith("pronos_cumules") 
        and not os.path.basename(f).startswith("points_cumules")
    ]

    if not csv_files:
        logger.warning("Aucun fichier pronos_*.csv valide (non cumulé) trouvé.")
        return None

    # Trier par taille de fichier décroissante pour traiter d'abord les fichiers avec le plus de matchs
    csv_files.sort(key=lambda x: os.path.getsize(x), reverse=True)

    master_matches = []
    seen_matches = set()

    # Récupérer la liste maître de tous les matchs dans l'ordre chronologique (du 1er match au dernier)
    for f in csv_files:
        with open(f, mode="r", encoding="utf-8") as fp:
            rows = list(reversed(list(csv.DictReader(fp))))
            for r in rows:
                m_key = (r.get("Date", ""), r.get("Equipe_Domicile", ""), r.get("Equipe_Exterieur", ""))
                if m_key not in seen_matches:
                    seen_matches.add(m_key)
                    master_matches.append({
                        "key": m_key,
                        "Date": r.get("Date", ""),
                        "Equipe_Domicile": r.get("Equipe_Domicile", ""),
                        "Score_Reel": r.get("Score_Reel", ""),
                        "Equipe_Exterieur": r.get("Equipe_Exterieur", "")
                    })

    player_data = {}
    player_names = []

    for f in sorted(csv_files):
        basename = os.path.basename(f)
        match = re.match(r"pronos_(.+)_\d+\.csv$", basename)
        player_name = match.group(1) if match else os.path.splitext(basename)[0]
        
        player_names.append(player_name)
        player_data[player_name] = {}
        
        with open(f, mode="r", encoding="utf-8") as fp:
            rows = list(csv.DictReader(fp))
            for r in rows:
                m_key = (r.get("Date", ""), r.get("Equipe_Domicile", ""), r.get("Equipe_Exterieur", ""))
                try:
                    pts = int(r["Points_Gagnes"]) if r.get("Points_Gagnes") else 0
                except (ValueError, TypeError):
                    pts = 0
                player_data[player_name][m_key] = pts

    # Charger les bonus (Vainqueur / Buteur) si le fichier existe
    bonuses = {}
    if target_dir:
        bonuses_path = os.path.join(target_dir, "bonuses.json")
        bonus_country_path = os.path.join(target_dir, "bonus_country.json")
        bonus_goals_path = os.path.join(target_dir, "bonus_goals.json")
        
        if os.path.exists(bonuses_path):
            try:
                with open(bonuses_path, "r", encoding="utf-8") as f:
                    bonuses = json.load(f)
                logger.info(f"Fichier de bonus chargé : {bonuses_path}")
            except Exception as e:
                logger.error(f"Erreur de chargement du fichier bonus.json : {e}")
                
        # Si le fichier principal n'a pas pu être chargé mais que les fichiers séparés existent
        if not bonuses and os.path.exists(bonus_country_path) and os.path.exists(bonus_goals_path):
            try:
                with open(bonus_country_path, "r", encoding="utf-8") as f:
                    bc = json.load(f)
                with open(bonus_goals_path, "r", encoding="utf-8") as f:
                    bg = json.load(f)
                for p in player_names:
                    bonuses[p] = {
                        "winner_value": bc.get(p, 0),
                        "winner_obtained": bc.get(p, 0) > 0,
                        "scorer_value": bg.get(p, 0),
                        "scorer_obtained": bg.get(p, 0) > 0
                    }
                logger.info("Dictionnaire de bonus reconstruit avec succès à partir de bonus_country.json et bonus_goals.json")
            except Exception as e:
                logger.error(f"Échec de l'intégration des fichiers de bonus alternatifs : {e}")

    # Calculer les points cumulés match par match
    cum_totals = {p: 0 for p in player_names}
    output_rows = []

    for idx, match_info in enumerate(master_matches, start=1):
        m_key = match_info["key"]
        row_dict = {
            "Match_Num": idx,
            "Date": match_info["Date"],
            "Match": f"{match_info['Equipe_Domicile']} {match_info['Score_Reel']} {match_info['Equipe_Exterieur']}".strip()
        }
        for p in player_names:
            pts = player_data[p].get(m_key, 0)
            cum_totals[p] += pts
            row_dict[p] = cum_totals[p]
        output_rows.append(row_dict)

    # Ajouter le match virtuel de bonus final s'il y a des données de bonus
    if bonuses:
        bonus_dict = {
            "Match_Num": len(master_matches) + 1,
            "Date": "Bonus",
            "Match": "Bonus Vainqueur & Buteur"
        }
        for p in player_names:
            p_bonus = bonuses.get(p)
            bonus_pts = 0
            if p_bonus:
                if p_bonus.get("winner_obtained"):
                    bonus_pts += p_bonus.get("winner_value", 0)
                if p_bonus.get("scorer_obtained"):
                    bonus_pts += p_bonus.get("scorer_value", 0)
            cum_totals[p] += bonus_pts
            bonus_dict[p] = cum_totals[p]
        output_rows.append(bonus_dict)

    fieldnames = ["Match_Num", "Date", "Match"] + player_names
    out_path = os.path.join(target_dir, output_filename)

    with open(out_path, mode="w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    logger.info(f"Fichier CSV des points cumulés créé avec succès : {out_path}")
    logger.info(f"  -> {len(output_rows)} matchs traités pour {len(player_names)} joueur(s).")
    return out_path


def save_intercepted_requests(driver, label="", target_file="intercepted_requests.txt"):
    """Enregistre uniquement la requête 'users-standings' et sa réponse complète dans target_file."""
    try:
        # Lire les requêtes interceptées par fetch monkeypatch
        calls = driver.execute_script("return window.__apiCalls || [];")
        
        target_calls = [c for c in calls if 'users-standings' in c.get('url', '')]
        
        if target_calls:
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(f"\n==================================================\n")
                f.write(f"POINT DE CAPTURE : {label} (Time: {time.asctime()})\n")
                f.write(f"URL ACTUELLE : {driver.current_url}\n")
                f.write(f"==================================================\n")
                
                for idx, c in enumerate(target_calls, 1):
                    f.write(f"\n[DÉTAILS REQUÊTE USERS-STANDINGS #{idx}]\n")
                    f.write(f"  Time: {c.get('timestamp')}\n")
                    f.write(f"  URL: {c.get('url')}\n")
                    f.write(f"  Method: {c.get('method')}\n")
                    f.write(f"  Headers: {c.get('headers')}\n")
                    f.write(f"  Body: {c.get('requestBody')}\n")
                    f.write(f"  Response Body:\n{c.get('responseBody')}\n")
                f.write(f"==================================================\n\n")
            logger.info(f"Requête 'users-standings' et sa réponse ont été écrites dans {target_file}")
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de la requête cible : {e}", exc_info=True)


def save_session_data(driver, session_file="mpp_session.json"):
    """Sauvegarde les dictionnaires localStorage et sessionStorage dans session_file."""
    logger.info("  -> Sauvegarde de la session d'authentification...")
    try:
        local_store = driver.execute_script("""
            var items = {};
            for (var i = 0; i < localStorage.length; i++) {
                var k = localStorage.key(i);
                items[k] = localStorage.getItem(k);
            }
            return items;
        """)
        session_store = driver.execute_script("""
            var items = {};
            for (var i = 0; i < sessionStorage.length; i++) {
                var k = sessionStorage.key(i);
                items[k] = sessionStorage.getItem(k);
            }
            return items;
        """)
        session_data = {
            "localStorage": local_store,
            "sessionStorage": session_store,
            "timestamp": time.time()
        }
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        logger.info(f"  -> Session sauvegardée avec succès dans {session_file}.")

        # Enregistrer une copie globale dans le dossier parent
        base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
        parent_session = os.path.join(base_dir, "mpp_session.json")
        if os.path.abspath(session_file) != os.path.abspath(parent_session):
            try:
                with open(parent_session, "w", encoding="utf-8") as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=2)
                logger.info(f"  -> Copie globale de session sauvegardée dans {parent_session}.")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"  -> Échec de la sauvegarde de la session : {e}", exc_info=True)


def restore_session_data(driver, session_file="mpp_session.json"):
    """Restaure les données localStorage et sessionStorage depuis session_file."""
    if not os.path.exists(session_file):
        return False
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        
        local_store = session_data.get("localStorage", {})
        for k, v in local_store.items():
            driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);", k, v)
            
        session_store = session_data.get("sessionStorage", {})
        for k, v in session_store.items():
            driver.execute_script("sessionStorage.setItem(arguments[0], arguments[1]);", k, v)
        
        logger.info(f"  -> Paramètres localStorage/sessionStorage injectés depuis {session_file}.")
        return True
    except Exception as e:
        logger.error(f"  -> Échec de la restauration de la session : {e}", exc_info=True)
        return False


def is_session_valid(driver, code_challenge="VOTRE_LIGUE"):
    """Vérifie si la session restaurée est valide en interrogeant l'API MPP avec le jeton extrait."""
    try:
        token = driver.execute_script(r"""
            for (var i = 0; i < localStorage.length; i++) {
                var val = localStorage.getItem(localStorage.key(i));
                if (val && val.includes("eyJ")) {
                    var m = val.match(/eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+/);
                    if (m) return m[0];
                }
            }
            for (var i = 0; i < sessionStorage.length; i++) {
                var val = sessionStorage.getItem(sessionStorage.key(i));
                if (val && val.includes("eyJ")) {
                    var m = val.match(/eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+/);
                    if (m) return m[0];
                }
            }
            return null;
        """)
        if not token:
            logger.warning("  -> Aucun jeton JWT trouvé dans le stockage local.")
            return False
            
        logger.info(f"  -> Jeton JWT détecté pour validation (Longueur: {len(token)}) : {token}")
            
        js_test = """
        var token = arguments[0];
        var challengeId = arguments[1];
        var callback = arguments[2];
        
        fetch('https://api.mpp.football/challenge-standings/users-standings?challengeId=' + challengeId + '&limit=1', {
            headers: {
                'Authorization': 'Bearer ' + token,
                'Accept': 'application/json'
            }
        })
        .then(r => callback(r.ok))
        .catch(() => callback(false));
        """
        res = driver.execute_async_script(js_test, token, f"mpp_challenge_{code_challenge}")
        return bool(res)
    except Exception:
        return False


def extract_league_bonuses(driver, users_list, output_dir, anon_map=None):
    """
    Visite la page de profil de chaque utilisateur et extrait les bonus 'Ses favoris'
    (Pays vainqueur + Meilleur Buteur) depuis la section dédiée.
    """
    logger.info("Extraction des bonus 'Ses favoris' depuis les profils individuels...")

    js_get_favorites = r"""
    const resolve = arguments[arguments.length - 1];
    (async () => {
        let attempts = 0;
        while (attempts < 30) {
            const h5s = document.querySelectorAll('h5');
            let found = false;
            for (const h of h5s) {
                if ((h.innerText || '').toLowerCase().includes('favoris')) { found = true; break; }
            }
            if (found) break;
            await new Promise(r => setTimeout(r, 300));
            attempts++;
        }

        let favH5 = null;
        const allH5 = document.querySelectorAll('h5');
        for (const h of allH5) {
            if ((h.innerText || '').toLowerCase().includes('favoris')) {
                favH5 = h;
                break;
            }
        }
        if (!favH5) {
            resolve(JSON.stringify({ error: 'h5 Ses favoris not found' }));
            return;
        }

        let card = favH5.parentElement;
        let depth = 0;
        while (card && card !== document.body && depth < 15) {
            const h4s = card.querySelectorAll('h4');
            let ptsCount = 0;
            for (const h4 of h4s) {
                if (/\d+\s*pts/i.test(h4.innerText || '')) ptsCount++;
            }
            if (ptsCount >= 2) break;
            card = card.parentElement;
            depth++;
        }
        if (!card || card === document.body) {
            resolve(JSON.stringify({ error: 'Card with 2+ h4 pts not found' }));
            return;
        }

        const ptsH4s = [];
        const allH4 = card.querySelectorAll('h4');
        for (const h4 of allH4) {
            const txt = (h4.innerText || '').trim();
            if (/\d+\s*pts/i.test(txt)) {
                ptsH4s.push(h4);
            }
        }
        if (ptsH4s.length < 2) {
            resolve(JSON.stringify({ error: 'Less than 2 h4 pts found', count: ptsH4s.length }));
            return;
        }

        function parseH4Block(h4El) {
            const ptsText = (h4El.innerText || '').trim();
            const m = ptsText.match(/(\d+)/);
            const ptsValue = m ? parseInt(m[1], 10) : 0;

            let isStrikethrough = false;
            let check = h4El;
            while (check && check !== card) {
                const computed = window.getComputedStyle(check);
                if (computed.textDecorationLine.includes('line-through') ||
                    computed.textDecoration.includes('line-through')) {
                    isStrikethrough = true;
                    break;
                }
                check = check.parentElement;
            }

            let name = '';
            let sibling = h4El.previousElementSibling;
            while (sibling) {
                const sibText = (sibling.innerText || sibling.textContent || '').trim();
                if (sibText.length > 0 && !/\d+\s*pts/i.test(sibText) && !sibText.toLowerCase().includes('favoris')) {
                    name = sibText;
                    break;
                }
                sibling = sibling.previousElementSibling;
            }
            if (!name && h4El.parentElement) {
                const siblings = h4El.parentElement.children;
                for (const s of siblings) {
                    if (s === h4El) continue;
                    if (s.tagName === 'SVG' || s.tagName === 'svg') continue;
                    const st = (s.innerText || s.textContent || '').trim();
                    if (st.length > 0 && !/\d+\s*pts/i.test(st) && !st.toLowerCase().includes('favoris')) {
                        name = st;
                        break;
                    }
                }
            }

            return { name, ptsValue, isStrikethrough };
        }

        const winner = parseH4Block(ptsH4s[0]);
        const scorer = parseH4Block(ptsH4s[1]);

        resolve(JSON.stringify({
            winner_name: winner.name,
            winner_value: winner.ptsValue,
            winner_obtained: !winner.isStrikethrough,
            scorer_name: scorer.name,
            scorer_value: scorer.ptsValue,
            scorer_obtained: !scorer.isStrikethrough
        }));
    })();
    """

    bonuses = {}
    bonus_country = {}
    bonus_goals = {}

    for user in users_list:
        u_id = user["id"]
        u_name = user["username"]
        save_u_name = anon_map.get(u_name, u_name) if anon_map else u_name
        profile_url = f"https://mpp.football/public-profile/user_{u_id}?userId=user_{u_id}"

        logger.info(f"  [bonus] Navigation vers le profil de {u_name} : {profile_url}")
        try:
            driver.get(profile_url)
            time.sleep(3)

            result_json = driver.execute_async_script(js_get_favorites)
            result = json.loads(result_json)

            if "error" in result:
                logger.warning(f"  [bonus] Erreur pour {u_name} : {result['error']}")
                bonuses[save_u_name] = None
                bonus_country[save_u_name] = 0
                bonus_goals[save_u_name] = 0
            else:
                logger.info(
                    f"  [bonus] {u_name} -> Pays: {result['winner_name']} "
                    f"({result['winner_value']} pts, obtenu={result['winner_obtained']}) | "
                    f"Buteur: {result['scorer_name']} "
                    f"({result['scorer_value']} pts, obtenu={result['scorer_obtained']})"
                )
                bonuses[save_u_name] = result
                bonus_country[save_u_name] = result["winner_value"] if result["winner_obtained"] else 0
                bonus_goals[save_u_name] = result["scorer_value"] if result["scorer_obtained"] else 0

        except Exception as e:
            logger.error(f"  [bonus] Exception pour {u_name} ({u_id}) : {e}", exc_info=True)
            bonuses[save_u_name] = None
            bonus_country[save_u_name] = 0
            bonus_goals[save_u_name] = 0

    # Sauvegarder les trois fichiers
    bonuses_file = os.path.join(output_dir, "bonuses.json")
    with open(bonuses_file, "w", encoding="utf-8") as f:
        json.dump(bonuses, f, indent=2, ensure_ascii=False)
    logger.info(f"Bonus complets enregistrés : {bonuses_file}")

    bonus_country_file = os.path.join(output_dir, "bonus_country.json")
    with open(bonus_country_file, "w", encoding="utf-8") as f:
        json.dump(bonus_country, f, indent=2, ensure_ascii=False)
    logger.info(f"Bonus Pays enregistrés : {bonus_country_file}")

    bonus_goals_file = os.path.join(output_dir, "bonus_goals.json")
    with open(bonus_goals_file, "w", encoding="utf-8") as f:
        json.dump(bonus_goals, f, indent=2, ensure_ascii=False)
    logger.info(f"Bonus Buteur enregistrés : {bonus_goals_file}")

    return bonuses





def main():
    logger.info("=== Lancement de l'extraction des données MPP ===")

    import sys
    is_anon = any(arg in sys.argv for arg in ['--anon', '--anonymize', '-a'])
    pos_args = [a for a in sys.argv[1:] if not a.startswith('-')]

    if pos_args:
        code_challenge = pos_args[0].strip()
    else:
        code_challenge = input(
            "--> Entrez le code du challenge (ex: VOTRE_LIGUE) : "
        ).strip()
    if not code_challenge:
        code_challenge = "VOTRE_LIGUE"

    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."

    if is_anon:
        from anonymizer import generate_random_league_code
        anon_code = generate_random_league_code(code_challenge)
        output_dir = os.path.join(base_dir, anon_code)
        logger.info(f"[MODE ANONYME] Dossier de sortie anonymisé direct : {anon_code} (pour le code réel {code_challenge})")
    else:
        anon_code = code_challenge
        output_dir = os.path.join(base_dir, code_challenge)

    os.makedirs(output_dir, exist_ok=True)

    # Reconfigurer la sortie log du fichier vers le dossier de la ligue
    global file_handler
    try:
        logger.removeHandler(file_handler)
        file_handler.close()
    except Exception:
        pass
    
    log_file_path = os.path.join(output_dir, "mpp_scraper.log")
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info(f"Log reconfiguré vers : {log_file_path}")

    # Paths pour les fichiers de session et requêtes interceptées
    session_file_path = os.path.join(output_dir, "mpp_session.json")
    intercepted_requests_path = os.path.join(output_dir, "intercepted_requests.txt")

    # 1. Ouverture de Firefox
    logger.info("[1/11] Lancement de Firefox...")
    from selenium.webdriver.firefox.options import Options
    options = Options()
    if "--headless" in sys.argv:
        logger.info("  -> Mode sans tête (headless) activé")
        options.add_argument("--headless")
    try:
        driver = webdriver.Firefox(options=options)
        driver.implicitly_wait(10)
    except Exception as e:
        logger.critical(f"Impossible d'ouvrir Firefox avec Selenium : {e}", exc_info=True)
        return

    try:
        # 2. Navigation vers MPP
        logger.info("[2/11] Navigation vers MPP (https://mpp.football/)...")
        driver.get("https://mpp.football/")
        time.sleep(3)

        # Tentative de restauration de session d'authentification
        session_restored = False
        restore_path = session_file_path
        if not os.path.exists(restore_path):
            fallback_path = os.path.join(base_dir, "mpp_session.json")
            if os.path.exists(fallback_path):
                restore_path = fallback_path

        if os.path.exists(restore_path) and "--fresh" not in sys.argv:
            logger.info(f"  -> Fichier de session trouvé : {restore_path}. Tentative de restauration...")
            if restore_session_data(driver, session_file=restore_path):
                driver.refresh()
                time.sleep(4)
                
                # Vérifier si le jeton restauré est toujours actif/fonctionnel sur l'API MPP
                if is_session_valid(driver, code_challenge):
                    logger.info("  -> Session restaurée avec succès ! Connexion active.")
                    session_restored = True
                else:
                    logger.warning("  -> La session restaurée est expirée ou invalide.")
            else:
                logger.warning("  -> Échec de la restauration de la session.")
                
        # 3. Pause pour laisser l'utilisateur se connecter si non restauré
        if not session_restored:
            if "--headless" in sys.argv:
                logger.critical("[ERREUR CRITIQUE] Session invalide ou expirée en mode headless. Impossible d'interagir visualement pour la connexion.")
                sys.exit(1)
            logger.info("[3/11] En attente de connexion utilisateur dans le navigateur...")
            print("\n[3/11] Veuillez vous connecter directement dans Firefox.")
            input(
                "--> Une fois connecté(e), appuyez sur [ENTRÉE] ici dans le terminal pour continuer..."
            )
            logger.info("Connexion validée par l'utilisateur.")
            time.sleep(2)
            save_session_data(driver, session_file=session_file_path)

        # Injection immédiate de l'intercepteur réseau fetch global sur la page d'accueil
        logger.info("Injection de l'intercepteur fetch global...")
        js_inject_fetch = """
        window.__apiCalls = [];
        if (!window.__fetchIntercepted) {
            window.__fetchIntercepted = true;
            const originalFetch = window.fetch;
            window.fetch = async function(...args) {
                const url = args[0] || '';
                const options = args[1] || {};
                
                if (typeof url === 'string' && url.includes('users-standings')) {
                    const callInfo = {
                        url: url,
                        method: options.method || 'GET',
                        headers: options.headers ? JSON.stringify(options.headers) : null,
                        requestBody: options.body || null,
                        responseBody: "En attente...",
                        timestamp: new Date().toISOString()
                    };
                    window.__apiCalls.push(callInfo);
                    
                    try {
                        const response = await originalFetch.apply(this, args);
                        const clone = response.clone();
                        const text = await clone.text();
                        callInfo.responseBody = text;
                        
                        try {
                            window.__mppFetchData = JSON.parse(text);
                        } catch(e) {}
                        
                        return response;
                    } catch(err) {
                        callInfo.responseBody = "Network error: " + err.toString();
                        throw err;
                    }
                }
                return originalFetch.apply(this, args);
            };
        }
        """
        driver.execute_script(js_inject_fetch)

        logger.info(f"[4/11] Code du challenge actif : {code_challenge}")

        # 5. Redirection vers la ligue (redirection classique directe)
        league_url = f"https://mpp.football/leagues/mpp_challenge_{code_challenge}"
        logger.info(f"[5/11] Redirection vers la ligue : {league_url}")
        driver.get(league_url)
        time.sleep(5)
        
        # Injection immédiate de l'intercepteur de fetch global après le premier chargement
        logger.info("Injection de l'intercepteur fetch après chargement de la ligue...")
        driver.execute_script(js_inject_fetch)
        
        # 6. Copie du DOM de la ligue
        logger.info("[6/11] Extraction du DOM de la ligue...")
        league_dom = driver.execute_script(
            "return document.documentElement.outerHTML;"
        )
        logger.debug(f"Taille du DOM de la ligue : {len(league_dom)} caractères.")
        save_intercepted_requests(driver, "Après chargement de la ligue", target_file=intercepted_requests_path)

        # Extraction du nom de la ligue depuis le DOM
        extracted_league_name = None
        import html
        import re

        # Tier 1: Direct Regex extraction on league_dom string (Fastest & Most Reliable)
        m = re.search(r'InsatiableDisplay[^\'">]*>\s*([^<]+?)\s*</', league_dom, re.IGNORECASE)
        if m:
            val = html.unescape(m.group(1)).strip()
            if val and val.lower() not in ['terminé', 'en cours', 'classement', 'matchs', 'retour', 'mes ligues']:
                extracted_league_name = val

        # Tier 2: Regex for 24px font-size near style
        if not extracted_league_name:
            m2 = re.search(r'font-size:\s*24px[^\'">]*>\s*([^<]+?)\s*</', league_dom, re.IGNORECASE)
            if m2:
                val = html.unescape(m2.group(1)).strip()
                if val and val.lower() not in ['terminé', 'en cours', 'classement', 'matchs', 'retour', 'mes ligues']:
                    extracted_league_name = val

        # Tier 3: BeautifulSoup parsing
        if not extracted_league_name:
            try:
                soup_l = BeautifulSoup(league_dom, "html.parser")
                for el in soup_l.find_all(["div", "span", "h1", "h2", "p"]):
                    style = el.get("style", "")
                    cls = " ".join(el.get("class", [])) if isinstance(el.get("class"), list) else el.get("class", "")
                    if "InsatiableDisplay" in style or "24px" in style or "InsatiableDisplay" in cls:
                        txt = el.get_text(strip=True)
                        if txt and len(txt) < 80 and txt.lower() not in ["terminé", "en cours", "classement", "matchs", "retour"]:
                            extracted_league_name = html.unescape(txt).strip()
                            break
            except Exception as e:
                logger.warning(f"  -> Échec de l'extraction du nom de ligue dans le DOM : {e}")

        # Tier 4: JS DOM query
        if not extracted_league_name:
            try:
                extracted_league_name = driver.execute_script(r"""
                    var els = document.querySelectorAll('div, span, h1, h2, p');
                    for (var i = 0; i < els.length; i++) {
                        var el = els[i];
                        var style = el.getAttribute('style') || '';
                        var cls = el.getAttribute('class') || '';
                        var txt = (el.innerText || el.textContent || '').trim();
                        if (txt && txt.length > 1 && txt.length < 80 && !['terminé', 'en cours', 'classement', 'matchs', 'mes ligues', 'retour'].includes(txt.toLowerCase())) {
                            if (style.includes('InsatiableDisplay') || style.includes('24px') || cls.includes('InsatiableDisplay')) {
                                return txt;
                            }
                        }
                    }
                    return null;
                """)
            except Exception as e:
                logger.warning(f"  -> Extraction JS du nom de ligue : {e}")

        if extracted_league_name:
            extracted_league_name = html.unescape(str(extracted_league_name)).strip()
            logger.info(f"Nom de ligue extrait avec succès : '{extracted_league_name}'")

        if is_anon:
            league_info_data = {
                "code": anon_code,
                "name": f"Ligue {anon_code}"
            }
        else:
            league_info_data = {
                "code": code_challenge,
                "name": extracted_league_name or f"Ligue {code_challenge}"
            }
        league_info_path = os.path.join(output_dir, "league_info.json")
        with open(league_info_path, "w", encoding="utf-8") as f:
            json.dump(league_info_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Informations de la ligue enregistrées : {league_info_data}")

        # 7. Collecte des utilisateurs (interception réseau + inspection React)
        logger.info(
            "[7/11] Collecte des utilisateurs (interception réseau + inspection React)..."
        )
        
        users_list = []
        
        # 7.1. Extraction du token JWT et tentative de fetch direct de l'API Challenge Standings
        try:
            logger.info("  -> Recherche automatique d'un jeton JWT d'authentification...")
            token = driver.execute_script(r"""
                function findJWTToken() {
                    for (var i = 0; i < localStorage.length; i++) {
                        var val = localStorage.getItem(localStorage.key(i));
                        if (val && val.includes("eyJ")) {
                            var m = val.match(/eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+/);
                            if (m) return m[0];
                        }
                    }
                    for (var i = 0; i < sessionStorage.length; i++) {
                        var val = sessionStorage.getItem(sessionStorage.key(i));
                        if (val && val.includes("eyJ")) {
                            var m = val.match(/eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+/);
                            if (m) return m[0];
                        }
                    }
                    var cookies = document.cookie.split(';');
                    for (var i = 0; i < cookies.length; i++) {
                        var parts = cookies[i].split('=');
                        if (parts[1] && parts[1].includes("eyJ")) {
                            var m = parts[1].match(/eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+/);
                            if (m) return m[0];
                        }
                    }
                    return null;
                }
                return findJWTToken();
            """)
            
            if token:
                logger.info(f"  -> Jeton JWT identifié (longueur: {len(token)}). Lancement du fetch direct...")
                js_fetch_direct = """
                var token = arguments[0];
                var challengeId = arguments[1];
                var callback = arguments[2];
                var url = 'https://api.mpp.football/challenge-standings/users-standings?challengeId=' + challengeId + '&offset=0&limit=100';
                
                fetch(url, {
                    headers: {
                        'Authorization': 'Bearer ' + token,
                        'Accept': 'application/json'
                    }
                })
                .then(r => {
                    if(!r.ok) throw new Error("HTTP " + r.status);
                    return r.json();
                })
                .then(data => {
                    callback(JSON.stringify(data));
                })
                .catch(err => {
                    callback("ERROR: " + err.toString());
                });
                """
                api_result = driver.execute_async_script(js_fetch_direct, token, f"mpp_challenge_{code_challenge}")
                if api_result.startswith("ERROR:"):
                    logger.warning(f"  -> Échec du fetch direct de l'API : {api_result}")
                else:
                    data = json.loads(api_result)
                    logger.info("  -> Liste complète des utilisateurs récupérée via fetch direct !")
                    items = data if isinstance(data, list) else data.get("users", data.get("standings", []))
                    if not items and isinstance(data, dict):
                        items = data.get("standings", [])
                    for item in items:
                        u_id = item.get("userId") or item.get("id") or item.get("user", {}).get("id")
                        u_name = item.get("username") or item.get("user", {}).get("username") or u_id
                        if u_id:
                            clean_id = str(u_id).replace("user_", "")
                            users_list.append({"id": clean_id, "username": u_name})
                    # Stocker la réponse dans window.__mppFetchData pour archivage
                    driver.execute_script("window.__mppFetchData = arguments[0];", data)
            else:
                logger.warning("  -> Aucun jeton d'authentification valide trouvé. Saut de l'appel direct.")
        except Exception as e:
            logger.error(f"  -> Échec lors de la tentative de fetch direct API : {e}", exc_info=True)

        # 7.2. Fallback 1: Simulation d'un clic d'onglet pour déclencher la requête réseau dans le navigateur
        if not users_list:
            logger.info("  -> Simulation d'un clic d'onglet pour déclencher la requête réseau dans le navigateur...")
            js_trigger_tab = """
            var tabs = document.querySelectorAll('[role="tab"]');
            var tab1 = null, tab2 = null;
            for (var i = 0; i < tabs.length; i++) {
                var txt = tabs[i].innerText || tabs[i].textContent || "";
                if (txt.includes("Résultats") || txt.includes("Matchs")) {
                    tab1 = tabs[i];
                }
                if (txt.includes("Classement")) {
                    tab2 = tabs[i];
                }
            }
            if (!tab1 || !tab2) {
                tab1 = document.querySelector('[aria-label="Résultats"]') || document.querySelector('[aria-label="Matchs"]');
                tab2 = document.querySelector('[aria-label="Classement"]');
            }
            if (tab1 && tab2) {
                tab1.click();
                setTimeout(() => { tab2.click(); }, 600);
                return true;
            }
            return false;
            """
            triggered = driver.execute_script(js_trigger_tab)
            logger.info(f"  -> Clics d'onglets simulés : {triggered}")
            
            if triggered:
                # Attendre l'interception et la résolution de la promesse (max 4 secondes)
                for _ in range(8):
                    time.sleep(0.5)
                    data = driver.execute_script("return window.__mppFetchData;")
                    if data:
                        logger.info("  -> Réponse API de la ligue interceptée avec succès !")
                        items = data if isinstance(data, list) else data.get("users", data.get("standings", []))
                        if not items and isinstance(data, dict):
                            items = data.get("standings", [])
                        for item in items:
                            u_id = item.get("userId") or item.get("id") or item.get("user", {}).get("id")
                            u_name = item.get("username") or item.get("user", {}).get("username") or u_id
                            if u_id:
                                clean_id = str(u_id).replace("user_", "")
                                users_list.append({"id": clean_id, "username": u_name})
                        break

        save_intercepted_requests(driver, "Après simulation d'onglets", target_file=intercepted_requests_path)
        
        # 7.3. Fallback 2: Si l'interception a échoué, on bascule sur l'analyse de l'arbre React Fiber (sécurisée avec scrolling robuste)
        if not users_list:
            logger.info("  -> Interception réseau non aboutie. Passage à l'inspection de l'arbre React Fiber avec défilement progressif...")
            js_find_users_fiber = """
            async function findUsersFromReactDom() {
                var output = [];
                var seen = new Set();
                var visited = new Set();
                
                function getFiber(el) {
                    for (var k in el) {
                        if (k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$")) {
                            return el[k];
                        }
                    }
                    return null;
                }
                
                function searchKeys(obj, name, depth) {
                    if (!obj || depth > 8) return null;
                    if (visited.has(obj)) return null;
                    visited.add(obj);
                    
                    if (typeof obj === 'object') {
                        var id = null;
                        var uname = null;
                        
                        try {
                            id = obj.userId || obj.id || obj.user_id;
                            uname = obj.username || obj.userName || obj.name;
                            
                            if (obj.user && typeof obj.user === 'object') {
                                id = id || obj.user.id || obj.user.userId;
                                uname = uname || obj.user.username || obj.user.name;
                            }
                        } catch(e) {}
                        
                        if (id && uname && String(uname).toLowerCase() === name.toLowerCase()) {
                            return String(id).replace("user_", "");
                        }
                        
                        for (var k in obj) {
                            if (k === 'sibling' || k === 'return' || k === 'child' || k === '_owner' || k === 'stateNode') continue;
                            
                            var subObj = null;
                            try {
                                subObj = obj[k];
                            } catch(e) {
                                continue;
                            }
                            
                            var res = searchKeys(subObj, name, depth + 1);
                            if (res) return res;
                        }
                    }
                    return null;
                }
                
                // Détecter le conteneur scrollable ou le body
                var scrollContainer = window;
                var divs = document.querySelectorAll('div');
                for (var i = 0; i < divs.length; i++) {
                    if (divs[i].scrollHeight > divs[i].clientHeight && 
                        window.getComputedStyle(divs[i]).overflowY !== 'visible') {
                        scrollContainer = divs[i];
                    }
                }
                
                // Défilement progressif pour extraire tous les membres (FlatList virtualisée)
                for (var step = 0; step < 15; step++) {
                    var elements = document.getElementsByTagName("h5");
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        var name = el.innerText || el.textContent;
                        if (!name || name.trim().length === 0 || 
                            /Points|Bons|Exacts|Journée|Mes ligues|Classements|Résultats|Matchs|Réglages|Profil/i.test(name)) continue;
                        
                        name = name.trim();
                        var current = el;
                        var userId = null;
                        visited.clear();
                        while (current && !userId) {
                            var fiber = getFiber(current);
                            if (fiber) {
                                if (fiber.memoizedProps) {
                                    userId = searchKeys(fiber.memoizedProps, name, 0);
                                }
                                if (!userId && fiber.memoizedState) {
                                    userId = searchKeys(fiber.memoizedState, name, 0);
                                }
                            }
                            current = current.parentElement;
                        }
                        
                        if (userId && !seen.has(userId)) {
                            seen.add(userId);
                            output.push({ id: userId, username: name });
                        }
                    }
                    
                    // Défiler (scrollTop et scrollBy pour être 100% sûr que le défilement est appliqué)
                    if (scrollContainer === window) {
                        window.scrollBy(0, 400);
                        window.scrollTo(0, (window.pageYOffset || document.documentElement.scrollTop) + 400);
                    } else {
                        scrollContainer.scrollTop += 400;
                        if (scrollContainer.scrollBy) {
                            try { scrollContainer.scrollBy(0, 400); } catch(e) {}
                        }
                    }
                    // Forcer également toutes les divs internes scrollables au cas où
                    for (var j = 0; j < divs.length; j++) {
                        var d = divs[j];
                        if (d.scrollHeight > d.clientHeight) {
                            d.scrollTop += 400;
                            if (d.scrollBy) {
                                try { d.scrollBy(0, 400); } catch(e) {}
                            }
                        }
                    }
                    await new Promise(r => setTimeout(r, 400));
                }
                
                // Revenir au début
                if (scrollContainer === window) {
                    window.scrollTo(0, 0);
                } else {
                    scrollContainer.scrollTo(0, 0);
                }
                
                return output;
            }
            const resolve = arguments[arguments.length - 1];
            findUsersFromReactDom().then(res => resolve(JSON.stringify(res)));
            """
            try:
                fiber_data = driver.execute_async_script(js_find_users_fiber)
                users_list = json.loads(fiber_data)
                if users_list:
                    logger.info(f"  -> {len(users_list)} utilisateur(s) extrait(s) via React Fiber.")
            except Exception as e:
                logger.error(f"  -> Échec de l'inspection de l'arbre React Fiber : {e}", exc_info=True)

        logger.info(f"[8/11] Collecte des profils terminée. {len(users_list)} utilisateur(s) prêt(s) à être traité(s).")
        for u in users_list:
            logger.info(f"  -> {u['username']} (ID: {u['id']})")

        # Validation manuelle désactivée
        print(f"\n==================================================")
        print(f"VOICI TOUS LES UTILISATEURS DÉTECTÉS ({len(users_list)} au total) :")
        for idx, u in enumerate(users_list, 1):
            print(f"  [{idx}] {u['username']} (ID: {u['id']})")
        print(f"==================================================")
        logger.info("Démarrage automatique du scraping des pronostics (validation sautée)...")

        if not users_list:
            logger.warning("Aucun utilisateur n'a pu être extrait. Fin du programme.")
            return

        anon_map = None
        if is_anon:
            from anonymizer import build_anonymous_mapping
            anon_map = build_anonymous_mapping([u["username"] for u in users_list])

        # Extraction des bonus de vainqueur & de meilleur buteur depuis la page de la ligue
        extract_league_bonuses(driver, users_list, output_dir, anon_map=anon_map)

        # 9, 10, 11. Pour chaque utilisateur : chargement du profil, capture du DOM, extraction et export CSV
        for idx, user in enumerate(users_list, start=1):
            u_id = user["id"]
            u_name = user["username"]
            save_u_name = anon_map[u_name] if (anon_map and u_name in anon_map) else u_name
            profile_url = f"https://mpp.football/public-profile/user_{u_id}?tab=forecasts"

            logger.info(
                f"[{idx}/{len(users_list)}] Traitement de {u_name} ({u_id})..."
            )
            logger.debug(f"Navigation vers le profil : {profile_url}")
            driver.get(profile_url)
            time.sleep(3)  # Temps de rendu dynamique React

            # Défilement progressif du profil pour charger l'intégralité des matchs
            logger.info("  -> Défilement progressif du profil pour charger tous les matchs...")
            js_scroll_profile = """
            const resolve = arguments[arguments.length - 1];
            (async () => {
                let scrollContainer = window;
                // Détecter un div scrollable interne avec barre de défilement active
                const divs = document.querySelectorAll('div');
                for (const d of divs) {
                    const style = window.getComputedStyle(d);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && d.scrollHeight > window.innerHeight) {
                        scrollContainer = d;
                        break;
                    }
                }
                
                let lastHeight = 0;
                let currentHeight = scrollContainer === window ? document.documentElement.scrollHeight : scrollContainer.scrollHeight;
                let attempts = 0;
                let noChangeCount = 0;
                
                while (attempts < 25) {
                    if (scrollContainer === window) {
                        window.scrollTo(0, document.documentElement.scrollHeight);
                    } else {
                        scrollContainer.scrollTo(0, scrollContainer.scrollHeight);
                    }
                    await new Promise(r => setTimeout(r, 600));
                    
                    lastHeight = currentHeight;
                    currentHeight = scrollContainer === window ? document.documentElement.scrollHeight : scrollContainer.scrollHeight;
                    
                    if (currentHeight === lastHeight) {
                        noChangeCount++;
                        if (noChangeCount >= 3) {
                            break; // Stable since 3 checks
                        }
                    } else {
                        noChangeCount = 0;
                    }
                    attempts++;
                }
                resolve(currentHeight);
            })();
            """
            try:
                driver.execute_async_script(js_scroll_profile)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"  -> Erreur mineure durant le défilement du profil : {e}")

            # Capture DOM
            logger.debug("Extraction du DOM...")
            user_dom = driver.execute_script(
                "return document.documentElement.outerHTML;"
            )
            
            # Écriture du DOM de debug pour le premier utilisateur
            if idx == 1:
                try:
                    debug_file_path = os.path.join(output_dir, "debug_profile.html")
                    with open(debug_file_path, "w", encoding="utf-8") as debug_file:
                        debug_file.write(user_dom)
                    logger.info(f"DOM de debug du premier profil écrit dans '{debug_file_path}'.")
                except Exception as de:
                    logger.error(f"Erreur lors de l'écriture de 'debug_profile.html' : {de}")

            # Extraction des pronostics
            pronos = parse_pronos_from_dom(user_dom)

            # Export en CSV
            clean_name = f"pronos_{re.sub(r'[^a-zA-Z0-9_-]', '_', save_u_name)}_{u_id}.csv"
            clean_filename = os.path.join(output_dir, clean_name)

            export_to_csv(clean_filename, pronos)
            logger.info(
                f"  -> Sauvegardé : {clean_filename} ({len(pronos)} pronostics enregistrés)"
            )

        logger.info("=== Fin de l'extraction. Génération du fichier des points cumulés... ===")
        cumul_path = generate_cumulative_csv(target_dir=output_dir)
        if cumul_path:
            logger.info(f"=== Traitement terminé avec succès ! CSV cumulé généré : {cumul_path} ===")

    except Exception as e:
        logger.critical(f"Une erreur fatale est survenue pendant le scraping : {e}", exc_info=True)
    finally:
        logger.info("Fermeture du navigateur...")
        driver.quit()
        if is_anon:
            try:
                debug_file_path = os.path.join(output_dir, "debug_profile.html")
                if os.path.exists(debug_file_path):
                    os.remove(debug_file_path)
                intercepted_requests_path = os.path.join(output_dir, "intercepted_requests.txt")
                if os.path.exists(intercepted_requests_path):
                    os.remove(intercepted_requests_path)
                logger.removeHandler(file_handler)
                file_handler.close()
                log_file_path = os.path.join(output_dir, "mpp_scraper.log")
                if os.path.exists(log_file_path):
                    os.remove(log_file_path)
            except Exception:
                pass


if __name__ == "__main__":
    main()