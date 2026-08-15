import os
import sys
import json
import base64
import uuid
import time
import threading
import subprocess
from http.server import SimpleHTTPRequestHandler, HTTPServer

# Global dictionary to track background scraping tasks
tasks = {}
tasks_lock = threading.Lock()

# Global dictionary to track active processes for standard input writes
active_processes = {}
processes_lock = threading.Lock()

class MPPDashboardServer(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default request logging to keep the console clean
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/run':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                params = json.loads(post_data.decode('utf-8'))
                league = params.get('league', '').strip().upper()
                token = params.get('token', '').strip()
                session = params.get('session', None)
                interactive = params.get('interactive', False)
                anon = params.get('anon', False)
                
                if not league:
                    self.send_error_json("Code de ligue manquant.")
                    return
                
                # Check target file on disk for fallback (if not interactive)
                if not interactive:
                    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
                    if anon:
                        from anonymizer import generate_random_league_code
                        chk_league = generate_random_league_code(league)
                    else:
                        chk_league = league
                    league_dir = os.path.abspath(os.path.join(base_dir, chk_league))
                    session_file = os.path.join(league_dir, "mpp_session.json")
                    real_session_file = os.path.join(os.path.abspath(os.path.join(base_dir, league)), "mpp_session.json")
                    root_session_file = os.path.join(base_dir, "mpp_session.json")
                    
                    if not token and not session and not (os.path.exists(session_file) or os.path.exists(real_session_file) or os.path.exists(root_session_file)):
                        self.send_error_json("Jeton ou session de connexion MPP manquant (fichier inexistant sur le disque).")
                        return
                
                # Generate a unique task ID
                task_id = str(uuid.uuid4())
                
                with tasks_lock:
                    tasks[task_id] = {
                        'status': 'running',
                        'progress': 0,
                        'logs': [],
                        'league': league
                    }
                
                # Start background scraping and generating process
                thread = threading.Thread(target=run_scraping_task, args=(league, token, task_id, session, interactive, anon))
                thread.daemon = True
                thread.start()
                
                # Return the task_id to the client
                self.send_json({'task_id': task_id})
                
            except Exception as e:
                self.send_error_json(f"Erreur d'analyse JSON des paramètres : {str(e)}")
        
        elif self.path == '/api/confirm_login':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode('utf-8'))
                task_id = params.get('task_id', '').strip()
                
                if not task_id:
                    self.send_error_json("Paramètre task_id manquant.")
                    return
                
                # Retrieve process and send newline
                with processes_lock:
                    proc = active_processes.get(task_id)
                
                if proc:
                    # Write newline to standard input to let the python prompt proceed!
                    try:
                        proc.stdin.write("\n")
                        proc.stdin.flush()
                        print(f"[API] Signal de connexion envoyé au processus de la tâche {task_id}.")
                        self.send_json({'success': True})
                    except Exception as e:
                        self.send_error_json(f"Impossible d'envoyer le signal au processus : {str(e)}")
                else:
                    self.send_error_json("Aucun processus actif trouvé pour cette tâche (déjà validé ou arrêté).")
            except Exception as e:
                self.send_error_json(f"Erreur d'analyse des paramètres : {str(e)}")
        
        elif self.path == '/api/session':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode('utf-8'))
                league = params.get('league', '').strip().upper()
                session = params.get('session', None)
                
                if not league:
                    self.send_error_json("Code de ligue manquant.")
                    return
                if not session:
                    self.send_error_json("Session manquante.")
                    return
                
                # Save session to file directly!
                base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
                league_dir = os.path.abspath(os.path.join(base_dir, league))
                os.makedirs(league_dir, exist_ok=True)
                session_file = os.path.join(league_dir, "mpp_session.json")
                
                session["timestamp"] = time.time()
                with open(session_file, "w", encoding="utf-8") as f:
                    json.dump(session, f, ensure_ascii=False, indent=2)
                
                # Read JWT token inside session for log transparency
                token_to_log = "Inconnu"
                if "localStorage" in session:
                    for k, v in session["localStorage"].items():
                        if v and "eyJ" in v:
                            import re
                            m = re.search(r'(eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+)', v)
                            if m:
                                token_to_log = m.group(1)
                                break
                print(f"[API_SESSION] Nouvelle session synchronisée pour la ligue {league}! Jeton capturé : {token_to_log}")
                
                self.send_json({'success': True, 'league': league, 'token': token_to_log})
            except Exception as e:
                self.send_error_json(f"Erreur d'enregistrement de session : {str(e)}")
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path.startswith('/api/status'):
            from urllib.parse import urlparse, parse_qs
            query = urlparse(self.path).query
            params = parse_qs(query)
            
            task_ids = params.get('task_id', [])
            if not task_ids:
                self.send_error_json("Paramètre task_id manquant.")
                return
                
            task_id = task_ids[0]
            with tasks_lock:
                task = tasks.get(task_id)
                
            if not task:
                self.send_error_json("Tâche introuvable.")
                return
                
            self.send_json({
                'status': task['status'],
                'progress': task['progress'],
                'logs': task['logs'],
                'target_league': task.get('target_league', task.get('league'))
            })
        else:
            # If accessing the root, serve index.html
            parts = self.path.split('?')
            clean_path = parts[0]
            if clean_path in ('', '/', '/index.html'):
                self.path = '/index.html'
            super().do_GET()

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        # Disable caching for API responses
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def send_error_json(self, message):
        self.send_response(400)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode('utf-8'))

    def end_headers(self):
        # Set standard CORS headers for development/hosting flex
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()


def reconstruct_auth0_session(token):
    """Reconstruct a complete Auth0 structure from a single raw JWT token."""
    payload_data = None
    header_data = {"alg": "RS256", "typ": "JWT", "kid": "YNoGteX9UUuLxyXRS8_PE"}
    parts = token.split('.')
    try:
        if len(parts) == 3:
            h_b64 = parts[0] + '=' * (-len(parts[0]) % 4)
            header_data = json.loads(base64.urlsafe_b64decode(h_b64).decode('utf-8'))
            p_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
            payload_data = json.loads(base64.urlsafe_b64decode(p_b64).decode('utf-8'))
    except Exception:
        pass

    if not payload_data:
        # Fallback to simple accessToken key
        return {
            "localStorage": {
                "com.monpetitprono.monpetitpronoapp.secureStorage\\accessToken": token
            },
            "sessionStorage": {},
            "timestamp": time.time()
        }

    # Extract claims
    sub = payload_data.get("sub", "auth0|user_unknown")
    aud = payload_data.get("aud", "grX5jWGWWQ4Uq91oe7KPNDZ96FS3jr0X")
    client_id = aud if isinstance(aud, str) else payload_data.get("azp", "grX5jWGWWQ4Uq91oe7KP6NDNDZ96FS3jr0X")
    if isinstance(aud, list) and len(aud) > 0:
        client_id = payload_data.get("azp", "grX5jWGWWQ4Uq91oe7KPNDZ96FS3jr0X")
    elif not isinstance(client_id, str):
        client_id = "grX5jWGWWQ4Uq91oe7KPNDZ96FS3jr0X"
    
    exp = payload_data.get("exp", int(time.time() + 3600))
    nickname = payload_data.get("nickname", payload_data.get("name", "User")).split('@')[0]
    
    # Build user info structure
    user_info = {
        "nickname": nickname,
        "name": payload_data.get("name", nickname),
        "picture": payload_data.get("picture", ""),
        "updated_at": payload_data.get("updated_at", ""),
        "email": payload_data.get("email", ""),
        "email_verified": payload_data.get("email_verified", True),
        "sub": sub
    }
    
    # Build auth0 user key value
    auth0_user_val = {
        "id_token": token,
        "decodedToken": {
            "encoded": {
                "header": parts[0],
                "payload": parts[1],
                "signature": parts[2]
            },
            "header": header_data,
            "claims": payload_data,
            "user": user_info
        }
    }
    
    # Build auth0 token key value
    auth0_token_val = {
        "body": {
            "access_token": token,
            "refresh_token": "dummy_refresh",
            "scope": "openid profile email offline_access",
            "expires_in": 2592000,
            "token_type": "Bearer",
            "audience": "https://mpp.ligue1.fr",
            "oauthTokenScope": "openid profile email offline_access",
            "client_id": client_id
        },
        "expiresAt": exp
    }
    
    return {
        "localStorage": {
            f"@@auth0spajs@@::{client_id}::@@user@@": json.dumps(auth0_user_val, ensure_ascii=False),
            f"@@auth0spajs@@::{client_id}::https://mpp.ligue1.fr::openid profile email offline_access": json.dumps(auth0_token_val, ensure_ascii=False),
            "com.monpetitprono.monpetitpronoapp.secureStorage\\accessToken": token,
            "appTheme": '{"state":{"_hasHydrated":true,"selectedTheme":"cdm","isThemeLoaderShown":false,"previousTheme":"cdm"},"version":0}',
            "language": "fr"
        },
        "sessionStorage": {},
        "timestamp": time.time()
    }


def run_scraping_task(league_code, token, task_id, session=None, interactive=False, anon=False):
    def update_task_log(msg):
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['logs'].append(msg)

    def set_task_progress(pct):
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['progress'] = pct

    def set_task_status(status):
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status'] = status

    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    if anon:
        from anonymizer import generate_random_league_code
        target_league_dir = generate_random_league_code(league_code)
    else:
        target_league_dir = league_code

    league_dir = os.path.abspath(os.path.join(base_dir, target_league_dir))
    os.makedirs(league_dir, exist_ok=True)
    
    # Save token or full session for Selenium manual session restores
    session_file = os.path.join(league_dir, "mpp_session.json")
    
    write_session = True
    
    if interactive:
        write_session = False
        update_task_log("[INFO] Mode interactif activé. Firefox s'ouvrira en mode visible sans session préalable.")
    elif session:
        session_data = session
        session_data["timestamp"] = time.time()
        
        # Extract JWT from session dictionary for logging transparency
        token_to_log = "Inconnue"
        if "localStorage" in session:
            for k, v in session["localStorage"].items():
                if v and "eyJ" in v:
                    import re
                    m = re.search(r'(eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+)', v)
                    if m:
                        token_to_log = m.group(1)
                        break
        update_task_log(f"[INFO] Session d'authentification complète sauvegardée dans mpp_session.json (Token: {token_to_log})")
    elif token and token != "Session synchronisée" and "eyJ" in token:
        # Reconstruct the absolute correct Auth0 structure from pasted token
        session_data = reconstruct_auth0_session(token)
        update_task_log(f"[INFO] Jeton d'accès décodé. Structure complète Auth0 régénérée dans mpp_session.json. Token: {token}")
    else:
        # Neither a new session payload nor a new raw token was sent.
        # We rely on the existing mpp_session.json already stored on disk.
        write_session = False
        update_task_log("[INFO] Utilisation de la session existante sur le disque.")
    
    if write_session:
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            update_task_log(f"[ERREUR] Impossible d'écrire la session : {str(e)}")
            set_task_status('failed')
            return

    # Log the exact token that will be passed into the scraper command line / sub-process
    actual_t = token
    if session and "localStorage" in session:
        for k, v in session["localStorage"].items():
            if v and "eyJ" in v:
                import re
                m = re.search(r'(eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+)', v)
                if m:
                    actual_t = m.group(1)
                    break
    elif not write_session:
        # Load from disk file to read token
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                disk_session = json.load(f)
                if "localStorage" in disk_session:
                    for k, v in disk_session["localStorage"].items():
                        if v and "eyJ" in v:
                            import re
                            m = re.search(r'(eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+)', v)
                            if m:
                                actual_t = m.group(1)
                                break
        except Exception:
            pass

    update_task_log(f"[INFO] Jeton MPP actif envoyé au scraper : {actual_t}")

    # Task 1: Run selenium scraper
    scraper_path = os.path.join(base_dir, "mpp_scraper.py")
    
    session_file_exists = os.path.exists(session_file) or os.path.exists(os.path.join(base_dir, "mpp_session.json"))
    headless_success = False
    
    # 1A. Try headless auto-login if session exists
    if interactive and session_file_exists:
        update_task_log("[INFO] Session existante détectée. Tentative de reconnexion automatique en arrière-plan (sans fenêtre)...")
        set_task_progress(5)
        cmd_scrape_headless = [sys.executable, scraper_path, league_code, "--headless"]
        if anon:
            cmd_scrape_headless.append("--anon")
        try:
            proc = subprocess.Popen(
                cmd_scrape_headless, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding='utf-8', 
                errors='replace', 
                cwd=base_dir
            )
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    clean_line = line.strip()
                    if clean_line:
                        # Log headless execution outputs
                        update_task_log(clean_line)
                        if "Ouverture de Firefox" in clean_line:
                            set_task_progress(10)
                        elif "Navigation vers MPP" in clean_line:
                            set_task_progress(15)
                        elif "Restauration de la session" in clean_line or "Session restaurée" in clean_line:
                            set_task_progress(20)
                        elif "Collecte des profils terminée" in clean_line:
                            set_task_progress(25)
                        elif "Traitement de " in clean_line:
                            import re
                            m = re.search(r'\[(\d+)\/(\d+)\]', clean_line)
                            if m:
                                current, total = int(m.group(1)), int(m.group(2))
                                pct = 30 + int((current / total) * 30)
                                set_task_progress(pct)
            proc.communicate()
            if proc.returncode == 0:
                headless_success = True
                update_task_log("[OK] Reconnexion automatique réussie ! Session toujours valide.")
            else:
                update_task_log("[INFO] Session expirée ou invalide. Démarrage de la connexion interactive...")
        except Exception as e:
            update_task_log(f"[INFO] Échec de la tentative en arrière-plan : {str(e)}")
            
    # 1B. Run visible interactive Firefox if no session exists or automatic connection failed
    if (interactive and not headless_success) or (not interactive):
        if interactive:
            update_task_log("[INFO] Démarrage de l'extraction MPP en mode INTERACTIF (fenêtre Firefox visible)...")
            cmd_scrape = [sys.executable, scraper_path, league_code, "--fresh"]
        else:
            update_task_log("[INFO] Démarrage de l'extraction des données MPP en arrière-plan (sans fenêtre)...")
            cmd_scrape = [sys.executable, scraper_path, league_code, "--headless"]
        
        if anon:
            cmd_scrape.append("--anon")
            
        set_task_progress(5)
        
        try:
            proc = subprocess.Popen(
                cmd_scrape, 
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding='utf-8', 
                errors='replace', 
                cwd=base_dir
            )
            
            with processes_lock:
                active_processes[task_id] = proc
                
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    clean_line = line.strip()
                    if clean_line:
                        update_task_log(clean_line)
                        # Heuristics for progress percentage & interactive prompt detection
                        if "Veuillez vous connecter" in clean_line or "Une fois connecté" in clean_line:
                            update_task_log("[CLI_WAITING_FOR_LOGIN] L'application attend votre connexion dans la fenêtre Firefox.")
                        elif "Ouverture de Firefox" in clean_line:
                            set_task_progress(10)
                        elif "Navigation vers MPP" in clean_line:
                            set_task_progress(15)
                        elif "Restauration de la session" in clean_line or "Session restaurée" in clean_line:
                            set_task_progress(20)
                        elif "Collecte des profils terminée" in clean_line:
                            set_task_progress(25)
                        elif "Traitement de " in clean_line:
                            import re
                            m = re.search(r'\[(\d+)\/(\d+)\]', clean_line)
                            if m:
                                current, total = int(m.group(1)), int(m.group(2))
                                pct = 30 + int((current / total) * 30)
                                set_task_progress(pct)
            proc.communicate()
            if proc.returncode != 0:
                update_task_log(f"[ERREUR] Le scraper s'est arrêté prématurément (Code retour : {proc.returncode}).")
                set_task_status('failed')
                return
        except Exception as e:
            update_task_log(f"[ERREUR] Exception durant le scraping : {str(e)}")
            set_task_status('failed')
            return
        finally:
            with processes_lock:
                if task_id in active_processes:
                    try:
                        active_processes[task_id].kill()
                    except Exception:
                        pass
                    del active_processes[task_id]

    # Task 2: Re-generate the analytical charts and neon dashboard
    if anon:
        from anonymizer import generate_random_league_code
        target_league_dir = generate_random_league_code(league_code)
        update_task_log(f"[INFO] Mode Anonyme activé : Dossier et URL anonymisés vers '{target_league_dir}'")
    else:
        target_league_dir = league_code

    with tasks_lock:
        if task_id in tasks:
            tasks[task_id]['target_league'] = target_league_dir

    update_task_log(f"[INFO] Lancement de la génération globale des dashboards et animations pour {target_league_dir}...")
    set_task_progress(65)
    generate_all_path = os.path.join(base_dir, "generate_all.py")
    cmd_gen = [sys.executable, generate_all_path, target_league_dir]
    if anon:
        cmd_gen.append("--anon")
    
    try:
        proc = subprocess.Popen(
            cmd_gen, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8', 
            errors='replace', 
            cwd=base_dir
        )
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                clean_line = line.strip()
                if clean_line:
                    update_task_log(clean_line)
                    if "Lancement de la génération des Gifs" in clean_line:
                        set_task_progress(75)
                    elif "Lancement de la génération du Dashboard Simple" in clean_line:
                        set_task_progress(85)
                    elif "Lancement de la génération du Dashboard Néon" in clean_line:
                        set_task_progress(95)
        proc.communicate()
        if proc.returncode != 0:
            update_task_log(f"[ERREUR] La génération a échoué (Code retour : {proc.returncode}).")
            set_task_status('failed')
            return
    except Exception as e:
        update_task_log(f"[ERREUR] Exception durant la génération : {str(e)}")
        set_task_status('failed')
        return

    update_task_log("[INFO] Dashboard et animations créés avec succès !")
    set_task_progress(100)
    set_task_status('completed')


def main():
    # Force the working directory to the server directory so index.html are found properly
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    os.chdir(base_dir)

    port = 8080
    server_address = ('', port)
    
    # Enable quick server port reuse to avoid Socket Errors on restarts
    class StoppableHTTPServer(HTTPServer):
        def server_bind(self):
            import socket
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            super().server_bind()

    httpd = StoppableHTTPServer(server_address, MPPDashboardServer)
    
    print("\n=========================================================")
    print("    🚀 SERVEUR DE DASHBOARD MPP INTÉGRÉ DÉMARRÉ AVEC SUCCÈS !")
    print(f"    Rendez-vous à l'adresse suivante :")
    print(f"    👉  http://localhost:{port}")
    print("=========================================================\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        httpd.server_close()

if __name__ == '__main__':
    main()
