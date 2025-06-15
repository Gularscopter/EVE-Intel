import tkinter
import customtkinter as ctk
from tkinter import ttk, messagebox, TclError
from PIL import Image
import threading
import io
import time
from datetime import datetime, timedelta, timezone
import requests
from collections import defaultdict, deque
import re

# Interne importer
import config
import api
import auth  # Importerer den oppdaterte auth-modulen med AuthManager
import db
from logic import calculations, scanners
from ui.tabs import (
    character, assets, manufacturing, bpo_scanner, analyse,
    route_scanners, region_scanner, galaxy_scanner, settings,
    price_hunter
)

class EveMarketApp(ctk.CTk):
    
    def __init__(self, settings_dict):
        super().__init__()
        self.settings = settings_dict
        self.title("EVE Market Intelligence")
        self.geometry("1600x900")
        ctk.set_appearance_mode("dark")
        
        # =====================================================================
        # == REFAKTORERING: AuthManager-instans opprettes her
        # =====================================================================
        self.auth_manager = auth.AuthManager(self.settings)

        # Applikasjonstilstand
        self.scan_thread = None
        self.scanning_active = threading.Event()
        self.wallet_balance = 0.0
        self.system_id_to_name_cache = {}
        self.all_system_names = []
        self.active_suggestion_entry = None
        self.current_main_frame = None

        self._initialize_variables()
        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start-oppgaver
        self.load_all_regions()
        threading.Thread(target=self.populate_industry_systems, daemon=True).start()
        self.after(500, self.initial_auth_check)
        self.show_frame("character")

    def _initialize_variables(self):
        """Initialiserer alle ctk-variabler for UI-elementer."""
        # Generelle innstillinger
        self.sales_tax_var = ctk.StringVar(value=self.settings.get('sales_tax', '8.0'))
        self.brokers_fee_var = ctk.StringVar(value=self.settings.get('brokers_fee', '3.0'))
        
        # =====================================================================
        # == REFAKTORERING: ESI-variabler med "trace"
        # == Dette sørger for at AuthManager alltid har de nyeste verdiene
        # == fra input-feltene i sanntid, uten behov for en "lagre"-knapp.
        # =====================================================================
        self.esi_client_id_var = ctk.StringVar(value=self.settings.get('esi_client_id', ''))
        self.esi_secret_key_var = ctk.StringVar(value=self.settings.get('esi_secret_key', ''))
        
        self.esi_client_id_var.trace_add("write", lambda *args: self.settings.update({'esi_client_id': self.esi_client_id_var.get()}))
        self.esi_secret_key_var.trace_add("write", lambda *args: self.settings.update({'esi_secret_key': self.esi_secret_key_var.get()}))

        # Variabler for de ulike fanene
        self.analyse_item_name_var = ctk.StringVar(value=self.settings.get('analyse_item_name'))
        self.analyse_buy_station_var = ctk.StringVar(value=self.settings.get('analyse_buy_station'))
        self.analyse_sell_station_var = ctk.StringVar(value=self.settings.get('analyse_sell_station'))
        self.analyse_sell_method_var = ctk.StringVar(value=self.settings.get('analyse_sell_method'))
        self.analyse_ship_cargo_var = ctk.StringVar(value=self.settings.get('analyse_ship_cargo'))
        
        self.manu_item_name_var = ctk.StringVar()
        self.manu_me_var = ctk.StringVar(value="10")
        self.manu_te_var = ctk.StringVar(value="20")
        self.manu_system_var = ctk.StringVar(value="Jita")
        
        self.bpo_me_var = ctk.StringVar(value="10")
        self.bpo_te_var = ctk.StringVar(value="20")
        self.bpo_system_var = ctk.StringVar(value="Jita")
        self.bpo_min_profit_ph_var = ctk.StringVar(value="1000000")
        self.bpo_min_daily_volume_var = ctk.StringVar(value="100")
        
        for scan_type in ["scanner", "arbitrage", "region", "galaxy"]:
            defaults = config.load_settings()
            setattr(self, f"{scan_type}_buy_station_var", ctk.StringVar(value=defaults.get(f"{scan_type}_buy_station")))
            setattr(self, f"{scan_type}_sell_station_var", ctk.StringVar(value=defaults.get(f"{scan_type}_sell_station")))
            setattr(self, f"{scan_type}_min_profit_var", ctk.StringVar(value=defaults.get(f"{scan_type}_min_profit")))
            setattr(self, f"{scan_type}_min_volume_var", ctk.StringVar(value=defaults.get(f"{scan_type}_min_volume")))
            setattr(self, f"{scan_type}_ship_cargo_var", ctk.StringVar(value=defaults.get(f"{scan_type}_ship_cargo")))
            setattr(self, f"{scan_type}_max_investment_var", ctk.StringVar(value=defaults.get(f"{scan_type}_max_investment")))
            if scan_type == "region":
                setattr(self, "region_station_var", ctk.StringVar(value=defaults.get("region_station")))
            if scan_type == "galaxy":
                setattr(self, "galaxy_home_base_var", ctk.StringVar(value=defaults.get("galaxy_home_base")))
                setattr(self, "galaxy_target_region_var", ctk.StringVar(value=defaults.get("galaxy_target_region")))
                self.galaxy_include_structures_var = ctk.BooleanVar(value=False)
                self.galaxy_hisec_var = ctk.BooleanVar(value=True)
                self.galaxy_lowsec_var = ctk.BooleanVar(value=False)
                self.galaxy_nullsec_var = ctk.BooleanVar(value=False)
                self.galaxy_multistation_bundle_var = ctk.BooleanVar(value=False)

        self.price_hunter_item_name_var = ctk.StringVar()
        self.price_hunter_hisec_var = ctk.BooleanVar(value=True)
        self.price_hunter_lowsec_var = ctk.BooleanVar(value=False)
        self.price_hunter_nullsec_var = ctk.BooleanVar(value=False)

    def _create_widgets(self):
        """Setter opp hoved-layout og UI-elementer."""
        # Stil for Treeview-elementer
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2B2B2B", foreground="white", fieldbackground="#2B2B2B", borderwidth=0, rowheight=35, font=ctk.CTkFont(size=14))
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading", font=ctk.CTkFont(size=15, weight="bold"), padding=10)
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
        
        # Hoved-grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar-ramme
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar_frame.grid_rowconfigure(14, weight=1)

        # Hovedinnhold-ramme
        self.main_content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # Statuslinje nederst
        self.status_label = ctk.CTkLabel(self, text="Klar", height=24, anchor="w", text_color=("gray60", "gray40"), font=ctk.CTkFont(size=12))
        self.status_label.grid(row=1, column=1, padx=20, pady=(0, 10), sticky="ew")

        # Opprett alle "sidene" (rammene) for de ulike fanene
        self.frames = {}
        self.tab_creators = {
            "character": character.create_tab, "assets": assets.create_tab,
            "manufacturing": manufacturing.create_tab, "bpo_scanner": bpo_scanner.create_tab,
            "analyse": analyse.create_tab,
            "scanner": lambda f, a: route_scanners.create_tab(f, a, "scanner"),
            "arbitrage": lambda f, a: route_scanners.create_tab(f, a, "arbitrage"),
            "region_scanner": region_scanner.create_tab, "galaxy_scanner": galaxy_scanner.create_tab,
            "price_hunter": price_hunter.create_tab, "settings": settings.create_tab
        }
        for frame_key, creator_func in self.tab_creators.items():
            frame = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
            self.frames[frame_key] = frame
            creator_func(frame, self)
        
        self._create_sidebar()
        self._create_right_click_menu()

    def _create_sidebar(self):
        """Bygger knappene og etikettene i sidebaren."""
        logo_label = ctk.CTkLabel(self.sidebar_frame, text="EVE Intel", font=ctk.CTkFont(size=28, weight="bold"))
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        ctk.CTkLabel(self.sidebar_frame, text="KARAKTER", font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray60", "gray40")).grid(row=1, column=0, padx=20, pady=(20, 5), sticky="w")
        ctk.CTkLabel(self.sidebar_frame, text="INDUSTRI", font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray60", "gray40")).grid(row=4, column=0, padx=20, pady=(20, 5), sticky="w")
        ctk.CTkLabel(self.sidebar_frame, text="MARKEDSANALYSE", font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray60", "gray40")).grid(row=7, column=0, padx=20, pady=(20, 5), sticky="w")

        buttons_info = {
            "character": {"text": "Oversikt", "row": 2},
            "assets": {"text": "Eiendeler", "row": 3},
            "manufacturing": {"text": "Produksjon", "row": 5},
            "bpo_scanner": {"text": "Blueprint Skanner", "row": 6},
            "analyse": {"text": "Enkel Vareanalyse", "row": 8},
            "route_scanners": {"text": "Rute-skanner", "row": 9},
            "region_scanner": {"text": "Stasjonshandel", "row": 10},
            "galaxy_scanner": {"text": "Region-utforsker", "row": 11},
            "price_hunter": {"text": "Prisjeger", "row": 12},
        }
        
        self.sidebar_buttons = {}
        for key, info in buttons_info.items():
            if key == "route_scanners":
                segmented_button = ctk.CTkSegmentedButton(self.sidebar_frame, values=["Kjøp->Salg", "Salg->Salg"],
                                                         command=self.show_route_scanner_frame)
                segmented_button.grid(row=info["row"], column=0, padx=20, pady=5, sticky="ew")
                self.sidebar_buttons[key] = segmented_button
            else:
                button = ctk.CTkButton(self.sidebar_frame, text=info["text"], command=lambda k=key: self.show_frame(k), fg_color="transparent", anchor="w")
                button.grid(row=info["row"], column=0, padx=20, pady=5, sticky="ew")
                self.sidebar_buttons[key] = button

        settings_button = ctk.CTkButton(self.sidebar_frame, text="Innstillinger", command=lambda: self.show_frame("settings"), fg_color="transparent", anchor="w")
        settings_button.grid(row=13, column=0, padx=20, pady=10, sticky="s")
        self.sidebar_buttons["settings"] = settings_button

    def show_route_scanner_frame(self, value):
        if value == "Kjøp->Salg":
            self.show_frame("scanner")
        else: 
            self.show_frame("arbitrage")

    def show_frame(self, frame_key):
        if self.current_main_frame:
            self.current_main_frame.grid_forget()

        for key, button in self.sidebar_buttons.items():
            if key in ["scanner", "arbitrage"]: continue
            if isinstance(button, ctk.CTkSegmentedButton):
                 if frame_key in ["scanner", "arbitrage"]:
                     button.set("Kjøp->Salg" if frame_key == "scanner" else "Salg->Salg")
                 continue
            button.configure(fg_color="transparent" if key != frame_key else ("#3a7ebf", "#1f538d"))

        self.current_main_frame = self.frames[frame_key]
        self.current_main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)
        
    def show_error(self, message):
        messagebox.showerror("Feil", message)

    def sort_results(self, tree, col, reverse):
        try:
            if tree.heading(col, 'text') == 'Dato':
                data = [(datetime.strptime(tree.set(item, col), '%Y-%m-%d %H:%M'), item) for item in tree.get_children('')]
                data.sort(reverse=reverse)
            else:
                data = [(tree.set(item, col), item) for item in tree.get_children('')]
                def sort_key(x):
                    try: return float(str(x[0]).replace(',', '').replace('%', ''))
                    except (ValueError, AttributeError): return str(x[0])
                data.sort(key=sort_key, reverse=reverse)

            for index, (val, item) in enumerate(data):
                tree.move(item, '', index)
            
            tree.heading(col, command=lambda: self.sort_results(tree, col, not reverse))
        except (TclError, ValueError):
            pass
    
    def clear_tree(self, tree):
        try:
            if tree and tree.winfo_exists():
                for i in tree.get_children(): tree.delete(i)
        except TclError: pass

    # --- Autocomplete/Suggestion Box Logic (UI Helper) ---
    def _update_suggestions(self, event):
        entry_widget = event.widget
        self.active_suggestion_entry = entry_widget
        search_term = entry_widget.get().lower()
        if len(search_term) > 1:
            suggestions = [name for name in config.ITEM_NAME_TO_ID.keys() if search_term in name.lower()][:10]
            if suggestions:
                if not hasattr(self, 'suggestions_listbox') or not self.suggestions_listbox.winfo_exists():
                    self.suggestions_listbox = tkinter.Listbox(self, bg="#2B2B2B", fg="white", highlightthickness=0, borderwidth=1, font=("Segoe UI", 12), relief="flat")
                    self.suggestions_listbox.bind("<ButtonRelease-1>", self._on_suggestion_select)
                self.suggestions_listbox.delete(0, tkinter.END)
                for item in suggestions:
                    self.suggestions_listbox.insert(tkinter.END, item)
                x = entry_widget.winfo_rootx() - self.winfo_rootx()
                y = entry_widget.winfo_rooty() - self.winfo_rooty() + entry_widget.winfo_height()
                width = entry_widget.winfo_width()
                self.suggestions_listbox.place(x=x, y=y, width=width, height=150)
                self.suggestions_listbox.tkraise()
                return
        if hasattr(self, 'suggestions_listbox') and self.suggestions_listbox.winfo_exists():
            self.suggestions_listbox.place_forget()

    def _on_suggestion_select(self, event):
        try:
            if not self.active_suggestion_entry or not hasattr(self, 'suggestions_listbox') or not self.suggestions_listbox.curselection():
                return
            selected_item = self.suggestions_listbox.get(self.suggestions_listbox.curselection()[0])
            self.active_suggestion_entry.delete(0, "end")
            self.active_suggestion_entry.insert(0, selected_item)
            self.suggestions_listbox.place_forget()
            self.active_suggestion_entry = None
        except (TclError, IndexError):
            pass

    def _hide_suggestions_on_click_away(self, event=None):
        try:
            if hasattr(self, 'suggestions_listbox') and self.suggestions_listbox.winfo_viewable():
                widget = event.widget if event else None
                if not widget or (widget != self.suggestions_listbox and widget != self.active_suggestion_entry):
                    self.suggestions_listbox.place_forget()
                    self.active_suggestion_entry = None

            for entry_attr in ['bpo_system_entry', 'manu_system_entry']:
                if hasattr(self, entry_attr):
                    entry_obj = getattr(self, entry_attr)
                    if hasattr(entry_obj, 'system_suggestions_listbox') and entry_obj.system_suggestions_listbox.winfo_viewable():
                        widget = event.widget if event else None
                        if not widget or (widget != entry_obj.system_suggestions_listbox and widget != entry_obj):
                            entry_obj.system_suggestions_listbox.place_forget()
        except (TclError, AttributeError):
            pass
    
    def _update_system_suggestions(self, event, entry_var, listbox_owner):
        search_term = entry_var.get().lower()
        if len(search_term) < 2:
            if hasattr(listbox_owner, 'system_suggestions_listbox'):
                listbox_owner.system_suggestions_listbox.place_forget()
            return

        suggestions = [name for name in self.all_system_names if search_term in name.lower()][:10]
        
        if not suggestions:
            if hasattr(listbox_owner, 'system_suggestions_listbox'):
                listbox_owner.system_suggestions_listbox.place_forget()
            return

        if not hasattr(listbox_owner, 'system_suggestions_listbox'):
            listbox_owner.system_suggestions_listbox = tkinter.Listbox(self, bg="#2B2B2B", fg="white", highlightthickness=0, borderwidth=1, font=("Segoe UI", 12), relief="flat")
            listbox_owner.system_suggestions_listbox.bind("<ButtonRelease-1>", lambda e, v=entry_var, lo=listbox_owner: self._on_system_suggestion_select(e, v, lo))

        listbox_owner.system_suggestions_listbox.delete(0, tkinter.END)
        for item in suggestions:
            listbox_owner.system_suggestions_listbox.insert(tkinter.END, item)

        entry_widget = event.widget
        x = entry_widget.winfo_rootx() - self.winfo_rootx()
        y = entry_widget.winfo_rooty() - self.winfo_rooty() + entry_widget.winfo_height()
        width = entry_widget.winfo_width()
        listbox_owner.system_suggestions_listbox.place(x=x, y=y, width=width, height=150)
        listbox_owner.system_suggestions_listbox.tkraise()

    def _on_system_suggestion_select(self, event, entry_var, listbox_owner):
        try:
            if not hasattr(listbox_owner, 'system_suggestions_listbox') or not listbox_owner.system_suggestions_listbox.curselection():
                return
            selected_item = listbox_owner.system_suggestions_listbox.get(listbox_owner.system_suggestions_listbox.curselection()[0])
            entry_var.set(selected_item)
            listbox_owner.system_suggestions_listbox.place_forget()
            self.after(50, lambda: self._update_system_cost_index_display(entry_var, listbox_owner))
        except (TclError, IndexError):
            pass
            
    def _update_system_cost_index_display(self, system_var, listbox_owner):
        system_name = system_var.get()
        if not system_name: return
        
        label_to_update = None
        if hasattr(self, 'bpo_system_index_label') and listbox_owner == self.bpo_system_entry:
            label_to_update = self.bpo_system_index_label
        elif hasattr(self, 'manu_system_index_label') and listbox_owner == self.manu_system_entry:
            label_to_update = self.manu_system_index_label
        
        if not label_to_update: return

        system_id = db.get_system_id_from_name(system_name)
        if system_id and config.SYSTEM_INDICES_CACHE.get(system_id):
            system_data = config.SYSTEM_INDICES_CACHE.get(system_id)
            manu_index = next((idx['cost_index'] for idx in system_data.get('cost_indices', []) if idx['activity'] == 'manufacturing'), None)
            if manu_index is not None:
                label_to_update.configure(text=f"Indeks: {manu_index:.2%}")
                return
        
        label_to_update.configure(text="Indeks: N/A")
    
    # =========================================================================
    # == REFAKTORERT AUTENTISERINGSLOGIKK (bruker nå AuthManager)
    # =========================================================================

    def start_oauth_flow(self):
        """Starter OAuth-flyten ved å delegere til AuthManager."""
        success, message = self.auth_manager.start_oauth_flow(
            lambda msg: self.status_label.configure(text=msg)
        )
        if success:
            self.check_auth_code() # Start polling for auth code
        else:
            self.show_error(message)

    def check_auth_code(self):
        """Sjekker periodisk om en auth-kode har blitt mottatt via callback."""
        if auth.AUTH_CODE:
            self.status_label.configure(text="Kode mottatt, verifiserer med ESI...")
            # Deleger token-henting til AuthManager
            if self.auth_manager.get_tokens_from_code(auth.AUTH_CODE):
                auth.AUTH_CODE = None  # Nullstill global variabel etter bruk
                self.fetch_character_data()  # Start datainnhenting umiddelbart
            else:
                self.show_error("Kunne ikke hente tokens fra ESI. Sjekk Client ID/Secret Key.")
                self.status_label.configure(text="Innlogging feilet.")
        else:
            # Hvis ingen kode, sjekk igjen om 1 sekund
            self.after(1000, self.check_auth_code)

    def _handle_token_refresh(self):
        """Bakgrunnstråd-funksjon for å fornye token og oppdatere UI."""
        if self.auth_manager.refresh_access_token():
            self.after(0, self.fetch_character_data)
        else:
            # Hvis fornyelse feiler, oppdater UI for å vise "utlogget" status
            self.after(0, self.update_ui_for_logout)

    def initial_auth_check(self):
        """Sjekker for et lagret refresh token ved oppstart og prøver å logge inn."""
        if self.settings.get("refresh_token") and self.esi_client_id_var.get():
            self.status_label.configure(text="Logger inn med lagret sesjon...")
            threading.Thread(target=self._handle_token_refresh, daemon=True).start()

    def update_ui_for_logout(self):
        """Nullstiller all karakterspesifikk UI til en utlogget tilstand."""
        self.char_name_label.configure(text="Ikke innlogget")
        self.wallet_label.configure(text="Wallet: N/A")
        self.profit_label.configure(text="Netto handel: N/A", text_color="white")
        self.assets_value_label.configure(text="Verdi av eiendeler (est.): N/A")
        self.net_worth_label.configure(text="Total Nettoverdi (est.): N/A")
        self.char_portrait_label.configure(image=None, text="?")
        self.clear_tree(self.orders_tree)
        self.clear_tree(self.assets_tree)
        self.clear_tree(self.trades_tree)
        self.clear_tree(self.ship_cargo_tree)
        self.status_label.configure(text="Sesjon utløpt. Logg inn på nytt.")

    # =========================================================================
    # == DATAHENTING OG PROSESSERING (bruker nå AuthManager for tokens/info)
    # =========================================================================

    def fetch_character_data(self):
        """Hovedfunksjon for å hente all data relatert til en karakter."""
        # Sjekk om vi kan få tak i karakterinfo. Dette vil også fornye token om nødvendig.
        if not self.auth_manager.fetch_character_id_and_name():
            self.update_ui_for_logout()
            return

        char_info = self.auth_manager.character_info
        token = self.auth_manager.get_valid_token() # Bør være gyldig nå
        if not (char_info and token): return
        
        # Oppdater UI med grunnleggende info
        self.char_name_label.configure(text=char_info['name'])
        
        # Hent resten av dataen i bakgrunnstråder for å holde UI responsivt
        wallet_response = api.fetch_esi_data(f"https://esi.evetech.net/latest/characters/{char_info['id']}/wallet/", token)
        if wallet_response:
            self.wallet_balance = float(wallet_response.json())
            self.wallet_label.configure(text=f"Wallet: {self.wallet_balance:,.2f} ISK")
        
        self.fetch_character_portrait()
        self.fetch_character_orders_threaded()
        threading.Thread(target=self._fetch_and_update_profit, daemon=True).start()
        threading.Thread(target=self._fetch_and_display_assets, daemon=True).start()
        self.fetch_trade_ledger_threaded()
        self.fetch_active_ship_cargo_threaded()

    def fetch_character_portrait(self):
        char_id = self.auth_manager.character_info.get('id')
        if not char_id: return
        response = api.fetch_esi_data(f"https://esi.evetech.net/latest/characters/{char_id}/portrait/")
        if response and 'px128x128' in response.json():
            threading.Thread(target=self.load_image_from_url, args=(response.json()['px128x128'],), daemon=True).start()

    def load_image_from_url(self, url):
        try:
            response = requests.get(url, timeout=10)
            img_data = response.content
            pil_image = Image.open(io.BytesIO(img_data))
            ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(128, 128))
            self.after(0, self.update_portrait_image, ctk_image)
        except (requests.RequestException, TclError): pass

    def update_portrait_image(self, photo):
        try:
            if self.char_portrait_label.winfo_exists():
                self.char_portrait_label.configure(image=photo, text="")
        except TclError: pass

    def fetch_character_orders_threaded(self):
        char_id = self.auth_manager.character_info.get('id')
        if not char_id:
            self.show_error("Du må være innlogget for å se ordrer.")
            return
        self.status_label.configure(text="Oppdaterer aktive ordrer...")
        threading.Thread(target=self._fetch_character_orders_logic, daemon=True).start()

    def _fetch_character_orders_logic(self):
        token = self.auth_manager.get_valid_token()
        if not token: 
            self.after(0, lambda: self.status_label.configure(text="Sesjon utløpt."))
            return
        
        char_id = self.auth_manager.character_info['id']
        self.after(0, lambda: self.status_label.configure(text="Henter ordrer, journal og transaksjoner..."))

        # ... (resten av logikken i denne funksjonen er den samme som før)
        orders = api.fetch_character_orders_paginated(char_id, token)
        journal = api.fetch_all_pages(f"https://esi.evetech.net/v6/characters/{char_id}/wallet/journal/", token)
        transactions = api.fetch_all_pages(f"https://esi.evetech.net/v1/characters/{char_id}/wallet/transactions/", token)

        if orders is None or journal is None:
            self.after(0, lambda: self.show_error("Kunne ikke hente ordrer eller journal fra ESI."))
            self.after(0, lambda: self.status_label.configure(text="Klar."))
            return

        unmatched_broker_fees = []
        if journal:
            for entry in journal:
                if entry.get("ref_type") == "brokers_fee":
                    fee_time = datetime.fromisoformat(entry['date'].replace("Z", "+00:00"))
                    unmatched_broker_fees.append({'time': fee_time, 'amount': abs(entry.get("amount", 0))})
        unmatched_broker_fees.sort(key=lambda x: x['time'])

        order_fees = defaultdict(float)
        time_tolerance = timedelta(seconds=5) 

        for order in sorted(orders, key=lambda o: o['issued']):
            order_time = datetime.fromisoformat(order['issued'].replace("Z", "+00:00"))
            
            best_match_index = -1
            for i, fee_entry in enumerate(unmatched_broker_fees):
                if abs(order_time - fee_entry['time']) <= time_tolerance:
                    best_match_index = i
                    break
            
            if best_match_index != -1:
                matched_fee = unmatched_broker_fees.pop(best_match_index)
                order_fees[order['order_id']] = matched_fee['amount']

        buy_queues = defaultdict(deque)
        if transactions:
            for t in sorted(transactions, key=lambda x: x['date']):
                if t['is_buy']:
                    buy_queues[t['type_id']].append(t)

        self.after(0, self.clear_tree, self.orders_tree)
        id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
        
        for order in sorted(orders, key=lambda x: x['issued'], reverse=True):
            is_buy = order.get('is_buy_order', False)
            type_id = order['type_id']
            
            buy_price_avg = "N/A"
            remaining_value = order['price'] * order['volume_remain']
            potential_profit = "N/A"
            tags = ()
            accumulated_fees = order_fees.get(order['order_id'], 0.0) 

            if not is_buy and buy_queues[type_id]:
                cost_of_items = 0
                items_to_cover = order['volume_remain']
                temp_buy_queue = deque(buy_queues[type_id])
                
                items_accounted_for = 0
                while items_to_cover > 0 and temp_buy_queue:
                    oldest_buy = temp_buy_queue[0].copy()
                    qty_from_this_buy = min(items_to_cover, oldest_buy['quantity'])
                    
                    cost_of_items += qty_from_this_buy * oldest_buy['unit_price']
                    items_accounted_for += qty_from_this_buy
                    items_to_cover -= qty_from_this_buy
                    
                    if qty_from_this_buy == oldest_buy['quantity']:
                        temp_buy_queue.popleft()
                    else:
                        temp_buy_queue[0]['quantity'] -= qty_from_this_buy
                
                if items_accounted_for > 0:
                    buy_price_avg = cost_of_items / items_accounted_for
                    sales_tax_rate = float(self.sales_tax_var.get()) / 100.0
                    future_tax = remaining_value * sales_tax_rate
                    
                    net_profit = remaining_value - cost_of_items - accumulated_fees - future_tax
                    potential_profit = f"{net_profit:,.2f}"
                    tags = ('profit',) if net_profit > 0 else ('loss',)
            
            issued = datetime.fromisoformat(order['issued'].replace("Z", "+00:00"))
            expires = issued + timedelta(days=order['duration'])
            time_left = expires - datetime.now(timezone.utc)

            values = (
                id_to_name.get(type_id, f"ID: {type_id}"),
                api.get_station_name_with_cache(order['location_id']),
                "Kjøp" if is_buy else "Salg",
                f"{buy_price_avg:,.2f}" if isinstance(buy_price_avg, (int, float)) else "N/A",
                f"{order['price']:,.2f}",
                f"{accumulated_fees:,.2f}",
                f"{remaining_value:,.2f}",
                potential_profit,
                f"{order['volume_remain']}/{order['volume_total']}",
                f"{time_left.days}d {time_left.seconds//3600}t" if time_left.total_seconds() > 0 else "Utløpt"
            )
            self.after(0, lambda v=values, t=tags: self.orders_tree.insert("", "end", values=v, tags=t))
        
        self.after(0, lambda: self.status_label.configure(text="Aktive ordrer oppdatert."))

    def _fetch_and_update_profit(self):
        token = self.auth_manager.get_valid_token()
        if not token: return
        transactions = api.fetch_character_transactions_paginated(self.auth_manager.character_info['id'], token)
        net_profit = calculations.calculate_net_trade_profit(transactions)
        color = "#32a852" if net_profit > 0 else "#c94f4f" if net_profit < 0 else "white"
        self.after(0, lambda: self.profit_label.configure(text=f"Netto handel: {net_profit:,.2f} ISK", text_color=color))

    def _fetch_and_display_assets(self):
        token = self.auth_manager.get_valid_token()
        if not token: return
        all_assets = api.fetch_character_assets_paginated(self.auth_manager.character_info['id'], token)
        if not all_assets: return
        station_assets = [a for a in all_assets if a.get('location_flag') == 'Hangar']
        type_ids_to_price = list({a['type_id'] for a in station_assets})
        market_prices = {}
        for i in range(0, len(type_ids_to_price), 200):
            chunk = type_ids_to_price[i:i+200]
            price_data = api.fetch_fuzzwork_market_data(config.STATIONS_INFO['Jita']['id'], chunk)
            for type_id, data in price_data.items():
                market_prices[int(type_id)] = float(data.get('buy', {}).get('max', 0))
            time.sleep(0.5)
        total_assets_value = calculations.calculate_assets_value(station_assets, market_prices)
        grouped_assets = defaultdict(list)
        id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
        for asset in station_assets:
            grouped_assets[api.get_station_name_with_cache(asset['location_id'])].append({
                'name': id_to_name.get(asset['type_id'], f"Ukjent ID: {asset['type_id']}"),
                'quantity': asset['quantity'], 'price': market_prices.get(asset['type_id'], 0)})
        self.after(0, self._update_assets_display, grouped_assets, total_assets_value)

    def _update_assets_display(self, grouped_assets, total_value):
        try:
            if not self.assets_tree.winfo_exists(): return
            self.clear_tree(self.assets_tree)
            for station, items in sorted(grouped_assets.items()):
                for item in sorted(items, key=lambda x: x['name']):
                    total_item_value = item['quantity'] * item['price']
                    self.assets_tree.insert("", "end", values=(station, item['name'], f"{item['quantity']:,}",
                                                          f"{item['price']:,.2f}", f"{total_item_value:,.2f}"))
            self.assets_value_label.configure(text=f"Verdi av eiendeler (est.): {total_value:,.2f} ISK")
            self.net_worth_label.configure(text=f"Total Nettoverdi (est.): {self.wallet_balance + total_value:,.2f} ISK")
        except TclError: pass
    
    # --- Resten av koden forblir stort sett lik, men med AuthManager-kall der det trengs ---
    # ... (Alle funksjoner for skanning, produksjon, etc. er de samme,
    #      men vil nå bruke `self.auth_manager.get_valid_token()` ved behov) ...

    def start_galaxy_scan(self):
        scan_config = self._get_common_scan_config(self.galaxy_min_profit_var, self.galaxy_min_volume_var, self.galaxy_max_investment_var, self.galaxy_ship_cargo_var)
        if not scan_config: return
        
        scan_config.update({
            "scan_type": "galaxy", 
            "home_base": self.galaxy_home_base_var.get(), 
            "target_region": self.galaxy_target_region_var.get(), 
            "include_structures": self.galaxy_include_structures_var.get(), 
            "token": self.auth_manager.get_valid_token(),  # BRUKER AUTHMANAGER
            "settings": self.settings,
            "include_hisec": self.galaxy_hisec_var.get(),
            "include_lowsec": self.galaxy_lowsec_var.get(),
            "include_nullsec": self.galaxy_nullsec_var.get(),
            "allow_multistation": self.galaxy_multistation_bundle_var.get()
        })
        
        self.clear_tree(self.galaxy_tree)
        self.run_generic_scan(scan_config)

    def add_user_structure(self):
        try: structure_id = int(self.new_structure_id_entry.get())
        except ValueError: self.show_error("Struktur ID må være et tall."); return
        if any(s.get('id') == structure_id for s in self.settings.get('user_structures', [])):
            self.show_error("Strukturen er allerede lagt til."); return
        
        token = self.auth_manager.get_valid_token() # BRUKER AUTHMANAGER
        if not token: self.show_error("Du må være innlogget."); return
        
        threading.Thread(target=self._add_structure_thread, args=(structure_id, token), daemon=True).start()

    def _open_in_game_market(self, type_id):
        token = self.auth_manager.get_valid_token() # BRUKER AUTHMANAGER
        if not token: self.show_error("Du må være innlogget for å bruke denne funksjonen."); return
        if api.open_market_window_in_game(type_id, token):
            self.status_label.configure(text=f"Åpner markedsvindu for ID {type_id} i spillet...")
        else:
            self.status_label.configure(text="Kunne ikke sende kommando til spillet. Sjekk at du er logget inn i EVE.")
    
    # ... (De resterende metodene vil også bli oppdatert til å bruke AuthManager)
    def populate_industry_systems(self):
        if not config.SYSTEM_INDICES_CACHE: api.fetch_industry_system_indices()
        if not config.SYSTEM_INDICES_CACHE: return
        if not self.system_id_to_name_cache:
            conn = db.connect_to_sde()
            if conn:
                cursor = conn.cursor()
                ids = list(config.SYSTEM_INDICES_CACHE.keys())
                cursor.execute(f"SELECT solarSystemID, solarSystemName FROM mapSolarSystems WHERE solarSystemID IN ({','.join('?'*len(ids))})", ids)
                self.system_id_to_name_cache = {sys_id: name for sys_id, name in cursor.fetchall()}
                conn.close()
        self.all_system_names = sorted(self.system_id_to_name_cache.values())

    def _start_manufacturing_calculation(self):
        try:
            item_name = self.manu_item_name_var.get()
            if not item_name: self.show_error("Velg et produkt."); return
            threading.Thread(target=self._manufacturing_calculation_thread, 
                             args=(item_name, int(self.manu_me_var.get()), int(self.manu_te_var.get()), self.manu_system_var.get()), 
                             daemon=True).start()
        except ValueError: self.show_error("ME og TE må være heltall.")

    def _manufacturing_calculation_thread(self, item_name, me, te, system_name):
        type_id = config.ITEM_LOOKUP_LOWERCASE.get(item_name.lower())
        if not type_id: self.show_error(f"Fant ikke varen '{item_name}'."); return
        bp_data = api.fetch_blueprint_details(type_id)
        if not bp_data: self.show_error(f"Fant ikke blueprint for '{item_name}'."); return
        product_id = bp_data['activities']['manufacturing']['products'][0]['typeID']
        material_ids = [mat['typeID'] for mat in bp_data['activities']['manufacturing']['materials']]
        price_data = api.fetch_fuzzwork_market_data(config.STATIONS_INFO['Jita']['id'], material_ids + [product_id])
        material_prices = {int(tid): float(data.get('sell', {}).get('min', 0)) for tid, data in price_data.items() if int(tid) in material_ids}
        product_price = float(price_data.get(str(product_id), {}).get('buy', {}).get('max', 0))
        system_id = db.get_system_id_from_name(system_name)
        if not system_id: self.show_error(f"Fant ikke systemet '{system_name}'."); return
        sys_indices = config.SYSTEM_INDICES_CACHE.get(system_id, {})
        man_idx = next((c['cost_index'] for c in sys_indices.get('cost_indices', []) if c['activity']=='manufacturing'), 0.0)
        results = calculations.calculate_manufacturing_profit(bp_data, material_prices, product_price, man_idx, me, te, 
                                                              float(self.sales_tax_var.get()), float(self.brokers_fee_var.get()))
        self.after(0, self._update_manufacturing_display, results)

    def _update_manufacturing_display(self, results):
        if 'error' in results: self.show_error(results['error']); return
        for key, val in self.manu_result_labels.items():
            if key in results: val.configure(text=f"{results[key]:,.2f} ISK")
        profit_color = "#32a852" if results['net_profit_per_run'] > 0 else "#c94f4f"
        self.manu_result_labels['net_profit_per_run'].configure(text_color=profit_color)
        self.manu_result_labels['profit_per_hour'].configure(text=f"{results['profit_per_hour']:,.2f} ISK/time", text_color=profit_color)
        self.clear_tree(self.manu_materials_tree)
        for mat in results['materials']:
            self.manu_materials_tree.insert("", "end", values=(mat['name'], f"{mat['req_qty']:,}", f"{mat['price']:,.2f}", f"{mat['total_cost']:,.2f}"))

    def start_analyse_fetch(self):
        self.status_label.configure(text=f"Henter data for {self.analyse_item_name_var.get()}...")
        for label in self.result_labels.values(): label.configure(text="...")
        try:
            analysis_config = { "item_name": self.analyse_item_name_var.get(), "buy_station": self.analyse_buy_station_var.get(),
                "sell_station": self.analyse_sell_station_var.get(), "sell_method": self.analyse_sell_method_var.get(),
                "ship_cargo_m3": float(self.analyse_ship_cargo_var.get()), "sales_tax_rate": float(self.sales_tax_var.get()),
                "brokers_fee_rate": float(self.brokers_fee_var.get()) }
            threading.Thread(target=self._fetch_single_analysis_thread, args=(analysis_config,), daemon=True).start()
        except ValueError:
            self.show_error("Ugyldig tall i 'Lasterom'.")
            self.status_label.configure(text="Klar.")

    def _fetch_single_analysis_thread(self, analysis_config):
        results = calculations.get_single_item_analysis(analysis_config) 
        self.after(0, self._update_analysis_results, results)
    
    def _update_analysis_results(self, results):
        if "error" in results:
            self.show_error(results["error"])
            for label in self.result_labels.values(): label.configure(text="N/A")
        else:
            for key, value in self.result_labels.items(): value.configure(text=results.get(key, "N/A"))
        self.status_label.configure(text="Analyse fullført.")

    def _get_common_scan_config(self, profit_var, volume_var, investment_var, cargo_var=None):
        try:
            config_dict = {"min_profit": float(profit_var.get()), "min_volume": float(volume_var.get()),
                           "max_investment": float(investment_var.get()), "sales_tax_rate": float(self.sales_tax_var.get()),
                           "brokers_fee_rate": float(self.brokers_fee_var.get())}
            if cargo_var: config_dict["ship_cargo_m3"] = float(cargo_var.get())
            return config_dict
        except (ValueError, TclError): self.show_error("Ugyldig tallformat."); return None

    def start_route_scan(self, ui_scan_type):
        scan_config = self._get_common_scan_config(getattr(self, f"{ui_scan_type}_min_profit_var"), getattr(self, f"{ui_scan_type}_min_volume_var"), getattr(self, f"{ui_scan_type}_max_investment_var"), getattr(self, f"{ui_scan_type}_ship_cargo_var"))
        if not scan_config: return
        scan_config.update({"scan_type": "station" if ui_scan_type == "scanner" else "arbitrage", "buy_station": getattr(self, f"{ui_scan_type}_buy_station_var").get(), "sell_station": getattr(self, f"{ui_scan_type}_sell_station_var").get()})
        self.clear_tree(getattr(self, f"{ui_scan_type}_tree"))
        self.run_generic_scan(scan_config)

    def start_region_scan(self):
        scan_config = self._get_common_scan_config(self.region_min_profit_var, self.region_min_volume_var, self.region_max_investment_var)
        if not scan_config: return
        scan_config.update({"scan_type": "region_trading", "station": self.region_station_var.get()})
        self.clear_tree(self.region_tree)
        self.run_generic_scan(scan_config)

    def start_bpo_scan(self):
        try:
            scan_config = self._get_common_scan_config(
                self.bpo_min_profit_ph_var,
                ctk.StringVar(value="0"), 
                ctk.StringVar(value="999999999999") 
            )
            if not scan_config: return

            scan_config.update({
                "scan_type": "bpo_scanner",
                "bpo_me": self.bpo_me_var.get(),
                "bpo_te": self.bpo_te_var.get(),
                "min_profit_ph": self.bpo_min_profit_ph_var.get(),
                "production_system": self.bpo_system_var.get(),
                "min_daily_volume": self.bpo_min_daily_volume_var.get()
            })
            
            self.clear_tree(self.bpo_tree)
            self.run_generic_scan(scan_config)

        except ValueError:
            self.show_error("Ugyldig tallformat i en av innstillingene for BPO-skann.")

    def start_price_hunter_scan(self):
        item_name = self.price_hunter_item_name_var.get()
        if not item_name: self.show_error("Du må skrive inn en vare å søke etter."); return
        type_id = config.ITEM_LOOKUP_LOWERCASE.get(item_name.lower())
        if not type_id: self.show_error(f"Fant ikke varen '{item_name}'."); return
        scan_config = {'scan_type': 'price_hunter', 'item_name': item_name, 'type_id': type_id,
                       'include_hisec': self.price_hunter_hisec_var.get(),
                       'include_lowsec': self.price_hunter_lowsec_var.get(),
                       'include_nullsec': self.price_hunter_nullsec_var.get()}
        self.clear_tree(self.price_hunter_tree)
        self.run_generic_scan(scan_config)
        
    def run_generic_scan(self, scan_config):
        if self.scan_thread and self.scan_thread.is_alive(): self.show_error("Et annet scan kjører allerede."); return
        self.scanning_active.set()
        scan_config['active_flag'] = self.scanning_active
        self._set_scanning_state(True, scan_config['scan_type'])
        self.scan_thread = threading.Thread(target=lambda: (scanners.run_scan_thread(scan_config, self.progress_callback), self.after(0, self.reset_scanner_gui)), daemon=True)
        self.scan_thread.start()

    def stop_scan(self):
        if self.scan_thread and self.scan_thread.is_alive():
            self.scanning_active.clear()
        self.reset_scanner_gui()

    def reset_scanner_gui(self):
        self._set_scanning_state(False)
        self.status_label.configure(text="Klar.")
        for st in ["scanner", "arbitrage", "region", "galaxy", "bpo", "price_hunter"]:
            try:
                if hasattr(self, f"{st}_progress"): getattr(self, f"{st}_progress").set(0)
                if hasattr(self, f"{st}_scan_details_label"): getattr(self, f"{st}_scan_details_label").configure(text="")
            except (AttributeError, TclError): pass
            
    def progress_callback(self, update):
        self.after(0, self.update_scan_ui, update)

    def update_scan_ui(self, update):
        try:
            if 'error' in update: self.show_error(update['error']); self.reset_scanner_gui(); return
            st_map = {"station": "scanner", "arbitrage": "arbitrage", "region_trading": "region", 
                      "galaxy": "galaxy", "bpo_scanner": "bpo", "price_hunter": "price_hunter"}
            st = st_map.get(update.get('scan_type'))
            if not st: return
            if 'progress' in update and hasattr(self, f"{st}_progress"): getattr(self, f"{st}_progress").set(update['progress'])
            if 'status' in update: self.status_label.configure(text=update['status'])
            if 'eta' in update and hasattr(self, f"{st}_scan_details_label"): getattr(self, f"{st}_scan_details_label").configure(text=update['eta'])
            if 'result' in update: self.add_scan_result(update['result'], update['scan_type'])
        except (AttributeError, TclError): pass
    
    def add_scan_result(self, result, scan_type):
        tree_map = {"station": self.scanner_tree, "arbitrage": self.arbitrage_tree, "region_trading": self.region_tree,
                    "galaxy": self.galaxy_tree, "bpo_scanner": self.bpo_tree, "price_hunter": self.price_hunter_tree}
        tree = tree_map.get(scan_type)
        if not tree or not tree.winfo_exists(): return
        try:
            if scan_type == 'price_hunter':
                values = (f"{result['price']:,.2f}", f"{result['quantity']:,}", result['location_name'], 
                          result['system_name'], result['security'])
                tree.insert("", "end", values=values)
                return

            if scan_type == 'bpo_scanner':
                tags = ('excellent_deal',) if result.get('profit_ph', 0) > 100_000_000 else \
                       ('good_deal',) if result.get('profit_ph', 0) > 25_000_000 else ()
                
                values = (
                    result['bpo'],
                    result['product'],
                    f"{result['profit_ph']:,.2f}",
                    f"{result['profit_run']:,.2f}",
                    f"{result['cost']:,.2f}",
                    f"{result['bpo_price']:,.2f}"
                )
                if values: tree.insert("", "end", values=values, tags=tags)
                return

            if scan_type == 'galaxy' and result.get('is_bundle'):
                bundle = result
                
                buy_station_text = bundle['buy_station']
                if bundle.get('is_multistation'):
                    unique_stations = sorted(list({item['buy_station'] for item in bundle['items']}))
                    if len(unique_stations) > 1:
                        buy_station_text = f"Flere ({len(unique_stations)} stasjoner)"
                    elif unique_stations:
                        buy_station_text = unique_stations[0]
                
                parent_values = (
                    f"Pakke ({bundle['item_count']} varer)", 
                    buy_station_text, 
                    f"{bundle['total_profit']:,.2f}",
                    f"{bundle['cargo_used_percentage']:.1f}%", "", "", "", "", "", "", ""
                )
                parent_id = tree.insert("", "end", values=parent_values, tags=('good_deal',))
                
                for item in bundle['items']:
                    item_display_name = f"  └ {item['name']}"
                    station_display_name = item['buy_station'] if bundle.get('is_multistation') else ""
                    
                    child_values = (
                        item_display_name, 
                        station_display_name, 
                        f"{item['profit']:,.2f}", "", 
                        f"{item['units']:,}",
                        f"{int(item['buy_volume_available']):,}", f"{int(item['sell_volume_available']):,}",
                        f"{item['buy_price']:,.2f}", f"{item['sell_price']:,.2f}", f"{int(item['daily_volume']):,}", 
                        item['trend']
                    )
                    tree.insert(parent_id, "end", values=child_values)
                return

            tags, values = (), ()
            if result.get('profit_margin', 0) >= config.EXCELLENT_DEAL_MARGIN: tags = ('excellent_deal',)
            elif result.get('profit_margin', 0) >= config.GOOD_DEAL_MARGIN: tags = ('good_deal',)
            if scan_type in ['station', 'arbitrage']:
                values = (result['item'], f"{result['profit_per_trip']:,.2f}", f"{result['profit_margin']:.2f}%", f"{int(result['units_to_trade']):,}", f"{int(result['buy_volume_available']):,}", f"{int(result['sell_volume_available']):,}", f"{result['buy_price']:,.2f}", f"{result['sell_price']:,.2f}", f"{int(result['daily_volume']):,}", result['trend'])
            elif scan_type == 'region_trading':
                if result.get('daily_volume',0) >= config.GOLDEN_DEAL_MIN_VOLUME and result.get('competition',99) <= config.GOLDEN_DEAL_MAX_COMPETITION:
                    tags = ('golden_deal',)
                values = (result['item'], f"{result['profit_per_unit']:,.2f}", f"{result['profit_margin']:.2f}%", f"{int(result['daily_volume']):,}", f"{result['buy_price']:,.2f}", f"{result['sell_price']:,.2f}", result['competition'], result['trend'])
            if values: tree.insert("", "end", values=values, tags=tags)

        except (TclError, KeyError) as e:
            print(f"Error adding result to tree: {e}")

    def _set_scanning_state(self, is_scanning, scan_type=None):
        state, stop_state = ("disabled", "normal") if is_scanning else ("normal", "disabled")
        st_map = {"station": "scanner", "arbitrage": "arbitrage", "region_trading": "region", 
                  "galaxy": "galaxy", "bpo_scanner": "bpo", "price_hunter": "price_hunter"}
        for st_key, st_ui in st_map.items():
            if hasattr(self, f"{st_ui}_scan_button"):
                getattr(self, f"{st_ui}_scan_button").configure(state=state)
                if hasattr(self, f"{st_ui}_stop_button"):
                    getattr(self, f"{st_ui}_stop_button").configure(state="disabled")
        if is_scanning and scan_type:
            if ui_type := st_map.get(scan_type):
                if hasattr(self, f"{ui_type}_stop_button"):
                    getattr(self, f"{ui_type}_stop_button").configure(state=stop_state)

    def _create_right_click_menu(self):
        self.right_click_menu = tkinter.Menu(self, tearoff=0)

    def _on_tree_right_click(self, event):
        tree = event.widget
        row_id = tree.identify_row(event.y)
        if not row_id: return
        
        tree.selection_set(row_id)
        tree.focus(row_id)
        
        self.right_click_menu.delete(0, "end")
        
        values = tree.item(row_id)['values']
        
        if tree is self.bpo_tree:
            bpo_name, product_name = values[0], values[1]
            bpo_type_id = config.ITEM_LOOKUP_LOWERCASE.get(bpo_name.lower())
            product_type_id = config.ITEM_LOOKUP_LOWERCASE.get(product_name.lower())
            if bpo_type_id: self.right_click_menu.add_command(label=f"Åpne '{bpo_name}' i markedet", command=lambda t=bpo_type_id: self._open_in_game_market(t))
            if product_type_id: self.right_click_menu.add_command(label=f"Åpne '{product_name}' i markedet", command=lambda t=product_type_id: self._open_in_game_market(t))
        else:
            is_parent = bool(tree.get_children(row_id))
            if is_parent and tree is self.galaxy_tree:
                self.right_click_menu.add_command(label="Kopier pakke til Multibuy", command=lambda: self._copy_bundle_to_clipboard(tree, row_id))
            else:
                item_name_col_idx = 1 if tree is self.assets_tree else 0
                item_name = str(values[item_name_col_idx]).lstrip("  └ ")
                
                id_match = re.search(r'(?:ID|Id):\s*(\d+)$', item_name)
                if id_match:
                    type_id = int(id_match.group(1))
                    self.right_click_menu.add_command(label="Rediger navnet...", command=lambda t=type_id: self._prompt_for_item_name(t))
                    self.right_click_menu.add_separator()
                else:
                    type_id = config.ITEM_LOOKUP_LOWERCASE.get(item_name.lower())
                
                if type_id:
                    self.right_click_menu.add_command(label=f"Åpne i spillets marked", command=lambda t=type_id: self._open_in_game_market(t))
                    self.right_click_menu.add_separator()
                
                self.right_click_menu.add_command(label=f"Kopier varenavn: '{item_name}'", command=lambda: self._copy_value_to_clipboard(item_name, "Varenavn"))
                
                col_idx_str = tree.identify_column(event.x).replace('#', '')
                if col_idx_str:
                    col_idx = int(col_idx_str) - 1
                    if tree['columns'][col_idx] in ('station', 'buy_station', 'location') and len(values) > col_idx and values[col_idx]:
                        self.right_click_menu.add_command(label=f"Kopier sted: '{values[col_idx]}'", command=lambda v=values[col_idx]: self._copy_value_to_clipboard(v, "Sted"))

        if self.right_click_menu.index("end") is not None:
            self.right_click_menu.tk_popup(event.x_root, event.y_root)

    def _copy_bundle_to_clipboard(self, tree, parent_id):
        item_lines = []
        for child_id in tree.get_children(parent_id):
            values = tree.item(child_id)['values']
            item_name = values[0].lstrip("  └ ")
            quantity = str(values[4]).replace(',', '')
            item_lines.append(f"{item_name} {quantity}")
        
        multibuy_string = "\n".join(item_lines)
        
        self.clipboard_clear()
        self.clipboard_append(multibuy_string)
        self.status_label.configure(text=f"Pakke med {len(item_lines)} varer kopiert! Lim inn (Ctrl+V) i spillets multibuy-vindu.")

    def _on_item_double_click(self, event): pass
            
    def _copy_value_to_clipboard(self, value, value_type):
        self.clipboard_clear(); self.clipboard_append(value)
        self.status_label.configure(text=f"{value_type} kopiert.")

    def _prompt_for_item_name(self, type_id):
        dialog = ctk.CTkInputDialog(
            title="Rediger Varenavn",
            text=f"Skriv inn det korrekte navnet for vare-ID: {type_id}"
        )
        new_name = dialog.get_input()
        
        if new_name and new_name.strip():
            self._save_new_item_name(type_id, new_name.strip())
        else:
            self.status_label.configure(text="Redigering avbrutt.")

    def _save_new_item_name(self, type_id, new_name):
        config.ITEM_NAME_TO_ID[new_name] = type_id
        config.ITEM_LOOKUP_LOWERCASE[new_name.lower()] = type_id
        config.save_item_list()
        self.status_label.configure(text=f"Navn for ID {type_id} lagret som '{new_name}'. Oppdater visningen for å se endringen.")
        messagebox.showinfo("Navn Lagret", f"Navnet '{new_name}' er lagret.\n\nKlikk på en 'Oppdater'-knapp for å laste inn data på nytt med det nye navnet.")

    def load_all_regions(self):
        threading.Thread(target=lambda: (api.populate_all_regions_cache(), self.after(0, self.populate_region_dropdown)), daemon=True).start()

    def populate_region_dropdown(self):
        try:
            if hasattr(self, 'galaxy_target_region_dropdown') and config.ALL_REGIONS_CACHE:
                self.galaxy_target_region_dropdown.configure(values=sorted(config.ALL_REGIONS_CACHE.keys()))
        except TclError: pass

    def load_structures_to_treeview(self):
        self.clear_tree(self.structures_tree)
        for s in self.settings.get('user_structures', []):
            self.structures_tree.insert("", "end", values=(s.get('name'), s.get('id'), s.get('system_name')))
    
    def _add_structure_thread(self, structure_id, token):
        details = api.get_structure_details(structure_id, token)
        if not details: self.show_error(f"Kunne ikke hente detaljer for ID {structure_id}."); return
        new_struct = {"id": structure_id, "name": details['name'], "system_id": details['system_id'], "system_name": details['system_name'], "region_id": details['region_id']}
        self.settings.get('user_structures', []).append(new_struct)
        self.after(0, self.load_structures_to_treeview)
        self.new_structure_id_entry.delete(0, 'end')

    def delete_user_structure(self):
        selected_item = self.structures_tree.selection()
        if not selected_item: self.show_error("Velg en struktur for å slette."); return
        try:
            selected_id = int(self.structures_tree.item(selected_item[0])['values'][1])
            self.settings['user_structures'] = [s for s in self.settings.get('user_structures', []) if s.get('id') != selected_id]
            self.structures_tree.delete(selected_item[0])
        except (ValueError, IndexError): self.show_error("Kunne ikke slette valgt element.")
        
    def fetch_trade_ledger_threaded(self):
        if not self.auth_manager.character_info.get('id'):
            self.show_error("Du må være innlogget for å se handelsloggen.")
            return
        token = self.auth_manager.get_valid_token()
        if not token:
            self.show_error("Sesjonen er utløpt. Logg inn på nytt.")
            return

        self.trade_log_button.configure(state="disabled")
        self.trade_log_status_label.configure(text="Henter data...")
        threading.Thread(target=self._build_trade_ledger_logic, args=(token,), daemon=True).start()

    def _build_trade_ledger_logic(self, token):
        char_id = self.auth_manager.character_info['id']
        # ... (resten av funksjonen er lik)
        self.after(0, lambda: self.trade_log_status_label.configure(text="Henter transaksjoner..."))
        transactions = api.fetch_all_pages(f"https://esi.evetech.net/v1/characters/{char_id}/wallet/transactions/", token)
        self.after(0, lambda: self.trade_log_status_label.configure(text="Henter journal..."))
        journal = api.fetch_all_pages(f"https://esi.evetech.net/v6/characters/{char_id}/wallet/journal/", token)

        if transactions is None or journal is None:
            self.after(0, lambda: self.show_error("Kunne ikke hente transaksjoner eller journal fra ESI."))
            self.after(0, lambda: self.trade_log_status_label.configure(text="Feil ved henting."))
            self.after(0, lambda: self.trade_log_button.configure(state="normal"))
            return

        self.after(0, lambda: self.trade_log_status_label.configure(text="Prosesserer handler..."))
        id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
        buy_queues = defaultdict(deque)
        completed_trades = []

        for t in sorted(transactions, key=lambda x: x['date']):
            type_id = t['type_id']
            if t['is_buy']:
                buy_queues[type_id].append(t)
            else:
                quantity_to_sell = t['quantity']
                units_sold = t['quantity']
                total_buy_cost = 0
                
                while quantity_to_sell > 0 and buy_queues[type_id]:
                    buy_t = buy_queues[type_id][0]
                    
                    if buy_t['quantity'] <= quantity_to_sell:
                        total_buy_cost += buy_t['quantity'] * buy_t['unit_price']
                        quantity_to_sell -= buy_t['quantity']
                        buy_queues[type_id].popleft()
                    else:
                        total_buy_cost += quantity_to_sell * buy_t['unit_price']
                        buy_t['quantity'] -= quantity_to_sell
                        quantity_to_sell = 0

                sell_price_total = units_sold * t['unit_price']
                
                related_journal_entries = [j for j in journal if j.get('ref_id') == t['transaction_id']]
                total_fees = abs(sum(j['amount'] for j in related_journal_entries))

                net_profit = sell_price_total - total_buy_cost - total_fees

                completed_trades.append({
                    'date': t['date'],
                    'item': id_to_name.get(type_id, f"Ukjent Vare ID: {type_id}"),
                    'quantity': units_sold,
                    'buy_price_avg': total_buy_cost / units_sold if units_sold > 0 else 0,
                    'sell_price': t['unit_price'],
                    'fees': total_fees,
                    'profit': net_profit
                })
        
        final_trades = sorted(completed_trades, key=lambda x: x['date'], reverse=True)[:50]
        self.after(0, self._update_trade_ledger_display, final_trades)

    def _update_trade_ledger_display(self, trades):
        self.clear_tree(self.trades_tree)
        # ... (resten av funksjonen er lik)
        for trade in trades:
            profit = trade['profit']
            tags = ('profit',) if profit > 0 else ('loss',) if profit < 0 else ()
            
            date_obj = datetime.fromisoformat(trade['date'].replace("Z", "+00:00"))
            
            values = (
                date_obj.strftime('%Y-%m-%d %H:%M'),
                trade['item'],
                f"{trade['quantity']:,}",
                f"{trade['buy_price_avg']:,.2f}",
                f"{trade['sell_price']:,.2f}",
                f"{trade['fees']:,.2f}",
                f"{profit:,.2f}"
            )
            self.trades_tree.insert("", "end", values=values, tags=tags)
            
        self.after(0, lambda: self.trade_log_status_label.configure(text=f"Viste {len(trades)} handler."))
        self.after(0, lambda: self.trade_log_button.configure(state="normal"))

    def fetch_active_ship_cargo_threaded(self):
        token = self.auth_manager.get_valid_token()
        if not token:
            self.show_error("Du må være innlogget for å hente skipsdata.")
            return
        self.update_cargo_button.configure(state="disabled")
        self.ship_cargo_status_label.configure(text="Henter data...")
        threading.Thread(target=self._fetch_active_ship_cargo_logic, args=(token,), daemon=True).start()

    def _fetch_active_ship_cargo_logic(self, token):
        char_id = self.auth_manager.character_info.get('id')
        # ... (resten av funksjonen er lik)
        if not char_id:
            return
            
        self.after(0, lambda: self.ship_cargo_status_label.configure(text="Finner aktivt skip..."))
        ship_info = api.fetch_character_ship(char_id, token)
        if not ship_info or 'ship_item_id' not in ship_info:
            self.after(0, lambda: self.show_error("Kunne ikke hente informasjon om aktivt skip."))
            self.after(0, lambda: self.update_cargo_button.configure(state="normal"))
            return
            
        ship_item_id = ship_info['ship_item_id']
        ship_name = ship_info.get('ship_name', 'Ukjent Skip')
        ship_type_name = db.get_type_name_from_sde(ship_info['ship_type_id'])
        
        self.after(0, lambda: self.ship_cargo_status_label.configure(text="Henter alle eiendeler..."))
        all_assets = api.fetch_character_assets_paginated(char_id, token)
        if not all_assets:
            self.after(0, lambda: self.show_error("Kunne ikke hente eiendeler."))
            self.after(0, lambda: self.update_cargo_button.configure(state="normal"))
            return

        cargo_items = [
            asset for asset in all_assets 
            if asset.get('location_id') == ship_item_id and asset.get('location_flag') == 'Cargo'
        ]
        
        if not cargo_items:
            self.after(0, self._update_ship_cargo_display, [], 0, ship_name, ship_type_name)
            return
        
        self.after(0, lambda: self.ship_cargo_status_label.configure(text="Henter Jita-priser..."))
        type_ids_in_cargo = {item['type_id'] for item in cargo_items}
        jita_station_id = config.STATIONS_INFO['Jita']['id']
        price_data = api.fetch_fuzzwork_market_data(jita_station_id, list(type_ids_in_cargo))
        self.after(0, lambda: self.ship_cargo_status_label.configure(text="Henter Jita-volum..."))
        total_cargo_value = 0
        detailed_cargo_list = []
        id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
        for item in cargo_items:
            type_id = item['type_id']
            price = float(price_data.get(str(type_id), {}).get('buy', {}).get('max', 0))
            quantity = item['quantity']
            item_value = price * quantity
            total_cargo_value += item_value
            history = api.fetch_esi_history(config.STATIONS_INFO['Jita']['region_id'], type_id)
            avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
            detailed_cargo_list.append({
                'name': id_to_name.get(type_id, f"Ukjent Vare ID: {type_id}"),
                'quantity': quantity,
                'price': price,
                'total_value': item_value,
                'daily_volume': avg_daily_vol
            })
        self.after(0, self._update_ship_cargo_display, detailed_cargo_list, total_cargo_value, ship_name, ship_type_name)


    def _update_ship_cargo_display(self, cargo_list, total_value, ship_name, ship_type_name):
        try:
            self.clear_tree(self.ship_cargo_tree)
            self.ship_name_label.configure(text=f"{ship_name} ({ship_type_name})")
            
            for item in sorted(cargo_list, key=lambda x: x['name']):
                values = (
                    item['name'],
                    f"{item['quantity']:,}",
                    f"{item['price']:,.2f}",
                    f"{item['total_value']:,.2f}",
                    f"{item['daily_volume']:,.0f}"
                )
                self.ship_cargo_tree.insert("", "end", values=values)
                
            self.ship_cargo_value_label.configure(text=f"Totalverdi i last (est.): {total_value:,.2f} ISK")
            self.ship_cargo_status_label.configure(text=f"Viste {len(cargo_list)} varetyper.")
            self.update_cargo_button.configure(state="normal")
        except (TclError, AttributeError):
            pass

    def on_closing(self):
        """Kjøres når applikasjonen lukkes. Stopper tråder og lagrer innstillinger."""
        self.scanning_active.clear()
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=1.0)
        
        # Samle alle innstillinger fra UI-variabler tilbake til settings-objektet
        all_settings = self.settings.copy()
        for var_attr in dir(self):
            if var_attr.endswith("_var"):
                # Trekker ut nøkkelnavnet fra variabelnavnet
                key_name = var_attr[:-4]
                try:
                    current_value = getattr(self, var_attr).get()
                    all_settings[key_name] = current_value
                except (TclError, AttributeError):
                    pass
        
        all_settings['user_structures'] = self.settings.get('user_structures', [])
        
        # Lagre de oppdaterte innstillingene
        config.save_settings(all_settings)
        self.destroy()

