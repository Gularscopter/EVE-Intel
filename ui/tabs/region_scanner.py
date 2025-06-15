import customtkinter as ctk
from tkinter import ttk
import config

def create_tab(tab_frame, app):
    """
    Creates the region/station trading scanner tab with a modern layout.
    """
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(2, weight=1)

    # --- Header ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    ctk.CTkLabel(header_frame, text="Stasjonshandel (Flipping)", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")

    # --- Settings Frame ---
    settings_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    settings_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
    for i in range(4): settings_frame.grid_columnconfigure(i, weight=1)

    # Column 0: Station
    ctk.CTkLabel(settings_frame, text="Handelshub").grid(row=0, column=0, padx=10, pady=5)
    station_names = list(config.STATIONS_INFO.keys())
    ctk.CTkComboBox(settings_frame, variable=app.region_station_var, values=station_names, state="readonly").grid(row=1, column=0, padx=10, pady=5, sticky="ew")
    
    # Column 1: Filters
    ctk.CTkLabel(settings_frame, text="Min. profitt/enhet").grid(row=0, column=1, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.region_min_profit_var).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    ctk.CTkLabel(settings_frame, text="Min. daglig volum").grid(row=2, column=1, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.region_min_volume_var).grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    # Column 2: Investment
    ctk.CTkLabel(settings_frame, text="Maks. investering").grid(row=0, column=2, padx=10, pady=5)
    ctk.CTkEntry(settings_frame, textvariable=app.region_max_investment_var).grid(row=1, column=2, padx=10, pady=5, sticky="ew")

    # Column 3: Controls
    button_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    button_frame.grid(row=1, column=3, rowspan=2)
    app.region_scan_button = ctk.CTkButton(button_frame, text="Start Skann", command=app.start_region_scan, height=40)
    app.region_scan_button.pack(pady=5)
    app.region_stop_button = ctk.CTkButton(button_frame, text="Stopp", command=app.stop_scan, state="disabled", height=30, fg_color="#D32F2F", hover_color="#B71C1C")
    app.region_stop_button.pack(pady=5)

    # Progress Bar
    progress_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
    progress_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=10)
    progress_frame.grid_columnconfigure(0, weight=1)
    app.region_progress = ctk.CTkProgressBar(progress_frame)
    app.region_progress.set(0)
    app.region_progress.grid(row=0, column=0, sticky="ew", padx=10)
    app.region_scan_details_label = ctk.CTkLabel(progress_frame, text="")
    app.region_scan_details_label.grid(row=0, column=1, padx=10)

    # --- Result Frame ---
    result_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    result_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
    result_frame.grid_columnconfigure(0, weight=1)
    result_frame.grid_rowconfigure(0, weight=1)
    
    columns = ('item', 'profit_unit', 'margin', 'daily_vol', 'buy_price', 'sell_price', 'competition', 'trend')
    app.region_tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    headings = {'item':'Vare', 'profit_unit':'Profitt/enhet', 'margin':'Margin %', 'daily_vol':'Daglig Volum', 'buy_price':'Kjøpspris', 'sell_price':'Salgspris', 'competition':'Konkurrenter', 'trend':'Trend'}
    for col, text in headings.items():
        app.region_tree.heading(col, text=text, command=lambda c=col: app.sort_results(app.region_tree, c, False))

    app.region_tree.column('item', anchor='w', width=250)
    for col in columns[1:]: app.region_tree.column(col, anchor='e', width=120)
    
    app.region_tree.tag_configure('golden_deal', background='#6a5101')
    app.region_tree.tag_configure('excellent_deal', background='#1B5E20')
    app.region_tree.tag_configure('good_deal', background='#2E7D32')

    app.region_tree.grid(row=0, column=0, sticky="nsew", padx=(1,0), pady=1)
    scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=app.region_tree.yview)
    app.region_tree.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0,1), pady=1)
    app.region_tree.bind("<Button-3>", app._on_tree_right_click)