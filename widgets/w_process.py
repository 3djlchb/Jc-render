import os 
import sys
sys.path.append(os.path.abspath('...'))

from typing import List

import sqlite3
import subprocess   # Para ejecutar Blender
import json         # Para manejar los metadatos JSON
import tempfile     # Para crear el script temporal de Blender

# sys.path.append(os.path.abspath('...')) 

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QBoxLayout, QGridLayout, QGroupBox, QTextEdit, QVBoxLayout, QLabel, QCheckBox,
    QHBoxLayout, QPushButton, QDialogButtonBox, QFormLayout, QComboBox, QRadioButton, QTreeView, QTabWidget,
    QListView, QTableView, QTableWidget, QTableWidgetItem, QWidget, QLineEdit, QFileDialog, QHeaderView,
    QMessageBox, QSizePolicy, QProgressBar
    )

from PySide6.QtGui import (QIcon, QStandardItemModel, QStandardItem, QPalette, QFont, QColor, QIcon)
from PySide6.QtCore import (Qt, QSize, QStringListModel, QSettings, QProcess, Slot, QFileInfo, QTimer) 


class EstadoProgressWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2) # Margen pequeño para que quepa en la fila
        layout.setSpacing(0)

        # 1. Texto de estado
        self.label = QLabel("Cargando...   ")
        self.label.setStyleSheet("font-size: 10px; font-weight: bold;")
        self.label.setAlignment(Qt.AlignCenter)
        
        # 2. Barra de progreso
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(12)
        self.pbar.setTextVisible(True) # Muestra el porcentaje (e.g. "50%")
        self.pbar.setRange(0, 0) # Estilo "Indeterminado" (animación infinita) hasta que sepamos el progreso
        self.pbar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                text-align: center;
                font-size: 9px;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #05B8CC;
                width: 10px;
            }
        """)

        layout.addWidget(self.label)
        layout.addWidget(self.pbar)

    def set_progress(self, value):
        """Actualiza el porcentaje manualmente si es necesario."""
        self.pbar.setRange(0, 100)
        self.pbar.setValue(value)

    def set_status(self, text):
        self.label.setText(text)