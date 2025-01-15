import sys
import requests
from bs4 import BeautifulSoup
import sqlite3
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QComboBox, 
                           QFrame, QProgressBar, QMessageBox, QGridLayout)  # Add QGridLayout here
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from datetime import datetime

# Keep only the necessary database and data fetching functions
def fon_kod_listesini_getir():
    conn = sqlite3.connect('fund_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT fund_code FROM funds ORDER BY fund_code')
    fon_kod_listesi = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return fon_kod_listesi

def veri_getir(fon_kod):
    url = f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={fon_kod}"
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        veri = {}
        
        # Fon adını al
        fon_adi = soup.find('span', {'id': 'MainContent_FormViewMainIndicators_LabelFund'})
        if fon_adi:
            veri["Fon Adı"] = fon_adi.text.strip()
        
        # Ana göstergeleri al
        gostergeler = soup.select('.main-indicators li')
        for gosterge in gostergeler:
            try:
                etiket = gosterge.contents[0].strip()
                deger = gosterge.find('span')
                if deger:
                    veri[etiket] = deger.text.strip()
            except:
                continue
        
        # Getiri oranlarını al
        getiri_div = soup.find('div', {'class': 'price-indicators'})
        if getiri_div:
            getiriler = getiri_div.find_all('li')
            for getiri in getiriler:
                try:
                    etiket = ' '.join(getiri.text.split())  # Normalize spaces
                    deger = getiri.find('span')
                    if deger:
                        # Remove the label part to get only the value
                        etiket = etiket.replace(deger.text.strip(), '').strip()
                        veri[etiket] = deger.text.strip()
                except:
                    continue
                
        return veri
    return "Veri alınamadı"

def doviz_fiyat_getir():
    url = "https://www.doviz.com/"
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        market_data = soup.find('div', class_='market-data')
        if market_data:
            items = market_data.find_all('div', class_='item')
            prices = {}
            for item in items:
                name = item.find('span', class_='name').text.strip()
                value = item.find('span', class_='value').text.strip()
                
                # Değişim oranını ve yönünü al
                change_rate = item.find('div', class_='change-rate')
                if change_rate:
                    direction = 'up' if 'up' in change_rate.get('class', []) else 'down'
                    rate = change_rate.text.strip()
                else:
                    direction = 'neutral'
                    rate = "0%"
                
                # Değişim miktarını al
                change_amount = item.find('div', class_='change-amount')
                amount = change_amount.text.strip() if change_amount else ""
                
                prices[name] = {
                    'value': value,
                    'change_rate': rate,
                    'direction': direction,
                    'change_amount': amount
                }
            return prices
    return {}

class DovizWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #2c3e50;")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)  # Add fixed margins
        self.setFixedHeight(100)  # Set fixed height for doviz widget
        # Create and start timer
        self.timer = QTimer(self)  # Added self as parent
        self.timer.timeout.connect(self.update_prices)
        self.timer.start(2000)
        self.update_prices()  # Initial update

    def update_prices(self):
        # Clear existing widgets
        for i in reversed(range(self.layout.count())): 
            widget = self.layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Fetch and display new prices
        prices = doviz_fiyat_getir()  # Direct call to fetch prices
        for name, data in prices.items():
            frame = QFrame()
            frame.setFixedWidth(150)  # Set fixed width for each currency frame
            frame.setStyleSheet("background-color: #34495e; border-radius: 5px;")
            layout = QVBoxLayout(frame)
            layout.setSpacing(2)  # Reduce spacing between elements
            layout.setContentsMargins(5, 5, 5, 5)  # Set small margins
            
            name_label = QLabel(name)
            name_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
            name_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(name_label)
            
            value_label = QLabel(data['value'])
            value_label.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 14px;")
            value_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(value_label)
            
            change_color = "#2ecc71" if data['direction'] == 'up' else "#e74c3c"
            change_symbol = "↑" if data['direction'] == 'up' else "↓"
            
            change_label = QLabel(f"{change_symbol} {data['change_rate']} {data['change_amount']}")
            change_label.setStyleSheet(f"color: {change_color}; font-size: 11px;")
            change_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(change_label)
            
            self.layout.addWidget(frame)
            
            if name != list(prices.keys())[-1]:
                separator = QFrame()
                separator.setFrameShape(QFrame.VLine)
                separator.setFixedWidth(1)  # Thin line
                separator.setStyleSheet("background-color: #95a5a6;")
                self.layout.addWidget(separator)

    def get_doviz_prices(self):
        # Mevcut doviz_fiyat_getir fonksiyonunu kullan
        return doviz_fiyat_getir()

class DataFetcherThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, fund_codes):
        super().__init__()
        self.fund_codes = fund_codes

    def run(self):
        try:
            results = []
            total = len(self.fund_codes)
            for i, fund_code in enumerate(self.fund_codes):
                veri = veri_getir(fund_code)
                if isinstance(veri, dict):
                    results.append((fund_code, veri))
                self.progress.emit(int((i + 1) / total * 100))
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

class FonWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #2c3e50;")
        self.layout = QVBoxLayout(self)
        
        # Üst kısım - Fon seçimi
        top_frame = QFrame()
        top_frame.setStyleSheet("background-color: #34495e;")
        top_layout = QHBoxLayout(top_frame)
        
        self.combo = QComboBox()
        self.combo.setStyleSheet("""
            QComboBox {
                background-color: #2c3e50;
                color: white;
                padding: 5px;
                border: 1px solid #3498db;
                border-radius: 3px;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2c3e50;
                color: white;
                selection-background-color: #3498db;
                selection-color: white;
            }
        """)
        self.combo.addItems(fon_kod_listesini_getir())
        
        fetch_button = QPushButton("Veri Getir")
        fetch_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        fetch_button.clicked.connect(self.fetch_fund_data)
        
        top_layout.addWidget(self.combo)
        top_layout.addWidget(fetch_button)
        self.layout.addWidget(top_frame)
        
        # Alt kısım - Fon bilgileri için tek bir frame
        self.data_frame = QFrame()
        self.data_frame.setStyleSheet("background-color: #34495e;")
        self.data_layout = QVBoxLayout(self.data_frame)  # Changed to QVBoxLayout
        self.layout.addWidget(self.data_frame)

    def fetch_fund_data(self):
        # Clear existing data
        for i in reversed(range(self.data_layout.count())): 
            widget = self.data_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        fon_kod = self.combo.currentText()
        if not fon_kod:
            return

        def update_ui(veri):
            if isinstance(veri, dict) and veri:  # Check if veri is not empty
                main_frame = QFrame()
                main_frame.setStyleSheet("""
                    QFrame {
                        background-color: #2c3e50;
                        border-radius: 5px;
                        padding: 10px;
                    }
                """)
                main_layout = QVBoxLayout(main_frame)
                main_layout.setSpacing(10)
                
                # Fon başlığı
                if "Fon Adı" in veri:
                    header = QLabel(veri["Fon Adı"])
                    header.setStyleSheet("""
                        color: #3498db;
                        font-size: 16px;
                        font-weight: bold;
                        background-color: #34495e;
                        padding: 8px;
                        border-radius: 4px;
                    """)
                    header.setAlignment(Qt.AlignCenter)
                    main_layout.addWidget(header)

                # Fon verileri grid
                data_widget = QWidget()
                data_layout = QGridLayout(data_widget)
                data_layout.setSpacing(8)
                data_layout.setContentsMargins(10, 10, 10, 10)
                
                # Normal verileri gride yerleştir
                row = 0
                col = 0
                max_cols = 3  # Her satırda 3 veri
                
                for key, value in veri.items():
                    if not 'Getiri' in key and key != "Fon Adı":
                        item_widget = QWidget()
                        item_layout = QHBoxLayout(item_widget)
                        item_layout.setContentsMargins(5, 5, 5, 5)
                        
                        key_label = QLabel(f"{key}:")
                        key_label.setStyleSheet("color: #95a5a6; font-weight: bold;")
                        key_label.setFixedWidth(150)
                        
                        value_label = QLabel(str(value))
                        value_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
                        
                        item_layout.addWidget(key_label)
                        item_layout.addWidget(value_label)
                        item_layout.addStretch()
                        
                        data_layout.addWidget(item_widget, row, col)
                        
                        col += 1
                        if col >= max_cols:
                            col = 0
                            row += 1
                
                main_layout.addWidget(data_widget)
                
                # Getiri verileri
                returns_widget = QWidget()
                returns_layout = QHBoxLayout(returns_widget)
                returns_layout.setSpacing(5)
                returns_layout.setContentsMargins(0, 10, 0, 0)
                
                for key, value in veri.items():
                    if 'Getiri' in key:
                        return_frame = QFrame()
                        return_frame.setStyleSheet("""
                            QFrame {
                                background-color: #34495e;
                                border-radius: 4px;
                                padding: 8px;
                            }
                        """)
                        return_layout = QVBoxLayout(return_frame)
                        return_layout.setSpacing(5)
                        
                        period_label = QLabel(key)
                        period_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
                        period_label.setAlignment(Qt.AlignCenter)
                        
                        value_label = QLabel(value)
                        value_label.setStyleSheet("color: #3498db; font-size: 16px; font-weight: bold;")
                        value_label.setAlignment(Qt.AlignCenter)
                        
                        return_layout.addWidget(period_label)
                        return_layout.addWidget(value_label)
                        returns_layout.addWidget(return_frame)
                
                main_layout.addWidget(returns_widget)
                self.data_layout.addWidget(main_frame)
            else:
                # Show error message if no data
                error_label = QLabel("Veri alınamadı veya boş veri döndü!")
                error_label.setStyleSheet("""
                    color: #e74c3c;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 10px;
                """)
                self.data_layout.addWidget(error_label)

        # Thread'de veri çekme
        class FetchThread(QThread):
            finished = pyqtSignal(dict)
            
            def run(self):
                data = veri_getir(fon_kod)
                self.finished.emit(data)

        self.thread = FetchThread()
        self.thread.finished.connect(update_ui)
        self.thread.start()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TEFAS Veri Çekici")
        self.setMinimumWidth(1000)
        self.setStyleSheet("background-color: #1a1a1a;")
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        doviz_widget = DovizWidget()
        layout.addWidget(doviz_widget)

        fon_widget = FonWidget()
        layout.addWidget(fon_widget)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
