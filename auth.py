import webbrowser
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import binascii
import logging
import requests

import api
import config

AUTH_CODE = None
OAUTH_STATE = None

def generate_oauth_state():
    return binascii.hexlify(os.urandom(16)).decode()

def get_auth_url(client_id, state):
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
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            global AUTH_CODE, OAUTH_STATE
            parsed_path = urlparse(self.path)
            query = parse_qs(parsed_path.query)
            
            AUTH_CODE = query.get('code', [None])[0]
            received_state = query.get('state', [None])[0]

            if received_state == OAUTH_STATE:
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window.</p>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"<h1>Authentication failed: State mismatch.</h1>")

    server_address = ('localhost', 8888)
    httpd = HTTPServer(server_address, CallbackHandler)
    httpd.handle_request()

class AuthManager:
    def __init__(self, main_app):
        self.main_app = main_app
        self.character_info = {}
        self.load_state()

    def load_state(self):
        char_id = self.main_app.get_config_value('character_id')
        char_name = self.main_app.get_config_value('character_name')
        if char_id and char_name:
            self.character_info = {'id': char_id, 'name': char_name}

    def start_full_auth_flow(self):
        global OAUTH_STATE, AUTH_CODE
        AUTH_CODE = None 
        OAUTH_STATE = generate_oauth_state()
        client_id = self.main_app.get_config_value('client_id')
        if not client_id:
            self.main_app.log_message("Error: CLIENT_ID is not set in config.")
            return False

        auth_url = get_auth_url(client_id, OAUTH_STATE)
        webbrowser.open(auth_url)
        
        server_thread = threading.Thread(target=run_callback_server)
        server_thread.daemon = True
        server_thread.start()
        server_thread.join(timeout=120)

        if AUTH_CODE:
            return self.exchange_code_for_token(AUTH_CODE)
        return False

    def exchange_code_for_token(self, auth_code):
        client_id = self.main_app.get_config_value('client_id')
        url = "https://login.eveonline.com/v2/oauth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Host": "login.eveonline.com"}
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": client_id,
        }
        response = requests.post(url, headers=headers, data=data)
        
        if response.status_code == 200:
            tokens = response.json()
            self.main_app.set_config_value('access_token', tokens['access_token'])
            self.main_app.set_config_value('refresh_token', tokens['refresh_token'])
            expiry = (datetime.now(timezone.utc) + timedelta(seconds=tokens['expires_in'])).isoformat()
            self.main_app.set_config_value('token_expiry', expiry)
            return self.fetch_character_id_and_name()
        else:
            logging.error(f"Token exchange failed: {response.status_code} - {response.text}")
            return False

    def get_valid_token(self):
        expiry_str = self.main_app.get_config_value('token_expiry')
        if not expiry_str: 
            return None
        
        # Parse the string into a datetime object
        expiry_time = datetime.fromisoformat(expiry_str)
        
        # --- KORRIGERING HER ---
        # If the parsed time is naive (no timezone), assume it's UTC and make it aware.
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
        # ----------------------

        # Now both are guaranteed to be offset-aware for comparison
        if datetime.now(timezone.utc) >= expiry_time:
            if not self.refresh_token_if_needed():
                return None
        
        return self.main_app.get_config_value('access_token')

    def refresh_token_if_needed(self):
        refresh_token = self.main_app.get_config_value('refresh_token')
        if not refresh_token: return False

        client_id = self.main_app.get_config_value('client_id')
        url = "https://login.eveonline.com/v2/oauth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Host": "login.eveonline.com"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }
        response = requests.post(url, headers=headers, data=data)
        if response.status_code == 200:
            tokens = response.json()
            self.main_app.set_config_value('access_token', tokens['access_token'])
            if 'refresh_token' in tokens:
                self.main_app.set_config_value('refresh_token', tokens['refresh_token'])
            expiry = (datetime.now(timezone.utc) + timedelta(seconds=tokens['expires_in'])).isoformat()
            self.main_app.set_config_value('token_expiry', expiry)
            return True
        else:
            self.logout()
            return False

    def fetch_character_id_and_name(self):
        token = self.get_valid_token()
        if not token: return False

        char_data = api.verify_token_and_get_character(token)
        if char_data and char_data.get('id'):
            self.character_info = char_data
            self.main_app.set_config_value('character_id', char_data['id'])
            self.main_app.set_config_value('character_name', char_data['name'])
            return True
        
        self.logout()
        return False

    def logout(self):
        self.character_info = {}
        for key in ['access_token', 'refresh_token', 'token_expiry', 'character_id', 'character_name']:
            self.main_app.set_config_value(key, None)