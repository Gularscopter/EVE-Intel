import customtkinter as ctk
from tkinter import ttk

def create_tab(tab_frame, app):
    """
    Creates the price hunter tab with a modern layout.
    """
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(2, weight=1)
    
    # --- Header ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    ctk.CTkLabel(header_frame, text="Prisjeger", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")

    # --- Input Frame ---
    input_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
    input_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(input_frame, text="Søk etter vare:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=15, pady=15, sticky="w")
    app.price_hunter_item_entry = ctk.CTkEntry(input_frame, textvariable=app.price_hunter_item_name_var)
    app.price_hunter_item_entry.grid(row=0, column=1, padx=15, pady=15, sticky="ew")
    app.price_hunter_item_entry.bind("<KeyRelease>", app._update_suggestions)

    security_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
    security_frame.grid(row=0, column=2, padx=15, pady=15)
    ctk.CTkCheckBox(security_frame, text="High-sec", variable=app.price_hunter_hisec_var).pack(side="left", padx=5)
    ctk.CTkCheckBox(security_frame, text="Low-sec", variable=app.price_hunter_lowsec_var).pack(side="left", padx=5)
    ctk.CTkCheckBox(security_frame, text="Null-sec", variable=app.price_hunter_nullsec_var).pack(side="left", padx=5)

    app.price_hunter_scan_button = ctk.CTkButton(input_frame, text="Start Søk", command=app.start_price_hunter_scan, height=35)
    app.price_hunter_scan_button.grid(row=0, column=3, padx=15, pady=15)
    app.price_hunter_stop_button = ctk.CTkButton(input_frame, text="Stopp", command=app.stop_scan, state="disabled", height=35, fg_color="#D32F2F", hover_color="#B71C1C")
    app.price_hunter_stop_button.grid(row=0, column=4, padx=15, pady=15)

    # --- Result Frame ---
    result_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    result_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
    result_frame.grid_columnconfigure(0, weight=1)
    result_frame.grid_rowconfigure(0, weight=1)

    columns = ('price', 'quantity', 'location', 'system', 'security')
    app.price_hunter_tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    headings = {'price': 'Pris', 'quantity': 'Antall', 'location': 'Lokasjon', 'system': 'System', 'security': 'Sikkerhet'}
    for col, text in headings.items():
        app.price_hunter_tree.heading(col, text=text, command=lambda c=col: app.sort_results(app.price_hunter_tree, c, False))
    
    app.price_hunter_tree.column('price', anchor='e', width=150)
    app.price_hunter_tree.column('quantity', anchor='e', width=120)
    app.price_hunter_tree.column('location', anchor='w', width=300)
    app.price_hunter_tree.column('system', anchor='w', width=150)
    app.price_hunter_tree.column('security', anchor='center', width=100)

    app.price_hunter_tree.grid(row=0, column=0, sticky="nsew", padx=(1,0), pady=1)
    scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=app.price_hunter_tree.yview)
    app.price_hunter_tree.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0,1), pady=1)
    app.price_hunter_tree.bind("<Button-3>", app._on_tree_right_click)