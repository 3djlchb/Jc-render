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


ICONO_ARCHIVO = "jc_render.ico"


class JcRender(MenuPrincipal):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JC Render")
        self.resize(1400, 900)
        
        try:
            # 1. Crear una instancia de QIcon desde el archivo .ico
            app_icon = QIcon(ICONO_ARCHIVO)
            
            # 2. Establecer el icono de la ventana principal
            self.setWindowIcon(app_icon)
            
            # También puedes hacerlo en una sola línea:
            # self.setWindowIcon(QIcon(ICONO_ARCHIVO))
            
        except Exception as e:
            print(f"Error al cargar el icono: {e}")
            print(f"Asegúrate de que el archivo '{ICONO_ARCHIVO}' exista.")

        #LLAMADO DE LA FUNCIONES PROPIAS DE LA CLASE
        self._crear_menu()


    def _crear_menu(self):
        self.menu_bar = QMenuBar(self) # Creación del menu general
        self.setMenuBar(self.menu_bar)  # Empaquetamiento del menubar en el layout principal

        #---MENÚ ARCHIVO
        self.menu_archivo = QMenu("&Archivo", self)
        #---MENÚ ARCHIVO: Submenús
        self.menu_archivo_nuevo = self.menu_archivo.addAction("&Nuevo")
        self.menu_archivo_abrir = self.menu_archivo.addAction("&Abrir")
        self.menu_archivo.addSeparator()
        self.menu_archivo_salir = self.menu_archivo.addAction("&Salir")

        #---MENÚ EDICIÓN
        self.menu_edicion = QMenu("&Edición", self)
        #---MENÚ EDICIÓN: Submenús
        self.menu_edicion_deshacer = self.menu_edicion.addAction("&Deshacer")
        self.menu_edicion_rehacer = self.menu_edicion.addAction("&Rehacer")
        self.menu_edicion.addSeparator()
        self.menu_edicion_preferencias = self.menu_edicion.addAction("&Preferencias")

        #---MENÚ AYUDA
        self.menu_ayuda = QMenu("&Ayuda", self)
        #---MENÚ AYUDA: Submenús
        self.menu_ayuda_documentacion = self.menu_ayuda.addAction("&Documentación")
        self.menu_ayuda_acerca = self.menu_ayuda.addAction("&Acerca de ...")


        # EMPAQUETAMIENTO DE LOS MENÚS EN LA BARRA DE MENÚS
        self.menu_bar.addMenu(self.menu_archivo)
        self.menu_bar.addMenu(self.menu_edicion)
        self.menu_bar.addMenu(self.menu_ayuda)


    def info_archivo_blend(self):
        pass



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