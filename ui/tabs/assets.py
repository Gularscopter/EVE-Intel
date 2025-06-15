import customtkinter as ctk
from tkinter import ttk

def create_tab(tab, app):
    """
    Creates the assets tab with a modern, clean layout.
    """
    # Configure grid layout
    tab.grid_columnconfigure(0, weight=1)
    tab.grid_rowconfigure(1, weight=1)
    
    # --- Header Frame ---
    header_frame = ctk.CTkFrame(tab, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    header_frame.grid_columnconfigure(0, weight=1)

    title_label = ctk.CTkLabel(header_frame, text="Mine Eiendeler", font=ctk.CTkFont(size=24, weight="bold"))
    title_label.grid(row=0, column=0, sticky="w")

    # --- Summary Frame for key values ---
    summary_frame = ctk.CTkFrame(tab, fg_color=("gray92", "gray28"))
    summary_frame.grid(row=0, column=1, padx=10, pady=(0, 20), sticky="e")
    
    app.assets_value_label = ctk.CTkLabel(summary_frame, text="Verdi: Henter...", font=ctk.CTkFont(size=16))
    app.assets_value_label.pack(side="left", padx=15, pady=10)
    
    app.net_worth_label = ctk.CTkLabel(summary_frame, text="Nettoverdi: Henter...", font=ctk.CTkFont(size=16, weight="bold"))
    app.net_worth_label.pack(side="left", padx=15, pady=10)

    # --- Treeview Frame for the list of assets ---
    result_frame = ctk.CTkFrame(tab, fg_color=("gray92", "gray28"))
    result_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=0)
    result_frame.grid_columnconfigure(0, weight=1)
    result_frame.grid_rowconfigure(0, weight=1)

    # Define columns and headings for the Treeview
    columns = ('station', 'item', 'quantity', 'price', 'total_value')
    app.assets_tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    
    headings = {
        'station': 'Stasjon', 'item': 'Vare', 'quantity': 'Antall', 
        'price': 'Pris/stk (est.)', 'total_value': 'Totalverdi (est.)'
    }
    
    for col, heading in headings.items():
        app.assets_tree.heading(col, text=heading, command=lambda c=col: app.sort_results(app.assets_tree, c, False))

    # Configure column properties
    app.assets_tree.column('station', anchor="w", width=300)
    app.assets_tree.column('item', anchor="w", width=300)
    app.assets_tree.column('quantity', anchor="e", width=120)
    app.assets_tree.column('price', anchor="e", width=150)
    app.assets_tree.column('total_value', anchor="e", width=150)

    # Place the Treeview and its scrollbar
    app.assets_tree.grid(row=0, column=0, sticky="nsew", padx=(1,0), pady=1)
    scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=app.assets_tree.yview)
    app.assets_tree.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0,1), pady=1)

    # Bind right-click event
    app.assets_tree.bind("<Button-3>", app._on_tree_right_click)
