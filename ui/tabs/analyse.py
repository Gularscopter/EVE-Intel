import tkinter
import customtkinter as ctk
import config

def create_tab(tab_frame, app):
    """
    Creates the single item analysis tab with a modern layout.
    """
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(2, weight=1)

    # --- Header Frame ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    ctk.CTkLabel(header_frame, text="Enkel Vareanalyse", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")

    # --- Input Frame ---
    input_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    input_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
    input_frame.grid_columnconfigure(1, weight=1)
    input_frame.grid_columnconfigure(3, weight=1)

    # Item Selection
    ctk.CTkLabel(input_frame, text="Vare:").grid(row=0, column=0, padx=10, pady=(10,5), sticky="w")
    app.item_entry = ctk.CTkEntry(input_frame, textvariable=app.analyse_item_name_var)
    app.item_entry.grid(row=0, column=1, columnspan=3, padx=10, pady=(10,5), sticky="ew")
    app.item_entry.bind("<KeyRelease>", app._update_suggestions)

    # Separator
    separator1 = ctk.CTkFrame(input_frame, height=1, fg_color=("gray81", "gray33"))
    separator1.grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

    # Stations and Cargo
    station_names = list(config.STATIONS_INFO.keys())
    ctk.CTkLabel(input_frame, text="Kjøp fra:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
    ctk.CTkComboBox(input_frame, variable=app.analyse_buy_station_var, values=station_names, state="readonly").grid(row=2, column=1, padx=10, pady=5, sticky="ew")
    
    ctk.CTkLabel(input_frame, text="Selg til:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
    ctk.CTkComboBox(input_frame, variable=app.analyse_sell_station_var, values=station_names, state="readonly").grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    ctk.CTkLabel(input_frame, text="Lasterom (m³):").grid(row=4, column=0, padx=10, pady=(5,10), sticky="w")
    ctk.CTkEntry(input_frame, textvariable=app.analyse_ship_cargo_var).grid(row=4, column=1, padx=10, pady=(5,10), sticky="ew")

    # Sell Method
    ctk.CTkLabel(input_frame, text="Salgsmetode:").grid(row=2, column=2, padx=(20, 10), pady=5, sticky="w")
    ctk.CTkRadioButton(input_frame, text="Selg til kjøpsordre (umiddelbart)", variable=app.analyse_sell_method_var, value="Kjøpsordre").grid(row=3, column=2, padx=20, pady=5, sticky="w")
    ctk.CTkRadioButton(input_frame, text="Konkurrer med salgsordre", variable=app.analyse_sell_method_var, value="Salgsordre").grid(row=4, column=2, padx=20, pady=5, sticky="w")
    
    # Action Button
    app.analyse_button = ctk.CTkButton(input_frame, text="Kjør Analyse", command=app.start_analyse_fetch, height=40)
    app.analyse_button.grid(row=3, column=3, rowspan=2, padx=10, pady=5, sticky="ns")

    # --- Results Frame ---
    results_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    results_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
    results_frame.grid_columnconfigure(1, weight=1)

    app.result_labels = {}
    labels_info = {
        "buy_price": "Pris / enhet (Kjøp):", 
        "buy_volume": "Volum på ordre (Kjøp):", 
        "sell_price": "Pris / enhet (Salg):", 
        "sell_volume": "Volum på ordre (Salg):", 
        "transaction_cost": "Transaksjonskostnad / enhet:", 
        "profit_per_unit": "Netto profitt / enhet:", 
        "units_per_trip": "Antall enheter per tur:", 
        "total_profit": "TOTAL NETTO PROFITT PER TUR:"
    }
    
    for i, (key, text) in enumerate(labels_info.items()):
        font_style = ctk.CTkFont(size=14)
        if key == "total_profit":
            font_style = ctk.CTkFont(size=18, weight="bold")
            separator = ctk.CTkFrame(results_frame, height=1, fg_color=("gray81", "gray33"))
            separator.grid(row=i, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        
        ctk.CTkLabel(results_frame, text=text, anchor="w", font=ctk.CTkFont(size=13)).grid(row=i + (1 if key == 'total_profit' else 0), column=0, padx=15, pady=5, sticky="w")
        app.result_labels[key] = ctk.CTkLabel(results_frame, text="...", font=font_style, anchor="e")
        app.result_labels[key].grid(row=i + (1 if key == 'total_profit' else 0), column=1, padx=15, pady=5, sticky="e")