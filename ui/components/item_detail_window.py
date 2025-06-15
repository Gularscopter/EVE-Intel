import tkinter
import customtkinter as ctk
from tkinter import ttk
from PIL import Image
import threading
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import api

class ItemDetailWindow(ctk.CTkToplevel):
    def __init__(self, master, item_name, type_id, buy_station_info, sell_station_info):
        super().__init__(master)
        self.transient(master)
        self.title(f"Detaljer for: {item_name}")
        self.geometry("1200x800")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.item_name = item_name
        self.type_id = type_id
        self.buy_station_info = buy_station_info
        self.sell_station_info = sell_station_info

        plt.style.use('dark_background')

        self._create_widgets()
        threading.Thread(target=self._fetch_and_display_data, daemon=True).start()

    def _create_widgets(self):
        orders_frame = ctk.CTkFrame(self)
        orders_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        orders_frame.grid_columnconfigure((0, 1), weight=1)

        buy_frame = ctk.CTkFrame(orders_frame)
        buy_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        buy_frame.grid_rowconfigure(1, weight=1)
        buy_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(buy_frame, text=f"Salgsordrer i {self.buy_station_info['name']}", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, pady=5)
        self.buy_orders_tree = ttk.Treeview(buy_frame, columns=('price', 'volume'), show="headings")
        self.buy_orders_tree.heading('price', text='Pris')
        self.buy_orders_tree.heading('volume', text='Volum')
        self.buy_orders_tree.grid(row=1, column=0, sticky="nsew")

        sell_frame = ctk.CTkFrame(orders_frame)
        sell_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        sell_frame.grid_rowconfigure(1, weight=1)
        sell_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(sell_frame, text=f"Kjøpsordrer i {self.sell_station_info['name']}", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, pady=5)
        self.sell_orders_tree = ttk.Treeview(sell_frame, columns=('price', 'volume'), show="headings")
        self.sell_orders_tree.heading('price', text='Pris')
        self.sell_orders_tree.heading('volume', text='Volum')
        self.sell_orders_tree.grid(row=1, column=0, sticky="nsew")

        self.graph_frame = ctk.CTkFrame(self)
        self.graph_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_frame.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(self.graph_frame, text="Henter historikk...").pack(pady=20)

    def _fetch_and_display_data(self):
        buy_region_orders = api.fetch_market_orders(self.buy_station_info['region_id'], self.type_id)
        sell_region_orders = api.fetch_market_orders(self.sell_station_info['region_id'], self.type_id)
        self.after(0, self._populate_order_trees, buy_region_orders, sell_region_orders)

        buy_history = api.fetch_esi_history(self.buy_station_info['region_id'], self.type_id)
        sell_history = api.fetch_esi_history(self.sell_station_info['region_id'], self.type_id)
        self.after(0, self._create_history_graphs, buy_history, sell_history)

    def _populate_order_trees(self, buy_region_orders, sell_region_orders):
        for i in self.buy_orders_tree.get_children(): self.buy_orders_tree.delete(i)
        for i in self.sell_orders_tree.get_children(): self.sell_orders_tree.delete(i)

        if buy_region_orders:
            station_sell_orders = [o for o in buy_region_orders if not o['is_buy_order'] and o['location_id'] == self.buy_station_info['id']]
            for order in sorted(station_sell_orders, key=lambda x: x['price']):
                self.buy_orders_tree.insert("", "end", values=(f"{order['price']:,.2f}", f"{order['volume_remain']:,}"))

        if sell_region_orders:
            station_buy_orders = [o for o in sell_region_orders if o['is_buy_order'] and o['location_id'] == self.sell_station_info['id']]
            for order in sorted(station_buy_orders, key=lambda x: x['price'], reverse=True):
                self.sell_orders_tree.insert("", "end", values=(f"{order['price']:,.2f}", f"{order['volume_remain']:,}"))

    def _create_history_graphs(self, buy_history, sell_history):
        for widget in self.graph_frame.winfo_children():
            widget.destroy()

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
        fig.tight_layout(pad=4.0)

        if buy_history:
            dates = [datetime.strptime(h['date'], '%Y-%m-%d').date() for h in buy_history[-60:]]
            volumes = [h['volume'] for h in buy_history[-60:]]
            prices = [h['average'] for h in buy_history[-60:]]

            ax1.set_title(f"Historikk i {self.buy_station_info['name']}'s Region")
            ax1.bar(dates, volumes, label='Omsatt Volum', color='gray', alpha=0.6)
            ax1.set_ylabel('Volum')
            ax1.tick_params(axis='y', labelcolor='gray')

            ax1_twin = ax1.twinx()
            ax1_twin.plot(dates, prices, label='Gj.snittspris', color='#3498db')
            ax1_twin.set_ylabel('Gj.snittspris (ISK)', color='#3498db')
            ax1_twin.tick_params(axis='y', labelcolor='#3498db')

        if sell_history:
            dates = [datetime.strptime(h['date'], '%Y-%m-%d').date() for h in sell_history[-60:]]
            volumes = [h['volume'] for h in sell_history[-60:]]
            prices = [h['average'] for h in sell_history[-60:]]

            ax2.set_title(f"Historikk i {self.sell_station_info['name']}'s Region")
            ax2.bar(dates, volumes, label='Omsatt Volum', color='gray', alpha=0.6)
            ax2.set_ylabel('Volum')
            ax2.tick_params(axis='y', labelcolor='gray')

            ax2_twin = ax2.twinx()
            ax2_twin.plot(dates, prices, label='Gj.snittspris', color='#e74c3c')
            ax2_twin.set_ylabel('Gj.snittspris (ISK)', color='#e74c3c')
            ax2_twin.tick_params(axis='y', labelcolor='#e74c3c')

            fig.autofmt_xdate()

        canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=True)