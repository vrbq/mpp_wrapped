import sys
import pandas as pd
import glob, os, csv, json

def select_data_directory():
    import sys
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    pos_args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if pos_args:
        arg_path = pos_args[0].rstrip('/\\')
        if os.path.exists(arg_path):
            selected = os.path.abspath(arg_path)
            print(f"Dossier de données passé en argument : {os.path.basename(selected)} ({selected})")
            return selected
        rel_path = os.path.join(base_dir, arg_path)
        if os.path.exists(rel_path):
            selected = os.path.abspath(rel_path)
            print(f"Dossier de données passé en argument (relatif) : {os.path.basename(selected)} ({selected})")
            return selected

    candidates = []
    if glob.glob(os.path.join(base_dir, 'pronos_*.csv')) or os.path.exists(os.path.join(base_dir, 'points_cumules.csv')):
        candidates.append(base_dir)
    try:
        for entry in os.scandir(base_dir):
            if entry.is_dir() and not entry.name.startswith('.') and entry.name != '__pycache__':
                sub_dir = entry.path
                if glob.glob(os.path.join(sub_dir, 'pronos_*.csv')) or os.path.exists(os.path.join(sub_dir, 'points_cumules.csv')):
                    candidates.append(sub_dir)
    except Exception:
        pass
    candidates = list(set(os.path.abspath(c) for c in candidates))
    if not candidates:
        fallback = os.path.abspath(os.path.join(base_dir, 'saved'))
        print(f"Aucun dossier avec CSV trouvé. Utilisation par défaut de : {fallback}")
        return fallback
    if len(candidates) == 1:
        selected = candidates[0]
        print(f"Dossier de données détecté : {os.path.basename(selected)} ({selected})")
        return selected
    print("\nPlusieurs dossiers de données ont été trouvés :")
    for idx, cand in enumerate(candidates, start=1):
        num_pronos = len(glob.glob(os.path.join(cand, 'pronos_*.csv')))
        has_points = "oui" if os.path.exists(os.path.join(cand, 'points_cumules.csv')) else "non"
        print(f"  [{idx}] {os.path.basename(cand)}/ ({cand}) | {num_pronos} pronos | points cumulés : {has_points}")
    try:
        user_choice = input(f"Choisissez un dossier (1 à {len(candidates)}, défaut: 1) : ").strip()
        if not user_choice: return candidates[0]
        idx_choice = int(user_choice) - 1
        if 0 <= idx_choice < len(candidates): return candidates[idx_choice]
    except Exception:
        pass
    return candidates[0]

def get_player_colors(players_list):
    VIBRANT_PALETTE = [
        '#FF0055', '#00E5FF', '#00FF87', '#B026FF', '#FF9100',
        '#76FF03', '#FF3D00', '#FFD600', '#FF00B7', '#00E676',
        '#2979FF', '#FFEA00', '#D500F9', '#00B0FF', '#FF1744'
    ]
    colors_map = {}
    for idx, p in enumerate(players_list):
        colors_map[p] = VIBRANT_PALETTE[idx % len(VIBRANT_PALETTE)]
    return colors_map

def get_league_info(data_dir):
    data_dir = os.path.abspath(data_dir)
    code_challenge = os.path.basename(data_dir)
    if code_challenge in ['.', '', 'MPP']:
        code_challenge = 'cdm2026'

    info_path = os.path.join(data_dir, 'league_info.json')
    if os.path.exists(info_path):
        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
                return {
                    'code': info.get('code', code_challenge),
                    'name': info.get('name', f"Ligue {code_challenge}")
                }
        except Exception:
            pass

    league_name = None
    html_files = glob.glob(os.path.join(data_dir, '*.html'))
    for h_file in html_files:
        try:
            with open(h_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if 'InsatiableDisplay' in content or 'font-size: 24px' in content or 'font-size:24px' in content:
                    soup = BeautifulSoup(content, 'html.parser')
                    for el in soup.find_all(['div', 'span', 'h1', 'h2', 'p']):
                        style = el.get('style', '')
                        if ('InsatiableDisplay' in style or 'font-size: 24px' in style or 'font-size:24px' in style):
                            txt = el.get_text(strip=True)
                            if txt and len(txt) < 60 and txt.lower() not in ['terminé', 'en cours', 'classement', 'matchs']:
                                league_name = txt
                                break
                if league_name:
                    break
        except Exception:
            pass

    if not league_name:
        league_name = f"Ligue {code_challenge}"

    league_data = {'code': code_challenge, 'name': league_name}
    try:
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(league_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return league_data

csv_dir = select_data_directory()
league_info = get_league_info(csv_dir)
league_name = league_info['name']
league_code = league_info['code']

points_df = pd.read_csv(os.path.join(csv_dir, 'points_cumules.csv'))

# Check if the last row is the virtual bonus row
has_bonus_row = False
if not points_df.empty and (points_df.iloc[-1]['Date'] == 'Bonus' or 'Bonus' in str(points_df.iloc[-1]['Match'])):
    has_bonus_row = True
    print("[INFO] Ligne de bonus détectée à la fin de points_cumules.csv")

# Filter out the bonus row to compute standard match metrics (played, missed, precision)
if has_bonus_row:
    base_points_df = points_df.iloc[:-1]
else:
    base_points_df = points_df

user_files = glob.glob(os.path.join(csv_dir, 'pronos_*.csv'))
user_files = [f for f in user_files if not os.path.basename(f).startswith('points_cumules')]
user_files.sort(key=lambda x: os.path.getsize(x), reverse=True)

# Build Master Matches list
master_matches = []
seen_matches = set()

for f in user_files:
    with open(f, mode='r', encoding='utf-8') as fp:
        rows = list(reversed(list(csv.DictReader(fp))))
        for r in rows:
            m_key = (r.get('Date', ''), r.get('Equipe_Domicile', ''), r.get('Equipe_Exterieur', ''))
            if m_key not in seen_matches:
                seen_matches.add(m_key)
                master_matches.append({
                    'key': m_key,
                    'Date': r.get('Date', ''),
                    'Equipe_Domicile': r.get('Equipe_Domicile', ''),
                    'Score_Reel': r.get('Score_Reel', ''),
                    'Equipe_Exterieur': r.get('Equipe_Exterieur', '')
                })

def get_star_count(tag):
    if not tag:
        return 0
    t = tag.lower()
    if 'ultra' in t: return 5
    if 'mega' in t or 'méga' in t: return 4
    if 'très' in t or 'tres' in t: return 3
    if 'rare' in t: return 2
    if 'exact' in t: return 1
    return 0

def get_star_suffix(tag):
    s = get_star_count(tag)
    if s == 5: return ' ⭐⭐⭐⭐⭐'
    if s == 4: return ' ⭐⭐⭐⭐'
    if s == 3: return ' ⭐⭐⭐'
    if s == 2: return ' ⭐⭐'
    if s == 1: return ' ⭐'
    return ''

# Parse individual player predictions & calculate player stats
player_pronos = {}
player_names = [c for c in points_df.columns if c not in ['Match_Num', 'Date', 'Match']]

player_stats = {}
for p in player_names:
    player_stats[p] = {
        'total_pts': int(points_df[p].iloc[-1]),
        'pts_matches': 0,
        'played_matches': 0,
        'missed_matches': 0,
        'real_accuracy': 0.0,
        'exact_matches': 0,
        'stars_breakdown': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        'total_stars': 0
    }

player_match_stars = {p: [] for p in player_names}

for f in user_files:
    basename = os.path.basename(f)
    parts = basename.split('_')
    p_name = '_'.join(parts[1:-1])
    player_pronos[p_name] = {}
    
    with open(f, mode='r', encoding='utf-8') as fp:
        rows = list(csv.DictReader(fp))
        for r in rows:
            m_key = (r.get('Date', ''), r.get('Equipe_Domicile', ''), r.get('Equipe_Exterieur', ''))
            prono = r.get('Prono_MPP', '').strip()
            score_reel = r.get('Score_Reel', '').strip()
            tag = r.get('Bonus_Tag', '').strip()
            pts = r.get('Points_Gagnes', '0').strip()
            
            try:
                pts_val = int(pts)
            except:
                pts_val = 0
                
            star_count = get_star_count(tag)
            
            if not prono and pts_val > 0:
                prono = score_reel
                if star_count == 0:
                    star_count = 1
            
            star_suffix = get_star_suffix(tag) if star_count > 0 else ''
            if not star_suffix and (star_count == 1 or (pts_val > 0 and prono == score_reel)):
                star_suffix = ' ⭐'
                star_count = 1

            if prono and prono != '-':
                player_stats[p_name]['played_matches'] += 1
            elif pts_val > 0:
                player_stats[p_name]['played_matches'] += 1

            if pts_val > 0:
                player_stats[p_name]['pts_matches'] += 1
            
            is_star_match = False
            if star_count > 0 or (pts_val > 0 and prono == score_reel):
                is_star_match = True
                player_stats[p_name]['exact_matches'] += 1
                if star_count == 0: star_count = 1
                player_stats[p_name]['stars_breakdown'][star_count] += 1
                player_stats[p_name]['total_stars'] += star_count

            prono_formatted = f"{prono}{star_suffix}" if prono else '-'
                
            player_pronos[p_name][m_key] = {
                'prono': prono_formatted,
                'pts_gained': str(pts_val),
                'is_star': is_star_match,
                'star_count': star_count
            }

is_anon = any(arg in sys.argv for arg in ['--anon', '--anonymize', '-a'])
if is_anon:
    print("[INFO] Mode Anonyme activé : pseudos et informations de ligue masqués.")
    from anonymizer import build_anonymous_mapping, get_anonymized_league_info, anonymize_dataframe, anonymize_player_pronos
    
    anon_league = get_anonymized_league_info(league_info)
    league_name = anon_league['name']
    league_code = anon_league['code']
    
    anon_map = build_anonymous_mapping(player_names)
    points_df = anonymize_dataframe(points_df, anon_map)
    base_points_df = anonymize_dataframe(base_points_df, anon_map)
    player_pronos = anonymize_player_pronos(player_pronos, anon_map)
    
    player_stats = {anon_map[p]: player_stats[p] for p in player_names if p in anon_map}
    for p, st in player_stats.items():
        st['player'] = p
    player_match_stars = {anon_map[p]: player_match_stars[p] for p in player_names if p in anon_map}
    player_names = [anon_map[p] for p in player_names]

# Compute missed matches & real accuracy (% on played matches)
num_matches = len(base_points_df)
for p in player_names:
    st = player_stats[p]
    st['missed_matches'] = num_matches - st['played_matches']
    if st['played_matches'] > 0:
        st['real_accuracy'] = round((st['pts_matches'] / st['played_matches']) * 100, 1)
    else:
        st['real_accuracy'] = 0.0

# Compute ranks for each match
ranks_df = pd.DataFrame()
for p in player_names:
    ranks_df[p] = points_df[player_names].rank(axis=1, ascending=False, method='min')[p]

vivid_colors = get_player_colors(player_names)

matches_payload = []
for idx, row in points_df.iterrows():
    m_num = int(row['Match_Num']) if str(row['Match_Num']).isdigit() else (idx + 1)
    date_str = str(row['Date'])
    match_str = str(row['Match'])
    
    m_key = master_matches[idx]['key'] if idx < len(master_matches) else None
    
    p_dict = {}
    for p in player_names:
        rank_val = int(ranks_df.loc[idx, p])
        cum_pts = int(points_df.loc[idx, p])
        
        # If this is the bonus row, map custom prono indicators
        if has_bonus_row and idx == len(points_df) - 1:
            pts_gained = cum_pts - int(points_df.loc[idx - 1, p])
            prono_data = {
                'prono': f"+{pts_gained} Bonus" if pts_gained > 0 else '0 Bonus',
                'pts_gained': str(pts_gained),
                'is_star': False,
                'star_count': 0
            }
        else:
            prono_data = player_pronos.get(p, {}).get(m_key, {'prono': '-', 'pts_gained': '0', 'is_star': False, 'star_count': 0}) if m_key else {'prono': '-', 'pts_gained': '0', 'is_star': False, 'star_count': 0}
        
        p_dict[p] = {
            'rank': rank_val,
            'cum_pts': cum_pts,
            'prono': prono_data['prono'],
            'pts_gained': prono_data['pts_gained'],
            'is_star': prono_data['is_star']
        }
        
        player_match_stars[p].append(prono_data['is_star'])
    
    matches_payload.append({
        'match_num': m_num,
        'date': date_str,
        'match': match_str,
        'players': p_dict
    })

# Compute Insolite / Fun Trophies with Ex-Aequo Support
insoliter_stats = {}

# 1. Longest Star / Exact Match Streak
player_streaks = {}
for p in player_names:
    curr_s = 0
    max_s = 0
    start_m = 0
    best_start = 0
    for idx in range(len(base_points_df)):
        m_key = master_matches[idx]['key'] if idx < len(master_matches) else None
        prono_info = player_pronos.get(p, {}).get(m_key, {}) if m_key else {}
        is_star = prono_info.get('is_star', False)
        if is_star:
            if curr_s == 0:
                start_m = idx + 1
            curr_s += 1
            if curr_s > max_s:
                max_s = curr_s
                best_start = start_m
        else:
            curr_s = 0
    player_streaks[p] = (max_s, best_start)

best_star_streak = max([s[0] for s in player_streaks.values()]) if player_streaks else 0
if best_star_streak > 0:
    tied_players = [p for p in player_names if player_streaks[p][0] == best_star_streak]
    if len(tied_players) == 1:
        p = tied_players[0]
        st_start = player_streaks[p][1]
        st_end = st_start + best_star_streak - 1
        detail_str = f"{best_star_streak} matchs exacts d'affilée (du Match {st_start} au Match {st_end})"
    else:
        details = [f"{p} (M{player_streaks[p][1]}-M{player_streaks[p][1]+best_star_streak-1})" for p in tied_players]
        detail_str = f"{best_star_streak} matchs exacts d'affilée pour " + ", ".join(details)
    
    insoliter_stats['star_streak'] = {
        'players': [{'name': p, 'color': vivid_colors[p]} for p in tied_players],
        'value': f"⭐ {best_star_streak} d'affilée" + (" (Ex aequo)" if len(tied_players) > 1 else ""),
        'detail': detail_str
    }
else:
    insoliter_stats['star_streak'] = {
        'players': [{'name': "Aucun", 'color': "#94A3B8"}],
        'value': "0 match",
        'detail': "Aucune série d'exacts"
    }

# 2. Greatest Comeback (La plus folle remontée: lowest rank -> highest rank later)
player_climbs = {}
for p in player_names:
    ranks = [int(ranks_df.loc[idx, p]) for idx in range(len(base_points_df))]
    best_c = 0
    best_detail = ""
    for i in range(len(ranks)):
        for j in range(i, len(ranks)):
            climb = ranks[i] - ranks[j]
            if climb > best_c:
                best_c = climb
                from_rk, to_rk = ranks[i], ranks[j]
                best_detail = f"du {from_rk}{'er' if from_rk==1 else 'ème'} (M{i+1}) au {to_rk}{'er' if to_rk==1 else 'ème'} (M{j+1})"
    player_climbs[p] = (best_c, best_detail)

best_climb_val = max([c[0] for c in player_climbs.values()]) if player_climbs else 0
if best_climb_val > 0:
    tied_players = [p for p in player_names if player_climbs[p][0] == best_climb_val]
    if len(tied_players) == 1:
        p = tied_players[0]
        detail_str = f"Remontée de +{best_climb_val} places pour {p} ({player_climbs[p][1]})"
    else:
        details = [f"{p} ({player_climbs[p][1]})" for p in tied_players]
        detail_str = f"Remontée de +{best_climb_val} places pour " + " | ".join(details)
        
    insoliter_stats['comeback'] = {
        'players': [{'name': p, 'color': vivid_colors[p]} for p in tied_players],
        'value': f"🚀 +{best_climb_val} places" + (" (Ex aequo)" if len(tied_players) > 1 else ""),
        'detail': detail_str
    }
else:
    insoliter_stats['comeback'] = {
        'players': [{'name': "Aucun", 'color': "#94A3B8"}],
        'value': "0 place",
        'detail': "Aucune remontée observée"
    }

# 3. Greatest Drop (La descente aux enfers: highest rank -> lowest rank later)
player_drops = {}
for p in player_names:
    ranks = [int(ranks_df.loc[idx, p]) for idx in range(len(base_points_df))]
    worst_d = 0
    worst_detail = ""
    for i in range(len(ranks)):
        for j in range(i, len(ranks)):
            drop = ranks[j] - ranks[i]
            if drop > worst_d:
                worst_d = drop
                from_rk, to_rk = ranks[i], ranks[j]
                worst_detail = f"du {from_rk}{'er' if from_rk==1 else 'ème'} (M{i+1}) au {to_rk}{'er' if to_rk==1 else 'ème'} (M{j+1})"
    player_drops[p] = (worst_d, worst_detail)

worst_drop_val = max([d[0] for d in player_drops.values()]) if player_drops else 0
if worst_drop_val > 0:
    tied_players = [p for p in player_names if player_drops[p][0] == worst_drop_val]
    if len(tied_players) == 1:
        p = tied_players[0]
        detail_str = f"Chute de -{worst_drop_val} places pour {p} ({player_drops[p][1]})"
    else:
        details = [f"{p} ({player_drops[p][1]})" for p in tied_players]
        detail_str = f"Chute de -{worst_drop_val} places pour " + " | ".join(details)
        
    insoliter_stats['drop'] = {
        'players': [{'name': p, 'color': vivid_colors[p]} for p in tied_players],
        'value': f"📉 -{worst_drop_val} places" + (" (Ex aequo)" if len(tied_players) > 1 else ""),
        'detail': detail_str
    }
else:
    insoliter_stats['drop'] = {
        'players': [{'name': "Aucun", 'color': "#94A3B8"}],
        'value': "0 place",
        'detail': "Aucune chute observée"
    }

# 4. Rank King (Le roi de la Xème place)
max_king_count = 0
king_candidates = []

for p in player_names:
    ranks = [int(ranks_df.loc[idx, p]) for idx in range(len(base_points_df))]
    for rk in range(1, len(player_names) + 1):
        cnt = ranks.count(rk)
        if cnt > max_king_count:
            max_king_count = cnt

if max_king_count > 0:
    for p in player_names:
        ranks = [int(ranks_df.loc[idx, p]) for idx in range(len(base_points_df))]
        for rk in range(1, len(player_names) + 1):
            if ranks.count(rk) == max_king_count:
                king_candidates.append({'player': p, 'rank': rk, 'count': max_king_count})

    pct = round((max_king_count / len(base_points_df)) * 100, 1)
    if len(king_candidates) == 1:
        item = king_candidates[0]
        p = item['player']
        rk = item['rank']
        val_str = f"👑 Roi de la {rk}{'er' if rk==1 else 'ème'} place"
        detail_str = f"{max_king_count} matchs occupés à cette position ({pct}% du temps)"
        players_payload = [{'name': p, 'color': vivid_colors[p]}]
    else:
        distinct_ranks = list(set([item['rank'] for item in king_candidates]))
        if len(distinct_ranks) == 1:
            rk = distinct_ranks[0]
            val_str = f"👑 Rois de la {rk}{'er' if rk==1 else 'ème'} place (Ex aequo)"
        else:
            val_str = f"👑 Rois de leur Position (Ex aequo)"
        
        details = [f"{item['player']} ({item['rank']}{'er' if item['rank']==1 else 'ème'})" for item in king_candidates]
        detail_str = f"{max_king_count} matchs chacun ({pct}% du temps) : " + ", ".join(details)
        players_payload = [{'name': item['player'], 'color': vivid_colors[item['player']]} for item in king_candidates]

    insoliter_stats['rank_king'] = {
        'players': players_payload,
        'value': val_str,
        'detail': detail_str
    }
else:
    insoliter_stats['rank_king'] = {
        'players': [{'name': "Aucun", 'color': "#94A3B8"}],
        'value': "👑 Roi du Classement",
        'detail': "Aucune position dominante"
    }

# 5. Earliest Abandonment (L'abandon le plus tôt)
player_last_match = {}
for p in player_names:
    played_indices = []
    for idx in range(len(base_points_df)):
        m_key = master_matches[idx]['key'] if idx < len(master_matches) else None
        prono_info = player_pronos.get(p, {}).get(m_key, {}) if m_key else {}
        prono_str = prono_info.get('prono', '-').strip()
        if prono_str and prono_str != '-' and not prono_str.startswith('0 Bonus'):
            played_indices.append(idx)
    
    if played_indices:
        last_m_idx = max(played_indices)
        if last_m_idx < len(base_points_df) - 1:
            player_last_match[p] = last_m_idx + 1

if player_last_match:
    min_abandon_m = min(player_last_match.values())
    abandon_players = [p for p, m in player_last_match.items() if m == min_abandon_m]
    
    if len(abandon_players) == 1:
        p = abandon_players[0]
        val_str = f"🏳️ Abandon M{min_abandon_m}"
        detail_str = f"Dernier prono effectué au Match {min_abandon_m} par {p} (aucun prono ensuite)"
    else:
        val_str = f"🏳️ Abandon M{min_abandon_m} (Ex aequo)"
        detail_str = f"Dernier prono au Match {min_abandon_m} pour " + " & ".join(abandon_players)
        
    insoliter_stats['abandonment'] = {
        'players': [{'name': p, 'color': vivid_colors[p]} for p in abandon_players],
        'value': val_str,
        'detail': detail_str
    }
else:
    insoliter_stats['abandonment'] = {
        'players': [{'name': "Tous les joueurs", 'color': "#00FF87"}],
        'value': "✅ Fidélité 100%",
        'detail': "Tout le monde a joué jusqu'au bout !"
    }

datasets_ranks = []
datasets_points = []

for p in player_names:
    is_stars = player_match_stars[p]
    
    datasets_ranks.append({
        'label': p,
        'data': ranks_df[p].tolist(),
        'borderColor': vivid_colors[p],
        'backgroundColor': vivid_colors[p],
        'borderWidth': 3.5,
        'tension': 0.25,
        'isStars': is_stars
    })
    datasets_points.append({
        'label': p,
        'data': points_df[p].tolist(),
        'borderColor': vivid_colors[p],
        'backgroundColor': vivid_colors[p],
        'borderWidth': 3.5,
        'tension': 0.25,
        'isStars': is_stars
    })
    gif_js_content = ""
    gif_worker_content = ""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
        libs_dir = os.path.join(script_dir, 'libs')
        gif_js_path = os.path.join(libs_dir, 'gif.js')
        gif_worker_path = os.path.join(libs_dir, 'gif.worker.js')

        if not os.path.exists(gif_js_path) or not os.path.exists(gif_worker_path):
            import urllib.request
            os.makedirs(libs_dir, exist_ok=True)
            try:
                urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/gif.js/dist/gif.js', gif_js_path)
                urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/gif.js/dist/gif.worker.js', gif_worker_path)
            except Exception as e:
                print("Warning: Could not download gif.js libraries over network:", e)

        if os.path.exists(gif_js_path):
            with open(gif_js_path, 'r', encoding='utf-8', errors='ignore') as f:
                gif_js_content = f.read()
        if os.path.exists(gif_worker_path):
            with open(gif_worker_path, 'r', encoding='utf-8', errors='ignore') as f:
                gif_worker_content = f.read()
    except Exception as e:
        print("Warning: Error accessing gif.js local files:", e)

html_template = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard MPP — {league_name} ({league_code})</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
    // Inlined GIF.js library
    __GIF_JS_CODE__
    </script>
    <style>
        :root {{
            --bg-color: #0B0F19;
            --card-bg: #151D2A;
            --border-color: #263346;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --accent-blue: #2563EB;
            --accent-purple: #8B5CF6;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            padding: 24px;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1650px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 24px;
        }}

        h1 {{
            font-size: 2.3rem;
            font-weight: 800;
            margin-bottom: 6px;
            background: linear-gradient(135deg, #38BDF8, #C084FC);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        p.subtitle {{
            color: var(--text-muted);
            font-size: 1.05rem;
        }}

        /* Control Panel */
        .control-panel {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 16px 24px;
            margin-bottom: 20px;
        }}

        .btn-group {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}

        button {{
            background-color: #0B0F19;
            color: var(--text-muted);
            border: 1px solid var(--border-color);
            padding: 11px 20px;
            font-size: 0.95rem;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}

        button:hover {{
            background-color: #1A2436;
            color: #FFFFFF;
            border-color: #38BDF8;
        }}

        button.active {{
            background-color: var(--accent-blue);
            color: #FFFFFF;
            border-color: #3B82F6;
            box-shadow: 0 0 16px rgba(37, 99, 235, 0.5);
        }}

        .btn-export {{
            background-color: #059669;
            color: #FFFFFF;
            border-color: #10B981;
            font-weight: 700;
        }}

        .btn-export:hover {{
            background-color: #047857;
            border-color: #34D399;
            box-shadow: 0 0 16px rgba(16, 185, 129, 0.4);
        }}

        .btn-gif {{
            background-color: #D97706;
            color: #FFFFFF;
            border-color: #F59E0B;
            font-weight: 700;
        }}

        .btn-gif:hover {{
            background-color: #B45309;
            border-color: #FBBF24;
            box-shadow: 0 0 16px rgba(245, 158, 11, 0.4);
        }}

        .btn-mp4 {{
            background-color: #0284C7;
            color: #FFFFFF;
            border-color: #0EA5E9;
            font-weight: 700;
        }}

        .btn-mp4:hover {{
            background-color: #0369A1;
            border-color: #38BDF8;
            box-shadow: 0 0 16px rgba(14, 165, 233, 0.4);
        }}

        .btn-export-video {{
            background-color: #7C3AED;
            color: #FFFFFF;
            border-color: #8B5CF6;
            font-weight: 700;
        }}

        .btn-export-video:hover {{
            background-color: #6D28D9;
            border-color: #A78BFA;
            box-shadow: 0 0 16px rgba(139, 92, 246, 0.4);
        }}

        /* Animation Player Control Bar */
        .anim-player-panel {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 15px;
            background-color: #0F172A;
            border: 1px solid #38BDF8;
            border-radius: 14px;
            padding: 14px 22px;
            margin-bottom: 20px;
            box-shadow: 0 0 20px rgba(56, 189, 248, 0.15);
        }}

        .anim-slider {{
            flex: 1;
            min-width: 250px;
            accent-color: #38BDF8;
            cursor: pointer;
            height: 8px;
        }}

        .match-badge {{
            background: rgba(56, 189, 248, 0.15);
            color: #38BDF8;
            border: 1px solid #38BDF8;
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 800;
            font-size: 0.9rem;
            white-space: nowrap;
        }}

        /* Star Legend Card */
        .star-legend-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 16px 24px;
            margin-bottom: 20px;
        }}

        .star-legend-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #FFEA00;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .star-legend-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px 24px;
        }}

        .star-legend-item {{
            font-size: 0.88rem;
            display: flex;
            align-items: center;
            gap: 8px;
            background: #0B0F19;
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid #FFEA00;
            box-shadow: 0 0 8px rgba(255, 234, 0, 0.2);
        }}

        .star-legend-item span.stars {{
            font-family: 'Segoe UI Emoji', sans-serif;
            color: #FFEA00;
            font-weight: 800;
        }}

        .star-legend-item span.desc {{
            color: #E2E8F0;
            font-weight: 600;
        }}

        /* Player Filter Chips */
        .player-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
        }}

        .chip {{
            padding: 7px 16px;
            border-radius: 25px;
            font-size: 0.9rem;
            font-weight: 700;
            cursor: pointer;
            user-select: none;
            transition: all 0.2s ease;
            border: 2px solid transparent;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background-color: #0B0F19;
        }}

        .chip:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}

        .chip.highlighted {{
            transform: scale(1.06);
            border-color: #FFFFFF !important;
            box-shadow: 0 0 16px currentColor;
        }}

        .chip.dimmed {{
            opacity: 0.35;
            filter: grayscale(30%);
        }}

        /* Color Picker Input */
        .color-picker-input {{
            -webkit-appearance: none;
            -moz-appearance: none;
            appearance: none;
            width: 22px;
            height: 22px;
            border: 2px solid #FFFFFF;
            border-radius: 50%;
            cursor: pointer;
            background: none;
            padding: 0;
            overflow: hidden;
            box-shadow: 0 0 4px rgba(0,0,0,0.5);
        }}

        .color-picker-input::-webkit-color-swatch-wrapper {{
            padding: 0;
        }}

        .color-picker-input::-webkit-color-swatch {{
            border: none;
            border-radius: 50%;
        }}

        /* Chart Card */
        .chart-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.5);
            position: relative;
            margin-bottom: 30px;
        }}

        .chart-wrapper {{
            position: relative;
            height: 720px;
            width: 100%;
        }}

        /* Custom HTML Tooltip */
        #custom-tooltip {{
            position: absolute;
            background: rgba(11, 15, 25, 0.96);
            backdrop-filter: blur(10px);
            border: 1px solid #38BDF8;
            border-radius: 14px;
            padding: 16px 20px;
            color: #F8FAFC;
            pointer-events: none;
            transition: all 0.15s ease-out;
            box-shadow: 0 20px 40px rgba(0,0,0,0.7);
            z-index: 1000;
            min-width: 420px;
            opacity: 0;
        }}

        .tt-header {{
            border-bottom: 1px solid #263346;
            padding-bottom: 8px;
            margin-bottom: 12px;
        }}

        .tt-title {{
            font-size: 1.1rem;
            font-weight: 800;
            color: #38BDF8;
        }}

        .tt-sub {{
            font-size: 0.88rem;
            color: #94A3B8;
        }}

        .tt-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }}

        .tt-table th {{
            text-align: left;
            color: #94A3B8;
            font-weight: 600;
            padding-bottom: 6px;
            border-bottom: 1px solid #263346;
        }}

        .tt-table td {{
            padding: 6px 4px;
            vertical-align: middle;
        }}

        .tt-rank {{
            font-weight: 800;
            width: 38px;
            text-align: center;
        }}

        .tt-badge {{
            display: inline-block;
            width: 11px;
            height: 11px;
            border-radius: 50%;
            margin-right: 8px;
        }}

        .tt-player {{
            font-weight: 700;
        }}

        .tt-prono {{
            color: #FFEA00;
            font-family: 'Segoe UI Emoji', sans-serif;
            font-size: 0.95rem;
            font-weight: 700;
        }}

        .tt-pts-gain {{
            color: #34D399;
            font-weight: 800;
            text-align: right;
        }}

        .tt-pts-cum {{
            color: #94A3B8;
            font-size: 0.82rem;
            text-align: right;
        }}

        /* Section Cards & Tables (3 Column Grid) */
        .section-grid-3 {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 40px;
        }}

        @media (max-width: 1400px) {{
            .section-grid-3 {{
                grid-template-columns: 1fr;
            }}
        }}

        .table-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 22px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.5);
        }}

        .table-card-title {{
            font-size: 1.15rem;
            font-weight: 800;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .mpp-table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}

        .mpp-table th {{
            background-color: #0B0F19;
            color: #94A3B8;
            font-weight: 700;
            padding: 11px 12px;
            border-bottom: 2px solid #263346;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
            transition: color 0.15s ease, background-color 0.15s ease;
        }}

        .mpp-table th:hover {{
            color: #38BDF8;
            background-color: #151D2A;
        }}

        /* Insolite Trophies Cards */
        .insolite-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
        }}

        .insolite-card {{
            background-color: #0B0F19;
            border: 1px solid #263346;
            border-radius: 12px;
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            transition: all 0.2s ease;
        }}

        .insolite-card:hover {{
            border-color: #F59E0B;
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(245, 158, 11, 0.12);
        }}

        .insolite-title {{
            font-size: 0.8rem;
            font-weight: 700;
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .insolite-desc {{
            font-size: 0.8rem;
            color: #64748B;
            margin-top: 2px;
        }}

        .mpp-table td {{
            padding: 11px 12px;
            border-bottom: 1px solid #263346;
            vertical-align: middle;
        }}

        .mpp-table tbody tr {{
            transition: all 0.2s ease;
            cursor: pointer;
            position: relative;
        }}

        .mpp-table tbody tr:hover {{
            background-color: rgba(56, 189, 248, 0.08);
        }}

        .badge-rank {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            font-weight: 800;
            font-size: 0.85rem;
        }}

        .badge-rank-1 {{ background: #F59E0B; color: #000000; }}
        .badge-rank-2 {{ background: #94A3B8; color: #000000; }}
        .badge-rank-3 {{ background: #D97706; color: #FFFFFF; }}
        .badge-rank-other {{ background: #263346; color: #94A3B8; }}

        .badge-missed-1 {{ background: #EF4444; color: #FFFFFF; box-shadow: 0 0 10px rgba(239, 68, 68, 0.4); }}
        .badge-missed-2 {{ background: #F97316; color: #FFFFFF; }}
        .badge-missed-3 {{ background: #F59E0B; color: #000000; }}

        .star-pill {{
            background: rgba(255, 234, 0, 0.18);
            color: #FFEA00;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 0.88rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border: 1px solid rgba(255, 234, 0, 0.4);
            box-shadow: 0 0 10px rgba(255, 234, 0, 0.2);
        }}

        .missed-pill {{
            background: rgba(239, 68, 68, 0.18);
            color: #F87171;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 0.85rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }}

        .perfect-pill {{
            background: rgba(16, 185, 129, 0.18);
            color: #34D399;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 0.85rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }}

        .accuracy-pill {{
            background: rgba(56, 189, 248, 0.18);
            color: #38BDF8;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 0.85rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border: 1px solid rgba(56, 189, 248, 0.4);
        }}

        .table-popover {{
            position: absolute;
            display: none;
            background: #0B0F19;
            border: 1px solid #FFEA00;
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 15px 30px rgba(0,0,0,0.9);
            z-index: 100;
            min-width: 260px;
            font-size: 0.88rem;
            pointer-events: none;
        }}

        .table-popover-title {{
            font-weight: 800;
            color: #FFEA00;
            margin-bottom: 8px;
            border-bottom: 1px solid #263346;
            padding-bottom: 6px;
        }}

        .table-popover-item {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            color: #E2E8F0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 {league_name} <span style="font-size: 1.15rem; color: #38BDF8; font-weight: 800; margin-left: 10px;">(Code : {league_code})</span></h1>
            <p class="subtitle">Analyse dynamique du classement, des points et des pronostics match par match — {league_name} (Code : {league_code})</p>
        </header>

        <!-- Control Bar -->
        <div class="control-panel">
            <div class="btn-group">
                <button id="btnRank" class="active" onclick="switchMode('rank')">📉 Classement (1er à 9ème)</button>
                <button id="btnPoints" onclick="switchMode('points')">📈 Points Cumulés</button>
            </div>

            <div class="btn-group" id="bonusToggleContainer" style="display: none;">
                <label style="display: inline-flex; align-items: center; gap: 8px; color: #94A3B8; font-weight: 700; font-size: 0.9rem; cursor: pointer; background: #0B0F19; border: 1px solid var(--border-color); padding: 9px 16px; border-radius: 10px; transition: all 0.2s ease;">
                    <input type="checkbox" id="chkBonus" checked onchange="toggleBonus()" style="width: 16px; height: 16px; accent-color: #38BDF8; cursor: pointer;">
                    <span>Inclure les Bonus Finaux</span>
                </label>
            </div>

            <div class="btn-group">
                <button onclick="resetHighlight()">👁️ Montrer Tous</button>
                <button onclick="dimAll()">🙈 Cacher Tous</button>
                <button class="btn-export" onclick="exportPNG()">📷 Exporter PNG</button>
            </div>

            <div class="btn-group" style="align-items: center; background: #0B0F19; border: 1px solid var(--border-color); padding: 5px 12px; border-radius: 10px; gap: 6px;">
                <span style="font-size: 0.82rem; font-weight: 800; color: #94A3B8;">🎬 Exporter GIF :</span>
                <button id="btnExportGifLow" class="btn-export-video" style="padding: 5px 10px; font-size: 0.78rem;" onclick="exportCustomVideo('low')">⚡ Low (640p)</button>
                <button id="btnExportGifMed" class="btn-export-video" style="padding: 5px 10px; font-size: 0.78rem;" onclick="exportCustomVideo('medium')">⚙️ Medium (960p)</button>
                <button id="btnExportGifHD" class="btn-export-video" style="padding: 5px 10px; font-size: 0.78rem;" onclick="exportCustomVideo('hd')">💎 HD (1400p)</button>
            </div>

            <div class="btn-group">
                <a href="evolution_classement.gif" download target="_blank" style="text-decoration:none;">
                    <button class="btn-gif">🎬 Télécharger GIF Animé</button>
                </a>
                <a href="evolution_classement.mp4" download target="_blank" style="text-decoration:none;">
                    <button class="btn-mp4">🎥 Télécharger Vidéo MP4</button>
                </a>
            </div>
        </div>

        <!-- Animation Player Panel -->
        <div class="anim-player-panel">
            <div class="btn-group">
                <button id="btnPlayAnim" onclick="togglePlayAnimation()">▶️ Lancer l'Animation</button>
                <button onclick="resetAnimation()">⏮️ Recommencer (M1)</button>
            </div>
            
            <div class="btn-group" style="gap:5px;">
                <button id="speed1" class="active" style="padding: 6px 12px; font-size: 0.82rem;" onclick="setAnimSpeed(1)">1x</button>
                <button id="speed2" style="padding: 6px 12px; font-size: 0.82rem;" onclick="setAnimSpeed(2)">2x</button>
                <button id="speed5" style="padding: 6px 12px; font-size: 0.82rem;" onclick="setAnimSpeed(5)">5x</button>
            </div>

            <input type="range" id="matchSlider" class="anim-slider" min="1" max="{num_matches}" value="{num_matches}" oninput="onSliderChange(this.value)">
            
            <div class="match-badge" id="matchBadgeText">
                Match {num_matches} / {num_matches} : {points_df.iloc[-1]['Match'] if num_matches > 0 else ''} ({points_df.iloc[-1]['Date'] if num_matches > 0 else ''})
            </div>
        </div>

        <!-- Star Rating Legend Card -->
        <div class="star-legend-card">
            <div class="star-legend-title">
                ⭐ Légende des Étoiles (Icônes Étoiles 5 Branches Pleines Jaune Fluo identiques au GIF Animé)
            </div>
            <div class="star-legend-grid">
                <div class="star-legend-item">
                    <span class="stars">⭐</span>
                    <span class="desc">Score Exact (+20 pts)</span>
                </div>
                <div class="star-legend-item">
                    <span class="stars">⭐⭐</span>
                    <span class="desc">Score Rare (+30 pts)</span>
                </div>
                <div class="star-legend-item">
                    <span class="stars">⭐⭐⭐</span>
                    <span class="desc">Score Très Rare (+50 pts)</span>
                </div>
                <div class="star-legend-item">
                    <span class="stars">⭐⭐⭐⭐</span>
                    <span class="desc">Score Mega Rare (+70 pts)</span>
                </div>
                <div class="star-legend-item">
                    <span class="stars">⭐⭐⭐⭐⭐</span>
                    <span class="desc">Score Ultra Rare (+100 pts)</span>
                </div>
            </div>
        </div>

        <!-- Player Filter & Color Picker Chips -->
        <div class="control-panel" style="margin-top: -10px; padding: 14px 24px;">
            <div style="width: 100%; display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 0.9rem; font-weight: 700; color: #94A3B8;">
                    🎨 Légende des Joueurs & Personnalisation des Couleurs :
                </span>
                <span style="font-size: 0.8rem; color: #64748B;">
                    (Cliquez sur un nom pour surligner | Utilisez le cercle pour changer la couleur)
                </span>
            </div>
            <div class="player-chips" id="playerChipsContainer"></div>
        </div>

        <!-- Chart Card -->
        <div class="chart-card">
            <div class="chart-wrapper">
                <canvas id="mppCanvas"></canvas>
            </div>
            <!-- Custom HTML Tooltip -->
            <div id="custom-tooltip"></div>
        </div>

        <!-- Leaderboard Section 3-Column Grid -->
        <div class="section-grid-3">
            
            <!-- Leaderboard 1: Matchs & Precision -->
            <div class="table-card">
                <div class="table-card-title">
                    <span>📊 Précision des Pronostics</span>
                </div>
                <table class="mpp-table" id="tablePrecision">
                    <thead>
                        <tr>
                            <th onclick="sortTable('precision', 'rank')">Pos<span id="sort_precision_rank"></span></th>
                            <th onclick="sortTable('precision', 'player')">Participant<span id="sort_precision_player"></span></th>
                            <th onclick="sortTable('precision', 'matches')" style="text-align:center;">Matchs (1N2)<span id="sort_precision_matches"></span></th>
                            <th onclick="sortTable('precision', 'exacts')" style="text-align:center;">Exacts<span id="sort_precision_exacts"></span></th>
                            <th onclick="sortTable('precision', 'pts')" style="text-align:right;">Points<span id="sort_precision_pts"></span></th>
                        </tr>
                    </thead>
                    <tbody id="tbodyPrecision"></tbody>
                </table>
            </div>

            <!-- Leaderboard 2: Stars & Top 3 Rarest Breakdown -->
            <div class="table-card" style="position: relative;">
                <div class="table-card-title" style="color: #FFEA00;">
                    <span>⭐ Étoiles & Rareté (Top 3)</span>
                </div>
                <table class="mpp-table" id="tableStars">
                    <thead>
                        <tr>
                            <th onclick="sortTable('stars', 'rank')">Pos<span id="sort_stars_rank"></span></th>
                            <th onclick="sortTable('stars', 'player')">Participant<span id="sort_stars_player"></span></th>
                            <th onclick="sortTable('stars', 'stars')" style="text-align:center;">Étoiles<span id="sort_stars_stars"></span></th>
                            <th onclick="sortTable('stars', 'exacts')" style="text-align:center;">Exacts<span id="sort_stars_exacts"></span></th>
                            <th onclick="sortTable('stars', 'rarest')" style="text-align:center;">Top 3 Raretés<span id="sort_stars_rarest"></span></th>
                        </tr>
                    </thead>
                    <tbody id="tbodyStars"></tbody>
                </table>
                <div id="tablePopover" class="table-popover"></div>
            </div>

            <!-- Leaderboard 3: Missed Matches + Real Accuracy on Played Matches -->
            <div class="table-card">
                <div class="table-card-title" style="color: #F87171;">
                    <span>💤 Matchs Manqués & Réussite Réelle</span>
                </div>
                <table class="mpp-table" id="tableMissed">
                    <thead>
                        <tr>
                            <th onclick="sortTable('missed', 'rank')">Pos<span id="sort_missed_rank"></span></th>
                            <th onclick="sortTable('missed', 'player')">Participant<span id="sort_missed_player"></span></th>
                            <th onclick="sortTable('missed', 'missed')" style="text-align:center;">Manqués<span id="sort_missed_missed"></span></th>
                            <th onclick="sortTable('missed', 'accuracy')" style="text-align:center;">Réussite (Sur Pariés)<span id="sort_missed_accuracy"></span></th>
                            <th onclick="sortTable('missed', 'played')" style="text-align:right;">Pariés<span id="sort_missed_played"></span></th>
                        </tr>
                    </thead>
                    <tbody id="tbodyMissed"></tbody>
                </table>
            </div>

        </div>

        <!-- Trophées Insolites Section -->
        <div class="table-card" style="margin-top: 24px; border-color: rgba(245, 158, 11, 0.4);">
            <div class="table-card-title" style="color: #F59E0B; font-size: 1.2rem;">
                <span>🤪 Trophées Insolites & Paris Débiles</span>
                <span style="font-size: 0.8rem; color: #64748B; font-weight: 500; margin-left: auto;">(Faits marquants & palmarès de la compétition)</span>
            </div>
            <div class="insolite-grid" id="insoliteGrid"></div>
        </div>

    </div>

    <script>
        // Data Payloads from Python
        const matchesData = {json.dumps(matches_payload, ensure_ascii=False)};
        const datasetsRanks = {json.dumps(datasets_ranks, ensure_ascii=False)};
        const datasetsPoints = {json.dumps(datasets_points, ensure_ascii=False)};
        let playerColors = {json.dumps(vivid_colors, ensure_ascii=False)};
        const playerNames = {json.dumps(player_names, ensure_ascii=False)};
        const playerStats = {json.dumps(player_stats, ensure_ascii=False)};
        const insoliterStats = {json.dumps(insoliter_stats, ensure_ascii=False)};

        let currentMode = 'rank';
        let activePlayers = []; // Support multi-selection
        let myChart = null;

        let showBonus = true;
        const hasBonusRow = matchesData.length > 0 && matchesData[matchesData.length - 1].date === 'Bonus';

        // Afficher le conteneur du bouton de toggle des bonus s'il y a des données de bonus
        if (hasBonusRow) {{
            document.getElementById('bonusToggleContainer').style.display = 'inline-flex';
        }}

        const getPointsAtStep = (player, step) => {{
            const ds = datasetsPoints.find(d => d.label === player);
            return ds ? ds.data[step - 1] : 0;
        }};

        let sortState = {{
            precision: {{ col: 'pts', dir: 'desc' }},
            stars: {{ col: 'stars', dir: 'desc' }},
            missed: {{ col: 'missed', dir: 'desc' }}
        }};

        function sortTable(tableKey, colKey) {{
            const st = sortState[tableKey];
            if (st.col === colKey) {{
                st.dir = st.dir === 'desc' ? 'asc' : 'desc';
            }} else {{
                st.col = colKey;
                st.dir = (colKey === 'rank' || colKey === 'player') ? 'asc' : 'desc';
            }}
            renderTables();
        }}

        function updateSortHeaderArrows() {{
            ['precision', 'stars', 'missed'].forEach(tKey => {{
                const activeCol = sortState[tKey].col;
                const activeDir = sortState[tKey].dir;
                
                ['rank', 'player', 'matches', 'exacts', 'pts', 'stars', 'rarest', 'missed', 'accuracy', 'played'].forEach(cKey => {{
                    const el = document.getElementById(`sort_${{tKey}}_${{cKey}}`);
                    if (el) {{
                        if (cKey === activeCol) {{
                            el.innerText = activeDir === 'asc' ? ' ▲' : ' ▼';
                            el.style.color = '#38BDF8';
                        }} else {{
                            el.innerText = ' ↕';
                            el.style.color = '#475569';
                        }}
                    }}
                }});
            }});
        }}

        function renderInsoliteGrid() {{
            const grid = document.getElementById('insoliteGrid');
            if (!grid) return;
            grid.innerHTML = '';

            const trophies = [
                {{ key: 'star_streak', title: "Série d'Exacts la plus Folle", icon: "⭐" }},
                {{ key: 'comeback', title: "La plus Folle Remontée", icon: "🚀" }},
                {{ key: 'drop', title: "La Descente aux Enfers", icon: "📉" }},
                {{ key: 'rank_king', title: "Le Roi de la Position", icon: "👑" }},
                {{ key: 'abandonment', title: "L'Abandon le plus Tôt", icon: "🏳️" }}
            ];

            trophies.forEach(t => {{
                const data = insoliterStats[t.key];
                if (!data) return;

                let playersList = data.players;
                if (!playersList && data.player) {{
                    const c = playerColors[data.player] || '#38BDF8';
                    playersList = [{{ name: data.player, color: c }}];
                }}

                const mainColor = (playersList && playersList.length > 0) ? (playersList[0].color || playerColors[playersList[0].name] || '#38BDF8') : '#38BDF8';

                let playersHtml = '';
                if (playersList && playersList.length > 0) {{
                    playersHtml = playersList.map(p => {{
                        const c = p.color || playerColors[p.name] || '#38BDF8';
                        return `<span style="color:${{c}}; font-weight:800; display:inline-flex; align-items:center;"><span class="tt-badge" style="background-color:${{c}}"></span>${{p.name}}</span>`;
                    }}).join('<span style="color:#64748B; margin:0 4px;">&</span>');
                }}

                const card = document.createElement('div');
                card.className = 'insolite-card';
                card.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="insolite-title">${{t.icon}} ${{t.title}}</span>
                        <span style="font-size:1.05rem; font-weight:800; color:${{mainColor}};">${{data.value}}</span>
                    </div>
                    <div style="font-size:1.1rem; font-weight:800; margin-top:4px; display:flex; flex-wrap:wrap; align-items:center; gap:4px;">
                        ${{playersHtml}}
                    </div>
                    <div class="insolite-desc">${{data.detail}}</div>
                `;
                grid.appendChild(card);
            }});
        }}

        function toggleBonus() {{
            showBonus = document.getElementById('chkBonus').checked;
            
            const slider = document.getElementById('matchSlider');
            const maxSteps = (hasBonusRow && !showBonus) ? matchesData.length - 1 : matchesData.length;
            slider.max = maxSteps;
            
            if (showBonus && hasBonusRow) {{
                currentStep = matchesData.length;
            }} else if (!showBonus && hasBonusRow) {{
                currentStep = matchesData.length - 1;
            }} else if (currentStep > maxSteps) {{
                currentStep = maxSteps;
            }}
            
            renderStep(currentStep);
        }}

        function createSolidStarCanvas(fillColor, strokeColor, outerRadius, innerRadius) {{
            const margin = 4;
            const size = Math.ceil((outerRadius + margin) * 2);
            const canvas = document.createElement('canvas');
            canvas.width = size;
            canvas.height = size;
            const ctx = canvas.getContext('2d');
            const cx = size / 2;
            const cy = size / 2;
            
            ctx.beginPath();
            for (let i = 0; i < 5; i++) {{
                let alpha = (Math.PI / 2) + (i * 2 * Math.PI / 5);
                let x = cx + Math.cos(alpha) * outerRadius;
                let y = cy - Math.sin(alpha) * outerRadius;
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                
                alpha += Math.PI / 5;
                x = cx + Math.cos(alpha) * innerRadius;
                y = cy - Math.sin(alpha) * innerRadius;
                ctx.lineTo(x, y);
            }}
            ctx.closePath();
            
            ctx.fillStyle = fillColor;
            ctx.fill();
            
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = 2;
            ctx.stroke();
            return canvas;
        }}

        const solidStarYellowNormal = createSolidStarCanvas('#FFEA00', '#FFFFFF', 10, 4.5);
        const solidStarYellowHover = createSolidStarCanvas('#FFEA00', '#FFFFFF', 15, 7);

        function attachStarPointStyles(datasets) {{
            datasets.forEach(ds => {{
                const isStars = ds.isStars || [];
                ds.pointStyle = isStars.map(s => s ? solidStarYellowNormal : 'circle');
                ds.pointHoverStyle = isStars.map(s => s ? solidStarYellowHover : 'circle');
                ds.pointRadius = isStars.map(s => s ? 12 : 3.5);
                ds.pointHoverRadius = isStars.map(s => s ? 17 : 8);
                ds.pointBackgroundColor = isStars.map(s => s ? '#FFEA00' : ds.borderColor);
                ds.pointBorderColor = isStars.map(s => s ? '#FFFFFF' : ds.borderColor);
                ds.pointBorderWidth = isStars.map(s => s ? 2 : 1);
            }});
        }}

        attachStarPointStyles(datasetsRanks);
        attachStarPointStyles(datasetsPoints);

        // Animation Player state
        let isPlaying = false;
        let animTimer = null;
        let currentStep = {num_matches};
        let animSpeedMultiplier = 1;

        function renderChips() {{
            const container = document.getElementById('playerChipsContainer');
            container.innerHTML = '';
            playerNames.forEach(p => {{
                const chip = document.createElement('div');
                chip.className = 'chip';
                chip.style.borderColor = playerColors[p];
                chip.style.color = playerColors[p];
                chip.id = `chip-${{p}}`;

                const picker = document.createElement('input');
                picker.type = 'color';
                picker.value = playerColors[p];
                picker.className = 'color-picker-input';
                picker.title = `Changer la couleur de ${{p}}`;
                picker.onclick = (e) => e.stopPropagation();
                picker.onchange = (e) => updatePlayerColor(p, e.target.value);

                const label = document.createElement('span');
                label.innerText = p;
                label.onclick = () => highlightPlayer(p);

                chip.appendChild(picker);
                chip.appendChild(label);
                container.appendChild(chip);
            }});
        }}

        function updatePlayerColor(player, newColor) {{
            playerColors[player] = newColor;

            datasetsRanks.forEach(ds => {{
                if (ds.label === player) {{
                    ds.borderColor = newColor;
                    ds.backgroundColor = newColor;
                }}
            }});
            datasetsPoints.forEach(ds => {{
                if (ds.label === player) {{
                    ds.borderColor = newColor;
                    ds.backgroundColor = newColor;
                }}
            }});

            attachStarPointStyles(datasetsRanks);
            attachStarPointStyles(datasetsPoints);

            renderChips();
            applyHighlightStyles();
            renderTables();
            myChart.update();
        }}

        function makeStarsStr(count) {{
            return '⭐'.repeat(count);
        }}

        function renderTables() {{
            const totalActualMatches = hasBonusRow ? matchesData.length - 1 : matchesData.length;

            // Table 1: Precision
            const tbodyPrec = document.getElementById('tbodyPrecision');
            tbodyPrec.innerHTML = '';
            
            let sortedByPrec = [...playerNames].sort((a, b) => {{
                const s = sortState.precision;
                let valA, valB;
                if (s.col === 'rank' || s.col === 'pts') {{
                    valA = getPointsAtStep(a, currentStep);
                    valB = getPointsAtStep(b, currentStep);
                    return s.dir === 'asc' ? valA - valB : valB - valA;
                }} else if (s.col === 'player') {{
                    return s.dir === 'asc' ? a.localeCompare(b) : b.localeCompare(a);
                }} else if (s.col === 'matches') {{
                    valA = playerStats[a].pts_matches;
                    valB = playerStats[b].pts_matches;
                    return s.dir === 'asc' ? valA - valB : valB - valA;
                }} else if (s.col === 'exacts') {{
                    valA = playerStats[a].exact_matches;
                    valB = playerStats[b].exact_matches;
                    return s.dir === 'asc' ? valA - valB : valB - valA;
                }}
                return 0;
            }});
            
            sortedByPrec.forEach((p, idx) => {{
                const st = playerStats[p];
                const c = playerColors[p];
                const rankBadgeClass = idx === 0 ? 'badge-rank-1' : idx === 1 ? 'badge-rank-2' : idx === 2 ? 'badge-rank-3' : 'badge-rank-other';
                
                const currentPts = getPointsAtStep(p, currentStep);
                const divisor = (hasBonusRow && !showBonus && currentStep === matchesData.length) ? matchesData.length - 1 : currentStep;
                const pct = divisor > 0 ? ((st.pts_matches / divisor) * 100).toFixed(1) : "0.0";

                const tr = document.createElement('tr');
                tr.onclick = () => highlightPlayer(p);
                tr.innerHTML = `
                    <td><span class="badge-rank ${{rankBadgeClass}}">${{idx + 1}}</span></td>
                    <td style="font-weight: 700; color: ${{c}}">
                        <span class="tt-badge" style="background-color: ${{c}}"></span>${{p}}
                    </td>
                    <td style="text-align:center; font-weight: 700;">
                        ${{st.pts_matches}} <span style="color: #64748B; font-size: 0.78rem;">(${{pct}}%)</span>
                    </td>
                    <td style="text-align:center; font-weight: 800; color: #FFEA00;">
                        ${{st.exact_matches}}
                    </td>
                    <td style="text-align:right; font-weight: 800; color: #38BDF8;">
                        ${{currentPts}} pts
                    </td>
                `;
                tbodyPrec.appendChild(tr);
            }});

            // Table 2: Stars
            const tbodyStars = document.getElementById('tbodyStars');
            tbodyStars.innerHTML = '';

            let sortedByStars = [...playerNames].sort((a, b) => {{
                const s = sortState.stars;
                let valA, valB;
                if (s.col === 'stars') {{
                    valA = playerStats[a].total_stars;
                    valB = playerStats[b].total_stars;
                }} else if (s.col === 'exacts') {{
                    valA = playerStats[a].exact_matches;
                    valB = playerStats[b].exact_matches;
                }} else if (s.col === 'player') {{
                    return s.dir === 'asc' ? a.localeCompare(b) : b.localeCompare(a);
                }} else if (s.col === 'rank') {{
                    valA = getPointsAtStep(a, currentStep);
                    valB = getPointsAtStep(b, currentStep);
                    return s.dir === 'asc' ? valB - valA : valA - valB;
                }} else if (s.col === 'rarest') {{
                    const sbA = playerStats[a].stars_breakdown;
                    const sbB = playerStats[b].stars_breakdown;
                    valA = sbA[5]*1000 + sbA[4]*100 + sbA[3]*10 + sbA[2];
                    valB = sbB[5]*1000 + sbB[4]*100 + sbB[3]*10 + sbB[2];
                }}
                return s.dir === 'asc' ? valA - valB : valB - valA;
            }});

            sortedByStars.forEach((p, idx) => {{
                const st = playerStats[p];
                const c = playerColors[p];
                const rankBadgeClass = idx === 0 ? 'badge-rank-1' : idx === 1 ? 'badge-rank-2' : idx === 2 ? 'badge-rank-3' : 'badge-rank-other';
                const sb = st.stars_breakdown;

                const top3 = [];
                [5, 4, 3, 2, 1].forEach(lvl => {{
                    if (sb[lvl] > 0 && top3.length < 3) {{
                        top3.push({{ lvl: lvl, count: sb[lvl] }});
                    }}
                }});

                const top3Html = top3.map(item => `<span>${{item.count}}×${{makeStarsStr(item.lvl)}}</span>`).join(' <span style="color:#475569;">|</span> ');

                const tr = document.createElement('tr');
                tr.onclick = () => highlightPlayer(p);
                
                tr.onmouseenter = (e) => showStarPopover(e, p);
                tr.onmousemove = (e) => positionStarPopover(e);
                tr.onmouseleave = hideStarPopover;

                tr.innerHTML = `
                    <td><span class="badge-rank ${{rankBadgeClass}}">${{idx + 1}}</span></td>
                    <td style="font-weight: 700; color: ${{c}}">
                        <span class="tt-badge" style="background-color: ${{c}}"></span>${{p}}
                    </td>
                    <td style="text-align:center;">
                        <span class="star-pill">⭐ ${{st.total_stars}}</span>
                    </td>
                    <td style="text-align:center; font-weight: 700; color: #E2E8F0;">
                        ${{st.exact_matches}}
                    </td>
                    <td style="text-align:center; font-size: 0.82rem; font-weight: 700; color: #FFEA00;">
                        ${{top3Html || '<span style="color:#64748B;">-</span>'}}
                    </td>
                `;
                tbodyStars.appendChild(tr);
            }});

            // Table 3: Missed Matches & REAL Accuracy on Played Matches
            const tbodyMissed = document.getElementById('tbodyMissed');
            tbodyMissed.innerHTML = '';

            let sortedByMissed = [...playerNames].sort((a, b) => {{
                const s = sortState.missed;
                let valA, valB;
                if (s.col === 'missed') {{
                    const diff = s.dir === 'asc' 
                        ? playerStats[a].missed_matches - playerStats[b].missed_matches 
                        : playerStats[b].missed_matches - playerStats[a].missed_matches;
                    if (diff !== 0) return diff;
                    // Tie-breaker: lower accuracy percentage first!
                    return playerStats[a].real_accuracy - playerStats[b].real_accuracy;
                }} else if (s.col === 'accuracy') {{
                    valA = playerStats[a].real_accuracy;
                    valB = playerStats[b].real_accuracy;
                }} else if (s.col === 'played') {{
                    valA = playerStats[a].played_matches;
                    valB = playerStats[b].played_matches;
                }} else if (s.col === 'player') {{
                    return s.dir === 'asc' ? a.localeCompare(b) : b.localeCompare(a);
                }} else if (s.col === 'rank') {{
                    valA = getPointsAtStep(a, currentStep);
                    valB = getPointsAtStep(b, currentStep);
                    return s.dir === 'asc' ? valB - valA : valA - valB;
                }}
                return s.dir === 'asc' ? valA - valB : valB - valA;
            }});

            sortedByMissed.forEach((p, idx) => {{
                const st = playerStats[p];
                const c = playerColors[p];
                const rankBadgeClass = idx === 0 ? 'badge-missed-1' : idx === 1 ? 'badge-missed-2' : idx === 2 ? 'badge-missed-3' : 'badge-rank-other';
                const pillClass = st.missed_matches > 0 ? 'missed-pill' : 'perfect-pill';
                const pillText = st.missed_matches > 0 ? `⚠️ ${{st.missed_matches}} m.` : `✅ 0 m.`;

                const tr = document.createElement('tr');
                tr.onclick = () => highlightPlayer(p);
                tr.innerHTML = `
                    <td><span class="badge-rank ${{rankBadgeClass}}">${{idx + 1}}</span></td>
                    <td style="font-weight: 700; color: ${{c}}">
                        <span class="tt-badge" style="background-color: ${{c}}"></span>${{p}}
                    </td>
                    <td style="text-align:center;">
                        <span class="${{pillClass}}">${{pillText}}</span>
                    </td>
                    <td style="text-align:center;">
                        <span class="accuracy-pill">🎯 ${{st.real_accuracy}}%</span>
                        <div style="font-size: 0.72rem; color: #64748B; margin-top: 2px;">(${{st.pts_matches}} / ${{st.played_matches}} pariés)</div>
                    </td>
                    <td style="text-align:right; font-weight: 700; color: #E2E8F0;">
                        ${{st.played_matches}} <span style="color: #64748B; font-size: 0.78rem;">/ ${{totalActualMatches}}</span>
                    </td>
                `;
                tbodyMissed.appendChild(tr);
            }});

            updateSortHeaderArrows();
        }}

        function showStarPopover(e, player) {{
            const popover = document.getElementById('tablePopover');
            const st = playerStats[player];
            const sb = st.stars_breakdown;
            const c = playerColors[player];

            popover.innerHTML = `
                <div class="table-popover-title" style="color: ${{c}};">
                    ⭐ Détail Rareté : ${{player}}
                </div>
                <div class="table-popover-item">
                    <span>⭐⭐⭐⭐⭐ Ultra Rare (+100pts)</span>
                    <strong style="color: #FFEA00;">${{sb[5]}} fois</strong>
                </div>
                <div class="table-popover-item">
                    <span>⭐⭐⭐⭐ Mega Rare (+70pts)</span>
                    <strong style="color: #FFEA00;">${{sb[4]}} fois</strong>
                </div>
                <div class="table-popover-item">
                    <span>⭐⭐⭐ Très Rare (+50pts)</span>
                    <strong style="color: #FFEA00;">${{sb[3]}} fois</strong>
                </div>
                <div class="table-popover-item">
                    <span>⭐⭐ Rare (+30pts)</span>
                    <strong style="color: #FFEA00;">${{sb[2]}} fois</strong>
                </div>
                <div class="table-popover-item">
                    <span>⭐ Score Exact (+20pts)</span>
                    <strong style="color: #FFEA00;">${{sb[1]}} fois</strong>
                </div>
            `;
            popover.style.display = 'block';
            positionStarPopover(e);
        }}

        function positionStarPopover(e) {{
            const popover = document.getElementById('tablePopover');
            const cardRect = e.currentTarget.closest('.table-card').getBoundingClientRect();
            let left = e.clientX - cardRect.left + 15;
            let top = e.clientY - cardRect.top - 45;
            
            popover.style.left = left + 'px';
            popover.style.top = top + 'px';
        }}

        function hideStarPopover() {{
            document.getElementById('tablePopover').style.display = 'none';
        }}

        function initChart() {{
            renderChips();
            const ctx = document.getElementById('mppCanvas').getContext('2d');
            
            myChart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: matchesData.map(m => m.date === 'Bonus' ? 'Bonus' : `M${{m.match_num}}`),
                    datasets: JSON.parse(JSON.stringify(datasetsRanks))
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: {{ duration: 250 }},
                    layout: {{
                        padding: {{
                            top: 25,
                            bottom: 25,
                            left: 15,
                            right: 35
                        }}
                    }},
                    interaction: {{
                        mode: 'index',
                        intersect: false
                    }},
                    plugins: {{
                        legend: {{
                            display: true,
                            position: 'top',
                            align: 'center',
                            labels: {{
                                color: '#F8FAFC',
                                font: {{ size: 13, weight: 'bold', family: 'Segoe UI' }},
                                usePointStyle: true,
                                pointStyle: 'circle',
                                padding: 22,
                                boxWidth: 10,
                                boxHeight: 10,
                                generateLabels: function(chart) {{
                                    const datasets = chart.data.datasets;
                                    return datasets.map((ds, i) => {{
                                        const pName = ds.label;
                                        const isHighlighted = activePlayers.length === 0 || activePlayers.includes(pName);
                                        const colorStr = isHighlighted ? playerColors[pName] : playerColors[pName] + '22';
                                        return {{
                                            text: pName,
                                            fillStyle: colorStr,
                                            strokeStyle: colorStr,
                                            lineWidth: 2,
                                            hidden: chart.isDatasetVisible(i) ? false : true,
                                            index: i,
                                            pointStyle: 'circle',
                                            fontColor: '#FFFFFF',
                                            color: '#FFFFFF'
                                        }};
                                    }});
                                }}
                            }},
                            onClick: function(e, legendItem) {{
                                highlightPlayer(legendItem.text);
                            }}
                        }},
                        tooltip: {{
                            enabled: false,
                            external: customTooltipHandler
                        }}
                    }},
                    scales: {{
                        x: {{
                            ticks: {{
                                color: '#94A3B8',
                                font: {{ size: 11, weight: '700' }},
                                maxRotation: 0,
                                callback: function(val, idx) {{
                                    return (idx + 1) % 5 === 0 || idx === 0 || idx === matchesData.length - 1 ? `M${{idx + 1}}` : '';
                                }}
                            }},
                            grid: {{ color: '#263346', strokeDash: [3, 3] }}
                        }},
                        y: {{
                            reverse: true,
                            min: 0.2,
                            max: playerNames.length + 0.8,
                            suggestedMin: 0.2,
                            suggestedMax: playerNames.length + 0.8,
                            ticks: {{
                                color: '#94A3B8',
                                stepSize: 1,
                                font: {{ size: 13, weight: '800' }},
                                callback: function(value) {{
                                    if (value >= 1 && value <= playerNames.length && Number.isInteger(value)) {{
                                        return value + (value === 1 ? 'er' : 'ème');
                                    }}
                                    return '';
                                }}
                            }},
                            grid: {{ color: '#263346' }}
                        }}
                    }}
                }}
            }});

            attachStarPointStyles(myChart.data.datasets);
            renderInsoliteGrid();
            
            // Initialiser les limites et lancer le rendu initial
            toggleBonus();
        }}

        function renderStep(step) {{
            currentStep = step;
            document.getElementById('matchSlider').value = step;

            const mData = matchesData[step - 1];
            const maxStepsDisplay = (hasBonusRow && !showBonus) ? matchesData.length - 1 : matchesData.length;
            const matchLabel = mData.date === 'Bonus' ? 'Bonus Finaux' : `Match ${{mData.match_num}} / ${{maxStepsDisplay}}`;
            document.getElementById('matchBadgeText').innerText = `${{matchLabel}} : ${{mData.match}} (${{mData.date}})`;

            const labelsSlice = matchesData.slice(0, step).map(m => m.date === 'Bonus' ? 'Bonus' : `M${{m.match_num}}`);
            myChart.data.labels = labelsSlice;

            const baseDatasets = currentMode === 'rank' ? datasetsRanks : datasetsPoints;

            myChart.data.datasets.forEach((ds, idx) => {{
                const fullDs = baseDatasets[idx];
                ds.data = fullDs.data.slice(0, step);
                ds.pointStyle = fullDs.pointStyle.slice(0, step);
                ds.pointHoverStyle = fullDs.pointHoverStyle ? fullDs.pointHoverStyle.slice(0, step) : fullDs.pointStyle.slice(0, step);
                ds.pointRadius = fullDs.pointRadius.slice(0, step);
                ds.pointHoverRadius = fullDs.pointHoverRadius.slice(0, step);
                ds.pointBackgroundColor = fullDs.pointBackgroundColor.slice(0, step);
                ds.pointBorderColor = fullDs.pointBorderColor.slice(0, step);
                ds.pointBorderWidth = fullDs.pointBorderWidth.slice(0, step);
            }});

            applyHighlightStyles();
            renderTables();
            myChart.update('none');
        }}

        function togglePlayAnimation() {{
            if (isPlaying) {{
                pauseAnimation();
            }} else {{
                startAnimation();
            }}
        }}

        function startAnimation() {{
            if (currentStep >= matchesData.length) currentStep = 1;
            isPlaying = true;
            document.getElementById('btnPlayAnim').innerText = "⏸️ Pause";
            
            const intervalMs = Math.max(30, 200 / animSpeedMultiplier);
            animTimer = setInterval(() => {{
                if (currentStep < matchesData.length) {{
                    currentStep++;
                    renderStep(currentStep);
                }} else {{
                    pauseAnimation();
                }}
            }}, intervalMs);
        }}

        function pauseAnimation() {{
            isPlaying = false;
            if (animTimer) clearInterval(animTimer);
            document.getElementById('btnPlayAnim').innerText = "▶️ Lancer la Simulation";
        }}

        function resetAnimation() {{
            pauseAnimation();
            renderStep(1);
        }}

        function setAnimSpeed(speed) {{
            animSpeedMultiplier = speed;
            document.getElementById('speed1').classList.toggle('active', speed === 1);
            document.getElementById('speed2').classList.toggle('active', speed === 2);
            document.getElementById('speed5').classList.toggle('active', speed === 5);
            if (isPlaying) {{
                pauseAnimation();
                startAnimation();
            }}
        }}

        function onSliderChange(val) {{
            pauseAnimation();
            renderStep(parseInt(val));
        }}

        function switchMode(mode) {{
            currentMode = mode;
            document.getElementById('btnRank').classList.toggle('active', mode === 'rank');
            document.getElementById('btnPoints').classList.toggle('active', mode === 'points');

            if (mode === 'rank') {{
                myChart.options.scales.y.reverse = true;
                myChart.options.scales.y.min = 0.2;
                myChart.options.scales.y.max = playerNames.length + 0.8;
                myChart.options.scales.y.ticks.stepSize = 1;
                myChart.options.scales.y.ticks.callback = function(val) {{
                    if (val >= 1 && val <= playerNames.length && Number.isInteger(val)) {{
                        return val + (val === 1 ? 'er' : 'ème');
                    }}
                    return '';
                }};
            }} else {{
                myChart.options.scales.y.reverse = false;
                delete myChart.options.scales.y.min;
                delete myChart.options.scales.y.max;
                myChart.options.scales.y.ticks.stepSize = 500;
                myChart.options.scales.y.ticks.callback = function(val) {{
                    return val + ' pts';
                }};
            }}

            renderStep(currentStep);
        }}

        function highlightPlayer(player) {{
            if (activePlayers.includes('__NONE__')) {{
                activePlayers = [];
            }}
            const idx = activePlayers.indexOf(player);
            if (idx > -1) {{
                activePlayers.splice(idx, 1);
            }} else {{
                activePlayers.push(player);
            }}
            applyHighlightStyles();
            myChart.update();
        }}

        function resetHighlight() {{
            activePlayers = [];
            applyHighlightStyles();
            myChart.update();
        }}

        function dimAll() {{
            activePlayers = ['__NONE__'];
            applyHighlightStyles();
            myChart.update();
        }}

        function applyHighlightStyles() {{
            const hasSelection = activePlayers.length > 0 && !activePlayers.includes('__NONE__');
            
            myChart.data.datasets.forEach(ds => {{
                const pName = ds.label;
                const chip = document.getElementById(`chip-${{pName}}`);

                if (activePlayers.includes('__NONE__')) {{
                    ds.borderColor = playerColors[pName] + '22';
                    ds.borderWidth = 1.5;
                    ds.hidden = false;
                    if (chip) chip.className = 'chip dimmed';
                }} else if (!hasSelection) {{
                    ds.borderColor = playerColors[pName];
                    ds.borderWidth = 3.5;
                    ds.hidden = false;
                    if (chip) chip.className = 'chip';
                }} else if (activePlayers.includes(pName)) {{
                    ds.borderColor = playerColors[pName];
                    ds.borderWidth = 5.5;
                    ds.hidden = false;
                    if (chip) chip.className = 'chip highlighted';
                }} else {{
                    ds.borderColor = playerColors[pName] + '22';
                    ds.borderWidth = 1.5;
                    ds.hidden = true; // zoom in on selection by hiding others
                    if (chip) chip.className = 'chip dimmed';
                }}
            }});

            // Adjust Scales dynamic zoom / centering
            if (hasSelection) {{
                let minVal = Infinity;
                let maxVal = -Infinity;
                
                // Get selected datasets
                const selectedDatasets = myChart.data.datasets.filter(ds => activePlayers.includes(ds.label));
                
                selectedDatasets.forEach(ds => {{
                    ds.data.forEach(val => {{
                        if (val !== undefined && val !== null) {{
                            if (val < minVal) minVal = val;
                            if (val > maxVal) maxVal = val;
                        }}
                    }});
                }});
                
                if (minVal !== Infinity && maxVal !== -Infinity) {{
                    if (currentMode === 'rank') {{
                        myChart.options.scales.y.min = Math.max(0.5, minVal - 0.5);
                        myChart.options.scales.y.max = Math.min(playerNames.length + 0.5, maxVal + 0.5);
                    }} else {{
                        const range = maxVal - minVal;
                        const pad = Math.max(100, range * 0.08); // 8% padding
                        myChart.options.scales.y.min = Math.max(0, Math.floor(minVal - pad));
                        myChart.options.scales.y.max = Math.ceil(maxVal + pad);
                    }}
                }}
            }} else {{
                // Restore defaults
                if (currentMode === 'rank') {{
                    myChart.options.scales.y.reverse = true;
                    myChart.options.scales.y.min = 0.2;
                    myChart.options.scales.y.max = playerNames.length + 0.8;
                    myChart.options.scales.y.ticks.stepSize = 1;
                }} else {{
                    myChart.options.scales.y.reverse = false;
                    delete myChart.options.scales.y.min;
                    delete myChart.options.scales.y.max;
                    myChart.options.scales.y.ticks.stepSize = 500;
                }}
            }}
        }}

        let isRecording = false;
        async function exportCustomVideo(level = 'medium') {{
            if (isRecording) return;
            
            const qualityConfigs = {{
                low: {{
                    targetWidth: 640,
                    sampleStep: 3,
                    quality: 15,
                    frameDelay: 350,
                    label: '⚡ Low (640p)',
                    btnId: 'btnExportGifLow'
                }},
                medium: {{
                    targetWidth: 960,
                    sampleStep: 2,
                    quality: 6,
                    frameDelay: 250,
                    label: '⚙️ Medium (960p)',
                    btnId: 'btnExportGifMed'
                }},
                hd: {{
                    targetWidth: 1400,
                    sampleStep: 1,
                    quality: 2,
                    frameDelay: 180,
                    label: '💎 HD (1400p)',
                    btnId: 'btnExportGifHD'
                }}
            }};

            const config = qualityConfigs[level] || qualityConfigs.medium;
            const btn = document.getElementById(config.btnId) || document.getElementById('btnExportGifMed');
            const originalBtnText = btn.innerText;
            const canvas = document.getElementById('mppCanvas');
            
            // Dynamically load gif.js only when needed
            if (typeof GIF === 'undefined') {{
                btn.innerText = "⏳ Chargement...";
                try {{
                    await new Promise((resolve, reject) => {{
                        const s = document.createElement('script');
                        s.src = 'https://cdn.jsdelivr.net/npm/gif.js/dist/gif.js';
                        s.onload = resolve;
                        s.onerror = reject;
                        document.head.appendChild(s);
                    }});
                }} catch(e) {{
                    alert("Impossible de charger la bibliothèque GIF : vérifiez votre connexion Internet.");
                    btn.innerText = originalBtnText;
                    return;
                }}
                if (typeof GIF === 'undefined') {{
                    btn.innerText = originalBtnText;
                    return;
                }}
            }}
            
            isRecording = true;
            pauseAnimation();
            renderStep(1);
            
            const targetWidth = config.targetWidth;
            const targetHeight = Math.round((canvas.height / canvas.width) * targetWidth);
            
            // Dedicated offscreen canvas
            const offscreen = document.createElement('canvas');
            offscreen.width = targetWidth;
            offscreen.height = targetHeight;
            const offCtx = offscreen.getContext('2d');
            
            const totalSteps = matchesData.length;
            const sampleStep = config.sampleStep;
            const frameDelay = config.frameDelay;
            
            // Create a Blob URL from the inlined worker code to bypass CORS/file:// restrictions
            let workerURL = 'https://cdn.jsdelivr.net/npm/gif.js/dist/gif.worker.js';
            try {{
                const workerCode = __GIF_WORKER_CODE__;
                if (workerCode && workerCode.length > 10) {{
                    const blob = new Blob([workerCode], {{ type: 'application/javascript' }});
                    workerURL = URL.createObjectURL(blob);
                }}
            }} catch(e) {{
                console.warn("Failed to create Blob URL for GIF worker, falling back to CDN:", e);
            }}

            // Create gif.js encoder
            const gif = new GIF({{
                workers: 4,
                quality: config.quality,
                width: targetWidth,
                height: targetHeight,
                workerScript: workerURL,
                background: '#0B0F19',
                repeat: 0
            }});
            
            const overlay = document.getElementById('gifProgressOverlay');
            const progressBar = document.getElementById('gifProgressInner');
            const progressText = document.getElementById('gifProgressText');
            
            gif.on('progress', function(p) {{
                const pct = Math.round(p * 100);
                progressBar.style.width = pct + '%';
                progressText.innerText = `Encodage GIF (${{config.label}}) : ${{pct}}%`;
            }});
            
            gif.on('finished', function(blob) {{
                overlay.style.display = 'none';
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const modeName = currentMode === 'rank' ? 'classement' : 'points';
                const filterDesc = activePlayers.length > 0 && !activePlayers.includes('__NONE__')
                    ? `_${{activePlayers.join('_')}}`
                    : '';
                a.download = `mpp_animation_${{modeName}}_${{level}}${{filterDesc}}.gif`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                btn.innerText = originalBtnText;
                isRecording = false;
                renderStep(matchesData.length);
            }});
            
            // Capture frames
            let capturedFrames = 0;
            const totalFrames = Math.ceil(totalSteps / sampleStep);
            btn.innerText = `⏳ (0/${{totalFrames}})`;
            
            for (let step = 1; step <= totalSteps; step += sampleStep) {{
                renderStep(step);
                capturedFrames++;
                btn.innerText = `⏳ (${{capturedFrames}}/${{totalFrames}})`;
                // Yield to browser so chart re-renders
                await new Promise(resolve => setTimeout(resolve, 30));
                // Clear + draw current frame to offscreen canvas
                offCtx.clearRect(0, 0, targetWidth, targetHeight);
                offCtx.fillStyle = '#0B0F19';
                offCtx.fillRect(0, 0, targetWidth, targetHeight);
                offCtx.drawImage(canvas, 0, 0, targetWidth, targetHeight);
                gif.addFrame(offCtx, {{ copy: true, delay: frameDelay }});
            }}
            
            // Ensure final step (bonus/last match) is included in HD mode
            if (sampleStep > 1 && (totalSteps % sampleStep !== 1)) {{
                renderStep(totalSteps);
                offCtx.clearRect(0, 0, targetWidth, targetHeight);
                offCtx.fillStyle = '#0B0F19';
                offCtx.fillRect(0, 0, targetWidth, targetHeight);
                offCtx.drawImage(canvas, 0, 0, targetWidth, targetHeight);
                gif.addFrame(offCtx, {{ copy: true, delay: frameDelay * 2 }});
            }}
            
            // Start encoding
            btn.innerText = "⏳ Encodage...";
            overlay.style.display = 'flex';
            progressBar.style.width = '0%';
            progressText.innerText = `Encodage GIF (${{config.label}}) : 0%`;
            gif.render();
        }}

        function customTooltipHandler(context) {{
            const {{ chart, tooltip }} = context;
            const tooltipEl = document.getElementById('custom-tooltip');

            if (tooltip.opacity === 0) {{
                tooltipEl.style.opacity = '0';
                return;
            }}

            if (tooltip.body) {{
                const matchIndex = tooltip.dataPoints[0].dataIndex;
                const mData = matchesData[matchIndex];

                let html = `
                    <div class="tt-header">
                        <div class="tt-title">Match ${{mData.match_num}} : ${{mData.match}}</div>
                        <div class="tt-sub">📅 ${{mData.date}}</div>
                    </div>
                    <table class="tt-table">
                        <thead>
                            <tr>
                                <th style="text-align:center;">Pos</th>
                                <th>Participant</th>
                                <th style="text-align:center;">Prono MPP</th>
                                <th style="text-align:right;">Pts Match</th>
                                <th style="text-align:right;">Cumul</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                const sortedP = [...playerNames].sort((a, b) => mData.players[a].rank - mData.players[b].rank);

                sortedP.forEach(p => {{
                    const pInfo = mData.players[p];
                    const c = playerColors[p];
                    const ptsGainedStr = parseInt(pInfo.pts_gained) > 0 ? `+${{pInfo.pts_gained}}` : '0';
                    const isSelected = activePlayers.includes(p);
                    const rowBg = isSelected ? 'rgba(56, 189, 248, 0.18)' : 'transparent';

                    html += `
                        <tr style="background-color: ${{rowBg}};">
                            <td class="tt-rank" style="color: ${{c}}">${{pInfo.rank}}</td>
                            <td class="tt-player">
                                <span class="tt-badge" style="background-color: ${{c}}"></span>${{p}}
                            </td>
                            <td class="tt-prono" style="text-align:center;">${{pInfo.prono}}</td>
                            <td class="tt-pts-gain">${{ptsGainedStr}}</td>
                            <td class="tt-pts-cum">${{pInfo.cum_pts}} pts</td>
                        </tr>
                    `;
                }});

                html += `</tbody></table>`;
                tooltipEl.innerHTML = html;
            }}

            const canvasRect = chart.canvas.getBoundingClientRect();
            let left = tooltip.caretX + 25;
            let top = tooltip.caretY - 50;

            if (left + 430 > canvasRect.width) {{
                left = tooltip.caretX - 440;
            }}

            if (top < 10) top = 10;
            if (top + 350 > canvasRect.height) top = canvasRect.height - 360;

            tooltipEl.style.opacity = '1';
            tooltipEl.style.left = left + 'px';
            tooltipEl.style.top = top + 'px';
        }}

        function exportPNG() {{
            const canvas = document.getElementById('mppCanvas');
            const exportCanvas = document.createElement('canvas');
            exportCanvas.width = canvas.width;
            exportCanvas.height = canvas.height;
            const ctx = exportCanvas.getContext('2d');

            ctx.fillStyle = '#151D2A';
            ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
            ctx.drawImage(canvas, 0, 0);

            const modeName = currentMode === 'rank' ? 'classement' : 'points';
            const filterName = activePlayers.length > 0 && !activePlayers.includes('__NONE__') ? `_${{activePlayers.join('_')}}` : '';
            const link = document.createElement('a');
            link.download = `graphique_mpp_${{modeName}}${{filterName}}.png`;
            link.href = exportCanvas.toDataURL('image/png', 1.0);
            link.click();
        }}

        window.onload = initChart;
    </script>

    <!-- GIF Progress Overlay -->
    <div id="gifProgressOverlay" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(11,15,25,0.90); z-index:9999; flex-direction:column; align-items:center; justify-content:center; gap:18px;">
        <div style="color:#F8FAFC; font-size:1.3rem; font-weight:700; letter-spacing:0.04em;">⚙️ Génération du GIF en cours...</div>
        <div style="width:420px; max-width:90vw; background:#263346; border-radius:12px; overflow:hidden; height:22px; box-shadow:0 0 18px rgba(0,245,255,0.15);">
            <div id="gifProgressInner" style="height:100%; width:0%; background:linear-gradient(90deg,#00F5FF,#7B2FFF); transition:width 0.25s ease; border-radius:12px;"></div>
        </div>
        <div id="gifProgressText" style="color:#00F5FF; font-size:1.1rem; font-weight:600;">0%</div>
        <div style="color:#64748B; font-size:0.82rem;">Ne fermez pas cette fenêtre...</div>
    </div>

</body>
</html>
"""

out_html = os.path.join(csv_dir, 'dashboard_mpp.html')
# Sanitize: encode then decode replacing surrogates to avoid UnicodeEncodeError
_safe_html = html_template.encode('utf-8', errors='replace').decode('utf-8')
# Inject the inlined lib code
_safe_html = _safe_html.replace('__GIF_JS_CODE__', gif_js_content)
_safe_html = _safe_html.replace('__GIF_WORKER_CODE__', json.dumps(gif_worker_content))

with open(out_html, 'w', encoding='utf-8') as f:
    f.write(_safe_html)

print(f"[OK] Enhanced dashboard with Real Accuracy on Played Matches generated at: {out_html}")
