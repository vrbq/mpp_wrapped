import sys
import os
import subprocess
import re

def parse_league_codes(input_args):
    codes = []
    for arg in input_args:
        parts = re.split(r'[,\s]+', arg.strip())
        for p in parts:
            p_clean = p.strip()
            if p_clean and p_clean not in codes:
                codes.append(p_clean)
    return codes

def main():
    print("=========================================================")
    print("   PIPELINE MAÎTRE BATCH MPP : SCRAPER & GÉNÉRATEUR     ")
    print("=========================================================\n")
    
    is_anon = any(arg in sys.argv for arg in ['--anon', '--anonymize', '-a'])
    raw_args = [a for a in sys.argv[1:] if a not in ['--anon', '--anonymize', '-a']]
    league_codes = parse_league_codes(raw_args)
    
    if not league_codes:
        user_input = input("--> Entrez le(s) code(s) de ligue (séparés par un espace ou une virgule, ex: LIGUE1 LIGUE2) : ").strip()
        league_codes = parse_league_codes([user_input]) if user_input else []
        
    if not league_codes:
        league_codes = ["VOTRE_LIGUE"]
        print("[INFO] Aucun code spécifié. Utilisation de la ligue par défaut : VOTRE_LIGUE")
        
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    scraper_path = os.path.join(base_dir, "mpp_scraper.py")
    generate_all_path = os.path.join(base_dir, "generate_all.py")

    total = len(league_codes)
    print(f"\n[MODE BATCH] {total} ligue(s) à traiter : {', '.join(league_codes)}")
    if is_anon:
        print("[INFO] Mode Anonyme activé pour l'ensemble de la génération !")
    print()

    successful_leagues = []
    failed_leagues = []

    for idx, code in enumerate(league_codes, start=1):
        print("=========================================================")
        print(f"  [{idx}/{total}] TRAITEMENT DE LA LIGUE : {code}")
        print("=========================================================")

        # 1. Scraping
        print(f"\n[1/2] Extraction Web (Selenium) pour {code}...")
        scrape_cmd = [sys.executable, scraper_path, code]
        if is_anon:
            scrape_cmd.append("--anon")
        res_scrape = subprocess.run(scrape_cmd)
        
        if res_scrape.returncode != 0:
            print(f"\n[ERREUR] Échec de l'extraction pour la ligue '{code}'.")
            failed_leagues.append((code, "Scraping"))
            continue

        # 2. Generation
        if is_anon:
            from anonymizer import generate_random_league_code
            target_name = generate_random_league_code(code)
        else:
            target_name = code

        output_dir = os.path.join(base_dir, target_name)
        print(f"\n[2/2] Génération des dashboards & animations pour {target_name}...")
        gen_cmd = [sys.executable, generate_all_path, output_dir]
        if is_anon:
            gen_cmd.append("--anon")
        res_gen = subprocess.run(gen_cmd)

        if res_gen.returncode == 0:
            print(f"\n[OK] Ligue '{code}' traitée avec succès !")
            successful_leagues.append(code)
        else:
            print(f"\n[ERREUR] Échec de la génération pour la ligue '{code}'.")
            failed_leagues.append((code, "Génération"))

    # Final Batch Summary
    print("\n=========================================================")
    print("             RÉSUMÉ DU TRAITEMENT BATCH                  ")
    print("=========================================================")
    print(f" ✅ Réussites ({len(successful_leagues)}/{total}) : {', '.join(successful_leagues) if successful_leagues else 'Aucune'}")
    if failed_leagues:
        fail_str = ", ".join([f"{c} ({step})" for c, step in failed_leagues])
        print(f" ❌ Échecs ({len(failed_leagues)}/{total}) : {fail_str}")
    print("=========================================================\n")

if __name__ == "__main__":
    main()
