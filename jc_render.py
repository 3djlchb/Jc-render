import os 
import sys
sys.path.append(os.path.abspath('...'))

import sqlite3
import subprocess   # Para ejecutar Blender
import json         # Para manejar los metadatos JSON
import tempfile     # Para crear el script temporal de Blender

# sys.path.append(os.path.abspath('...')) 

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QBoxLayout, QGridLayout, QGroupBox, QTextEdit, QVBoxLayout, QLabel, QCheckBox,
    QHBoxLayout, QPushButton, QDialogButtonBox, QFormLayout, QComboBox, QRadioButton, QTreeView, QTabWidget,
    QListView, QTableView, QTableWidget, QTableWidgetItem, QWidget, QLineEdit, QFileDialog, QHeaderView,
    QMessageBox, QSizePolicy, QMenuBar, QMenu
    )

from PySide6.QtGui import (QIcon, QStandardItemModel, QStandardItem, QPalette, QFont, QColor,QIcon)
from PySide6.QtCore import (Qt, QStringListModel, QSettings, QProcess, Slot) 

# IMPORTACIÓN DE LOS MODULOS CREADOS
from menu_principal import MenuPrincipal
from dialogos.dialogo_preferencias import PreferenciasDialog


ICONO_ARCHIVO = "jc_render.ico"


class JcRender(QMainWindow): # HEREDA DE QMainWindow
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JC Render - Batch Manager Pro")
        self.resize(1600, 900)
        
        # 1. ESTABLECER EL CONTENIDO (Lógica de menu_principal)
        # Al hacer esto, JcRender tiene acceso a 'self.contenido.cargar_datos_desde_db()'
        self.contenido = MenuPrincipal(self)
        self.setCentralWidget(self.contenido)

        # 2. CONFIGURAR INTERFAZ
        if os.path.exists(ICONO_ARCHIVO):
            self.setWindowIcon(QIcon(ICONO_ARCHIVO))
        
        self._crear_menu()

    def _crear_menu(self):
        # Ahora setMenuBar funcionará porque JcRender es un QMainWindow
        self.barra_menu = self.menuBar() 

        # Menú Archivo
        menu_archivo = self.barra_menu.addMenu("&Archivo")
        menu_archivo.addAction("&Salir", self.close)

        # Menú Edición
        menu_edicion = self.barra_menu.addMenu("&Edición")
        acc_pref = menu_edicion.addAction("&Preferencias")
        acc_pref.triggered.connect(self._abrir_preferencias)

        # Menú Ayuda
        menu_ayuda = self.barra_menu.addMenu("&Ayuda")
        menu_ayuda.addAction("&Acerca de...")


    def _abrir_preferencias(self):
        try:
            print("Intentando abrir preferencias...") # Debug en consola
            dialogo = PreferenciasDialog(self)
            
            # exec() devuelve QDialog.Accepted (1) si el usuario pulsa Aceptar/Guardar
            if dialogo.exec():
                print("Preferencias cerradas con éxito. Recargando base de datos...")
                self.contenido.cargar_datos_desde_db()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir el diálogo: {str(e)}")
        



if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 2. Establecer el icono a nivel de aplicación (Barra de Tareas)
    # ¡Esta es la clave para la barra de tareas en Windows!
    if not QIcon.hasThemeIcon(""):
        icon_path = ICONO_ARCHIVO
        if not QIcon(icon_path).isNull():
            app.setWindowIcon(QIcon(icon_path))
        else:
            print(f"ERROR: No se pudo cargar el icono desde la ruta: {icon_path}")
            # El programa continuará, pero sin el icono.

    ventana = JcRender()
    ventana.show()
    sys.exit(app.exec())