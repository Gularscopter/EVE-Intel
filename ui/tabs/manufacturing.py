import tkinter
import customtkinter as ctk
from tkinter import ttk

def create_tab(tab_frame, app):
    """
    Creates the manufacturing calculator tab with a modern, clean layout.
    """
    # Main grid layout
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(1, weight=1)

    # --- Header & Input Frame ---
    input_outer_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    input_outer_frame.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="ew")
    input_outer_frame.grid_columnconfigure(0, weight=1)

    title_label = ctk.CTkLabel(input_outer_frame, text="Produksjonskalkulator", font=ctk.CTkFont(size=18, weight="bold"))
    title_label.grid(row=0, column=0, columnspan=4, padx=15, pady=10, sticky="w")
    
    # Input fields grouped inside the frame
    app.manu_input_frame = ctk.CTkFrame(input_outer_frame, fg_color="transparent")
    app.manu_input_frame.grid(row=1, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
    app.manu_input_frame.grid_columnconfigure(1, weight=3)
    app.manu_input_frame.grid_columnconfigure(3, weight=1)

    ctk.CTkLabel(app.manu_input_frame, text="Produkt:", anchor="w").grid(row=0, column=0, padx=5, pady=5, sticky="w")
    app.manu_item_entry = ctk.CTkEntry(app.manu_input_frame, textvariable=app.manu_item_name_var)
    app.manu_item_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="ew")
    app.manu_item_entry.bind("<KeyRelease>", app._update_suggestions)

    ctk.CTkLabel(app.manu_input_frame, text="ME (%):", anchor="w").grid(row=1, column=0, padx=5, pady=5, sticky="w")
    ctk.CTkEntry(app.manu_input_frame, textvariable=app.manu_me_var, width=120).grid(row=1, column=1, padx=5, pady=5, sticky="w")

    ctk.CTkLabel(app.manu_input_frame, text="TE (%):", anchor="w").grid(row=2, column=0, padx=5, pady=5, sticky="w")
    ctk.CTkEntry(app.manu_input_frame, textvariable=app.manu_te_var, width=120).grid(row=2, column=1, padx=5, pady=5, sticky="w")
    
    ctk.CTkLabel(app.manu_input_frame, text="System:", anchor="w").grid(row=1, column=2, padx=(20, 5), pady=5, sticky="w")
    app.manu_system_entry = ctk.CTkEntry(app.manu_input_frame, textvariable=app.manu_system_var)
    app.manu_system_entry.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
    app.manu_system_entry.bind("<KeyRelease>", lambda e: app._update_system_suggestions(e, app.manu_system_var, app.manu_system_entry))
    app.manu_system_entry.bind("<FocusOut>", lambda e: app._update_system_cost_index_display(app.manu_system_var, app.manu_system_entry))

    app.manu_system_index_label = ctk.CTkLabel(app.manu_input_frame, text="Indeks: N/A", font=ctk.CTkFont(size=12, slant="italic"))
    app.manu_system_index_label.grid(row=2, column=2, padx=20, pady=5, sticky="w")

    ctk.CTkButton(app.manu_input_frame, text="Kalkuler Profitt", command=app._start_manufacturing_calculation, height=40).grid(row=1, rowspan=2, column=4, padx=20, pady=5)

    # --- Results Area ---
    results_container = ctk.CTkFrame(tab_frame, fg_color="transparent")
    results_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
    results_container.grid_columnconfigure(0, weight=2) # Materials list gets more space
    results_container.grid_columnconfigure(1, weight=1)
    results_container.grid_rowconfigure(0, weight=1)

    # Left side: Materials list
    materials_frame = ctk.CTkFrame(results_container, fg_color=("gray92", "gray28"))
    materials_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    materials_frame.grid_columnconfigure(0, weight=1)
    materials_frame.grid_rowconfigure(1, weight=1)
    ctk.CTkLabel(materials_frame, text="Nødvendige Materialer", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")
    
    cols = ('name', 'req_qty', 'price', 'total_cost')
    app.manu_materials_tree = ttk.Treeview(materials_frame, columns=cols, show='headings')
    app.manu_materials_tree.heading('name', text='Materiale')
    app.manu_materials_tree.heading('req_qty', text='Antall')
    app.manu_materials_tree.heading('price', text='Pris/stk (Jita Salg)')
    app.manu_materials_tree.heading('total_cost', text='Totalkostnad')
    app.manu_materials_tree.column('name', anchor='w', width=200)
    app.manu_materials_tree.column('req_qty', anchor='e', width=100)
    app.manu_materials_tree.column('price', anchor='e', width=150)
    app.manu_materials_tree.column('total_cost', anchor='e', width=150)
    app.manu_materials_tree.grid(row=1, column=0, sticky='nsew', padx=(1,0), pady=(0,1))
    materials_scrollbar = ttk.Scrollbar(materials_frame, orient="vertical", command=app.manu_materials_tree.yview)
    app.manu_materials_tree.configure(yscroll=materials_scrollbar.set)
    materials_scrollbar.grid(row=1, column=1, sticky="ns", padx=(0,1), pady=(0,1))

    # Right side: Profit summary
    profit_frame = ctk.CTkFrame(results_container, fg_color=("gray92", "gray28"))
    profit_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    profit_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(profit_frame, text="Resultat", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")
    
    app.manu_result_labels = {}
    labels_info = {
        "material_cost": "Total Materialkostnad:",
        "installation_cost": "Installasjonsavgift:",
        "total_cost_per_run": "Total Produksjonskostnad:",
        "product_sell_price": "Produkt Salgspris (Jita Kjøp):",
        "net_profit_per_run": "Netto Profitt / Bygg:",
        "profit_per_hour": "Profitt / Time:"
    }
    
    for i, (key, text) in enumerate(labels_info.items()):
        font_style = ctk.CTkFont(size=14)
        if "total_cost_per_run" in key:
            separator = ctk.CTkFrame(profit_frame, height=1, fg_color=("gray81", "gray33"))
            separator.grid(row=i+1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        if "net_profit_per_run" in key or "profit_per_hour" in key:
            font_style = ctk.CTkFont(size=16, weight="bold")
        
        ctk.CTkLabel(profit_frame, text=text, anchor="w", font=ctk.CTkFont(size=13)).grid(row=i+2, column=0, padx=10, pady=4, sticky="w")
        app.manu_result_labels[key] = ctk.CTkLabel(profit_frame, text="...", font=font_style, anchor="e")
        app.manu_result_labels[key].grid(row=i+2, column=1, padx=10, pady=4, sticky="e")