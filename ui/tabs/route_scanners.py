import customtkinter as ctk
from tkinter import ttk
import config

def create_tab(tab_frame, app, scan_type):
    """
    Creates the route scanner tab with a modern layout for a specific scan type.
    """
    if scan_type == "scanner":
        title = "Ruteskanner (Kjøp til Salgsordre)"
        buy_text = "Kjøp fra"
        sell_text = "Selg til"
    else: # arbitrage
        title = "Ruteskanner (Salg til Salgsordre)"
        buy_text = "Hub A"
        sell_text = "Hub B"

    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(2, weight=1)
    
    # --- Header ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")

    # --- Settings Frame ---
    settings_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    settings_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
    for i in range(4): settings_frame.grid_columnconfigure(i, weight=1)

    station_names = list(config.STATIONS_INFO.keys())
    
    # Column 0: Locations
    ctk.CTkLabel(settings_frame, text=buy_text).grid(row=0, column=0, padx=10, pady=5)
    ctk.CTkComboBox(settings_frame, variable=getattr(app, f"{scan_type}_buy_station_var"), values=station_names, state="readonly").grid(row=1, column=0, padx=10, pady=5, sticky="ew")
    ctk.CTkLabel(settings_frame, text=sell_text).grid(row=2, column=0, padx=10, pady=5)
    ctk.CTkComboBox(settings_frame, variable=getattr(app, f"{scan_type}_sell_station_var"), values=station_names, state="readonly").grid(row=3, column=0, padx=10, pady=5, sticky="ew")

    # Column 1: Filters
    ctk.CTkLabel(settings_frame, text="Min. profitt").grid(row=0, column=1, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=getattr(app, f"{scan_type}_min_profit_var")).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    ctk.CTkLabel(settings_frame, text="Min. volum").grid(row=2, column=1, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=getattr(app, f"{scan_type}_min_volume_var")).grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    # Column 2: More Filters
    ctk.CTkLabel(settings_frame, text="Maks. investering").grid(row=0, column=2, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=getattr(app, f"{scan_type}_max_investment_var")).grid(row=1, column=2, padx=10, pady=5, sticky="ew")
    ctk.CTkLabel(settings_frame, text="Lasterom (m³)").grid(row=2, column=2, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=getattr(app, f"{scan_type}_ship_cargo_var")).grid(row=3, column=2, padx=10, pady=5, sticky="ew")

    # Column 3: Controls
    button_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    button_frame.grid(row=1, column=3, rowspan=2)
    setattr(app, f"{scan_type}_scan_button", ctk.CTkButton(button_frame, text="Start Skann", command=lambda: app.start_route_scan(scan_type), height=40))
    getattr(app, f"{scan_type}_scan_button").pack(pady=5)
    setattr(app, f"{scan_type}_stop_button", ctk.CTkButton(button_frame, text="Stopp", command=app.stop_scan, state="disabled", height=30, fg_color="#D32F2F", hover_color="#B71C1C"))
    getattr(app, f"{scan_type}_stop_button").pack(pady=5)
    
    # Progress Bar
    progress_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    progress_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=10)
    progress_frame.grid_columnconfigure(0, weight=1)
    setattr(app, f"{scan_type}_progress", ctk.CTkProgressBar(progress_frame))
    getattr(app, f"{scan_type}_progress").set(0)
    getattr(app, f"{scan_type}_progress").grid(row=0, column=0, sticky="ew", padx=10)
    setattr(app, f"{scan_type}_scan_details_label", ctk.CTkLabel(progress_frame, text=""))
    getattr(app, f"{scan_type}_scan_details_label").grid(row=0, column=1, padx=10)

    # --- Result Frame ---
    result_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    result_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
    result_frame.grid_columnconfigure(0, weight=1)
    result_frame.grid_rowconfigure(0, weight=1)

    columns = ('item', 'profit', 'margin', 'units', 'buy_vol', 'sell_vol', 'buy_price', 'sell_price', 'daily_vol', 'trend')
    tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    setattr(app, f"{scan_type}_tree", tree)
    
    headings = {'item':'Vare', 'profit':'Profitt/Tur', 'margin':'Margin', 'units':'Enheter/Tur', 'buy_vol':'Kjøp Vol.', 'sell_vol':'Salg Vol.', 'buy_price':'Kjøpspris', 'sell_price':'Salgspris', 'daily_vol':'Daglig Vol.', 'trend':'Trend'}
    for col, text in headings.items():
        tree.heading(col, text=text, command=lambda c=col: app.sort_results(tree, c, False))

    tree.column('item', anchor='w', width=200)
    for col in columns[1:]: tree.column(col, anchor='e', width=100)
        
    tree.tag_configure('excellent_deal', background='#1B5E20')
    tree.tag_configure('good_deal', background='#2E7D32')

    tree.grid(row=0, column=0, sticky="nsew", padx=(1,0), pady=1)
    scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=tree.yview)
    tree.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0,1), pady=1)
    tree.bind("<Button-3>", app._on_tree_right_click)