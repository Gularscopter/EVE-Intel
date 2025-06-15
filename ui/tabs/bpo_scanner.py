import customtkinter as ctk
from tkinter import ttk
import math

def create_tab(tab_frame, app):
    """
    Creates the BPO scanner tab with a modern, clean layout.
    """
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(1, weight=1)
    
    # --- Settings Frame ---
    settings_outer_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    settings_outer_frame.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="ew")
    settings_outer_frame.grid_columnconfigure(0, weight=1)

    title_label = ctk.CTkLabel(settings_outer_frame, text="Blueprint Skanner", font=ctk.CTkFont(size=18, weight="bold"))
    title_label.grid(row=0, column=0, columnspan=4, padx=15, pady=10, sticky="w")

    settings_frame = ctk.CTkFrame(settings_outer_frame, fg_color="transparent")
    settings_frame.grid(row=1, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
    settings_frame.grid_columnconfigure(1, weight=1)
    settings_frame.grid_columnconfigure(3, weight=1)

    ctk.CTkLabel(settings_frame, text="ME (%):", anchor="w").grid(row=0, column=0, padx=5, pady=5, sticky="w")
    ctk.CTkEntry(settings_frame, textvariable=app.bpo_me_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
    
    ctk.CTkLabel(settings_frame, text="TE (%):", anchor="w").grid(row=1, column=0, padx=5, pady=5, sticky="w")
    ctk.CTkEntry(settings_frame, textvariable=app.bpo_te_var).grid(row=1, column=1, padx=5, pady=5, sticky="ew")
    
    ctk.CTkLabel(settings_frame, text="System:", anchor="w").grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")
    app.bpo_system_entry = ctk.CTkEntry(settings_frame, textvariable=app.bpo_system_var)
    app.bpo_system_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
    app.bpo_system_entry.bind("<KeyRelease>", lambda e: app._update_system_suggestions(e, app.bpo_system_var, app.bpo_system_entry))
    app.bpo_system_entry.bind("<FocusOut>", lambda e: app._update_system_cost_index_display(app.bpo_system_var, app.bpo_system_entry))

    app.bpo_system_index_label = ctk.CTkLabel(settings_frame, text="Indeks: N/A", font=ctk.CTkFont(size=12, slant="italic"))
    app.bpo_system_index_label.grid(row=1, column=2, padx=20, pady=5, sticky="w")

    ctk.CTkLabel(settings_frame, text="Min. Profitt/Time:", anchor="w").grid(row=2, column=0, padx=5, pady=5, sticky="w")
    ctk.CTkEntry(settings_frame, textvariable=app.bpo_min_profit_ph_var).grid(row=2, column=1, padx=5, pady=5, sticky="ew")

    ctk.CTkLabel(settings_frame, text="Min. Kjøpsordre Volum:", anchor="w").grid(row=2, column=2, padx=(20,5), pady=5, sticky="w")
    ctk.CTkEntry(settings_frame, textvariable=app.bpo_min_daily_volume_var).grid(row=2, column=3, padx=5, pady=5, sticky="ew")

    # --- Control Frame (Buttons & Progress) ---
    control_frame = ctk.CTkFrame(settings_outer_frame, fg_color="transparent")
    control_frame.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
    control_frame.grid_columnconfigure(1, weight=1)

    app.bpo_scan_button = ctk.CTkButton(control_frame, text="Start Skann", command=app.start_bpo_scan, height=35)
    app.bpo_scan_button.grid(row=0, column=0, padx=5)
    app.bpo_stop_button = ctk.CTkButton(control_frame, text="Stopp", command=app.stop_scan, state="disabled", height=35, fg_color="#D32F2F", hover_color="#B71C1C")
    app.bpo_stop_button.grid(row=0, column=1, padx=5, sticky="w")
    
    app.bpo_progress = ctk.CTkProgressBar(control_frame)
    app.bpo_progress.set(0)
    app.bpo_progress.grid(row=0, column=2, padx=10, sticky="ew", columnspan=2)
    control_frame.grid_columnconfigure(2, weight=2)
    
    app.bpo_scan_details_label = ctk.CTkLabel(control_frame, text="", font=ctk.CTkFont(size=12, slant="italic"))
    app.bpo_scan_details_label.grid(row=0, column=4, padx=10)

    # --- Result Frame ---
    result_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    result_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
    result_frame.grid_columnconfigure(0, weight=1)
    result_frame.grid_rowconfigure(0, weight=1)
    
    columns = ('bpo', 'product', 'profit_ph', 'profit_run', 'cost', 'bpo_price')
    app.bpo_tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    headings = {
        'bpo':'Blueprint', 'product':'Produkt', 'profit_ph':'Profitt/Time', 
        'profit_run':'Profitt/Bygg', 'cost':'Kostnad/Bygg', 'bpo_price': 'BPO Kjøpspris'
    }
    for col, heading_text in headings.items():
        app.bpo_tree.heading(col, text=heading_text, command=lambda c=col: app.sort_results(app.bpo_tree, c, False))
        
    app.bpo_tree.column('bpo', anchor="w", width=250)
    app.bpo_tree.column('product', anchor="w", width=250)
    app.bpo_tree.column('profit_ph', anchor="e", width=160)
    app.bpo_tree.column('profit_run', anchor="e", width=160)
    app.bpo_tree.column('cost', anchor="e", width=160)
    app.bpo_tree.column('bpo_price', anchor="e", width=160)
    
    app.bpo_tree.tag_configure('excellent_deal', background='#1B5E20')
    app.bpo_tree.tag_configure('good_deal', background='#2E7D32')
    app.bpo_tree.grid(row=0, column=0, sticky="nsew", padx=(1,0), pady=1)
    
    scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=app.bpo_tree.yview)
    app.bpo_tree.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0,1), pady=1)