import customtkinter as ctk
from tkinter import ttk
import config

def create_tab(tab_frame, app):
    """
    Creates the galaxy/region explorer scanner tab with a modern layout.
    """
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(2, weight=1)

    # --- Header ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    ctk.CTkLabel(header_frame, text="Region-utforsker (Import/Eksport)", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")

    # --- Settings Frame ---
    settings_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    settings_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
    for i in range(4): settings_frame.grid_columnconfigure(i, weight=1)

    # Column 0: Locations
    ctk.CTkLabel(settings_frame, text="Hjemmebase (Selg til)").grid(row=0, column=0, padx=10, pady=5)
    station_names = list(config.STATIONS_INFO.keys())
    app.galaxy_home_base_dropdown = ctk.CTkComboBox(settings_frame, variable=app.galaxy_home_base_var, values=station_names, state="readonly")
    app.galaxy_home_base_dropdown.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

    ctk.CTkLabel(settings_frame, text="Mål-region (Kjøp fra)").grid(row=2, column=0, padx=10, pady=5)
    app.galaxy_target_region_dropdown = ctk.CTkComboBox(settings_frame, variable=app.galaxy_target_region_var, values=["Laster..."], state="readonly")
    app.galaxy_target_region_dropdown.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

    # Column 1: Filters
    ctk.CTkLabel(settings_frame, text="Min. profitt/tur").grid(row=0, column=1, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.galaxy_min_profit_var).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    ctk.CTkLabel(settings_frame, text="Min. volum").grid(row=2, column=1, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.galaxy_min_volume_var).grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    # Column 2: Investment & Security
    ctk.CTkLabel(settings_frame, text="Maks. investering").grid(row=0, column=2, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.galaxy_max_investment_var).grid(row=1, column=2, padx=10, pady=5, sticky="ew")
    ctk.CTkLabel(settings_frame, text="Lasterom (m³)").grid(row=2, column=2, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.galaxy_ship_cargo_var).grid(row=3, column=2, padx=10, pady=5, sticky="ew")

    # --- Seksjon for avanserte valg ---
    adv_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    adv_frame.grid(row=4, column=0, columnspan=3, padx=10, pady=(10,5), sticky="w")
    
    # Sikkerhetsvalg
    ctk.CTkLabel(adv_frame, text="Inkluder kjøp fra:").pack(side="left", padx=(0,10))
    ctk.CTkCheckBox(adv_frame, text="High-sec", variable=app.galaxy_hisec_var).pack(side="left", padx=5)
    ctk.CTkCheckBox(adv_frame, text="Low-sec", variable=app.galaxy_lowsec_var).pack(side="left", padx=5)
    ctk.CTkCheckBox(adv_frame, text="Null-sec/WH", variable=app.galaxy_nullsec_var).pack(side="left", padx=5)
    
    # Separator
    ctk.CTkFrame(adv_frame, width=2, height=20, fg_color="gray50").pack(side="left", padx=15, fill="y")
    
    # Andre valg
    ctk.CTkCheckBox(adv_frame, text="Inkluder spiller-strukturer", variable=app.galaxy_include_structures_var).pack(side="left", padx=5)
    app.galaxy_multistation_bundle_var = ctk.BooleanVar(value=False) # NY
    ctk.CTkCheckBox(adv_frame, text="Tillat pakker fra flere stasjoner", variable=app.galaxy_multistation_bundle_var).pack(side="left", padx=5)


    # Column 3: Controls
    button_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    button_frame.grid(row=1, column=3, rowspan=3, sticky="ns")
    app.galaxy_scan_button = ctk.CTkButton(button_frame, text="Start Skann", command=app.start_galaxy_scan, height=40)
    app.galaxy_scan_button.pack(pady=5, padx=5)
    app.galaxy_stop_button = ctk.CTkButton(button_frame, text="Stopp", command=app.stop_scan, state="disabled", height=30, fg_color="#D32F2F", hover_color="#B71C1C")
    app.galaxy_stop_button.pack(pady=5, padx=5)

    # Progress Bar
    progress_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    progress_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=10)
    progress_frame.grid_columnconfigure(0, weight=1)
    app.galaxy_progress = ctk.CTkProgressBar(progress_frame)
    app.galaxy_progress.set(0)
    app.galaxy_progress.grid(row=0, column=0, sticky="ew", padx=10)
    app.galaxy_scan_details_label = ctk.CTkLabel(progress_frame, text="")
    app.galaxy_scan_details_label.grid(row=0, column=1, padx=10)

    # --- Result Frame ---
    result_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    result_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
    result_frame.grid_columnconfigure(0, weight=1)
    result_frame.grid_rowconfigure(0, weight=1)
    
    columns = ('item', 'buy_station', 'profit', 'cargo_used', 'units', 'buy_vol', 'sell_vol', 'buy_price', 'sell_price', 'daily_vol', 'trend')
    app.galaxy_tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    headings = {'item':'Vare/Pakke', 'buy_station':'Kjøp Fra', 'profit':'Profitt', 'cargo_used':'Last %', 'units':'Enheter', 'buy_vol':'Kjøp Vol.', 'sell_vol':'Salg Vol.', 'buy_price':'Kjøpspris', 'sell_price':'Salgspris', 'daily_vol':'Daglig Vol.', 'trend':'Trend'}
    for col, text in headings.items():
        app.galaxy_tree.heading(col, text=text, command=lambda c=col: app.sort_results(app.galaxy_tree, c, False))
    
    for col, width in {'item':300, 'buy_station':200, 'profit':120, 'cargo_used':80}.items():
        app.galaxy_tree.column(col, anchor='w', width=width)
    for col in columns[4:]:
        app.galaxy_tree.column(col, anchor='e', width=100)
    
    app.galaxy_tree.tag_configure('good_deal', background='#2E7D32')

    app.galaxy_tree.grid(row=0, column=0, sticky="nsew", padx=(1,0), pady=1)
    scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=app.galaxy_tree.yview)
    app.galaxy_tree.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0,1), pady=1)
    app.galaxy_tree.bind("<Button-3>", app._on_tree_right_click)