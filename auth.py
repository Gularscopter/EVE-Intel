# ==============================================================================
# EVE INTEL - AUTHENTICATION MODULE
# ==============================================================================
import webbrowser
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import binascii

# Interne importer
import api
import config

# Globale variabler for den lokale webserveren som håndterer OAuth callback.
# Disse er nødvendige fordi serveren kjører i sin egen tråd.
AUTH_CODE = None
OAUTH_STATE = None

def generate_oauth_state():
    """Genererer en sikker, tilfeldig state-string for OAuth2-flyten."""
    return binascii.hexlify(os.urandom(16)).decode()

def get_auth_url(client_id, state):
    """Bygger den fullstendige URL-en brukeren sendes til for å logge inn."""
    base_url = "https://login.eveonline.com/v2/oauth/authorize/"
    params = {
        "response_type": "code",
        "redirect_uri": "http://localhost:8888/callback",
        "client_id": client_id,
        "scope": config.EVE_SCOPES,
        "state": state
    }
    return f"{base_url}?{urlencode(params)}"

def run_callback_server():
    """Starter en enkel, lokal HTTP-server for å motta callback fra EVE Online."""
    
    class CallbackHandler(BaseHTTPRequestHandler):
        """Håndterer GET-requesten fra EVE etter innlogging."""
        def do_GET(self):
            global AUTH_CODE, OAUTH_STATE
            try:
                if self.path.startswith("/callback"):
                    query_string = self.path.split('?', 1)[-1]
                    params = dict(p.split('=') for p in query_string.split('&'))
                    
                    if params.get('state') == OAUTH_STATE:
                        AUTH_CODE = params.get('code')
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(
                            b"<html><head><title>Innlogging Vellykket</title>"
                            b"<style>body { font-family: sans-serif; background-color: #1a1a1a; color: #f0f0f0; text-align: center; padding-top: 50px; }</style></head>"
                            b"<body><h1>Innlogging vellykket!</h1>"
                            b"<p>Du kan n\xc3\xa5 lukke dette vinduet og g\xc3\xa5 tilbake til EVE Intel-applikasjonen.</p></body></html>"
                        )
                        # Stopper serveren i en egen tråd for å unngå at den henger
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                    else:
                        self.send_error(400, "State mismatch. Prøv igjen.")
                else:
                    self.send_error(404, "Not Found")
            except Exception:
                self.send_error(500, "Internal Server Error")

    server_address = ('localhost', 8888)
    # Tillat gjenbruk av adressen for å unngå feil ved rask omstart
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(server_address, CallbackHandler)
    httpd.serve_forever()

class AuthManager:
    """
    Håndterer ESI OAuth2-flyt, token-lagring og fornyelse.
    Dette sentraliserer all autentiseringslogikk.
    """
    def __init__(self, settings_instance):
        """
        Initialiserer AuthManager.
        :param settings_instance: En referanse til hovedapplikasjonens settings-dictionary.
        """
        self.settings = settings_instance
        self.character_info = {}

    @property
    def client_id(self):
        """Henter client_id trygt fra settings."""
        return self.settings.get('esi_client_id')
        
    @property
    def secret_key(self):
        """Henter secret_key trygt fra settings."""
        return self.settings.get('esi_secret_key')

    def is_token_valid(self):
        """Sjekker om det nåværende access_token er gyldig (ikke utløpt)."""
        expiry_str = self.settings.get("token_expiry")
        if not expiry_str:
            return False
        try:
            # Utløpstiden lagres som en ISO-formatert streng.
            expiry_dt = datetime.fromisoformat(expiry_str)
            # Sammenligner med nåværende UTC-tid.
            return expiry_dt > datetime.utcnow()
        except ValueError:
            return False

    def get_valid_token(self):
        """
        Returnerer et gyldig access token. Fornyer det automatisk om nødvendig.
        Dette er hovedmetoden som resten av appen bruker for å få et token.
        """
        if self.is_token_valid():
            return self.settings.get('access_token')
        
        # Hvis tokenet er utløpt, prøv å fornye det
        if self.settings.get("refresh_token"):
            if self.refresh_access_token():
                return self.settings.get('access_token')
        
        # Hvis ingen gyldig token kan skaffes, returner None
        return None

    def start_oauth_flow(self, status_callback):
        """
        Starter OAuth-prosessen ved å åpne nettleseren for brukeren.
        :param status_callback: En funksjon for å sende statusoppdateringer til UI.
        """
        if not self.client_id or not self.secret_key:
            return False, "ESI Client ID og/eller Secret Key mangler i innstillingene."
        
        global AUTH_CODE, OAUTH_STATE
        AUTH_CODE = None  # Nullstill eventuell gammel kode
        OAUTH_STATE = generate_oauth_state()
        
        auth_url = get_auth_url(self.client_id, OAUTH_STATE)
        webbrowser.open(auth_url)
        status_callback("Venter på EVE Online-innlogging i nettleseren din...")
        
        # Start den lokale serveren for å fange opp callback i en egen tråd
        threading.Thread(target=run_callback_server, daemon=True).start()
        return True, "OAuth-prosess startet."

    def get_tokens_from_code(self, code):
        """Bytter en autorisasjonskode mottatt fra ESI mot access og refresh tokens."""
        tokens = api.fetch_tokens_from_code(self.client_id, self.secret_key, code)
        if tokens:
            self.settings['access_token'] = tokens['access_token']
            self.settings['refresh_token'] = tokens['refresh_token']
            # Beregn og lagre utløpstiden for tokenet
            self.settings['token_expiry'] = (datetime.utcnow() + timedelta(seconds=tokens['expires_in'])).isoformat()
            return True
        return False

    def refresh_access_token(self):
        """Fornyer access token ved hjelp av det lagrede refresh token."""
        refresh_token = self.settings.get("refresh_token")
        if not refresh_token:
            return False

        tokens = api.refresh_esi_tokens(self.client_id, self.secret_key, refresh_token)
        if tokens:
            self.settings['access_token'] = tokens['access_token']
            # ESI returnerer ikke alltid et nytt refresh token. Behold det gamle om det mangler.
            if 'refresh_token' in tokens:
                self.settings['refresh_token'] = tokens['refresh_token']
            self.settings['token_expiry'] = (datetime.utcnow() + timedelta(seconds=tokens['expires_in'])).isoformat()
            return True
        else:
            # Hvis fornyelse feiler (f.eks. refresh token er utløpt), nullstill alt.
            self.logout()
            return False
            
    def fetch_character_id_and_name(self):
        """Henter karakter-ID og navn ved hjelp av et gyldig token og lagrer det."""
        token = self.get_valid_token()
        if not token:
            return False

        response = api.fetch_esi_data("https://esi.evetech.net/verify/?datasource=tranquility", token=token)
        char_data = response.json() if response else None

        if char_data and 'CharacterID' in char_data:
            self.character_info = {'id': char_data['CharacterID'], 'name': char_data['CharacterName']}
            return True
        
        # Hvis verifisering feiler, logg ut
        self.logout()
        return False
        
    def logout(self):
        """Nullstiller all autentiserings- og karakterdata."""
        for key in ['access_token', 'refresh_token', 'token_expiry']:
            if key in self.settings:
                self.settings[key] = None
        self.character_info = {}
