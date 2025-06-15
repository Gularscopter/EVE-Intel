import customtkinter as ctk
from tkinter import ttk

def create_tab(tab_frame, app):
    """
    Creates the settings tab with a modern layout.
    """
    tab_frame.grid_columnconfigure(0, weight=1)
    
    # --- Header ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    ctk.CTkLabel(header_frame, text="Innstillinger", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")

    # --- Fees Settings Frame ---
    fees_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    fees_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
    fees_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(fees_frame, text="Globale Avgifter", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, padx=15, pady=10, sticky="w")
    
    ctk.CTkLabel(fees_frame, text="Salgsskatt (%):").grid(row=1, column=0, padx=15, pady=10, sticky="w")
    ctk.CTkEntry(fees_frame, textvariable=app.sales_tax_var).grid(row=1, column=1, padx=15, pady=10, sticky="ew")
    ctk.CTkLabel(fees_frame, text="Megleravgift (%):").grid(row=2, column=0, padx=15, pady=10, sticky="w")
    ctk.CTkEntry(fees_frame, textvariable=app.brokers_fee_var).grid(row=2, column=1, padx=15, pady=10, sticky="ew")

    # --- API Settings Frame ---
    api_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    api_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
    api_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(api_frame, text="ESI/API Innstillinger", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, padx=15, pady=10, sticky="w")

    ctk.CTkLabel(api_frame, text="ESI Client ID:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
    ctk.CTkEntry(api_frame, textvariable=app.esi_client_id_var, show="*").grid(row=1, column=1, padx=15, pady=10, sticky="ew")
    ctk.CTkLabel(api_frame, text="ESI Secret Key:").grid(row=2, column=0, padx=15, pady=10, sticky="w")
    ctk.CTkEntry(api_frame, textvariable=app.esi_secret_key_var, show="*").grid(row=2, column=1, padx=15, pady=10, sticky="ew")

    # --- Structures Frame ---
    structures_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    structures_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
    structures_frame.grid_columnconfigure(0, weight=1)
    structures_frame.grid_rowconfigure(1, weight=1)
    tab_frame.grid_rowconfigure(3, weight=1)
    
    ctk.CTkLabel(structures_frame, text="Mine Strukturer", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=15, pady=10, sticky="w")
    
    tree_frame = ctk.CTkFrame(structures_frame, fg_color="transparent")
    tree_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10)
    tree_frame.grid_columnconfigure(0, weight=1)
    tree_frame.grid_rowconfigure(0, weight=1)

    app.structures_tree = ttk.Treeview(tree_frame, columns=('name', 'id', 'system'), show='headings')
    app.structures_tree.heading('name', text='Navn')
    app.structures_tree.heading('id', text='ID')
    app.structures_tree.heading('system', text='System')
    app.structures_tree.grid(row=0, column=0, sticky="nsew")
    app.load_structures_to_treeview()

    # Controls for adding/deleting structures
    control_frame = ctk.CTkFrame(structures_frame, fg_color="transparent")
    control_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
    control_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(control_frame, text="Ny ID:").grid(row=0, column=0, padx=(5,0))
    app.new_structure_id_entry = ctk.CTkEntry(control_frame)
    app.new_structure_id_entry.grid(row=0, column=1, padx=5, sticky="ew")
    ctk.CTkButton(control_frame, text="Legg til", command=app.add_user_structure).grid(row=0, column=2, padx=5)
    ctk.CTkButton(control_frame, text="Slett valgt", command=app.delete_user_structure, fg_color="#D32F2F", hover_color="#B71C1C").grid(row=0, column=3, padx=5)