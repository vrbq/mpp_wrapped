import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
import os
import glob

# Set style
plt.style.use('default')
plt.rcParams['font.sans-serif'] = 'Segoe UI', 'DejaVu Sans', 'Arial'
plt.rcParams['axes.edgecolor'] = '#CCCCCC'
plt.rcParams['axes.linewidth'] = 0.8

def select_data_directory():
    import sys
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        selected = os.path.abspath(sys.argv[1])
        print(f"Dossier de données passé en argument : {os.path.basename(selected)} ({selected})")
        return selected

    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
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

# Load CSV
csv_dir = select_data_directory()
csv_path = os.path.join(csv_dir, 'points_cumules.csv')
df = pd.read_csv(csv_path)

players = [c for c in df.columns if c not in ['Match_Num', 'Date', 'Match']]
num_matches = len(df)
num_players = len(players)
has_bonus_row = not df[df['Date'] == 'Bonus'].empty
num_actual_matches = num_matches - 1 if has_bonus_row else num_matches

# Compute cumulative ranks (1 = highest points)
# method='min' gives standard ranking; we add tiny offset for visual separation if tied
ranks_df = pd.DataFrame()
for p in players:
    # rank ascending=False so max points = rank 1
    ranks_df[p] = df[players].rank(axis=1, ascending=False, method='min')[p]

colors = get_player_colors(players)

# Create figure
fig, ax = plt.subplots(figsize=(18, 10), dpi=300)

# Set background color
fig.patch.set_facecolor('#F8F9FA')
ax.set_facecolor('#FFFFFF')

# Grid setup
ax.grid(True, which='major', axis='y', color='#E5E5E5', linestyle='--', linewidth=0.7, zorder=1)
ax.grid(True, which='major', axis='x', color='#F0F0F0', linestyle=':', linewidth=0.5, zorder=1)

# X axis: Match numbers
x = df['Match_Num'].values

# Track final ranks for right-side annotations
final_points = df[players].iloc[-1]
final_ranks = ranks_df.iloc[-1]

# To prevent overlapping lines when tied, compute jittered display Y values
display_ranks = ranks_df.copy()
for i in range(len(df)):
    row_vals = ranks_df.iloc[i]
    # find duplicates
    counts = row_vals.value_counts()
    for rank_val, count in counts.items():
        if count > 1:
            tied_players = row_vals[row_vals == rank_val].index
            for idx, tp in enumerate(tied_players):
                # offset slightly around the rank value
                offset = (idx - (count - 1) / 2.0) * 0.12
                display_ranks.loc[i, tp] = rank_val + offset

# Plot lines for each player
sorted_players_by_final = sorted(players, key=lambda p: (final_ranks[p], -final_points[p]))

for player in reversed(sorted_players_by_final):
    color = colors.get(player, '#333333')
    y_vals = display_ranks[player].values
    
    # Plot main line
    line = ax.plot(x, y_vals, label=f"{player} ({int(final_points[player])} pts)", 
                   color=color, linewidth=2.8, alpha=0.9, zorder=3)
    
    # Add subtle dots at key points (e.g. every 5 matches or when rank changes)
    # We plot small markers for every match to make it detailed
    ax.scatter(x, y_vals, color=color, s=12, zorder=4, alpha=0.7)

# Format Y axis (Ranks 1 to N)
ax.set_ylim(num_players + 0.6, 0.4) # Inverted Y axis
ax.set_yticks(range(1, num_players + 1))
ax.set_yticklabels([f"{r}er" if r == 1 else f"{r}ème" for r in range(1, num_players + 1)], 
                   fontsize=12, fontweight='bold', color='#333333')

# Format X axis
ax.set_xlim(0.5, num_matches + 14) # Extra space on right for labels
xticks_step = 5
xticks_locs = list(range(1, num_matches + 1, xticks_step))
if num_matches not in xticks_locs:
    xticks_locs.append(num_matches)
ax.set_xticks(xticks_locs)
xtick_labels = []
for m in xticks_locs:
    row_tick = df[df['Match_Num'] == m].iloc[0]
    if row_tick['Date'] == 'Bonus' or 'Bonus' in str(row_tick['Match']):
        xtick_labels.append("Bonus")
    else:
        xtick_labels.append(f"M{m}")
ax.set_xticklabels(xtick_labels, fontsize=9, rotation=0, color='#555555')

# Title and subtitles
plt.suptitle("Évolutive du Classement MPP — Coupe du Monde 2026", fontsize=20, fontweight='bold', y=0.96, color='#111111')
ax.set_title(f"Évolution place par place au fil des {num_actual_matches} matchs" + (" (avec bonus)" if has_bonus_row else "") + " | MPP Scraper", fontsize=11, color='#666666', pad=12)

ax.set_xlabel(f"Matchs (1 à {num_matches})", fontsize=11, fontweight='bold', labelpad=10, color='#333333')
ax.set_ylabel("Position au Classement", fontsize=11, fontweight='bold', labelpad=10, color='#333333')

# Annotating final positions on the right side (Reference Image Style!)
# Group players by final rank to avoid label collision on right side
right_x = num_matches + 1.2

# Calculate right label Y positions with vertical repulsion if needed
y_labels_pos = []
for p in sorted_players_by_final:
    y_labels_pos.append({
        'player': p,
        'rank': int(final_ranks[p]),
        'pts': int(final_points[p]),
        'target_y': final_ranks[p],
        'color': colors.get(p, '#333333')
    })

# Adjust Y positions for right side labels if any overlap
for i in range(len(y_labels_pos)):
    for j in range(i + 1, len(y_labels_pos)):
        if abs(y_labels_pos[j]['target_y'] - y_labels_pos[i]['target_y']) < 0.4:
            y_labels_pos[j]['target_y'] += 0.35

for item in y_labels_pos:
    p = item['player']
    rk = item['rank']
    pts = item['pts']
    y_pos = item['target_y']
    c = item['color']
    
    # Draw rank badge
    ax.scatter(right_x, y_pos, color=c, s=180, zorder=5)
    ax.text(right_x, y_pos, str(rk), color='#FFFFFF', fontsize=9, fontweight='bold', 
            ha='center', va='center', zorder=6)
    
    # Draw player name and score
    label_text = f"  {p}  ({pts} pts)"
    txt = ax.text(right_x + 0.8, y_pos, label_text, color=c, fontsize=11, fontweight='bold', 
                  va='center', zorder=6)
    txt.set_path_effects([path_effects.withStroke(linewidth=2, foreground='#FFFFFF')])

# Legend at top right/left inside graph
legend = ax.legend(loc='lower left', bbox_to_anchor=(0.01, 0.01), frameon=True, 
                   facecolor='#FFFFFF', edgecolor='#CCCCCC', fontsize=9, ncol=3)
legend.get_frame().set_alpha(0.9)

# Remove top and right spines
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.subplots_adjust(top=0.90, right=0.88)

output_png = os.path.join(csv_dir, 'evolution_classement.png')
plt.savefig(output_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"Graph saved successfully to: {output_png}")
