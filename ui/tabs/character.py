import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, 
                             QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QRunnable, QThreadPool
import requests
import api
import db
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# --- Worker for multi-threading ---
class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(Exception)
    result = pyqtSignal(dict)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn; self.args = args; self.kwargs = kwargs; self.signals = WorkerSignals()
    def run(self):
        try: self.signals.result.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:
            logging.error("Exception in worker thread", exc_info=True)
            self.signals.error.emit(e)
        finally: self.signals.finished.emit()

# --- Main Character Tab Class ---
class CharacterTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.threadpool = QThreadPool()
        self.worker_data_cache = {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        top_section_layout = QHBoxLayout()
        self.portrait_label = QLabel("Not logged in"); self.portrait_label.setFixedSize(128, 128); self.portrait_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.portrait_label.setStyleSheet("border: 1px solid grey;")
        top_section_layout.addWidget(self.portrait_label)
        info_grid = QGridLayout(); self.name_label = QLabel("<b>Name:</b> N/A"); self.corporation_label = QLabel("<b>Corporation:</b> N/A"); self.location_label = QLabel("<b>Location:</b> N/A"); self.ship_label = QLabel("<b>Current Ship:</b> N/A")
        info_grid.addWidget(self.name_label, 0, 0); info_grid.addWidget(self.corporation_label, 1, 0); info_grid.addWidget(self.location_label, 0, 1); info_grid.addWidget(self.ship_label, 1, 1)
        top_section_layout.addLayout(info_grid); top_section_layout.addStretch()
        button_layout = QVBoxLayout(); self.login_button = QPushButton("Login / Switch Character"); self.login_button.clicked.connect(self.main_app.trigger_full_authentication)
        self.refresh_button = QPushButton("Refresh Data"); self.refresh_button.clicked.connect(self.load_character_data)
        button_layout.addWidget(self.login_button); button_layout.addWidget(self.refresh_button); top_section_layout.addLayout(button_layout); main_layout.addLayout(top_section_layout)
        self.sub_tabs = QTabWidget(); main_layout.addWidget(self.sub_tabs)
        self.create_summary_tab(); self.create_active_orders_tab(); self.create_transaction_history_tab(); self.create_cargo_tab()

    def create_summary_tab(self):
        summary_widget = QWidget(); layout = QVBoxLayout(summary_widget); layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.wallet_label = QLabel("<h2>Wallet: N/A</h2>"); self.active_sell_orders_label = QLabel("<b>Value of Active Sell Orders:</b> N/A"); self.active_buy_orders_label = QLabel("<b>Escrow in Active Buy Orders:</b> N/A"); self.ship_cargo_label = QLabel("<b>Current Ship Cargo Value:</b> N/A")
        self.total_sales_label = QLabel("<b>Total Sales:</b> N/A"); self.total_taxes_label = QLabel("<b>Total Taxes Paid:</b> N/A"); self.estimated_profit_label = QLabel("<b>Estimated Profit:</b> N/A")
        layout.addWidget(self.wallet_label); layout.addWidget(self.active_sell_orders_label); layout.addWidget(self.active_buy_orders_label); layout.addWidget(self.ship_cargo_label)
        layout.addWidget(QLabel("<hr>")); layout.addWidget(QLabel("<h3>Market Summary (from wallet journal)</h3>")); layout.addWidget(self.total_sales_label); layout.addWidget(self.total_taxes_label); layout.addWidget(self.estimated_profit_label)
        self.sub_tabs.addTab(summary_widget, "Financial Summary")

    def create_table(self, headers):
        table = QTableWidget(); table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers); table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setSortingEnabled(True)
        return table

    def create_active_orders_tab(self):
        headers = ["Vare", "Stasjon", "Type", "Innkjøpspris", "Nåværende Pris", "Akk. Avgifter", "Pot. Profitt", "Utløper om"]
        self.active_orders_table = self.create_table(headers); self.sub_tabs.addTab(self.active_orders_table, "Aktive Markedsordrer")
    def create_transaction_history_tab(self):
        headers = ["Dato", "Vare", "Antall", "Kjøpspris/stk", "Salgspris/stk", "Totale Avgifter", "Reell Netto Profitt"]
        self.history_table = self.create_table(headers); self.sub_tabs.addTab(self.history_table, "Handelslogg")
    def create_cargo_tab(self):
        headers = ["Vare", "Antall", "Jita Pris/stk (Kjøp)", "Totalverdi", "Jita Daglig Volum"]
        self.cargo_table = self.create_table(headers); self.sub_tabs.addTab(self.cargo_table, "Ship Cargo")

    def load_character_data(self):
        if not self.main_app.character_id: self.clear_all_fields(); return
        self.refresh_button.setEnabled(False); self.main_app.update_status_bar("Loading character data in background...")
        worker = Worker(self._fetch_all_data_in_background); worker.signals.result.connect(self._update_ui_with_fetched_data)
        worker.signals.error.connect(self._on_loading_error); worker.signals.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self.threadpool.start(worker)

    def _fetch_all_data_in_background(self):
        char_id, token = self.main_app.character_id, self.main_app.access_token
        orders = api.get_character_orders(char_id, token); transactions = api.get_character_wallet_transactions(char_id, token)
        assets = api.get_character_assets_with_names(char_id, token); ship = api.get_character_ship(char_id, token)
        price_type_ids = set()
        if orders: price_type_ids.update([o['type_id'] for o in orders])
        cargo_type_ids = set()
        if ship and assets:
            cargo = [a for asset_list in assets.values() for a in asset_list if a.get('location_id') == ship.get('ship_item_id') and a.get('location_flag') == 'Cargo']
            if cargo:
                cargo_type_ids = {c['type_id'] for c in cargo}
                price_type_ids.update(cargo_type_ids)
        else: cargo = []
        market_prices = api.get_market_prices(list(price_type_ids)) if price_type_ids else {}
        market_volumes = api.get_market_history_for_items(list(cargo_type_ids)) if cargo_type_ids else {}
        return {'details': api.get_character_details(char_id), 'wallet': api.get_character_wallet(char_id, token), 'location': api.get_character_location(char_id, token), 'ship': ship, 'orders': orders, 'transactions': transactions, 'assets': assets, 'cargo': cargo, 'market_prices': market_prices, 'market_volumes': market_volumes, 'journal': api.get_character_wallet_journal(char_id, token)}

    def _on_loading_error(self, e):
        logging.error(f"Error loading character data: {e}", exc_info=True); self.main_app.log_message(f"Error loading data: {e}")

    def _update_ui_with_fetched_data(self, data):
        self.main_app.update_status_bar("Updating UI..."); self.worker_data_cache = data
        if data.get('details'):
            self.name_label.setText(f"<b>Name:</b> {data['details'].get('name', 'N/A')}"); self.corporation_label.setText(f"<b>Corporation:</b> {data['details'].get('corporation_name', 'N/A')}"); self.load_character_portrait()
        if data.get('wallet') is not None: self.wallet_label.setText(f"<h2>Wallet: {data['wallet']:,.2f} ISK</h2>")
        if data.get('location'):
            loc_names = api.get_location_names({data['location']['solar_system_id']}, self.main_app.access_token, self.main_app.character_id)
            self.location_label.setText(f"<b>Location:</b> {loc_names.get(data['location']['solar_system_id'], 'Unknown')}")
        if data.get('ship'):
            ship_type = db.get_item_name(data['ship']['ship_type_id']) or "Unknown"; self.ship_label.setText(f"<b>Current Ship:</b> {data['ship']['ship_name']} ({ship_type})")
        self._update_active_orders(); self._update_trade_log(); self._update_ship_cargo(); self.main_app.update_status_bar("Character data updated.")

    def _update_active_orders(self):
        orders = self.worker_data_cache.get('orders', []); market_prices = self.worker_data_cache.get('market_prices', {})
        transactions = self.worker_data_cache.get('transactions', []); journal = self.worker_data_cache.get('journal', [])
        self.active_orders_table.setRowCount(0); total_sell, total_buy = 0, 0
        if not orders: return
        loc_ids = {o['location_id'] for o in orders}; loc_names = api.get_location_names(loc_ids, self.main_app.access_token, self.main_app.character_id)
        
        buy_transactions = {t['type_id']: t['unit_price'] for t in transactions if t.get('is_buy')}
        journal_fees = {entry.get('order_id'): abs(entry.get('amount', 0)) for entry in journal if entry.get('ref_type') in ['brokers_fee', 'transaction_tax'] and 'order_id' in entry}

        for o in orders:
            row = self.active_orders_table.rowCount(); self.active_orders_table.insertRow(row)
            is_buy = o.get('is_buy_order', False); type_id = o.get('type_id'); price_info = market_prices.get(type_id, {})
            current_price = price_info.get('buy' if is_buy else 'sell', 0)
            
            purchase_price = 0; profit = 0
            purchase_price_str = "N/A"
            fees = journal_fees.get(o.get('order_id'), 0)

            if not is_buy:
                purchase_price = buy_transactions.get(type_id, 0)
                if purchase_price > 0:
                    purchase_price_str = f"{purchase_price:,.2f}"
                    profit = (o['price'] - purchase_price) * o['volume_remain']
                else:
                    profit = (o['price'] - current_price) * o['volume_remain']
            else:
                profit = (current_price - o['price']) * o['volume_remain']

            issued = datetime.fromisoformat(o['issued'].replace('Z', '+00:00')); expires = issued + timedelta(days=o['duration'])
            expires_in = expires - datetime.now(timezone.utc); expires_str = f"{expires_in.days}d {expires_in.seconds//3600}h" if expires_in.days >= 0 else "Expired"
            if is_buy: total_buy += o.get('escrow', 0)
            else: total_sell += o.get('price', 0) * o.get('volume_remain', 0)
            
            self.active_orders_table.setItem(row, 0, QTableWidgetItem(db.get_item_name(type_id)))
            self.active_orders_table.setItem(row, 1, QTableWidgetItem(loc_names.get(o['location_id'])))
            self.active_orders_table.setItem(row, 2, QTableWidgetItem("Kjøp" if is_buy else "Salg"))
            self.active_orders_table.setItem(row, 3, QTableWidgetItem(purchase_price_str))
            self.active_orders_table.setItem(row, 4, QTableWidgetItem(f"{o['price']:,.2f}"))
            self.active_orders_table.setItem(row, 5, QTableWidgetItem(f"{fees:,.2f}"))
            self.active_orders_table.setItem(row, 6, QTableWidgetItem(f"{profit:,.2f}"))
            self.active_orders_table.setItem(row, 7, QTableWidgetItem(expires_str))
        self.active_sell_orders_label.setText(f"<b>Value of Active Sell Orders:</b> {total_sell:,.2f} ISK"); self.active_buy_orders_label.setText(f"<b>Escrow in Active Buy Orders:</b> {total_buy:,.2f} ISK")

    def _calculate_trade_log(self, transactions, journal):
        buys = [t for t in transactions if t.get('is_buy')]; sells = [t for t in transactions if not t.get('is_buy')]
        buys_by_item = defaultdict(list); sells_by_item = defaultdict(list)
        for b in buys: buys_by_item[b['type_id']].append(b)
        for s in sells: sells_by_item[s['type_id']].append(s)
        for item_id in buys_by_item: buys_by_item[item_id].sort(key=lambda x: x['date'])
        for item_id in sells_by_item: sells_by_item[item_id].sort(key=lambda x: x['date'])
        trade_log = []; total_profit, total_fees = 0, 0
        journal_fees = {entry['transaction_id']: abs(entry.get('amount', 0)) for entry in journal if 'transaction_id' in entry and entry.get('ref_type') in ['brokers_fee', 'transaction_tax']}
        for item_id, sales in sells_by_item.items():
            if item_id not in buys_by_item: continue
            buy_list = buys_by_item[item_id][:]
            for sale in sales:
                sale_quantity_to_match = sale['quantity']; sale_price = sale['unit_price']; cost_of_goods_sold = 0; temp_buy_list = []
                last_buy = None
                fees_for_this_trade = journal_fees.get(sale['transaction_id'], 0)
                for buy in buy_list:
                    if sale_quantity_to_match == 0: temp_buy_list.append(buy); continue
                    last_buy = buy; buy_quantity = buy['quantity']; buy_price = buy['unit_price']
                    if buy_quantity >= sale_quantity_to_match:
                        cost_of_goods_sold += sale_quantity_to_match * buy_price; buy['quantity'] -= sale_quantity_to_match
                        if buy['quantity'] > 0: temp_buy_list.append(buy)
                        if last_buy: fees_for_this_trade += journal_fees.get(last_buy.get('transaction_id',-1), 0)
                        sale_quantity_to_match = 0
                    else:
                        cost_of_goods_sold += buy_quantity * buy_price; sale_quantity_to_match -= buy_quantity
                        if last_buy: fees_for_this_trade += journal_fees.get(last_buy.get('transaction_id',-1), 0)
                buy_list = temp_buy_list
                if cost_of_goods_sold > 0:
                    sale_revenue = sale['quantity'] * sale_price
                    net_profit = sale_revenue - cost_of_goods_sold - fees_for_this_trade
                    total_profit += net_profit; total_fees += fees_for_this_trade
                    trade_log.append({'date': sale['date'], 'type_id': item_id, 'quantity': sale['quantity'], 'buy_price': cost_of_goods_sold / sale['quantity'], 'sell_price': sale_price, 'profit': net_profit, 'fees': fees_for_this_trade})
        summary = {'total_sales': sum(s['unit_price']*s['quantity'] for s in sells), 'total_taxes': total_fees, 'estimated_profit': total_profit}
        return sorted(trade_log, key=lambda x: x['date'], reverse=True), summary

    def _update_trade_log(self):
        transactions = self.worker_data_cache.get('transactions', []); journal = self.worker_data_cache.get('journal', [])
        self.history_table.setRowCount(0)
        if not transactions or not journal: return
        trade_log, summary = self._calculate_trade_log(transactions, journal)
        for trade in trade_log:
            row = self.history_table.rowCount(); self.history_table.insertRow(row)
            date = datetime.fromisoformat(trade['date'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
            self.history_table.setItem(row, 0, QTableWidgetItem(date)); self.history_table.setItem(row, 1, QTableWidgetItem(db.get_item_name(trade['type_id'])))
            self.history_table.setItem(row, 2, QTableWidgetItem(f"{trade['quantity']:,}")); self.history_table.setItem(row, 3, QTableWidgetItem(f"{trade['buy_price']:,.2f}"))
            self.history_table.setItem(row, 4, QTableWidgetItem(f"{trade['sell_price']:,.2f}")); self.history_table.setItem(row, 5, QTableWidgetItem(f"{trade.get('fees', 0):,.2f}")); self.history_table.setItem(row, 6, QTableWidgetItem(f"{trade['profit']:,.2f}"))
        self.total_sales_label.setText(f"<b>Total Sales:</b> {summary['total_sales']:,.2f} ISK"); self.total_taxes_label.setText(f"<b>Total Taxes Paid:</b> {summary['total_taxes']:,.2f} ISK")
        self.estimated_profit_label.setText(f"<b>Estimated Profit:</b> {summary['estimated_profit']:,.2f} ISK"); self.estimated_profit_label.setStyleSheet("color: green;" if summary['estimated_profit'] > 0 else "color: red;")

    def _update_ship_cargo(self):
        market_prices = self.worker_data_cache.get('market_prices', {}); cargo = self.worker_data_cache.get('cargo', []); market_volumes = self.worker_data_cache.get('market_volumes', {})
        self.cargo_table.setRowCount(0); total_value = 0
        if not cargo: self.clear_cargo_fields(); return
        for item in cargo:
            row = self.cargo_table.rowCount(); self.cargo_table.insertRow(row)
            type_id = item.get('type_id'); price_info = market_prices.get(type_id, {});
            buy_price = price_info.get('buy', 0); daily_volume = market_volumes.get(type_id, 0)
            value = buy_price * item.get('quantity', 0); total_value += value
            self.cargo_table.setItem(row, 0, QTableWidgetItem(item.get('name', 'Unknown')))
            self.cargo_table.setItem(row, 1, QTableWidgetItem(f"{item.get('quantity', 0):,}")); 
            self.cargo_table.setItem(row, 2, QTableWidgetItem(f"{buy_price:,.2f}"))
            self.cargo_table.setItem(row, 3, QTableWidgetItem(f"{value:,.2f}")); 
            self.cargo_table.setItem(row, 4, QTableWidgetItem(f"{daily_volume:,}"))
        self.ship_cargo_label.setText(f"<b>Current Ship Cargo Value:</b> {total_value:,.2f} ISK")

    def clear_all_fields(self):
        self.portrait_label.setText("Not logged in"); self.portrait_label.setPixmap(QPixmap()); self.name_label.setText("<b>Name:</b> N/A"); self.corporation_label.setText("<b>Corporation:</b> N/A"); self.location_label.setText("<b>Location:</b> N/A"); self.ship_label.setText("<b>Current Ship:</b> N/A")
        self.wallet_label.setText("<h2>Wallet: N/A</h2>"); self.active_sell_orders_label.setText("<b>Value of Active Sell Orders:</b> N/A"); self.active_buy_orders_label.setText("<b>Escrow in Active Buy Orders:</b> N/A"); self.clear_cargo_fields()
        self.total_sales_label.setText("<b>Total Sales:</b> N/A"); self.total_taxes_label.setText("<b>Total Taxes Paid:</b> N/A"); self.estimated_profit_label.setText("<b>Estimated Profit:</b> N/A"); self.estimated_profit_label.setStyleSheet("")
        self.active_orders_table.setRowCount(0); self.history_table.setRowCount(0)
        
    def clear_cargo_fields(self):
        self.ship_cargo_label.setText("<b>Current Ship Cargo Value:</b> 0.00 ISK"); self.cargo_table.setRowCount(0)

    def load_character_portrait(self):
        try:
            url = f"https://images.evetech.net/characters/{self.main_app.character_id}/portrait?size=128"
            response = requests.get(url, stream=True)
            if response.status_code == 200: pixmap = QPixmap(); pixmap.loadFromData(response.content); self.portrait_label.setPixmap(pixmap)
        except Exception as e:
            logging.error(f"Could not load character portrait: {e}")