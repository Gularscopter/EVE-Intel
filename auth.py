import base64
import webbrowser
import requests
import logging
import config
from urllib.parse import urlencode, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Globale variabler for å håndtere server-callback
auth_code_holder = [None]
auth_server = [None]

class CallbackHandler(BaseHTTPRequestHandler):
    """En enkel HTTP-server for å fange opp callback fra EVE SSO."""
    def do_GET(self):
        if 'code' in self.path:
            parsed_path = parse_qs(self.path.split('?', 1)[1])
            auth_code_holder[0] = parsed_path['code'][0]
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>Authentication Successful</h1><p>You can close this window and return to the application.</p>")
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>Authentication Failed</h1><p>Could not retrieve authorization code.</p>")
        
        threading.Thread(target=lambda: auth_server[0].shutdown()).start()

def _run_callback_server():
    """Starter den midlertidige webserveren."""
    server_address = ('localhost', 8888)
    auth_server[0] = HTTPServer(server_address, CallbackHandler)
    logging.info("Starting temporary server on http://localhost:8888 for SSO callback...")
    auth_server[0].serve_forever()

def _fetch_access_token(code):
    """Bytter autorisasjonskode mot et access token."""
    client_id = config.get_config_value("CLIENT_ID")
    client_secret = config.get_config_value("CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("CLIENT_ID or CLIENT_SECRET is not set in config.")
        return None

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com"
    }
    data = {"grant_type": "authorization_code", "code": code}

    try:
        response = requests.post("https://login.eveonline.com/v2/oauth/token", headers=headers, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching access token: {e.response.text if e.response else e}")
        return None

def refresh_access_token(refresh_token):
    """Fornyer et utløpt access token ved hjelp av et refresh token."""
    client_id = config.get_config_value("CLIENT_ID")
    client_secret = config.get_config_value("CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("CLIENT_ID or CLIENT_SECRET is not set in config.")
        return None

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com"
    }
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    
    try:
        response = requests.post("https://login.eveonline.com/v2/oauth/token", headers=headers, data=data)
        response.raise_for_status()
        new_token_data = response.json()
        new_token_data['refresh_token'] = refresh_token
        return new_token_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error refreshing access token: {e.response.text if e.response else e}")
        return None

def authenticate_and_get_token():
    """Hovedfunksjon for autentisering. Kjører hele flyten."""
    client_id = config.get_config_value("CLIENT_ID")
    if not client_id:
        logging.error("CLIENT_ID not found in configuration. Please set it in the Settings tab.")
        return None

    # *** LISTEN ER NÅ OPPDATERT MED EKSAKTE NAVN FRA BILDET DITT ***
    scopes = [
        "publicData",
        "esi-location.read_location.v1",
        "esi-location.read_ship_type.v1",
        "esi-wallet.read_character_wallet.v1",
        "esi-search.search_structures.v1",
        "esi-universe.read_structures.v1",
        "esi-assets.read_assets.v1",
        "esi-ui.open_window.v1",
        "esi-markets.structure_markets.v1",
        "esi-industry.read_character_jobs.v1",
        "esi-markets.read_character_orders.v1",
        "esi-location.read_online.v1",
        "esi-industry.read_corporation_jobs.v1",
        "esi-industry.read_character_mining.v1",
        "esi-industry.read_corporation_mining.v1"
    ]

    params = {
        "response_type": "code", "redirect_uri": "http://localhost:8888/callback",
        "client_id": client_id, "scope": " ".join(scopes), "state": "eve-intel-sso"
    }
    auth_url = f"https://login.eveonline.com/v2/oauth/authorize/?{urlencode(params)}"
    
    logging.info("Opening browser for EVE SSO authentication...")
    webbrowser.open(auth_url)
    
    _run_callback_server()
    
    if auth_code_holder[0]:
        logging.info("Authorization code received. Fetching access token...")
        return _fetch_access_token(auth_code_holder[0])
    else:
        logging.error("Authentication failed: No authorization code was received from server.")
        return None
