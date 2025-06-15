# ==============================================================================
# EVE MARKET VERKTØY - AUTENTISERINGSMODUL
# ==============================================================================
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import secrets

# Globale variabler for OAuth-flyt
OAUTH_SERVER = None
AUTH_CODE = None
OAUTH_STATE = None

def generate_oauth_state():
    """Genererer en sikker, tilfeldig state-string for CSRF-beskyttelse."""
    return secrets.token_urlsafe(16)

def get_auth_url(client_id, state):
    """Bygger ESI-autentiserings-URLen med alle nødvendige scopes."""
    # ENDRET: Fjernet det unødvendige journal-scopet, da wallet-scopet dekker alt.
    scopes = (
        "publicData "
        "esi-markets.read_character_orders.v1 "
        "esi-wallet.read_character_wallet.v1 " # Dekker balanse, transaksjoner OG journal
        "esi-ui.open_window.v1 "
        "esi-assets.read_assets.v1 "
        "esi-universe.read_structures.v1 "
        "esi-markets.structure_markets.v1 "
        "esi-location.read_ship_type.v1 " # NY: For å se aktivt skip
        "esi-location.read_location.v1"   # NY: For å se hvor skipet er
    )
    callback_url = "http://localhost:8888/callback"
    return f"https://login.eveonline.com/v2/oauth/authorize/?response_type=code&redirect_uri={callback_url}&client_id={client_id}&scope={scopes.replace(' ', '%20')}&state={state}"

class CallbackHandler(BaseHTTPRequestHandler):
    """Håndterer callback fra EVE SSO."""
    def do_GET(self):
        global AUTH_CODE, OAUTH_STATE
        
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        received_state = query_params.get('state', [None])[0]

        if OAUTH_STATE is None or received_state != OAUTH_STATE:
            self.send_response(403)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Autentiseringsfeil</h1><p>Ugyldig 'state'. Pr&oslash;v &aring; logge inn p&aring; nytt.</p>")
            AUTH_CODE = None
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Autentisering vellykket!</h1><p>Du kan n&aring; lukke dette vinduet.</p>")
        
        AUTH_CODE = query_params.get('code', [None])[0]
    
    def log_message(self, format, *args):
        return

def run_callback_server():
    """Starter, håndterer ett request, og stopper den lokale webserveren."""
    global OAUTH_SERVER
    if OAUTH_SERVER: return
    
    try:
        OAUTH_SERVER = HTTPServer(('localhost', 8888), CallbackHandler)
        OAUTH_SERVER.handle_request()
        OAUTH_SERVER.server_close()
        OAUTH_SERVER = None
    except Exception as e:
        print(f"Feil i callback-server: {e}")
        OAUTH_SERVER = None