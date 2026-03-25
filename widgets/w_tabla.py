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


class Prueba(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.estilo_campos = "QHeaderView::section { background-color: rgb(40,108,25) }"
        layout =QVBoxLayout(self)

        grupo_versiones_blender = QGroupBox("Versiones de blender.exe y archivos .blend")
        layout_versiones_blender = QVBoxLayout(grupo_versiones_blender)
        layout_versiones_blender.addWidget(QLabel("Ruta blender.exe:"))

        # Ruta del ejecutable de blender (Layout Horizontal)
        frame_layout_ejecutables = QWidget()
        layout_ejecutables = QHBoxLayout(frame_layout_ejecutables)
        layout_ejecutables.setSpacing(5)
        layout_ejecutables.setContentsMargins(0, 0, 0, 0)

        self.ent_blend_exe = QLineEdit()
        self.btn_examinar_exe = QPushButton("Examinar")
        #self.btn_examinar_exe.clicked.connect(self._buscar_blender_exe)

        layout_ejecutables.addWidget(self.ent_blend_exe)
        layout_ejecutables.addWidget(self.btn_examinar_exe)

        layout_versiones_blender.addWidget(frame_layout_ejecutables)
        layout.addWidget(grupo_versiones_blender)
        layout.addStretch()
