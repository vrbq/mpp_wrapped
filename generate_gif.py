import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from PIL import Image
import glob, io, os, csv, sys, shutil
import imageio

# Set global matplotlib style
plt.style.use('default')
plt.rcParams['font.sans-serif'] = 'Segoe UI', 'DejaVu Sans', 'Arial', 'sans-serif'

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
                    from bs4 import BeautifulSoup
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

# 1. Load Data
csv_dir = select_data_directory()
league_info = get_league_info(csv_dir)
league_name = league_info['name']
league_code = league_info['code']

csv_path = os.path.join(csv_dir, 'points_cumules.csv')
df = pd.read_csv(csv_path)

user_files = glob.glob(os.path.join(csv_dir, 'pronos_*.csv'))
user_files = [f for f in user_files if not os.path.basename(f).startswith('points_cumules')]

def get_star_count(tag):
    if not tag: return 0
    t = tag.lower()
    if 'ultra' in t: return 5
    if 'mega' in t or 'méga' in t: return 4
    if 'très' in t or 'tres' in t: return 3
    if 'rare' in t: return 2
    if 'exact' in t: return 1
    return 0

players = [c for c in df.columns if c not in ['Match_Num', 'Date', 'Match']]

is_anon = any(arg in sys.argv for arg in ['--anon', '--anonymize', '-a'])
anon_map = {}
if is_anon:
    print("[INFO] Mode Anonyme activé (GIF) : pseudos et informations de ligue masqués.")
    from anonymizer import build_anonymous_mapping, get_anonymized_league_info, anonymize_dataframe
    anon_league = get_anonymized_league_info(league_info)
    league_name = anon_league['name']
    league_code = anon_league['code']
    anon_map = build_anonymous_mapping(players)
    df = anonymize_dataframe(df, anon_map)
    players = [anon_map[p] for p in players]

num_matches = len(df)
num_players = len(players)
has_bonus_row = not df[df['Date'] == 'Bonus'].empty
num_actual_matches = num_matches - 1 if has_bonus_row else num_matches

# Build star mask per player match
player_stars = {p: [] for p in players}

for f in user_files:
    basename = os.path.basename(f)
    p_name = '_'.join(basename.split('_')[1:-1])
    if is_anon:
        p_name = anon_map.get(p_name, p_name)
    if p_name not in player_stars: continue
    
    with open(f, mode='r', encoding='utf-8') as fp:
        rows = list(csv.DictReader(fp))
        for r in rows:
            pts = int(r.get('Points_Gagnes', 0) or 0)
            tag = r.get('Bonus_Tag', '').strip()
            prono = r.get('Prono_MPP', '').strip()
            score = r.get('Score_Reel', '').strip()
            star = get_star_count(tag)
            if star == 0 and pts > 0 and (not prono or prono == score):
                star = 1
            player_stars[p_name].append(star > 0)

# Compute Ranks (1 = highest score)
ranks_df = pd.DataFrame()
for p in players:
    ranks_df[p] = df[players].rank(axis=1, ascending=False, method='min')[p]

# Vibrant colors mapping
colors = get_player_colors(players)

# Jitter Y offsets for tied ranks
display_ranks = ranks_df.copy()
for i in range(len(df)):
    row_vals = ranks_df.iloc[i]
    counts = row_vals.value_counts()
    for rank_val, count in counts.items():
        if count > 1:
            tied_players = row_vals[row_vals == rank_val].index
            for idx, tp in enumerate(tied_players):
                offset = (idx - (count - 1) / 2.0) * 0.12
                display_ranks.loc[i, tp] = rank_val + offset

# Quality config detection from command line
quality_preset = 'hd'
for arg in sys.argv[1:]:
    arg_lower = arg.lower()
    if arg_lower in ['low', 'medium', 'hd']:
        quality_preset = arg_lower
        break

QUALITY_PRESETS = {
    'low': {'dpi': 75, 'step': 3, 'colors': 128, 'fps': 6, 'label': 'Low (75 DPI, 1 match / 3)'},
    'medium': {'dpi': 110, 'step': 2, 'colors': 256, 'fps': 8, 'label': 'Medium (110 DPI, 1 match / 2)'},
    'hd': {'dpi': 150, 'step': 1, 'colors': 256, 'fps': 10, 'label': 'HD (150 DPI, 100% Matches)'}
}

q_config = QUALITY_PRESETS.get(quality_preset, QUALITY_PRESETS['hd'])
print(f"[INFO] Quality Preset GIF selected: {quality_preset.upper()} -> {q_config['label']}")

sample_step = q_config['step']
dpi_val = q_config['dpi']
max_colors = q_config['colors']
fps_val = q_config['fps']

frames = []
print(f"Generating GIF frames with glowing electric star markers for {num_matches} matches (Step: {sample_step})...")

fig, ax = plt.subplots(figsize=(16, 9), dpi=dpi_val)

match_indices = list(range(1, num_matches + 1, sample_step))
if num_matches not in match_indices:
    match_indices.append(num_matches)

for m_curr in match_indices:
    fig.texts.clear()
    ax.clear()
    
    fig.patch.set_facecolor('#0B0F19')
    ax.set_facecolor('#151D2A')
    
    ax.grid(True, which='major', axis='y', color='#263346', linestyle='-', linewidth=1, zorder=1)
    ax.grid(True, which='major', axis='x', color='#1E293B', linestyle='--', linewidth=0.6, zorder=1)

    sub_df = df.iloc[:m_curr]
    sub_ranks = display_ranks.iloc[:m_curr]
    x_vals = sub_df['Match_Num'].values

    curr_pts = sub_df[players].iloc[-1]
    curr_ranks = ranks_df.iloc[m_curr - 1]
    sorted_players_curr = sorted(players, key=lambda p: (curr_ranks[p], -curr_pts[p]))

    for player in reversed(sorted_players_curr):
        c = colors[player]
        y_vals = sub_ranks[player].values
        p_star_mask = player_stars.get(player, [])[:m_curr]
        
        ax.plot(x_vals, y_vals, color=c, linewidth=4, alpha=0.2, zorder=2)
        ax.plot(x_vals, y_vals, color=c, linewidth=2.8, alpha=0.95, zorder=3)
        
        x_circles = [x_vals[i] for i in range(len(x_vals)) if not (i < len(p_star_mask) and p_star_mask[i])]
        y_circles = [y_vals[i] for i in range(len(y_vals)) if not (i < len(p_star_mask) and p_star_mask[i])]
        
        x_stars = [x_vals[i] for i in range(len(x_vals)) if (i < len(p_star_mask) and p_star_mask[i])]
        y_stars = [y_vals[i] for i in range(len(y_vals)) if (i < len(p_star_mask) and p_star_mask[i])]

        if x_circles:
            ax.scatter(x_circles, y_circles, color=c, s=16, marker='o', zorder=4)
        if x_stars:
            ax.scatter(x_stars, y_stars, color='#FFFFFF', s=340, marker='*', zorder=5, alpha=0.95)
            ax.scatter(x_stars, y_stars, color='#FFEA00', s=210, marker='*', zorder=6, edgecolors=c, linewidth=1.2)
        
        is_curr_star = len(p_star_mask) >= m_curr and p_star_mask[m_curr - 1]
        cur_marker = '*' if is_curr_star else 'o'
        cur_size = 280 if is_curr_star else 50
        cur_color = '#FFEA00' if is_curr_star else '#FFFFFF'
        ax.scatter(x_vals[-1], y_vals[-1], color=cur_color, s=cur_size, marker=cur_marker, zorder=7, edgecolors=c, linewidth=2)

    ax.set_ylim(num_players + 0.6, 0.4)
    ax.set_yticks(range(1, num_players + 1))
    ax.set_yticklabels([f"{r}er" if r == 1 else f"{r}ème" for r in range(1, num_players + 1)], 
                       fontsize=11, fontweight='bold', color='#94A3B8')

    ax.set_xlim(0.5, num_matches + 18)
    xticks_locs = list(range(1, num_matches + 1, 10))
    if num_matches not in xticks_locs: xticks_locs.append(num_matches)
    ax.set_xticks(xticks_locs)
    xtick_labels = []
    for m in xticks_locs:
        row_tick = df[df['Match_Num'] == m].iloc[0]
        if row_tick['Date'] == 'Bonus' or 'Bonus' in str(row_tick['Match']):
            xtick_labels.append("Bonus")
        else:
            xtick_labels.append(f"M{m}")
    ax.set_xticklabels(xtick_labels, fontsize=9, fontweight='bold', color='#94A3B8')

    curr_match_info = sub_df.iloc[-1]
    is_bonus = curr_match_info['Date'] == 'Bonus' or 'Bonus' in str(curr_match_info['Match'])
    if is_bonus:
        match_str = f"Bonus Vainqueur & Buteur Finaux"
    else:
        match_str = f"Match {m_curr} / {num_actual_matches} : {curr_match_info['Match']} ({curr_match_info['Date']})"
    
    fig.text(0.5, 0.95, f"ÉVOLUTION DU CLASSEMENT — {league_name.upper()} ({league_code.upper()})", 
             fontsize=16, fontweight='bold', ha='center', color='#38BDF8')
    fig.text(0.5, 0.91, match_str, 
             fontsize=11, fontweight='bold', ha='center', color='#FFEA00')

    ax.set_xlabel(f"Matchs (1 à {num_matches})", fontsize=10, fontweight='bold', labelpad=8, color='#94A3B8')
    ax.set_ylabel("Place au Classement", fontsize=10, fontweight='bold', labelpad=8, color='#94A3B8')

    right_x = num_matches + 1.8
    for player in sorted_players_curr:
        rk = int(curr_ranks[player])
        pts = int(curr_pts[player])
        c = colors[player]
        y_pos = rk
        ax.scatter(right_x, y_pos, color=c, s=280, zorder=6, edgecolors='none')
        ax.text(right_x, y_pos, str(rk), color='#FFFFFF', fontsize=9, fontweight='bold', 
                ha='center', va='center', zorder=7)
        label_text = f"  {player} ({pts} pts)"
        txt = ax.text(right_x + 0.6, y_pos, label_text, color=c, fontsize=10, fontweight='bold', 
                      va='center', zorder=7)
        txt.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground='#0B0F19')])

    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_color('#263346')

    plt.tight_layout()
    plt.subplots_adjust(top=0.88, right=0.84, bottom=0.09)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), dpi=dpi_val)
    buf.seek(0)
    img = Image.open(buf)
    frames.append(img.copy())
    buf.close()

plt.close()

# Save animated GIF
out_gif = os.path.join(csv_dir, 'evolution_classement.gif')
out_gif_preset = os.path.join(csv_dir, f'evolution_classement_{quality_preset}.gif')
out_mp4 = os.path.join(csv_dir, 'evolution_classement.mp4')

print(f"Saving glowing animated GIF in {quality_preset.upper()} quality ({len(frames)} frames)...")
quantized_frames = []
for frame in frames:
    opt_frame = frame.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE, colors=max_colors)
    quantized_frames.append(opt_frame)

frame_duration = int(1000 / fps_val)
durations = [frame_duration] * (len(frames) - 1) + [4000]

quantized_frames[0].save(
    out_gif,
    save_all=True,
    append_images=quantized_frames[1:],
    duration=durations,
    loop=0,
    optimize=True
)
if out_gif_preset != out_gif:
    shutil.copyfile(out_gif, out_gif_preset)

print(f"[OK] {quality_preset.upper()} GIF saved to: {out_gif}")

print("Saving video in MP4...")
writer = imageio.get_writer(out_mp4, fps=fps_val, codec='libx264', quality=8)
for frame in frames:
    writer.append_data(imageio.core.asarray(frame.convert('RGB')))
writer.close()
print(f"[OK] MP4 video saved to: {out_mp4}")
