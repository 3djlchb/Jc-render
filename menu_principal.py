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


def get_resource_path(relative_path):
    """
    Obtiene la ruta absoluta del recurso, compatible con desarrollo y cx_Freeze.
    
    En cx_Freeze, la base de los archivos de datos es el directorio 
    donde se encuentra el ejecutable o el paquete congelado.
    """
    if getattr(sys, 'frozen', False):
        # Estamos en modo ejecutable (cx_Freeze)
        # sys.executable es la ruta del EXE.
        # sys._MEIPASS (usado por PyInstaller) generalmente no se usa aquí.
        base_path = os.path.dirname(sys.executable)
    else:
        # Modo de desarrollo (archivo .py)
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)



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



class MenuPrincipal(QMainWindow):

    def __init__(self):
        super().__init__()

        self.central_widget = QWidget()  # Contenedor central
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)  # Layout principal del contenedor central

        self.notebook = QTabWidget()  # Crear el widget de pestañas (Notebook)
        self.main_layout.addWidget(self.notebook)

        # Inicializa la lista que guardará las rutas.
        self.lista_rutas_blend_exe = []
        self.lista_rutas_blend = []


        # 🟢 Paso Clave 2: Definir la ruta del script usando la función de arriba
        # Esto funciona en .py y en .exe.
        self.info_script_path = get_resource_path("info_archivo_blend.py")

        # ... (resto de tu __init__) ...
        
        # Opcional: Verifica si el script existe.
        if not os.path.exists(self.info_script_path):
            QMessageBox.critical(self, "Error de Archivo", f"El script auxiliar no se encuentra en: {self.info_script_path}")

        # Configuración para persistencia (QSettings)
        self.settings = QSettings("JC", "JcRenderApp")
        self._default_dir = os.path.expanduser("~")  # Inicialización de la variable _default_dir (Solución al AttributeError)

        # Creación de los tabs y widgets
        self._crear_tabs()
        
        # Cargar la configuración persistente
        self._cargar_configuracion() 

        # --- INICIALIZACION DE QPROCESS
        self.blender_process = QProcess(self)
        self.info_process = QProcess(self)
        self.progress_timer = QTimer(self) # <-- ¡ESTA LÍNEA ES CLAVE!

        # 🟢 INICIALIZACIÓN FALTANTE: TEMPORIZADOR Y VARIABLES DE ESTADO
        # Buffer para acumular la salida de Blender
        self._json_buffer = ""
        self._current_process_row = -1 
        self._simulated_progress = 0

        # 1. DEFINICIÓN DENTRO DE __init__
        self.DB_FOLDER = 'bbdd' 
        self.DB_NAME = 'configuracion.db'
        
        # self.DB_FILE contendrá 'bbdd/configuracion.db'
        self.DB_FILE = os.path.join(self.DB_FOLDER, self.DB_NAME) 
        self.TABLA_SQL = 'rutas_blender'

        # 2. 🔗 Conexiones de Procesos Asíncronos (CRÍTICAS)
        self._connect_async_processes()

        # 3. 🔗 Conexiones de Eventos de la Interfaz
        #self._connect_ui_signals()

        # 4. 🚀 Inicialización Final
        self._initial_load()

    
    def _connect_async_processes(self):

        self.blender_process.readyReadStandardOutput.connect(self.read_std_output)
        self.blender_process.readyReadStandardError.connect(self.read_std_error)
        self.blender_process.finished.connect(self.process_finished) 

        self.progress_timer.timeout.connect(self._update_simulated_progress)

        # --- NUEVO: Proceso para obtener info del archivo ---
        self.info_process.readyReadStandardOutput.connect(self.read_info_output)
        self.info_process.readyReadStandardError.connect(self.read_info_error)
        self.info_process.finished.connect(self.info_process_finished)

    
    def _connect_ui_signals(self):
        """Conecta los botones, campos de texto y tablas a sus slots."""
        
        # --- PESTAÑA PRINCIPAL (Carga de Archivos) ---
        
        # 1. Selector de Archivo .blend
        # self.btn_browse_blend.clicked.connect(self._browse_blend_file)
        # 2. Botón de Carga (Inicia el QProcess de metadatos)
        self.btn_cargar.clicked.connect(self._cargar_blend_a_tabla) 
        
        # 3. Clics en la Tabla Principal (para interacción/selección)
        self.tabla_archivos_blend.cellClicked.connect(self.manejar_clic_celda)
        # Si tienes la ruta del script guardada:
        # self.btn_select_script.clicked.connect(self._browse_script_file)


        # --- PESTAÑA DE CONFIGURACIÓN DE BLENDER (Base de Datos) ---
        
        # 4. Selector de Ejecutable de Blender
        self.btn_examinar_exe.clicked.connect(self._buscar_blender_exe)
        # 5. Botón Añadir a DB
        self.btn_examinar_exe.clicked.connect(self._procesar_y_cargar_db)
        # 6. Botón Eliminar de DB
        self.btn_eliminar_exe.clicked.connect(self._eliminar_ruta_seleccionada)
        
        
        # --- PESTAÑA DE RENDERIZADO ---
        
        # 7. Disparador de Render (Clic en la columna 9 de la tabla de render)
        # Aquí conectamos la activación/clic de la celda "Render"
        self.tabla_metadatos_a_renderizar.cellActivated.connect(self.manejar_activacion_celda_render)
        
        # 8. Botón General de Render (Si existe, usar la versión con parámetros)
        # self.btn_renderizar.clicked.connect(self.start_render) # <-- Si el botón lee los campos de la tabla


    def _initial_load(self):
        """Carga inicial de datos al iniciar la aplicación."""
        
        # 1. Cargar las rutas de Blender desde la Base de Datos
        self._cargar_rutas_blender_db()
        


    def _cargar_configuracion(self):
        """Carga la configuración persistente (rutas de Blender y carpeta .blend)."""
        
        # 1. Cargar ruta del ejecutable de Blender
        blender_path = self.settings.value("blender_exe_path", "", type=str)
        if blender_path:
            self.ent_blend_exe.setText(blender_path)
            print(f"Configuración cargada: Ruta de Blender establecida a {blender_path}")

        # 2. Cargar la última carpeta del archivo .blend
        blend_dir = self.settings.value("blend_file_directory", "", type=str)
        if blend_dir and os.path.isdir(blend_dir):
            self._default_dir = blend_dir
            print(f"Configuración cargada: Carpeta de .blend por defecto establecida a {blend_dir}")
        

    def _crear_tabs(self):
        """Inicializa y añade las tres pestañas al QTabWidget."""
        
        # --- Pestaña 1: Render ---
        self.tab1_iniciar = QWidget()
        self.notebook.addTab(self.tab1_iniciar, "⚙️ Inicio")
        self._setup_tab_iniciar()
        #self._cargar_rutas_blender_db()

        # --- Pestaña 2: Configuración ---
        self.tab2_configurar = QWidget()
        self.notebook.addTab(self.tab2_configurar, "🔧 Configuración y Render")
        self._setup_tab_configurar()
        
        # --- Pestaña 3: Consola de Salida ---
        self.tab3_consola = QWidget()
        self.notebook.addTab(self.tab3_consola, "🖥️ Consola de Salida")
        self._setup_tab_consola()

    
    def _setup_tab_iniciar(self):
        """Define los elementos de la pestaña principal de Render y las dos tablas."""

        self.estilo_campos = "QHeaderView::section { background-color: rgb(40,108,25) }"
        
        # --- Grupo 0: Rutas y tablas
        layout = QVBoxLayout(self.tab1_iniciar)

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
        self.btn_examinar_exe.clicked.connect(self._buscar_blender_exe)

        layout_ejecutables.addWidget(self.ent_blend_exe)
        layout_ejecutables.addWidget(self.btn_examinar_exe)
        
        #----------------------------------------------------------------
        
        frame_btn_ejecutables = QWidget()
        layout_btn_ejecutables = QHBoxLayout(frame_btn_ejecutables)
        layout_btn_ejecutables.setSpacing(5)
        layout_btn_ejecutables.setContentsMargins(0, 0, 0, 0)

        self.btn_cargar_exe = QPushButton("Cargar rutas ejecutables blender.exe")
        self.btn_cargar_exe.clicked.connect(self._procesar_y_cargar_db)
        self.btn_eliminar_exe = QPushButton("Eliminar ruta blender.exe seleccionada")
        self.btn_eliminar_exe.clicked.connect(self._eliminar_ruta_seleccionada)

        layout_btn_ejecutables.addWidget(self.btn_cargar_exe)
        layout_btn_ejecutables.addWidget(self.btn_eliminar_exe)

        #-------------------------------------------------------------------
        # Tabla de guardado de los ejecutables
        campos_blend_exe = ["Ruta completa blender.exe", "Version blender.exe"]

        frame_tabla_ejecutables = QWidget()
        layout_tabla_ejecutables = QGridLayout(frame_tabla_ejecutables)
        layout_tabla_ejecutables.setSpacing(5)
        layout_tabla_ejecutables.setContentsMargins(0, 0, 0, 0)

        self.tabla_blend_exe = QTableWidget()
        self.tabla_blend_exe.setColumnCount(len(campos_blend_exe))
        self.tabla_blend_exe.setHorizontalHeaderLabels(campos_blend_exe)
        self.tabla_blend_exe.horizontalHeader().setStyleSheet(self.estilo_campos)

        self.tabla_blend_exe.setColumnWidth(0, 800) # Ruta completa blender.exe
        self.tabla_blend_exe.setColumnWidth(1, 250) # Version blender.exe

        header0 = self.tabla_blend_exe.horizontalHeader()

        # Columna 1 (Ruta completa) toma el espacio restante
        header0.setSectionResizeMode(0, QHeaderView.Stretch) 
        
        # Columna 0 (Nombre archivo) y 2 (Estado) se ajustan al contenido, pero permiten arrastrar
        header0.setSectionResizeMode(1, QHeaderView.ResizeToContents)
         
        # Aseguramos que todas son interactivas (permite arrastrar)
        header0.setSectionResizeMode(0, QHeaderView.Interactive)
        header0.setSectionResizeMode(1, QHeaderView.Interactive)
        header0.setStretchLastSection(True)

        layout_tabla_ejecutables.addWidget(self.tabla_blend_exe, 0, 0)
        

        #----------------------------------------------------------------
        frame_lista_ejecutables = QWidget()
        layout_lista_ejecutables = QGridLayout(frame_lista_ejecutables)
        layout_lista_ejecutables.setSpacing(5)
        layout_lista_ejecutables.setContentsMargins(0, 0, 0, 0)

        lb_lista_blend_exe = QLabel("Lista blend.exe:")
        self.cmb_blend_exe = QComboBox()

        lb_ent_archivo_blend = QLabel("Ruta del archivo .blend:")
        self.ent_blend = QLineEdit()
        btn_blend = QPushButton("Examinar")
        btn_blend.clicked.connect(self._browse_blend_file)

        layout_lista_ejecutables.addWidget(lb_lista_blend_exe, 0, 0)
        layout_lista_ejecutables.addWidget(self.cmb_blend_exe, 1, 0, 1, 2)
        layout_lista_ejecutables.addWidget(lb_ent_archivo_blend, 2, 0)
        layout_lista_ejecutables.addWidget(self.ent_blend, 3, 0)
        layout_lista_ejecutables.addWidget(btn_blend, 3, 1)

        #-----------------------------------------------------------------
        frame_btn_cargar = QWidget()
        layout_btn_cargar = QHBoxLayout(frame_btn_cargar)
        layout_btn_cargar.setSpacing(5)
        layout_btn_cargar.setContentsMargins(0, 0, 0, 0)

        self.btn_cargar = QPushButton("Cargar")
        self.btn_cargar.clicked.connect(self._cargar_blend_a_tabla)

        layout_btn_cargar.addWidget(self.btn_cargar)

        # --------------------------------------------------------------
        # Empaquetado de widgets al layout versiones blender
        layout_versiones_blender.addWidget(frame_layout_ejecutables)
        layout_versiones_blender.addWidget(frame_btn_ejecutables)
        layout_versiones_blender.addWidget(frame_tabla_ejecutables)
        layout_versiones_blender.addWidget(frame_lista_ejecutables)
        layout_versiones_blender.addWidget(frame_btn_cargar)
        layout_versiones_blender.addStretch(1)

        # --- Grupo 2: Tabla de los archivos .blend cargados
        campos_archivos_blend = ["Ruta completa", "Nombre de archivo", "Version blender", "Estado"]
        
        grupo_tabla_archivos_blend = QGroupBox("Carga de archivos .blend")
        layout_tabla_archivos_blend = QVBoxLayout(grupo_tabla_archivos_blend) 
        self.tabla_archivos_blend = QTableWidget()
        self.tabla_archivos_blend.setColumnCount(len(campos_archivos_blend))
        self.tabla_archivos_blend.setHorizontalHeaderLabels(campos_archivos_blend)
        self.tabla_archivos_blend.horizontalHeader().setStyleSheet(self.estilo_campos)

        self.tabla_archivos_blend.setColumnWidth(0, 600) # Ruta completa
        self.tabla_archivos_blend.setColumnWidth(1, 250) # Nombre de archivo
        self.tabla_archivos_blend.setColumnWidth(2, 100) # Version blender
        self.tabla_archivos_blend.setColumnWidth(3, 100) # Estado

        header1 = self.tabla_archivos_blend.horizontalHeader()
        
        # 🟢 Lógica de AJUSTE MIXTO (Tabla 1: Archivos .blend)
        
        # Columna 1 (Ruta completa) toma el espacio restante
        header1.setSectionResizeMode(0, QHeaderView.Stretch) 
        
        # Columna 0 (Nombre archivo) y 2 (Estado) se ajustan al contenido, pero permiten arrastrar
        header1.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header1.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        # Aseguramos que todas son interactivas (permite arrastrar)
        header1.setSectionResizeMode(0, QHeaderView.Interactive)
        header1.setSectionResizeMode(1, QHeaderView.Interactive)
        header1.setSectionResizeMode(2, QHeaderView.Interactive)
        header1.setStretchLastSection(True)

        layout_tabla_archivos_blend.addWidget(self.tabla_archivos_blend)
        
        # La última columna NO necesita estirarse si la columna 1 ya lo hace,
        # pero para asegurar que el contenido corto esté visible, usamos esta lógica.
        # Ya que la columna 1 será la principal estirada.
        #header1.setStretchLastSection(False)
        layout.addWidget(grupo_versiones_blender)
        layout.addWidget(grupo_tabla_archivos_blend)
        
        
    def _setup_tab_configurar(self):

        """Define los elementos de la pestaña de Configuración avanzada."""
        layout = QVBoxLayout(self.tab2_configurar)
        
        # --- Grupo 3: Tabla de Metadatos --- (NUEVO)
        campos_metadatos = ["Nombre de archivo", "Version blender", "Escena activa", "View Layer", "Camara activa", 
                            "Frame Inicio", "Frame Fin", "fps", "Resolución", "Cameras"]

        grupo_tabla_metadatos = QGroupBox("Metadatos del Archivo .blend")
        layout_tabla_metadatos = QVBoxLayout(grupo_tabla_metadatos)
        self.tabla_metadatos = QTableWidget()
        self.tabla_metadatos.setColumnCount(len(campos_metadatos))
        self.tabla_metadatos.setHorizontalHeaderLabels(campos_metadatos)
        self.tabla_metadatos.horizontalHeader().setStyleSheet(self.estilo_campos)

        self.tabla_metadatos.setColumnWidth(0, 250) # Nombre de archivo
        self.tabla_metadatos.setColumnWidth(1, 90) # Version blender
        self.tabla_metadatos.setColumnWidth(2, 150) # Escena activa
        self.tabla_metadatos.setColumnWidth(3, 150) # View Layer
        self.tabla_metadatos.setColumnWidth(4, 180) # Camara activa
        self.tabla_metadatos.setColumnWidth(5, 80) # Frame Inicio
        self.tabla_metadatos.setColumnWidth(6, 80) # Frame Fin
        self.tabla_metadatos.setColumnWidth(7, 80) # fps
        self.tabla_metadatos.setColumnWidth(8, 100) # Resolucion
        self.tabla_metadatos.setColumnWidth(9, 150) # Cameras

        layout_tabla_metadatos.addWidget(self.tabla_metadatos)
        layout_tabla_metadatos.addStretch()
        grupo_tabla_metadatos.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        layout.addWidget(grupo_tabla_metadatos)
        
        header2 = self.tabla_metadatos.horizontalHeader()
        
        # 🟢 Lógica de AJUSTE MIXTO (Tabla 2: Metadatos)
        
        # Columna 5 (Frame Fin) o la que sea más crítica para estirar, toma el espacio restante.
        header2.setSectionResizeMode(7, QHeaderView.Stretch) 
        
        # Las columnas 0 a 7 se ajustan al contenido, pero permiten arrastrar
        for i in range(7): 
            # Primero: Ajuste por contenido
            header2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            # Segundo: Habilitar interacción para poder arrastrar
            header2.setSectionResizeMode(i, QHeaderView.Interactive)

        # La última columna (5) es la que se estira y rellena el espacio.
        header2.setSectionResizeMode(7, QHeaderView.Interactive) # También debe ser interactiva
        header2.setStretchLastSection(True)


        # --- Grupo 4: Tabla de Metadatos para renderizar --- (NUEVO)
        campos_metadatos_a_renderizar = ["Nombre de archivo", "Version blender", "Motor de render", "Procesamiento", 
                                         "Carpeta de salida (//)", "Nombre de imagen", "Formato de imagen", 
                                         "Desde Frame", "Hasta Frame", "Render"]

        grupo_tabla_metadatos_a_renderizar = QGroupBox("Configuración de los archivos .blend a renderizar")
        layout_tabla_metadatos_a_renderizar = QVBoxLayout(grupo_tabla_metadatos_a_renderizar)
        self.tabla_metadatos_a_renderizar = QTableWidget()
        self.tabla_metadatos_a_renderizar.setColumnCount(len(campos_metadatos_a_renderizar))
        self.tabla_metadatos_a_renderizar.setHorizontalHeaderLabels(campos_metadatos_a_renderizar)
        self.tabla_metadatos_a_renderizar.horizontalHeader().setStyleSheet(self.estilo_campos)

        self.tabla_metadatos_a_renderizar.setColumnWidth(0, 250) # Nombre de archivo
        self.tabla_metadatos_a_renderizar.setColumnWidth(1, 100) # Version blender
        self.tabla_metadatos_a_renderizar.setColumnWidth(2, 100) # Motor de render
        self.tabla_metadatos_a_renderizar.setColumnWidth(3, 100) # Procesamiento
        self.tabla_metadatos_a_renderizar.setColumnWidth(4, 150) # Carpeta de salida
        self.tabla_metadatos_a_renderizar.setColumnWidth(5, 120) # Nombre de imagen
        self.tabla_metadatos_a_renderizar.setColumnWidth(6, 120) # Formato de imagen
        self.tabla_metadatos_a_renderizar.setColumnWidth(7, 100) # Desde Frame
        self.tabla_metadatos_a_renderizar.setColumnWidth(8, 100) # Hasta Frame
        self.tabla_metadatos_a_renderizar.setColumnWidth(9, 100) # Render

        self.tabla_metadatos_a_renderizar.cellClicked.connect(self.manejar_activacion_celda_render)

        layout_tabla_metadatos_a_renderizar.addWidget(self.tabla_metadatos_a_renderizar)
        layout_tabla_metadatos_a_renderizar.addStretch()
        grupo_tabla_metadatos.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        layout.addWidget(grupo_tabla_metadatos_a_renderizar)

        header3 = self.tabla_metadatos_a_renderizar.horizontalHeader()
        
        # 🟢 Lógica de AJUSTE MIXTO (Tabla 2: Metadatos)
        
        # Columna 5 (Frame Fin) o la que sea más crítica para estirar, toma el espacio restante.
        header3.setSectionResizeMode(9, QHeaderView.Stretch) 
        
        # Las columnas 0 a 7 se ajustan al contenido, pero permiten arrastrar
        for i in range(7): 
            # Primero: Ajuste por contenido
            header3.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            # Segundo: Habilitar interacción para poder arrastrar
            header3.setSectionResizeMode(i, QHeaderView.Interactive)

        # La última columna (5) es la que se estira y rellena el espacio.
        header3.setSectionResizeMode(7, QHeaderView.Interactive) # También debe ser interactiva
        header3.setStretchLastSection(True)

        

        # EMPAQUETAMIENTO DE LOS DIFERENTES GRUPOBOX
        
        #layout_tabla_metadatos_a_renderizar.addStretch(1) 

        
        # --- Grupo 1: Configurar y renderizar ---
        cfg_group = QGroupBox("Configuración del archivo .blend a renderizar")
        cfg_layout = QGridLayout(cfg_group)

        # Fila 0: Ruta del archivo .blend
        cfg_layout.addWidget(QLabel("Ruta completa .blend:"), 0, 0)
        self.cmb_ruta_blend_a_renderizar = QComboBox()
        self.l = self.obtener_lista_de_columna_cero()
        self.cmb_ruta_blend_a_renderizar.addItems(self.l)
        #self.cmb_ruta_blend_a_renderizar.setCurrentText(self.lista_rutas_blend[0])
        cfg_layout.addWidget(self.cmb_ruta_blend_a_renderizar, 0, 1, 1, 14)

        # Fila 1: Nombre del archivo .blend
        cfg_layout.addWidget(QLabel("Nombre de archivo:"), 1, 0)
        self.ent_nombre_archivo_a_renderizar = QLineEdit()
        cfg_layout.addWidget(self.ent_nombre_archivo_a_renderizar, 1, 1, 1, 14)

        # Fila 2: Motor de Render
        cfg_layout.addWidget(QLabel("Motor de Render:"), 2, 0)
        lista_motor = ["EEVEE", "CYCLES"]
        self.cmb_engine = QComboBox()
        self.cmb_engine.addItems(lista_motor)
        self.cmb_engine.setCurrentText(lista_motor[1])
        cfg_layout.addWidget(self.cmb_engine, 2, 1)

        # Fila 3: Procesamiento
        cfg_layout.addWidget(QLabel("Dispositivo de Procesamiento:"), 2, 3)
        self.cmb_procesamiento_render = QComboBox()
        self.cmb_procesamiento_render.addItems(["CPU", "CUDA", "OPTIX", "METAL"])
        self.cmb_procesamiento_render.setCurrentText("CUDA")
        cfg_layout.addWidget(self.cmb_procesamiento_render, 2, 4)

        # Fila 4 Carpeta de Salida
        cfg_layout.addWidget(QLabel("Carpeta de Salida (Relativa):"), 2, 5)
        self.ent_carpeta_salida = QLineEdit("render")
        cfg_layout.addWidget(self.ent_carpeta_salida, 2, 6)

        # Fila 5 Nombre de imagen
        cfg_layout.addWidget(QLabel("Nombre de imagen:"), 2, 7)
        self.ent_nombre_imagen = QLineEdit("img_")
        cfg_layout.addWidget(self.ent_nombre_imagen, 2, 8)

        # Fila 6: Formato de Imagen
        cfg_layout.addWidget(QLabel("Formato de Imagen:"), 2, 9)
        lista_formato_img = ["PNG", "JPEG", "EXR", "TIFF"]
        self.cmb_formato_img = QComboBox()
        self.cmb_formato_img.addItems(lista_formato_img)
        self.cmb_formato_img.setCurrentText(lista_formato_img[0])
        cfg_layout.addWidget(self.cmb_formato_img, 2, 10)

        # Fila 7: Desde frame
        cfg_layout.addWidget(QLabel("Desde Frame:"), 2, 11)
        self.ent_desde_frame = QLineEdit("1")
        cfg_layout.addWidget(self.ent_desde_frame, 2, 12)

        # Fila 8: Hasta frame
        cfg_layout.addWidget(QLabel("Hasta Frame:"), 2, 13)
        self.ent_hasta_frame = QLineEdit("1")
        cfg_layout.addWidget(self.ent_hasta_frame, 2, 14)

        # Fila 9: Btn Renderizar
        self.btn_renderizar = QPushButton("🚀 Iniciar Renderizado en Background")
        self.btn_renderizar.clicked.connect(self._start_render_con_params)
        cfg_layout.addWidget(self.btn_renderizar, 3, 0, 1, 15)

        # EMPAQUETAMIENTO DE LOS DIFERENTES 
        #cfg_layout.addWidget(self.tabla_metadatos)
        #cfg_layout.rowStretch()
        layout.addWidget(cfg_group)
        

    def _setup_tab_consola(self):
        """Define los elementos de la pestaña de Consola de salida."""
        layout = QVBoxLayout(self.tab3_consola)
        
        # --- Grupo 1: Configurar y renderizar ---
        consola_group = QGroupBox("Salida de información de la ejecución")
        consola_layout = QGridLayout(consola_group)

        # Fila 1: Consola
        self.consola_salida = QTextEdit()
        self.consola_salida.setReadOnly(True)
        self.consola_salida.setStyleSheet("background-color: #333; color: white; border: 2px solid #555;")
        self.consola_salida.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Estilo de consola oscura
        palette = self.consola_salida.palette()
        palette.setColor(QPalette.Base, QColor(25, 25, 25)) # Fondo oscuro
        palette.setColor(QPalette.Text, QColor(50, 255, 50)) # Texto verde (lima)
        self.consola_salida.setPalette(palette)
        self.consola_salida.setFont(QFont("Consolas", 10))

        consola_layout.addWidget(self.consola_salida, 0, 0)

        # EMPAQUETAMIENTO DE LOS DIFERENTES GRUPOBOX
        layout.addWidget(consola_group)


    
    def read_info_output(self):
        """
        Captura la salida incremental de Blender de forma asíncrona, la acumula, 
        busca el JSON completo, lo decodifica y actualiza la interfaz al finalizar.
    
        NOTA: La limpieza de variables de estado (row, progress) se hace en 
        info_process_finished, NO aquí.
        """
        import json
    
        # 1. Leer y acumular el output de Blender
        chunk = self.info_process.readAllStandardOutput().data().decode(errors='ignore')
        self._json_buffer += chunk
    
        data = self._json_buffer
        json_start = data.find('{')
        json_end = data.rfind('}')

        # 2. Intentar parsear el JSON si encontramos los delimitadores
        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_str = data[json_start : json_end + 1]
        
            try:
                metadata = json.loads(json_str)
            
                # --- 🟢 PASOS DE FINALIZACIÓN EXITOSA (ASÍNCRONA) ---

                # A. Detener el temporizador de simulación inmediatamente
                self.progress_timer.stop() 
            
                # B. Obtener la fila de trabajo y el nombre del archivo
                row = self._current_process_row 
                file_item = self.tabla_archivos_blend.item(row, 1)
                nombre_archivo = file_item.text() if file_item else "Archivo Desconocido"

                # C. Actualizar el widget de progreso (Columna 'Estado')
                widget = self.tabla_archivos_blend.cellWidget(row, 3)
            
                if widget:
                    widget.set_progress(100) # Finalización real al 100%
                    widget.set_status("Finalizado")
                
                    # Estilo verde para éxito
                    widget.pbar.setStyleSheet("""
                        QProgressBar::chunk { background-color: #32CD32; }
                        QProgressBar { border: 1px solid #555; border-radius: 5px; text-align: center; font-size: 9px; color: white; }
                    """) 
            
                #   D. Llenar la tabla de metadatos (segunda tabla)
                #self.llenar_tabla_archivos_blend(metadata)
                self.llenar_tabla_metadatos(metadata)
                self.llenar_tabla_metadatos_render(metadata)

                # E. ⚠️ CAMBIO CRÍTICO: Limpieza inteligente del buffer
                # Elimina el JSON procesado (desde el inicio hasta el fin de la llave de cierre).
                # Conserva cualquier dato que haya llegado después del JSON.
                self._json_buffer = data[json_end + 1:]

                # E. Mensaje de éxito en la consola
                self.consola_salida.append(
                    f"El archivo: {nombre_archivo} <span style='color: #32CD32;'> ✔ Metadatos cargados correctamente.</span>"
                )

                #   ❌ F. ELIMINAR ESTA SECCIÓN. La limpieza se hace en info_process_finished.
                # self._json_buffer = "" 
                # self._current_process_row = -1 
                # self._simulated_progress = 0 

            except json.JSONDecodeError:
                # Si el JSON no es válido, se espera el siguiente chunk.
                pass

        
              

    def read_info_error(self):
        err_data = self.info_process.readAllStandardError().data().decode(errors='ignore')
    
        # Filtrar basura conocida de Blender/Addons
        filtros = ["atexit", "cleanup()", "terminate", "GA destroy", "D5"]
        if any(f in err_data for f in filtros):
            return # Ignorar estos mensajes

        if err_data.strip():
            self.consola_salida.append(f"<span style='color: red;'>Blender Error: {err_data}</span>")
 


    def info_process_finished(self, exit_code, exit_status):

        #file_path = self.ent_blend.text().strip()

        """
        Se ejecuta cuando el QProcess de Blender finaliza, independientemente 
        de si fue éxito o fallo. Su principal objetivo es realizar la limpieza 
        final de las variables de estado.
        """
    
        # 1. Detener el temporizador de simulación de progreso
        self.progress_timer.stop() 
    
        # Obtener la fila de trabajo, ya que la usaremos para actualizar
        row = self._current_process_row 
    
        # 2. Verificar el estado de salida del QProcess
        if exit_status == QProcess.NormalExit and exit_code == 0:
            # El proceso de Blender terminó con éxito (código 0). 
            # Si ya encontró el JSON, read_info_output ya actualizó la barra a 100%.
        
            # Si read_info_output no encontró el JSON (ejecución muy rápida y limpia), 
            # el buffer estará vacío, pero la barra ya debería estar en verde.
        
            pass # No hacemos nada más aquí.
        
        else:
            # El proceso terminó de forma anormal (fallo en Blender, aborto, crash).
        
            # A. Actualizar el widget de progreso a estado de fallo (ROJO)
            if row != -1:
                widget = self.tabla_archivos_blend.cellWidget(row, 3)
            
                if widget:
                    # Si la barra no se completó (no está en "Finalizado"), marcar como error
                    if widget.label.text() != "Finalizado":
                        widget.set_progress(0)
                        widget.set_status(f"❌ Fallo ({exit_code})")
                    
                        #   Estilo rojo para fallo
                        widget.pbar.setStyleSheet("""
                            QProgressBar::chunk { background-color: #DC143C; }
                            QProgressBar { border: 1px solid #555; border-radius: 5px; text-align: center; font-size: 9px; color: white; }
                        """)
        
            # B. Mensaje de error en la consola
            self.consola_salida.append(
                f"❌ <span style='color: #DC143C;'>El proceso de extracción falló. Código: {exit_code}.</span>"
            )
        
        # 3. 🟢 LIMPIEZA CRÍTICA DE ESTADO (Permite cargar el siguiente archivo)
    
        # Restablece todas las variables de estado compartidas
        self._current_process_row = -1
        self._simulated_progress = 0
        #self._json_buffer = ""
    
        # ⚠️ Esta línea resuelve el estado "sucio" del QProcess
        self.info_process.reset()

        # 🟢 ACCIÓN CLAVE 2: HABILITAR el botón de carga
        self.btn_cargar.setEnabled(True) # Usar el nombre de tu variable de botón

        



    @Slot()
    def _cargar_blend_a_tabla(self):
        """
        Lee la ruta del archivo .blend, extrae metadatos y añade la información 
        a ambas tablas.
        """
        file_path = self.ent_blend.text().strip()

        
        if not file_path or not os.path.exists(file_path):
            print("Error: La ruta del archivo .blend está vacía o el archivo no existe.")
            return

        file_name = os.path.basename(file_path)
        
        # 1. Comprobar si el archivo ya está en la tabla (opcional)
        for row in range(self.tabla_archivos_blend.rowCount()):
            item = self.tabla_archivos_blend.item(row, 0)


            if item and item.text() == file_path:
                print(f"Advertencia: El archivo {file_name} ya está cargado.")
                QMessageBox.critical(self, "Error", f"Advertencia: El archivo {file_name} ya está cargado.")
                return
            
        # 🟢 VERIFICACIÓN CRÍTICA (NUEVA LÍNEA CLAVE)
        # Se añade la verificación para asegurar que solo se ejecuta un QProcess a la vez.
        if self.info_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(
                self, 
                "Proceso Ocupado", 
                "Espere a que termine la carga del archivo actual antes de iniciar otro."
            )
            return
            
            
        # --- 2. Si el proceso está libre, preparamos el entorno ---
    
        # 🟢 ACCIÓN CLAVE 1: DESHABILITAR el botón de carga
        self.btn_cargar.setEnabled(False) # Usar el nombre de tu variable de botón

    
        # Insertar la nueva fila y obtener el índice
        row_idx = self.tabla_archivos_blend.rowCount()
        self.tabla_archivos_blend.insertRow(row_idx)
    
        # 🟢 ASIGNACIÓN CRÍTICA para el flujo asíncrono
        # Guardar el índice de la fila para que 'read_info_output' y el timer sepan qué actualizar.
        self._current_process_row = row_idx
       
        # Llenar las columnas de Nombre y Ruta
        
        self.tabla_archivos_blend.setItem(row_idx, 0, QTableWidgetItem(file_path))
        self.tabla_archivos_blend.setItem(row_idx, 1, QTableWidgetItem(os.path.basename(file_path)))
        #self.tabla_archivos_blend.setItem(row_idx, 2, QTableWidgetItem(os.path.basename(file_path)))

        # 🟢 LLAMADA CLAVE: Actualizar el combobox SÓLO AHORA
        self._actualizar_combobox_rutas()
        

        # 3. Configurar el Widget de Progreso (Columna de Estado, índice 2)
        progreso_widget = EstadoProgressWidget()
        progreso_widget.pbar.setRange(0, 100) # Usamos rango normal para la simulación
        self.tabla_archivos_blend.setCellWidget(row_idx, 3, progreso_widget)
        self.tabla_archivos_blend.setRowHeight(row_idx, 45)

        # 4. Iniciar la Simulación de Progreso (QTimer)
        self._simulated_progress = 0
        progreso_widget.set_progress(0) 
    
        # Si el timer ya estaba corriendo (lo cual no debería pasar si se limpia bien), lo paramos primero
        if self.progress_timer.isActive():
            self.progress_timer.stop() 
        
        self.progress_timer.start(300) # Iniciar el timer para que llame a _update_simulated_progress cada 300ms

        # 5. Iniciar el Proceso Asíncrono de Blender (QProcess)
        self._json_buffer = ""
        self.ejecutar_extractor_blender(file_path)

 

    def ejecutar_extractor_blender(self, blend_path):
        blender_exe = self.cmb_blend_exe.currentData()
        #blender_exe = self.ent_exe.text().strip()
    
        # 🟢 Paso Clave 3: Usar la ruta de clase resuelta
        script_py = self.info_script_path
    
        # Si por alguna razón la ruta está mal, salimos antes de llamar a Blender
        if not os.path.exists(blender_exe):
            self.consola_salida.append(f"<span style='color: red;'>Error: Ejecutable de Blender no encontrado en {blender_exe}</span>")
            # 🟢 Es crucial limpiar las variables de estado si se detecta un error aquí
            self._current_process_row = -1
            self.progress_timer.stop()
            return

        args = ["-b", blend_path, "--python", script_py]
        # 🟢 INICIA EL PROCESO ASÍNCRONO
        try:
            self.info_process.start(blender_exe, args)
            self.consola_salida.append(f"Iniciando Blender para {os.path.basename(blend_path)}...")
        except Exception as e:
            self.consola_salida.append(f"<span style='color: red;'>Error al iniciar QProcess: {e}</span>")
            # 🟢 Limpiar variables si la ejecución inicial falla
            self._current_process_row = -1
            self.progress_timer.stop()

            # Nota: La función _cargar_blend_a_tabla() debe asegurar que 
            # self.info_process.state() == QProcess.NotRunning antes de llamar a esta función.


    def _update_simulated_progress(self):
        """
        Simula el avance del progreso mientras se espera la respuesta de Blender.
    
        Avanza el porcentaje hasta un límite (e.g., 95%) para dar feedback visual,
        deteniéndose allí hasta que el proceso asíncrono real (Blender) complete la tarea.
        """
    
        # 1. Validación de estado: Asegurar que hay un proceso activo.
        if self._current_process_row == -1:
            self.progress_timer.stop()
            return

        # 2. Obtener el widget de la fila actual para la columna de Estado (Columna 2)
        row = self._current_process_row
        widget = self.tabla_archivos_blend.cellWidget(row, 3)
    
        if not widget:
            # Si el widget no existe (lo quitaron o hubo un error), detenemos el timer.
            self.progress_timer.stop()
            return

        # 3. Simulación del avance
        MAX_SIMULATED_PROGRESS = 90
        #INCREMENT_STEP = 5 # Velocidad de la simulación
        incremento = 3
        self._simulated_progress += incremento
    
        if self._simulated_progress >= MAX_SIMULATED_PROGRESS:
            self._simulated_progress = MAX_SIMULATED_PROGRESS
        
            # Incrementar el progreso simulado
            #self._simulated_progress += INCREMENT_STEP 
        
            # Asegurarse de no exceder el límite de simulación
            #if self._simulated_progress > MAX_SIMULATED_PROGRESS:
                #self._simulated_progress = MAX_SIMULATED_PROGRESS
        
        # Actualizar la barra con el valor limitado
        widget.set_progress(self._simulated_progress)
    
        # Opcional: Si está esperando, puedes cambiar el estado a "Procesando..."
        if self._simulated_progress < MAX_SIMULATED_PROGRESS:
            widget.set_status("Cargando...")
        else:
            widget.set_status("Procesando...") # Cambia a "Procesando" mientras espera el JSON



    def llenar_tabla_archivos_blend(self, metadata):
        #row = self.tabla_archivos_blend.rowCount()
        #self.tabla_archivos_blend.insertRow(row)

        #self.tabla_archivos_blend.setItem(row, 2, metadata.get('version_blender', 'N/A'))

        #self.version_blender = 

        pass


    def llenar_tabla_metadatos(self, metadata):

        row = self.tabla_metadatos.rowCount()
        self.tabla_metadatos.insertRow(row)

        self.ruta_archivo_prueba = QTableWidgetItem(metadata.get('ruta_archivo', 'N/A'))
        self.nombre_archivo = QTableWidgetItem(metadata.get('file_name', 'N/A'))
        self.version_blender_meta = QTableWidgetItem(metadata.get('version_blender', 'N/A'))
        self.version_blender_meta.setTextAlignment(Qt.AlignCenter)
        self.frame_inicio = QTableWidgetItem(str(metadata.get('frame_start', 'N/A')))
        self.frame_inicio.setTextAlignment(Qt.AlignCenter)
        self.frame_fin = QTableWidgetItem(str(metadata.get('frame_end', 'N/A')))
        self.frame_fin.setTextAlignment(Qt.AlignCenter)
        self.frame_fps = QTableWidgetItem(str(metadata.get('frame_rate', 'N/A')))
        self.frame_fps.setTextAlignment(Qt.AlignCenter)
        self.resolution_xy_render = QTableWidgetItem(f"{metadata.get('resolution_x', 'N/A')} x {metadata.get('resolution_y', 'N/A')}")
        self.resolution_xy_render.setTextAlignment(Qt.AlignCenter)

        self.cameras = QTableWidgetItem(metadata.get('cameras', 'N/A'))
    
        self.tabla_metadatos.setItem(row, 0, self.nombre_archivo)
        self.tabla_metadatos.setItem(row, 1, self.version_blender_meta)
        self.tabla_metadatos.setItem(row, 2, QTableWidgetItem(metadata.get('active_scene', 'N/A')))
        self.tabla_metadatos.setItem(row, 3, QTableWidgetItem(metadata.get('view_layer', 'N/A')))
        self.tabla_metadatos.setItem(row, 4, QTableWidgetItem(metadata.get('active_camera', 'N/A')))       
        self.tabla_metadatos.setItem(row, 5, self.frame_inicio)
        self.tabla_metadatos.setItem(row, 6, self.frame_fin)
        self.tabla_metadatos.setItem(row, 7, self.frame_fps)
        self.tabla_metadatos.setItem(row, 8, self.resolution_xy_render)
        self.tabla_metadatos.setItem(row, 9, self.ruta_archivo_prueba)



    def llenar_tabla_metadatos_render(self, metadata):

        file_path = self.ent_blend.text().strip()

        # PROPIEDADES A USAR PARA RENDERIZAR
        row_render = self.tabla_metadatos_a_renderizar.rowCount()
        self.tabla_metadatos_a_renderizar.insertRow(row_render)

        self.ruta_archivo_blend = QTableWidgetItem(metadata.get('file_path', 'N/A'))
        self.nombre_archivo_render = QTableWidgetItem(metadata.get('file_name', 'N/A')) # Nombre de archivo
        self.version_blender_meta_render = QTableWidgetItem(metadata.get('version_blender', 'N/A'))
        self.version_blender_meta_render.setTextAlignment(Qt.AlignCenter)

        self.cmb_motor = QComboBox()
        self.lista_motor = ["EEVEE", "CYCLES"]
        self.cmb_motor.addItems(self.lista_motor)
        self.cmb_motor.setCurrentText(self.lista_motor[1])

        self.cmb_proceso_render = QComboBox()
        self.lista_proceso_render = ["CPU", "CUDA", "OPTIX", "METAL"]
        self.cmb_proceso_render.addItems(self.lista_proceso_render)
        self.cmb_proceso_render.setCurrentText(self.lista_proceso_render[1])

        self.carpeta_salida = QTableWidgetItem("render")
        self.nombre_imagen = QTableWidgetItem("img_")

        self.t_cmb_formato_img = QComboBox()
        self.lista_formato_img = ["PNG", "JPEG", "EXR", "TIFF"]
        self.t_cmb_formato_img.addItems(self.lista_formato_img)
        self.t_cmb_formato_img.setCurrentText(self.lista_formato_img[0])

        self.desde_frame = QTableWidgetItem("1")
        self.desde_frame.setTextAlignment(Qt.AlignCenter)
        self.hasta_frame = QTableWidgetItem("1")
        self.hasta_frame.setTextAlignment(Qt.AlignCenter)


        #self.btn_render = QPushButton("Render")
        #self.tabla_metadatos_a_renderizar.cellClicked.connect(self.imprimir_texto)
        #self.tabla_metadatos_a_renderizar.cellActivated.connect(self.manejar_activacion_celda)
        self.celda_render = QTableWidgetItem("Render")
        self.celda_render.setTextAlignment(Qt.AlignCenter)

        
        #self.tabla_metadatos_a_renderizar.setItem(row_render, 0, self.ruta_archivo_blend)
        self.tabla_metadatos_a_renderizar.setItem(row_render, 0, self.nombre_archivo_render)
        self.tabla_metadatos_a_renderizar.setItem(row_render, 1, self.version_blender_meta_render)
        self.tabla_metadatos_a_renderizar.setCellWidget(row_render, 2, self.cmb_motor)
        self.tabla_metadatos_a_renderizar.setCellWidget(row_render, 3, self.cmb_proceso_render)
        self.tabla_metadatos_a_renderizar.setItem(row_render, 4, self.carpeta_salida)
        self.tabla_metadatos_a_renderizar.setItem(row_render, 5, self.nombre_imagen)
        self.tabla_metadatos_a_renderizar.setCellWidget(row_render, 6, self.t_cmb_formato_img)
        self.tabla_metadatos_a_renderizar.setItem(row_render, 7, self.desde_frame)
        self.tabla_metadatos_a_renderizar.setItem(row_render, 8, self.hasta_frame)


        self.insertar_celda_no_editable_clickeable(row_render, 9, "Render")
        #self.tabla_metadatos_a_renderizar.setItem(row_render, 9, self.celda_render)

        #self.cmb_engine
        #self.cmb_procesamiento_render

        #self.lista_rutas_blend.append(file_path)
        #self.cmb_ruta_blend_a_renderizar.addItem(self.lista_rutas_blend)


    def obtener_lista_de_columna_cero(self) -> List[str]:
        """
        Crea una lista con el contenido de la Columna 0 de TODAS las filas de la tabla.
        """
    
        COLUMNA_BUSCADA = 0
        lista_de_items = []
    
        # Iterar sobre todas las filas de la tabla
        for r in range(self.tabla_archivos_blend.rowCount()):
        
            # Obtener el objeto QTableWidgetItem para la fila 'r' y columna 0
            item = self.tabla_archivos_blend.item(r, COLUMNA_BUSCADA)
        
            # Verificar que el ítem existe antes de intentar obtener su texto
            if item is not None:
                lista_de_items.append(item.text())
            else:
                # Puedes añadir un valor predeterminado si la celda está vacía
                lista_de_items.append("Celda Vacía") 
            
        return lista_de_items

    # Ejemplo de uso:
    # lista_nombres_archivos = self.obtener_lista_de_columna_cero()
    # print("Todos los nombres/rutas en Columna 0:", lista_nombres_archivos)

    def _actualizar_combobox_rutas(self):
        """
        Limpia el QComboBox y lo rellena con todas las rutas de la Columna 1 de la tabla.
        """
        # Limpiar el ComboBox existente para evitar duplicados
        self.cmb_ruta_blend_a_renderizar.clear()
    
        # Limpiar tu lista de Python (si es que la usas para algo más)
        self.lista_rutas_blend.clear() 

        # Iterar sobre la tabla
        for row in range(self.tabla_archivos_blend.rowCount()):
            item_ruta = self.tabla_archivos_blend.item(row, 0) # Asumimos Columna 0 = Ruta
            item_nombre = self.tabla_archivos_blend.item(row, 1) # Columna 1 = Nombre

            if item_ruta and item_nombre:
                ruta = item_ruta.text()
                nombre = item_nombre.text()
            
                # Añadir a la lista de Python (si es necesario)
                self.lista_rutas_blend.append(ruta) 
            
                # Añadir al ComboBox (puedes mostrar el nombre, pero almacenar la ruta)
                #self.cmb_ruta_blend_a_renderizar.addItem(nombre, userData=ruta)
                self.cmb_ruta_blend_a_renderizar.addItem(ruta)

                # El argumento 'userData' es genial para almacenar la ruta completa sin mostrarla.


    @Slot(int, int)
    def manejar_activacion_celda(self, row, column):
        print(f"DEBUG: Clic detectado en Fila {row}, Columna {column}")
        """
        Slot que se llama al activar cualquier celda. Filtra por la celda específica (fila X, columna 9).
        """
        # Define la fila y columna que te interesa monitorear (ejemplo)
        COLUMNA_CLAVE = 9
        
        # ⚠️ Debes obtener la fila específica que deseas monitorear, por ejemplo,
        # si solo te interesa la primera fila que se cargó, usa 0, o si lo guardaste:
        FILA_A_MONITOREAR = self._fila_fija_a_monitorear 

        # 1. Verificar si la celda activada coincide con la fila y columna que te interesa
        if row == FILA_A_MONITOREAR and column == COLUMNA_CLAVE:
            
            # 2. Si coincide, llama a tu función original (imprimir_texto)
            self.imprimir_texto(row, column)
            
        else:
            # Opcional: Ignorar el clic en otras celdas
            print(f"Activación ignorada en ({row}, {column}).")


    def imprimir_texto(self, row, column):
        """
        Función que contiene la lógica de lo que debe suceder al activar la celda (Fila X, Columna 9).
        """
        # Ejemplo: Obtener el texto de la columna 9 de esa fila
        item = self.tabla_metadatos_a_renderizar.item(row, column)
        if item:
            texto = item.text()
            print(f"✅ ¡Activación exitosa en la celda ({row}, {column})!")
            print(f"Contenido: {texto}")


    
    @Slot(int, int)
    def manejar_clic_celda(self, row, column):
        """
        Se ejecuta al hacer clic en cualquier celda. 
        Extrae el file_path de la Columna 0 de la fila clickeada.
        """
    
        # La columna clave donde asumimos que está el file_path
        COLUMNA_FILE_PATH = 0 
    
        # 1. Obtener el objeto QTableWidgetItem de la fila 'row' y la columna CLAVE (0)
        # Ignoramos la variable 'column' que nos dice dónde se hizo clic
        item_path = self.tabla_archivos_blend.item(row, COLUMNA_FILE_PATH)
    
        # 2. Verificar que el ítem existe y extraer el texto
        file_path = None
        if item_path is not None:
            file_path = item_path.text()
        
            print(f"File path extraído de (Fila: {row}, Columna: {COLUMNA_FILE_PATH}): {file_path}")
        
            # 3. Puedes llamar a tu función de acción con esta ruta
            self.procesar_ruta_archivo(file_path)
        else:
            print(f"Advertencia: No se encontró un ítem en Fila {row}, Columna {COLUMNA_FILE_PATH}.")


    def procesar_ruta_archivo(self, ruta):
        # Función que hace algo con la ruta, por ejemplo, abrir el archivo
        print(f"Ruta de archivo lista para ser procesada: {ruta}")


    def insertar_celda_no_editable_clickeable(self, row, column, text_data):
        """
        Inserta el texto en la celda y la configura para que no sea editable, 
        pero sí sea seleccionable y funcional para clics.
        """
    
        # 1. Crear el ítem con el dato
        item = QTableWidgetItem(text_data)
        item.setTextAlignment(Qt.AlignCenter)
    
        # 2. Establecer los flags deseados: Habilitado y Seleccionable (Omite ItemIsEditable)
        # Qt.ItemIsEditable es el flag que permite la doble pulsación para editar.
    
        # Usamos ItemIsEnabled (para que se vea normal)
        # Usamos ItemIsSelectable (para que se pueda seleccionar/clickear)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    
        # También puedes usar la forma de negación para ser más explícito
        # current_flags = item.flags()
        # item.setFlags(current_flags & ~Qt.ItemIsEditable) 
    
        # 3. Insertar el ítem en la tabla
        self.tabla_metadatos_a_renderizar.setItem(row, column, item)


    def _buscar_blender_exe(self):
        """
        Abre el diálogo de archivo y establece la ruta en el QLineEdit.
        """
        # Abre el diálogo de archivo para seleccionar el ejecutable
        ruta_archivo, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar blender.exe", "", "Ejecutables (*.exe);;Todos los archivos (*)"
        )

        if ruta_archivo:
            # Rellena el campo de texto (QLineEdit)
            self.ent_blend_exe.setText(ruta_archivo)


    def _obtener_version_blender(self, ruta_blender_exe):
        """
        Ejecuta 'blender --version' usando la ruta proporcionada y retorna la versión.
        Retorna None y muestra un error si falla.
        """
        try:
            # Usa subprocess.run para ejecutar el comando
            resultado = subprocess.run(
                [ruta_blender_exe, "--version"], 
                capture_output=True, 
                text=True, 
                check=True,
                timeout=5 # Tiempo límite de 5 segundos
            )
            # La versión suele ser la primera línea del output
            version_linea = resultado.stdout.split('\n')[0].strip()
            # Busca el número de versión (ej: "Blender 4.0.2 (hash: 998f413a9670)")
            if version_linea.startswith("Blender"):
                # Retorna la línea completa o solo el número, según prefieras
                return version_linea
            else:
                return "Versión no detectada"

        except subprocess.CalledProcessError as e:
            QMessageBox.warning(self, "Error de Ejecución", 
                                f"El ejecutable no pudo reportar su versión. Error: {e.stderr}")
            return None
        except FileNotFoundError:
            QMessageBox.critical(self, "Error de Archivo", 
                                f"No se encontró el ejecutable en: {ruta_blender_exe}")
            return None
        except Exception as e:
            QMessageBox.critical(self, "Error Desconocido", 
                             f"Fallo al intentar obtener la versión: {e}")
            return None
        

    def _cargar_rutas_blender_db(self):
        """
        Conecta a la DB, consulta TODAS las rutas y llena self.tabla_blend_exe y self.cmb_blend_exe.
        """
    
        # -- 1. Limpiar los widgets
        self.tabla_blend_exe.setRowCount(0)
        self.cmb_blend_exe.clear() # <--- LIMPIAR EL COMBOBOX

        rutas_completas = []
    
        try:
            conn = sqlite3.connect(self.DB_FILE)
            cursor = conn.cursor()

            # Obtenemos solo la ruta y la versión.
            cursor.execute(f"SELECT ruta_ejecutable, version FROM {self.TABLA_SQL} ORDER BY version DESC")
            filas = cursor.fetchall()
        
            self.tabla_blend_exe.setRowCount(len(filas))
        
            # -- 2. Llenar QTableWidget y recolectar datos
            for num_fila, fila_data in enumerate(filas):
                ruta = fila_data[0]
                version = fila_data[1]
            
                # Formato a mostrar en el ComboBox (opcional, pero útil)
                texto_combo = f"{version} ({os.path.basename(ruta)})" 
            
                # Guardamos la ruta (el valor interno real)
                rutas_completas.append((texto_combo, ruta)) 
            
                # Llenar QTableWidget
                item_ruta = QTableWidgetItem(ruta)
                self.tabla_blend_exe.setItem(num_fila, 0, item_ruta)
            
                item_version = QTableWidgetItem(version)
                self.tabla_blend_exe.setItem(num_fila, 1, item_version)

            # -- 3. Llenar QComboBox
            for texto_mostrar, ruta_valor in rutas_completas:
                # Añade el texto visible y el dato real (la ruta completa)
                self.cmb_blend_exe.addItem(texto_mostrar, ruta_valor) # <--- LLENAR CON DATOS

            print(f"Tabla y ComboBox actualizados con {len(filas)} ejecutables.")

        except sqlite3.OperationalError:
            pass # La tabla no existe, no hay problema.
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error de Base de Datos", 
                                f"No se pudo cargar la base de datos: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()


    def _procesar_y_cargar_db(self):
        """
        Toma la ruta del QLineEdit, asegura la carpeta, guarda la versión en la DB, 
        y luego refresca la QTableWidget.
        """
        ruta_archivo = self.ent_blend_exe.text().strip()
    
        if not ruta_archivo or not os.path.exists(ruta_archivo):
            QMessageBox.warning(self, "Advertencia", 
                            "Por favor, seleccione un ejecutable de Blender válido primero.")
            return

        # A. Obtener la versión (función auxiliar)
        version = self._obtener_version_blender(ruta_archivo)
    
        if version is None:
            return
        
        # B. Asegurar la Carpeta 'bbdd'
        if not os.path.exists(self.DB_FOLDER): 
            try:
                os.makedirs(self.DB_FOLDER)
            except OSError as e:
                QMessageBox.critical(self, "Error de Directorio", 
                                 f"No se pudo crear la carpeta de la DB: {e}")
                return
        
        # C. Guardar en la Base de Datos
        try:
            # **USO DE self.DB_FILE**
            conn = sqlite3.connect(self.DB_FILE)
            cursor = conn.cursor()
        
            # **USO DE self.TABLA_SQL**
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLA_SQL} (
                    id INTEGER PRIMARY KEY,
                    ruta_ejecutable TEXT NOT NULL UNIQUE,
                    version TEXT
                );
            """)
        
            sql_insert = f"""
            INSERT OR IGNORE INTO {self.TABLA_SQL} (ruta_ejecutable, version) 
            VALUES (?, ?)
            """
            cursor.execute(sql_insert, (ruta_archivo, version))
        
            conn.commit()
            # Muestra mensaje solo si se insertó algo
            if cursor.rowcount > 0:
                QMessageBox.information(self, "Éxito", "Ruta de Blender guardada y tabla actualizada.")

        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error DB", 
                                f"Fallo al guardar/crear la DB: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

        # D. Recargar la tabla visual
        self._cargar_rutas_blender_db()



    def _eliminar_ruta_seleccionada(self):
        """
        Elimina la ruta seleccionada de la QTableWidget de la base de datos SQLite.
        """
        indices_seleccionados = self.tabla_blend_exe.selectedIndexes()
    
        if not indices_seleccionados:
            QMessageBox.warning(self, "Advertencia", 
                                "Por favor, seleccione una fila completa para eliminar.")
            return
        
        fila_a_eliminar = indices_seleccionados[0].row()
        item_ruta = self.tabla_blend_exe.item(fila_a_eliminar, 0)

        if item_ruta is None:
            QMessageBox.critical(self, "Error", "No se pudo obtener el dato de la ruta.")
            return

        ruta_a_eliminar = item_ruta.text()
    
        respuesta = QMessageBox.question(self, 'Confirmar Eliminación',
            f"¿Está seguro que desea eliminar la ruta:\n{ruta_a_eliminar}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if respuesta == QMessageBox.No:
            return

        # 4. Eliminar el registro de la Base de Datos
        try:
            # **USO DE self.DB_FILE**
            conn = sqlite3.connect(self.DB_FILE)
            cursor = conn.cursor()
        
            # **USO DE self.TABLA_SQL**
            sql_delete = f"""
            DELETE FROM {self.TABLA_SQL} WHERE ruta_ejecutable = ?
            """
            cursor.execute(sql_delete, (ruta_a_eliminar,))
        
            conn.commit()

            if cursor.rowcount > 0:
                QMessageBox.information(self, "Éxito", "Ruta eliminada correctamente.")

        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error DB", 
                                f"Fallo al eliminar la ruta de la DB: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

        # 5. Recargar la tabla visual
        self._cargar_rutas_blender_db()

            
    def _browse_blend_file(self):
        """Selecciona el archivo .blend y guarda la carpeta contenedora de forma persistente."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Seleccionar Archivo .blend", 
            self._default_dir, 
            "Archivos de Blender (*.blend); Todos los archivos (*.*)"
        )
        if file_path:
            self.ent_blend.setText(file_path)
            
            # Persistencia de la carpeta
            new_dir = os.path.dirname(file_path)
            if new_dir != self._default_dir:
                self._default_dir = new_dir
                self.settings.setValue("blend_file_directory", new_dir)
                print(f"Carpeta de .blend guardada: {new_dir}")
            print(f"Archivo .blend seleccionado: {file_path}")


    #--- LÓGICA DE QPROCESS PARA EL RENDERIZADO (Mismos que antes) ---

    def read_std_output(self):
        data = self.blender_process.readAllStandardOutput().data().decode()
        self.consola_salida.append(data.strip())

    def read_std_error(self):
        data = self.blender_process.readAllStandardError().data().decode()
        self.consola_salida.append(f"<span style='color: red;'>{data.strip()}</span>")

    def process_finished(self, exit_code, exit_status):
        """
        Maneja el resultado del QProcess de Blender, clasificando el código de salida
        en Éxito (0), Advertencia (1) o Error Crítico (>1).
        """
        # Reactivar el botón de renderizar
        self.btn_renderizar.setEnabled(True)
    
        es_salida_normal = (exit_status == QProcess.NormalExit)
    
        if es_salida_normal:
        
            if exit_code == 0:
                # 1. NIVEL: ÉXITO LIMPIO (Código 0)
                message = "✅ **Renderizado Finalizado Correctamente.**"
                QMessageBox.information(self, "Proceso Finalizado", "El renderizado ha terminado con éxito.")
            
            elif exit_code == 1:
                # 2. NIVEL: ADVERTENCIA (Código 1)
                # Cubre errores comunes de Blender como fallos de add-ons, archivos faltantes (el 'version'), etc.
                message = f"⚠️ **Renderizado Finalizado con Advertencias (Código: 1).**"
            
                QMessageBox.warning(self, "Advertencia de Renderizado", 
                    "El renderizado terminó, pero Blender reportó fallos menores (ej. errores de add-ons o archivos de configuración faltantes).\n\n"
                    "**Si el archivo de salida existe y es utilizable, puede ignorar esta advertencia.**"
                )
            
            else: # Códigos de salida mayores a 1 (2, 3, etc.)
                # 3. NIVEL: ERROR CRÍTICO (Código >1)
                message = f"❌ **El renderizado finalizó con un error CRÍTICO.** Código: ({exit_code})"
                QMessageBox.critical(self, "Proceso Fallido", 
                                    f"El renderizado ha fallado debido a un error crítico (Código: {exit_code}).\n\n"
                                    "Esto puede ser causado por argumentos de línea de comandos incorrectos o un fallo interno de Blender."
                )
            
        else:
            # El proceso fue detenido, fue un crash del sistema operativo, o no finalizó correctamente.
            message = f"❌ **El proceso de renderizado no finalizó normalmente.**"
            QMessageBox.critical(self, "Proceso Fallido", 
                                "El proceso de Blender fue detenido o finalizó de forma inesperada. No se pudo obtener la salida normal.")

        # Siempre añadir el resultado a la consola de salida
        self.consola_salida.append(message)


    @Slot(int, int)
    def manejar_activacion_celda_render(self, row, column):
        print(f"DEBUG: Clic detectado en Fila {row}, Columna {column}")
        """
        Slot que se llama al activar la celda (Fila X, Columna 9) de la tabla de render.
        """
        COLUMNA_RENDER = 9 # La columna donde se insertó el texto "Render" (no editable)
    
        if column == COLUMNA_RENDER:
            self._preparar_y_lanzar_render(row)


    def _preparar_y_lanzar_render(self, render_row):

        blender_path = self.cmb_blend_exe.currentData()
        """
        Obtiene la configuración de render de una fila específica de la tabla 
        y ejecuta la función start_render con estos datos.
        """
    
        # 1. Obtener la ruta del archivo .blend (Columna 0 de la tabla de archivos principal)
        # Necesitas un mapping para obtener la ruta de la tabla principal
        # ASUMIMOS que la fila 'render_row' en la tabla de render corresponde a la misma 
        # fila en la tabla principal (self.tabla_archivos_blend).
    
        item_nombre = self.tabla_metadatos_a_renderizar.item(render_row, 0) # Columna de Nombre
        if not item_nombre:
            QMessageBox.critical(self, "Error", "No se encontró el nombre del archivo en la fila.")
            return

        nombre_archivo = item_nombre.text()
    
        # Buscar la ruta completa en la tabla principal (Columna 0) usando el nombre (Columna 1)
        blend_file_path = None
        for row in range(self.tabla_archivos_blend.rowCount()):
            item_ruta = self.tabla_archivos_blend.item(row, 0)
            item_nombre_main = self.tabla_archivos_blend.item(row, 1)
            if item_nombre_main and item_nombre_main.text() == nombre_archivo:
                blend_file_path = item_ruta.text()
                break
            
        if not blend_file_path:
            QMessageBox.critical(self, "Error", f"No se encontró la ruta para '{nombre_archivo}'.")
            return
        
        # 2. Obtener los Widgets y Valores de la Fila de Render
    
        # Usamos QTableWidgetItem.text() para los campos de texto
        carpeta_salida = self.tabla_metadatos_a_renderizar.item(render_row, 4).text()
        nombre_imagen = self.tabla_metadatos_a_renderizar.item(render_row, 5).text()
        desde_frame = self.tabla_metadatos_a_renderizar.item(render_row, 7).text()
        hasta_frame = self.tabla_metadatos_a_renderizar.item(render_row, 8).text()

        # Usamos cellWidget para los QComboBox
        cmb_motor = self.tabla_metadatos_a_renderizar.cellWidget(render_row, 2)
        cmb_proceso = self.tabla_metadatos_a_renderizar.cellWidget(render_row, 3)
        cmb_formato = self.tabla_metadatos_a_renderizar.cellWidget(render_row, 6)
    
        if not all([cmb_motor, cmb_proceso, cmb_formato]):
            QMessageBox.critical(self, "Error", "Faltan widgets de configuración en la tabla.")
            return

        # Obtener los valores actuales de los ComboBox
        motor_render = cmb_motor.currentText()
        proceso_render = cmb_proceso.currentText()
        formato_img = cmb_formato.currentText()

        # 3. Llamar a la función de renderizado
        self._start_render_con_params(
            blend_file_path=blend_file_path,
            motor=motor_render,
            proceso=proceso_render,
            carpeta=carpeta_salida,
            nombre_img=nombre_imagen,
            formato=formato_img,
            frame_s=desde_frame,
            frame_e=hasta_frame
        )
    
    # Nueva versión de start_render que acepta parámetros de la tabla
    def _start_render_con_params(self, blend_file_path, motor, proceso, carpeta, nombre_img, formato, frame_s, frame_e):
        """Inicia el proceso de renderizado de Blender con parámetros explícitos."""
    
        blender_path = self.cmb_blend_exe.currentData()

        if not blender_path or not os.path.exists(blender_path):
            QMessageBox.warning(self, "Error de Ruta", "Ruta de Blender no válida o vacía.")
            return
        if self.blender_process.state() == QProcess.Running:
            QMessageBox.information(self, "Proceso Activo", "Un renderizado ya está en curso.")
            return

        # Construir los argumentos con los nuevos parámetros
        command_args = [
            "-b", 
            blend_file_path,
            "-y",
            "-E", f"{motor}",
            "--debug-all",
            "-o", f"//{carpeta}/{nombre_img}", 
            "-F", f"{formato}", 
            "-s", f"{frame_s}", 
            "-e", f"{frame_e}", 
            "-a", # Comando para iniciar el render
            "--", 
            "--cycles-device", 
            f"{proceso}",
            "--cycles-print-stats",
        ]
    
        full_command_str = f"'{blender_path}' {' '.join([f'\"{arg}\"' if ' ' in arg else arg for arg in command_args])}"
        self.consola_salida.clear()
        self.consola_salida.append(f"Iniciando Renderizado (DEBUG): **{full_command_str}**")
    
        self.btn_renderizar.setEnabled(False) # Bloquear el botón de render general si existe

        try:
            self.blender_process.start(blender_path, command_args)
        except Exception as e:
            self.consola_salida.append(f"<span style='color: red;'>Error al intentar iniciar el proceso: {e}</span>")
            self.btn_renderizar.setEnabled(True)