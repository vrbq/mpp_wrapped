import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
import os
import json
import glob

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

csv_dir = select_data_directory()
csv_path = os.path.join(csv_dir, 'points_cumules.csv')
df = pd.read_csv(csv_path)

players = [c for c in df.columns if c not in ['Match_Num', 'Date', 'Match']]

is_anon = any(arg in sys.argv for arg in ['--anon', '--anonymize', '-a'])
if is_anon:
    print("[INFO] Mode Anonyme activé (Global PNG) : pseudos et informations de ligue masqués.")
    from anonymizer import build_anonymous_mapping, anonymize_dataframe
    anon_map = build_anonymous_mapping(players)
    df = anonymize_dataframe(df, anon_map)
    players = [anon_map[p] for p in players]

num_matches = len(df)
num_players = len(players)

has_bonus_row = not df[df['Date'] == 'Bonus'].empty
num_actual_matches = num_matches - 1 if has_bonus_row else num_matches

# 2. Compute Ranks (1 = highest score)
ranks_df = pd.DataFrame()
for p in players:
    ranks_df[p] = df[players].rank(axis=1, ascending=False, method='min')[p]

# Color palette for 9 players
colors = get_player_colors(players)

final_points = df[players].iloc[-1]
final_ranks = ranks_df.iloc[-1]
sorted_players = sorted(players, key=lambda p: (final_ranks[p], -final_points[p]))

# ---------------------------------------------------------
# GRAPH 1: EVOLUTION DU CLASSEMENT (SCOREBOARD BUMP CHART)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(22, 12), dpi=300)
fig.patch.set_facecolor('#F8F9FA')
ax.set_facecolor('#FFFFFF')

# Grid
ax.grid(True, which='major', axis='y', color='#E2E8F0', linestyle='-', linewidth=1, zorder=1)
ax.grid(True, which='major', axis='x', color='#F1F5F9', linestyle='--', linewidth=0.6, zorder=1)

# Jitter slight Y offsets for tied ranks so lines don't completely hide each other
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

x = df['Match_Num'].values

# Plot lines in reverse final rank order so top players are drawn on top
for player in reversed(sorted_players):
    color = colors[player]
    y_vals = display_ranks[player].values
    
    # Glow effect
    ax.plot(x, y_vals, color=color, linewidth=4.5, alpha=0.15, zorder=2)
    # Main Line
    ax.plot(x, y_vals, label=f"{player} ({int(final_points[player])} pts)", 
            color=color, linewidth=2.8, alpha=0.95, zorder=3)
    # Markers
    ax.scatter(x, y_vals, color=color, s=14, zorder=4, alpha=0.8, edgecolors='none')

# Y-Axis (Ranks 1 to N, inverted)
ax.set_ylim(num_players + 0.6, 0.4)
ax.set_yticks(range(1, num_players + 1))
ax.set_yticklabels([f"{r}er" if r == 1 else f"{r}ème" for r in range(1, num_players + 1)], 
                   fontsize=13, fontweight='bold', color='#1E293B')

# X-Axis Bottom (Match numbers)
ax.set_xlim(0.5, num_matches + 18)
xticks_step = 5
xticks_locs = list(range(1, num_matches + 1, xticks_step))
if num_matches not in xticks_locs:
    xticks_locs.append(num_matches)

ax.set_xticks(xticks_locs)
xtick_labels = []
for m in xticks_locs:
    row = df[df['Match_Num'] == m].iloc[0]
    if row['Date'] == 'Bonus' or 'Bonus' in str(row['Match']):
        xtick_labels.append("Bonus")
    else:
        xtick_labels.append(f"M{m}")
ax.set_xticklabels(xtick_labels, fontsize=10, fontweight='bold', color='#475569')

# Top X-Axis (Dates / Match highlights rotated like reference image!)
secax = ax.secondary_xaxis('top')
secax.set_xticks(xticks_locs)

top_labels = []
for m in xticks_locs:
    row = df[df['Match_Num'] == m].iloc[0]
    match_str = str(row['Match'])
    if row['Date'] == 'Bonus' or 'Bonus' in match_str:
        top_labels.append("Bonus Finaux")
    else:
        top_labels.append(f"M{m}: {row['Date']} ({match_str.split(' ')[0]}...)")

secax.set_xticklabels(top_labels, fontsize=7.5, rotation=35, ha='left', color='#64748B', fontweight='bold')

# Suptitle & Titles with increased padding to avoid collision
plt.suptitle("ÉVOLUTION DU CLASSEMENT MPP — COUPE DU MONDE 2026", 
             fontsize=22, fontweight='bold', y=0.985, color='#0F172A')
ax.set_title(f"Positions place par place au fil des {num_actual_matches} matchs" + (" (avec bonus finaux)" if has_bonus_row else " disputés"), 
             fontsize=12, color='#64748B', pad=45)

ax.set_xlabel(f"Matchs (1 à {num_matches})", fontsize=12, fontweight='bold', labelpad=12, color='#1E293B')
ax.set_ylabel("Place au Classement Général", fontsize=12, fontweight='bold', labelpad=12, color='#1E293B')

# Right-side Annotations (Reference Image Style with Rank Badges using scatter for perfect circles)
right_x = num_matches + 1.5
for player in sorted_players:
    rk = int(final_ranks[player])
    pts = int(final_points[player])
    c = colors[player]
    y_pos = rk
    
    # Scatter circle marker for perfect round badge
    ax.scatter(right_x, y_pos, color=c, s=350, zorder=5, edgecolors='none')
    ax.text(right_x, y_pos, str(rk), color='#FFFFFF', fontsize=10, fontweight='bold', 
            ha='center', va='center', zorder=6)
    
    # Draw Player Name and Total Points
    label_text = f"  {player}   ({pts} pts)"
    txt = ax.text(right_x + 0.6, y_pos, label_text, color=c, fontsize=12, fontweight='bold', 
                  va='center', zorder=6)
    txt.set_path_effects([path_effects.withStroke(linewidth=3, foreground='#FFFFFF')])

# Legend inside top-left
legend = ax.legend(loc='lower left', bbox_to_anchor=(0.01, 0.01), frameon=True, 
                   facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=9.5, ncol=3)
legend.get_frame().set_alpha(0.95)

# Spines styling
for spine in ['top', 'right', 'left', 'bottom']:
    ax.spines[spine].set_color('#CBD5E1')

plt.tight_layout()
plt.subplots_adjust(top=0.84, right=0.85, bottom=0.08)

out_classement_png = os.path.join(csv_dir, 'evolution_classement.png')
plt.savefig(out_classement_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print(f"[OK] Classement PNG saved to {out_classement_png}")

# ---------------------------------------------------------
# GRAPH 2: EVOLUTION DES POINTS CUMULÉS (POINTS CHART)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(22, 11), dpi=300)
fig.patch.set_facecolor('#F8F9FA')
ax.set_facecolor('#FFFFFF')

ax.grid(True, which='major', axis='y', color='#E2E8F0', linestyle='-', linewidth=1, zorder=1)
ax.grid(True, which='major', axis='x', color='#F1F5F9', linestyle='--', linewidth=0.6, zorder=1)

for player in sorted_players:
    color = colors[player]
    pts_vals = df[player].values
    ax.plot(x, pts_vals, label=f"{player} ({int(final_points[player])} pts)", 
            color=color, linewidth=2.8, alpha=0.9, zorder=3)

ax.set_xlim(0.5, num_matches + 18)
ax.set_xticks(xticks_locs)
xtick_labels_pts = []
for m in xticks_locs:
    row = df[df['Match_Num'] == m].iloc[0]
    if row['Date'] == 'Bonus' or 'Bonus' in str(row['Match']):
        xtick_labels_pts.append("Bonus")
    else:
        xtick_labels_pts.append(f"M{m}")
ax.set_xticklabels(xtick_labels_pts, fontsize=10, fontweight='bold', color='#475569')

plt.suptitle("ÉVOLUTION DES POINTS CUMULÉS — COUPE DU MONDE 2026", 
             fontsize=22, fontweight='bold', y=0.96, color='#0F172A')
ax.set_title(f"Progression des points match par match pour l'ensemble des {num_players} joueurs", 
             fontsize=12, color='#64748B', pad=15)

ax.set_xlabel(f"Matchs (1 à {num_matches})", fontsize=12, fontweight='bold', labelpad=12, color='#1E293B')
ax.set_ylabel("Points Cumulés", fontsize=12, fontweight='bold', labelpad=12, color='#1E293B')

# Vertical repulsion for right side labels on points graph
right_labels = []
for p in sorted_players:
    right_labels.append({
        'player': p,
        'pts': int(final_points[p]),
        'target_y': float(final_points[p]),
        'color': colors[p]
    })

# Adjust label positions if too close
min_dist = 90 # min points distance visually
for i in range(len(right_labels)):
    for j in range(i + 1, len(right_labels)):
        if abs(right_labels[j]['target_y'] - right_labels[i]['target_y']) < min_dist:
            right_labels[j]['target_y'] -= min_dist

for item in right_labels:
    p = item['player']
    pts = item['pts']
    y_pos = item['target_y']
    c = item['color']
    ax.scatter(right_x, df[p].iloc[-1], color=c, s=50, zorder=5)
    txt = ax.text(right_x + 0.5, y_pos, f"  {p} ({pts} pts)", color=c, fontsize=11, fontweight='bold', 
                  va='center', zorder=6)
    txt.set_path_effects([path_effects.withStroke(linewidth=3, foreground='#FFFFFF')])

legend = ax.legend(loc='upper left', bbox_to_anchor=(0.01, 0.98), frameon=True, 
                   facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=10, ncol=3)
legend.get_frame().set_alpha(0.95)

plt.tight_layout()
plt.subplots_adjust(top=0.90, right=0.85)

out_points_png = os.path.join(csv_dir, 'evolution_points.png')
plt.savefig(out_points_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print(f"[OK] Points PNG saved to {out_points_png}")

# Launch the other generations sequentially to generate gif/mp4 and html dashboards
import subprocess
import sys

base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
extra_args = ["--anon"] if is_anon else []

print("\n=== Lancement de la génération des Gifs & Vidéo MP4 ===")
subprocess.run([sys.executable, os.path.join(base_dir, "generate_gif.py"), csv_dir] + extra_args, check=False)

print("\n=== Lancement de la génération du Dashboard Simple ===")
subprocess.run([sys.executable, os.path.join(base_dir, "generate_html_dashboard.py"), csv_dir] + extra_args, check=False)

print("\n=== Lancement de la génération du Dashboard Néon/Interactif ===")
subprocess.run([sys.executable, os.path.join(base_dir, "generate_enhanced_dashboard.py"), csv_dir] + extra_args, check=False)

print("\n=== [OK] Génération globale terminée avec succès ! ===")
