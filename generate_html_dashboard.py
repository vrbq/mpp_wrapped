import sys
import pandas as pd
import json
import os
import glob

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

csv_dir = select_data_directory()
league_info = get_league_info(csv_dir)
league_name = league_info['name']
league_code = league_info['code']

csv_path = os.path.join(csv_dir, 'points_cumules.csv')
df = pd.read_csv(csv_path)

players = [c for c in df.columns if c not in ['Match_Num', 'Date', 'Match']]

is_anon = any(arg in sys.argv for arg in ['--anon', '--anonymize', '-a'])
if is_anon:
    print("[INFO] Mode Anonyme activé (Simple HTML) : pseudos et informations de ligue masqués.")
    from anonymizer import build_anonymous_mapping, get_anonymized_league_info, anonymize_dataframe
    anon_league = get_anonymized_league_info(league_info)
    league_name = anon_league['name']
    league_code = anon_league['code']
    anon_map = build_anonymous_mapping(players)
    df = anonymize_dataframe(df, anon_map)
    players = [anon_map[p] for p in players]

ranks_df = pd.DataFrame()
for p in players:
    ranks_df[p] = df[players].rank(axis=1, ascending=False, method='min')[p]

colors = get_player_colors(players)

matches_list = df['Match_Num'].tolist()
match_details = []
for m in matches_list:
    row = df.loc[df['Match_Num']==m].iloc[0]
    if row['Date'] == 'Bonus' or 'Bonus' in str(row['Match']):
        match_details.append("Bonus")
    else:
        match_details.append(f"M{m}")

has_bonus_row = (df.iloc[-1]['Date'] == 'Bonus' or 'Bonus' in str(df.iloc[-1]['Match']))
num_actual_matches = len(df) - 1 if has_bonus_row else len(df)

datasets_ranks = []
datasets_points = []

for p in players:
    c = colors[p]
    datasets_ranks.append({
        'label': p,
        'data': ranks_df[p].tolist(),
        'borderColor': c,
        'backgroundColor': c,
        'borderWidth': 3,
        'tension': 0.35,
        'pointRadius': 3,
        'pointHoverRadius': 8
    })
    datasets_points.append({
        'label': p,
        'data': df[p].tolist(),
        'borderColor': c,
        'backgroundColor': c,
        'borderWidth': 3,
        'tension': 0.35,
        'pointRadius': 3,
        'pointHoverRadius': 8
    })

html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Évolution Classement MPP — {league_name} ({league_code})</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background-color: #0F172A;
            color: #F8FAFC;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        h1 {{
            font-size: 2rem;
            margin-bottom: 5px;
            color: #F8FAFC;
        }}
        p.subtitle {{
            color: #94A3B8;
            font-size: 1rem;
        }}
        .controls {{
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-bottom: 20px;
        }}
        button {{
            background-color: #1E293B;
            color: #94A3B8;
            border: 1px solid #334155;
            padding: 10px 20px;
            font-size: 0.95rem;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        button:hover {{
            background-color: #334155;
            color: #F8FAFC;
        }}
        button.active {{
            background-color: #2563EB;
            color: #FFFFFF;
            border-color: #3B82F6;
        }}
        .card {{
            background-color: #1E293B;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            border: 1px solid #334155;
        }}
        .chart-container {{
            position: relative;
            height: 650px;
            width: 100%;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 {league_name} <span style="font-size: 1.15rem; color: #38BDF8; font-weight: 800;">(Code : {league_code})</span></h1>
            <p class="subtitle">Suivi détaillé des {num_actual_matches} matchs disputés — {league_name} ({league_code})</p>
        </header>

        <div class="controls">
            <button id="btnRank" class="active" onclick="showChart('rank')">📉 Position au Classement (1er à 9ème)</button>
            <button id="btnPoints" onclick="showChart('points')">📈 Points Cumulés</button>
        </div>

        <div class="card">
            <div class="chart-container">
                <canvas id="mppChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        const matchDetails = {json.dumps(match_details)};
        const datasetsRanks = {json.dumps(datasets_ranks)};
        const datasetsPoints = {json.dumps(datasets_points)};

        let currentMode = 'rank';
        let chart;

        function initChart() {{
            const ctx = document.getElementById('mppChart').getContext('2d');
            chart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: matchDetails,
                    datasets: datasetsRanks
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{
                        mode: 'index',
                        intersect: false,
                    }},
                    plugins: {{
                        legend: {{
                            position: 'bottom',
                            labels: {{
                                color: '#E2E8F0',
                                font: {{ size: 13, weight: 'bold' }},
                                usePointStyle: true,
                                padding: 20
                            }}
                        }},
                        tooltip: {{
                            backgroundColor: '#0F172A',
                            titleColor: '#F8FAFC',
                            bodyColor: '#E2E8F0',
                            borderColor: '#334155',
                            borderWidth: 1,
                            padding: 12,
                            callbacks: {{
                                label: function(context) {{
                                    let label = context.dataset.label || '';
                                    if (label) label += ': ';
                                    if (currentMode === 'rank') {{
                                        label += context.raw + (context.raw === 1 ? 'er' : 'ème');
                                    }} else {{
                                        label += context.raw + ' pts';
                                    }}
                                    return label;
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            ticks: {{
                                color: '#94A3B8',
                                callback: function(val, index) {{
                                    const details = matchDetails[index];
                                    if (details && details.startsWith('Bonus:')) return 'Bonus';
                                    return 'M' + (index + 1);
                                }}
                            }},
                            grid: {{ color: '#334155' }}
                        }},
                        y: {{
                            reverse: true, // Rank 1 on top!
                            min: 1,
                            max: {len(players)},
                            ticks: {{
                                color: '#94A3B8',
                                stepSize: 1,
                                callback: function(value) {{
                                    return value + (value === 1 ? 'er' : 'ème');
                                }}
                            }},
                            grid: {{ color: '#334155' }}
                        }}
                    }}
                }}
            }});
        }}

        function showChart(mode) {{
            currentMode = mode;
            document.getElementById('btnRank').classList.toggle('active', mode === 'rank');
            document.getElementById('btnPoints').classList.toggle('active', mode === 'points');

            chart.data.datasets = mode === 'rank' ? datasetsRanks : datasetsPoints;
            
            if (mode === 'rank') {{
                chart.options.scales.y.reverse = true;
                chart.options.scales.y.min = 1;
                chart.options.scales.y.max = {len(players)};
                chart.options.scales.y.ticks.stepSize = 1;
                chart.options.scales.y.ticks.callback = function(value) {{
                    return value + (value === 1 ? 'er' : 'ème');
                }};
            }} else {{
                chart.options.scales.y.reverse = false;
                delete chart.options.scales.y.min;
                delete chart.options.scales.y.max;
                chart.options.scales.y.ticks.stepSize = 500;
                chart.options.scales.y.ticks.callback = function(value) {{
                    return value + ' pts';
                }};
            }}

            chart.update();
        }}

        window.onload = initChart;
    </script>
</body>
</html>
"""

out_html = os.path.join(csv_dir, 'dashboard_simple.html')
with open(out_html, 'w', encoding='utf-8') as f:
    f.write(html_content)

print("[OK] Interactive dashboard generated at saved/dashboard_simple.html")
