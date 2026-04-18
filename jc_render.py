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
    QMessageBox, QSizePolicy, QMenuBar, QMenu, QToolBar
    )

from PySide6.QtGui import (QIcon, QStandardItemModel, QStandardItem, QPalette, QFont, QColor, QAction)
from PySide6.QtCore import (Qt, QStringListModel, QSettings, QProcess, Slot, QSize) 

# IMPORTACIÓN DE LOS MODULOS CREADOS
from menu_principal import MenuPrincipal
from dialogos.dialogo_preferencias import PreferenciasDialog


ICONO_ARCHIVO = "jc_render.ico"
VERSION_COMPILADO = "v- 0.1.5"


class JcRender(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"JC Render - Batch Manager Pro {VERSION_COMPILADO}")
        self.resize(1600, 900)
        
        # 1. CONTENIDO CENTRAL
        self.contenido = MenuPrincipal(self)
        self.setCentralWidget(self.contenido)

        # 2. CONFIGURAR INTERFAZ
        if os.path.exists(ICONO_ARCHIVO):
            self.setWindowIcon(QIcon(ICONO_ARCHIVO))
        
        # Inicializar Menús y Barra de Herramientas
        self._crear_acciones() # Creamos las acciones primero
        self._crear_menu()
        self._crear_barra_herramientas()


    def _crear_acciones(self):
        """Define las acciones que se compartirán entre menú y barra de herramientas"""
        # Acción Preferencias
        self.acc_pref = QAction("⚙️ Preferencias.", self)
        # Si tienes un icono específico: self.acc_pref = QAction(QIcon("tu_icono.png"), "Pref...", self)
        self.acc_pref.setShortcut("Ctrl+P")
        self.acc_pref.setStatusTip("Configurar rutas de Blender y Base de Datos")
        self.acc_pref.triggered.connect(self._abrir_preferencias)

        # Acción Salir
        self.acc_salir = QAction("&Salir", self)
        self.acc_salir.triggered.connect(self.close)

    def _crear_menu(self):
        self.barra_menu = self.menuBar() 

        # Menú Archivo
        menu_archivo = self.barra_menu.addMenu("&Archivo")
        menu_archivo.addAction(self.acc_salir)

        # Menú Edición
        menu_edicion = self.barra_menu.addMenu("&Edición")
        menu_edicion.addAction(self.acc_pref) # Reutilizamos la acción

        # Menú Ayuda
        menu_ayuda = self.barra_menu.addMenu("&Ayuda")
        menu_ayuda.addAction("&Acerca de...")

    def _crear_barra_herramientas(self):

        self.config_panel = PreferenciasDialog(self)

        """Configuración de la QToolBar"""
        self.toolbar = QToolBar("Barra de Herramientas Principal")
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setMovable(False) # Opcional: fijar la barra
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        # Añadir la acción de Preferencias a la barra
        self.toolbar.addAction(self.acc_pref)
        
        # Ejemplo: Añadir un separador y más botones
        #self.toolbar.addSeparator()
        
        # Si quieres añadir un botón que llame a la sincronización de menu_principal
        acc_sync = QAction("🔄 Sync. Cambios", self)
        acc_sync.triggered.connect(self.contenido.cargar_datos_desde_db)
        self.toolbar.addAction(acc_sync)

        # Creamos el botón aquí para la toolbar
        btn_sync = QPushButton("🔄 Sincronizar Proyectos")
        btn_sync.setFixedHeight(35)
        btn_sync.setStyleSheet("background-color: #d68910; color: white;")
        
        # CONEXIÓN CRUZADA: Conectamos el click a la función que vive en el otro script
        btn_sync.clicked.connect(self.config_panel.sincronizar_todos_los_proyectos)
        
        # Añadir a la toolbar principal
        self.toolbar.addWidget(btn_sync)
        

    def _abrir_preferencias(self):
        try:
            print("Intentando abrir preferencias...")
            dialogo = PreferenciasDialog(self)
            if dialogo.exec():
                print("Preferencias cerradas con éxito. Recargando...")
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