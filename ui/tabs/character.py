import customtkinter as ctk
from tkinter import ttk
from datetime import datetime, timedelta

def create_tab(tab_frame, app):
    """
    Creates the character tab with a modern, clean layout.
    """
    # Main grid layout
    tab_frame.grid_columnconfigure(0, weight=1)
    tab_frame.grid_rowconfigure(1, weight=1) # Active orders table
    tab_frame.grid_rowconfigure(2, weight=1) # Trade ledger table
    tab_frame.grid_rowconfigure(3, weight=1) # Active ship cargo table

    # --- Header & Auth Frame ---
    header_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
    header_frame.grid(row=0, column=0, padx=10, pady=(0, 20), sticky="ew")
    header_frame.grid_columnconfigure(1, weight=1)

    # Left side: Login button
    app.login_button = ctk.CTkButton(header_frame, text="Logg inn med EVE Online", command=app.start_oauth_flow, height=40)
    app.login_button.grid(row=0, column=0, rowspan=2, padx=0, pady=0, sticky="w")
    
    # Center: Character Info
    char_info_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
    char_info_frame.grid(row=0, column=1, rowspan=2, padx=20, pady=0, sticky="w")
    
    app.char_name_label = ctk.CTkLabel(char_info_frame, text="Ikke innlogget", font=ctk.CTkFont(size=20, weight="bold"))
    app.char_name_label.pack(anchor="w")
    
    app.wallet_label = ctk.CTkLabel(char_info_frame, text="", font=ctk.CTkFont(size=14))
    app.wallet_label.pack(anchor="w")
    
    app.profit_label = ctk.CTkLabel(char_info_frame, text="", font=ctk.CTkFont(size=14, slant="italic"))
    app.profit_label.pack(anchor="w")

    # Right side: Portrait
    app.char_portrait_label = ctk.CTkLabel(header_frame, text="", width=128, height=128)
    app.char_portrait_label.grid(row=0, column=2, rowspan=2, padx=0, pady=0, sticky="e")

    # --- Active Market Orders Frame ---
    orders_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    orders_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
    orders_frame.grid_columnconfigure(0, weight=1)
    orders_frame.grid_rowconfigure(1, weight=1)

    orders_header_frame = ctk.CTkFrame(orders_frame, fg_color="transparent")
    orders_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
    ctk.CTkLabel(orders_header_frame, text="Aktive Markedsordrer", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
    ctk.CTkButton(orders_header_frame, text="Oppdater", command=app.fetch_character_orders_threaded).pack(side="right")

    # Treeview for active orders
    columns = ('item', 'station', 'type', 'buy_price', 'sell_price', 'acc_fees', 'total_value', 'potential_profit', 'volume', 'expires')
    app.orders_tree = ttk.Treeview(orders_frame, columns=columns, show="headings")
    headings = {
        'item': 'Vare', 'station': 'Stasjon', 'type': 'Type', 
        'buy_price': 'Innkjøpspris', 'sell_price': 'Nåværende Pris', 
        'acc_fees': 'Akk. Avgifter', 'total_value': 'Gjenv. Verdi',
        'potential_profit': 'Pot. Profitt', 'volume': 'Volum (Rem/Tot)', 
        'expires': 'Utløper om'
    }
    for col, heading in headings.items():
        app.orders_tree.heading(col, text=heading, command=lambda c=col: app.sort_results(app.orders_tree, c, False))

    col_widths = {'item': 220, 'station': 180, 'type': 80, 'buy_price': 110, 'sell_price': 110, 
                  'acc_fees': 110, 'total_value': 120, 'potential_profit': 120, 'volume': 120, 'expires': 100}
    for col, width in col_widths.items():
        app.orders_tree.column(col, width=width, anchor='e' if col not in ['item', 'station', 'type'] else 'w')
    app.orders_tree.column('type', anchor='center')
    
    app.orders_tree.grid(row=1, column=0, sticky="nsew", padx=(1,0), pady=(0,1))
    orders_scrollbar = ttk.Scrollbar(orders_frame, orient="vertical", command=app.orders_tree.yview)
    app.orders_tree.configure(yscroll=orders_scrollbar.set)
    orders_scrollbar.grid(row=1, column=1, sticky="ns", padx=(0,1), pady=(0,1))
    app.orders_tree.tag_configure('profit', foreground='#4CAF50')
    app.orders_tree.tag_configure('loss', foreground='#F44336')
    app.orders_tree.bind("<Button-3>", app._on_tree_right_click)


    # --- Trade Ledger Frame ---
    trades_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    trades_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
    trades_frame.grid_columnconfigure(0, weight=1)
    trades_frame.grid_rowconfigure(1, weight=1)

    trades_header_frame = ctk.CTkFrame(trades_frame, fg_color="transparent")
    trades_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
    ctk.CTkLabel(trades_header_frame, text="Handelslogg (Siste 50 handler)", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
    app.trade_log_status_label = ctk.CTkLabel(trades_header_frame, text="", font=ctk.CTkFont(size=12, slant="italic"))
    app.trade_log_status_label.pack(side="left", padx=10)
    app.trade_log_button = ctk.CTkButton(trades_header_frame, text="Oppdater", command=app.fetch_trade_ledger_threaded)
    app.trade_log_button.pack(side="right")

    # Treeview for trade ledger
    trade_cols = ('date', 'item', 'quantity', 'buy_price', 'sell_price', 'fees', 'profit')
    app.trades_tree = ttk.Treeview(trades_frame, columns=trade_cols, show="headings")
    trade_headings = {
        'date': 'Dato', 'item': 'Vare', 'quantity': 'Antall', 
        'buy_price': 'Kjøpspris/stk', 'sell_price': 'Salgspris/stk', 
        'fees': 'Totale Avgifter', 'profit': 'Reell Netto Profitt'
    }
    for col, heading in trade_headings.items():
        app.trades_tree.heading(col, text=heading, command=lambda c=col: app.sort_results(app.trades_tree, c, False))

    trade_col_widths = {'date': 150, 'item': 250, 'quantity': 100, 'buy_price': 150, 
                        'sell_price': 150, 'fees': 150, 'profit': 150}
    for col, width in trade_col_widths.items():
        app.trades_tree.column(col, width=width, anchor='e' if col not in ['date', 'item'] else 'w')

    app.trades_tree.grid(row=1, column=0, sticky="nsew", padx=(1,0), pady=(0,1))
    trades_scrollbar = ttk.Scrollbar(trades_frame, orient="vertical", command=app.trades_tree.yview)
    app.trades_tree.configure(yscroll=trades_scrollbar.set)
    trades_scrollbar.grid(row=1, column=1, sticky="ns", padx=(0,1), pady=(0,1))
    app.trades_tree.tag_configure('profit', foreground='#4CAF50')
    app.trades_tree.tag_configure('loss', foreground='#F44336')

    # --- Active Ship Cargo Frame ---
    cargo_frame = ctk.CTkFrame(tab_frame, fg_color=("gray92", "gray28"))
    cargo_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
    cargo_frame.grid_columnconfigure(0, weight=1)
    cargo_frame.grid_rowconfigure(1, weight=1)

    cargo_header_frame = ctk.CTkFrame(cargo_frame, fg_color="transparent")
    cargo_header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
    
    app.ship_name_label = ctk.CTkLabel(cargo_header_frame, text="Aktivt Skip / Last", font=ctk.CTkFont(size=16, weight="bold"))
    app.ship_name_label.pack(side="left")

    app.ship_cargo_status_label = ctk.CTkLabel(cargo_header_frame, text="", font=ctk.CTkFont(size=12, slant="italic"))
    app.ship_cargo_status_label.pack(side="left", padx=10)
    
    app.update_cargo_button = ctk.CTkButton(cargo_header_frame, text="Oppdater Last", command=app.fetch_active_ship_cargo_threaded)
    app.update_cargo_button.pack(side="right")

    # Treeview for ship cargo
    cargo_cols = ('item', 'quantity', 'jita_price', 'total_value', 'jita_volume')
    app.ship_cargo_tree = ttk.Treeview(cargo_frame, columns=cargo_cols, show="headings")
    cargo_headings = {
        'item': 'Vare', 'quantity': 'Antall', 
        'jita_price': 'Jita Pris/stk (Kjøp)', 'total_value': 'Totalverdi', 
        'jita_volume': 'Jita Daglig Volum'
    }
    for col, heading in cargo_headings.items():
        app.ship_cargo_tree.heading(col, text=heading, command=lambda c=col: app.sort_results(app.ship_cargo_tree, c, False))

    app.ship_cargo_tree.column('item', width=250, anchor='w')
    app.ship_cargo_tree.column('quantity', width=120, anchor='e')
    app.ship_cargo_tree.column('jita_price', width=180, anchor='e')
    app.ship_cargo_tree.column('total_value', width=180, anchor='e')
    app.ship_cargo_tree.column('jita_volume', width=180, anchor='e')
    
    app.ship_cargo_tree.grid(row=1, column=0, sticky="nsew", padx=(1,0), pady=(0,1))
    cargo_scrollbar = ttk.Scrollbar(cargo_frame, orient="vertical", command=app.ship_cargo_tree.yview)
    app.ship_cargo_tree.configure(yscroll=cargo_scrollbar.set)
    cargo_scrollbar.grid(row=1, column=1, sticky="ns", padx=(0,1), pady=(0,1))
    app.ship_cargo_tree.bind("<Button-3>", app._on_tree_right_click)

    # Total value label
    app.ship_cargo_value_label = ctk.CTkLabel(cargo_frame, text="Totalverdi i last (est.): 0.00 ISK", font=ctk.CTkFont(size=14, weight="bold"))
    app.ship_cargo_value_label.grid(row=2, column=0, sticky="e", padx=10, pady=5)