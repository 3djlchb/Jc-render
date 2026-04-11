import os
import re 
import sqlite3
import json
import subprocess
import datetime
import sys 

sys.path.append(os.path.abspath('...'))

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                               QTextEdit, QCheckBox, QGroupBox, QComboBox, QMessageBox,
                               QPushButton, QHBoxLayout, QProgressBar, QApplication, QMenu,
                               QLabel, QSplitter, QSizePolicy)
from PySide6.QtCore import Qt, QProcess, QTimer, Slot
from PySide6.QtGui import (QColor, QAction, QPixmap, QImageReader)

from dialogos.dialogo_preferencias import PreferenciasDialog


class MenuPrincipal(QWidget): 
    def __init__(self, parent=None):
        super().__init__(parent)

        # DETECCIÓN DE RUTA PARA COMPILADO
        if getattr(sys, 'frozen', False):
            # Si es el .exe, la base es la carpeta donde está el ejecutable
            base_dir = os.path.dirname(sys.executable)
        else:
            # Si es script .py, la base es la carpeta del archivo
            base_dir = os.path.dirname(__file__)

        self.db_path = os.path.join(base_dir, 'bbdd', 'config.db')
        
        # Procesos
        self.proceso_render = QProcess(self)
        self.proceso_render.readyReadStandardOutput.connect(self.leer_consola_blender)
        self.proceso_render.readyReadStandardError.connect(self.leer_errores_blender)
        self.proceso_render.finished.connect(self.al_finalizar_render_actual)
        
        self.cola_render = []
        self.proceso_actual_row = -1
        
        self.init_ui()
        self._verificar_y_crear_tablas()
        self.cargar_datos_desde_db()
        
        QTimer.singleShot(500, self.verificar_cambios_al_inicio)


    def _verificar_y_crear_tablas(self):
        directorio_db = os.path.dirname(self.db_path)
        if not os.path.exists(directorio_db): os.makedirs(directorio_db)
    
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON") 
    
        # --- TABLA PROYECTOS ---
        cursor.execute("""CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            carpeta TEXT UNIQUE, 
            blender_version TEXT, 
            fecha_mod TEXT)""")
    
        # --- TABLA EJECUTABLES (LA QUE FALTA) ---
        cursor.execute("""CREATE TABLE IF NOT EXISTS ejecutables (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            ruta TEXT UNIQUE, 
            version TEXT,
            tipo_instalacion TEXT DEFAULT 'DESCONOCIDO')""")
    
        # Corrección de la estructura de la tabla metadatos
        cursor.execute("""CREATE TABLE IF NOT EXISTS metadatos (
            id_proyecto INTEGER PRIMARY KEY, 
            escena TEXT,
            viewlayer TEXT, 
            camara TEXT,
            f_inicio INTEGER,
            f_final INTEGER,
            fps INTEGER, 
            res_x INTEGER, 
            res_y INTEGER, 
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE
        ) WITHOUT ROWID""")
    
        # --- TABLA RENDERIZADO ---
        cursor.execute("""CREATE TABLE IF NOT EXISTS renderizado (
            id_proyecto INTEGER PRIMARY KEY, 
            motor TEXT, dispositivo TEXT, formato TEXT, 
            f_start INTEGER, f_end INTEGER, ruta_output TEXT, nombre_out TEXT,
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
    
        conn.commit()
        conn.close()
    
    def init_ui(self):
        # 1. Layout Raíz Principal (Vertical)
        self.layout_raiz = QVBoxLayout(self)

        # 2. CREAR EL SPLITTER HORIZONTAL (Principal)
        self.splitter_principal = QSplitter(Qt.Horizontal)

        # ---------------------------------------------------------
        # PANEL IZQUIERDO: (Contenedor para Botones + Splitter Vertical)
        # ---------------------------------------------------------
        self.widget_izquierdo = QWidget()
        self.layout_izq_final = QVBoxLayout(self.widget_izquierdo)
        self.layout_izq_final.setContentsMargins(0, 0, 0, 0)

        # --- BOTONES DE ACCIÓN (Se quedan fijos arriba) ---
        layout_tools = QHBoxLayout()
        self.btn_sync = QPushButton("🔄 Sincronizar Cambios")
        self.btn_sync.clicked.connect(self.sincronizar_todo_desde_principal)
        
        self.btn_batch = QPushButton("🚀 Iniciar Renderizado Batch")
        self.btn_batch.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 5px;")
        self.btn_batch.clicked.connect(self.preparar_cola_batch)
        
        layout_tools.addWidget(self.btn_sync)
        layout_tools.addWidget(self.btn_batch)
        self.layout_izq_final.addLayout(layout_tools)

        # --- CREAR EL SPLITTER VERTICAL (Para los grupos) ---
        self.splitter_izq_v = QSplitter(Qt.Vertical)

        # --- GRUPO 1: METADATOS ---
        self.grupo_metadatos = QGroupBox("Metadatos Técnicos")
        ly_meta = QVBoxLayout(self.grupo_metadatos)
        self.tabla_metadatos = QTableWidget(0, 11)
        self.tabla_metadatos.setHorizontalHeaderLabels([
            "Nombre", "Versión", "Escena", "ViewLayer", "Cámara", "Inicio", "Fin", "FPS", "Res X", "Res Y", "Ruta"
        ])
        
        #self.tabla_metadatos.itemDoubleClicked.connect(self.abrir_con_blender_desde_tabla) # <--- AÑADIR ESTO

        # --- Para Tabla Metadatos ---
        self.tabla_metadatos.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla_metadatos.customContextMenuRequested.connect(self.mostrar_menu_contextual)
        self.tabla_metadatos.itemDoubleClicked.connect(self.abrir_con_blender_desde_tabla)

        anchos_meta = [200, 100, 100, 180, 180, 55, 55, 55, 55, 55, 300]
        for i, ancho_m in enumerate(anchos_meta):
            self.tabla_metadatos.setColumnWidth(i, ancho_m)
        ly_meta.addWidget(self.tabla_metadatos)
        
        # --- GRUPO 2: RENDERIZADO ---
        self.grupo_renderizado = QGroupBox("Cola de Render")
        ly_render = QVBoxLayout(self.grupo_renderizado)
        self.tabla_renderizar = QTableWidget(0, 12)
        self.tabla_renderizar.setHorizontalHeaderLabels([
            "Sel", "Archivo", "Blender", "Motor", "Disp", "Carpeta Out", 
            "Nombre Out", "Formato", "Desde", "Hasta", "PROGRESO", "ACCIÓN"
        ])

        self.tabla_renderizar.itemDoubleClicked.connect(self.abrir_con_blender_desde_tabla) # <--- AÑADIR ESTO
        # --- Para Tabla Renderizado ---
        self.tabla_renderizar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla_renderizar.customContextMenuRequested.connect(self.mostrar_menu_contextual)
        self.tabla_renderizar.itemDoubleClicked.connect(self.abrir_con_blender_desde_tabla)

        anchos_renderizado = [30, 200, 100, 100, 100, 80, 150, 80, 55, 55, 120, 120]
        for j, ancho_r in enumerate(anchos_renderizado):
            self.tabla_renderizar.setColumnWidth(j, ancho_r)
        ly_render.addWidget(self.tabla_renderizar)

        # --- GRUPO 3: CONSOLA ---
        self.grupo_consola = QGroupBox("Consola")
        ly_con = QVBoxLayout(self.grupo_consola)
        self.consola = QTextEdit()
        self.consola.setReadOnly(True)
        self.consola.setStyleSheet("background-color: #1e1e1e; color: #a6e22e; font-family: 'Consolas'; font-size: 10pt;")
        ly_con.addWidget(self.consola)

        # Añadir los grupos al SPLITTER VERTICAL
        self.splitter_izq_v.addWidget(self.grupo_metadatos)
        self.splitter_izq_v.addWidget(self.grupo_renderizado)
        self.splitter_izq_v.addWidget(self.grupo_consola)
        
        # Definir alturas iniciales del splitter vertical (Metadatos, Renderizado, Consola)
        self.splitter_izq_v.setSizes([350, 350, 300])

        # Añadir el splitter vertical al layout del panel izquierdo
        self.layout_izq_final.addWidget(self.splitter_izq_v)

        # ---------------------------------------------------------
        # ---------------------------------------------------------
        # PANEL DERECHO: Vista Previa con Pie de Foto
        # ---------------------------------------------------------
        self.widget_derecho = QWidget()
        self.layout_der_final = QVBoxLayout(self.widget_derecho)
        self.layout_der_final.setContentsMargins(0, 0, 0, 0) # Alineación limpia con el splitter
        
        self.grupo_preview = QGroupBox("📸 Última Imagen Guardada")
        self.layout_der_img = QVBoxLayout(self.grupo_preview)
        
        # 1. Contenedor de Imagen
        self.lbl_preview = QLabel("Esperando renderizado...")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setScaledContents(False) # Escalado manual para evitar deformación
        self.lbl_preview.setStyleSheet("""
            border: 2px dashed #444; 
            background-color: #000; 
            color: #666; 
            font-weight: bold;
        """)
        
        # Permitir que el label se expanda para ocupar el espacio del splitter
        self.lbl_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_preview.setMinimumSize(250, 200) # Tamaño mínimo razonable
        
        self.layout_der_img.addWidget(self.lbl_preview)

        # ---------------------------------------------------------
        # SECCIÓN: PIE DE FOTO (Información del archivo)
        # ---------------------------------------------------------
        self.container_caption = QWidget()
        layout_caption = QVBoxLayout(self.container_caption)
        layout_caption.setContentsMargins(5, 5, 5, 5)
        layout_caption.setSpacing(2)
        
        # Label para el Nombre del Archivo
        self.lbl_caption_name = QLabel("")
        self.lbl_caption_name.setAlignment(Qt.AlignCenter)
        self.lbl_caption_name.setWordWrap(True)
        self.lbl_caption_name.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 11pt;")
        
        # Label para la Ruta (Estilo Consola)
        self.lbl_caption_path = QLabel("")
        self.lbl_caption_path.setAlignment(Qt.AlignCenter)
        self.lbl_caption_path.setWordWrap(True) 
        self.lbl_caption_path.setStyleSheet("color: #888; font-size: 8pt; font-family: 'Consolas';")
        
        layout_caption.addWidget(self.lbl_caption_name)
        layout_caption.addWidget(self.lbl_caption_path)
        
        # Añadir el pie de foto al layout del grupo
        self.layout_der_img.addWidget(self.container_caption)
        
        # CORRECCIÓN FINAL: Añadir el grupo al layout del widget derecho
        self.layout_der_final.addWidget(self.grupo_preview)

        # ---------------------------------------------------------
        # ENSAMBLAJE FINAL DEL SPLITTER PRINCIPAL
        # ---------------------------------------------------------
        self.splitter_principal.addWidget(self.widget_izquierdo)
        self.splitter_principal.addWidget(self.widget_derecho)

        # Proporción inicial del ancho (75% y 25%)
        self.splitter_principal.setSizes([750, 250]) 
        
        # Estilo para los divisores (manillas)
        self.splitter_principal.setStyleSheet("QSplitter::handle { background-color: #3d3d3d; }")
        self.splitter_izq_v.setStyleSheet("QSplitter::handle { background-color: #3d3d3d; }")

        # Añadir el gran splitter horizontal al layout de la ventana
        self.layout_raiz.addWidget(self.splitter_principal)


    def extraer_version_desde_blend(self, ruta_archivo):
        """
        Extrae la versión del ADN del archivo .blend y la normaliza.
        """
        try:
            if not os.path.exists(ruta_archivo):
                return "Desconocida"
                
            with open(ruta_archivo, 'rb') as f:
                header = f.read(12).decode('utf-8', errors='ignore')
                
                if not header.startswith('BLENDER'):
                    return "Desconocida"

                v_str = header.split('v')[-1].strip()
                
                if len(v_str) >= 3:
                    major = v_str[0]
                    minor = int(v_str[1:3]) 
                    
                    # Normalizamos a formato X.Y (ej: 4.5 o 5.1)
                    # Esto facilita la búsqueda LIKE en la base de datos
                    return f"{major}.{minor}"
                    
                return "Desconocida"
        except Exception as e:
            if hasattr(self, 'consola'):
                self.consola.append(f"⚠️ Error ADN: {e}")
            return "Error"
        

    def obtener_metadata_pro(self, exe, ruta):
        """
        Extrae metadatos técnicos ejecutando un script de introspección en Blender.
        Prioriza la versión del ADN del archivo para garantizar la consistencia en la DB.
        """
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        script_extractor = os.path.join(base_dir, "info_archivo_blend.py")
        
        if not os.path.exists(script_extractor):
            self.consola.append(f"❌ Error: No se encuentra '{script_extractor}'")
            return None

        # --- 1. VALIDACIÓN DE ADN PRE-EJECUCIÓN ---
        # Obtenemos la versión real (ej. 4.5) leyendo los bytes del archivo
        version_real_adn = self.extraer_version_desde_blend(ruta)

        try:
            ## --- GESTIÓN DEL EJECUTABLE ---
            if not exe or not os.path.exists(exe):
                conn = sqlite3.connect(self.db_path)
                # version_real_adn ahora devolverá algo como "5.1" o "4.5"
                version_filtro = f"%{version_real_adn}%"
                
                # Buscamos cualquier registro que contenga los números (ej: %5.1%)
                res = conn.execute(
                    "SELECT ruta FROM ejecutables WHERE version LIKE ? ORDER BY version DESC", 
                    (version_filtro,)
                ).fetchone()
                conn.close()
                
                if res:
                    exe = res[0]
                else:
                    # Fallback: Usar el ejecutable más reciente si no hay match
                    conn = sqlite3.connect(self.db_path)
                    res = conn.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
                    conn.close()
                    exe = res[0] if res else exe

            # Si después de la búsqueda seguimos sin exe, abortamos
            if not exe or not os.path.exists(exe):
                self.consola.append(f"⚠️ No hay ejecutable de Blender para extraer metadata de: {os.path.basename(ruta)}")
                return None

            # --- 3. EJECUCIÓN DEL SUBPROCESO ---
            resultado = subprocess.run(
                [exe, "-b", ruta, "--python", script_extractor],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=25, # Tiempo suficiente para archivos pesados
                # Solo usamos CREATE_NO_WINDOW en Windows para evitar errores en Linux
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # --- 4. PARSEO SEGURO DE LA SALIDA ---
            if resultado.stdout:
                lineas = resultado.stdout.splitlines()
                # Buscamos de atrás hacia adelante para encontrar la salida del script
                for linea in reversed(lineas):
                    linea_limpia = linea.strip()
                    
                    # Verificamos si la línea contiene nuestro marcador de seguridad
                    if "JCRENDER_DATA:" in linea_limpia:
                        try:
                            json_str = linea_limpia.split("JCRENDER_DATA:")[1]
                            datos = json.loads(json_str)
                            
                            if "active_scene" in datos:
                                # Sobrescribimos la versión con el ADN real del archivo
                                # Esto corrige el error de "Versiones cambiadas"
                                datos['version_blender'] = version_real_adn
                                return datos
                                
                        except (json.JSONDecodeError, IndexError):
                            continue
                    
                    # Fallback por si el script no usó el prefijo pero devolvió un JSON puro
                    elif linea_limpia.startswith('{') and linea_limpia.endswith('}'):
                        try:
                            datos = json.loads(linea_limpia)
                            datos['version_blender'] = version_real_adn
                            return datos
                        except:
                            continue

            return None

        except subprocess.TimeoutExpired:
            self.consola.append(f"⏳ Timeout: Blender tardó demasiado en leer {os.path.basename(ruta)}")
            return None
        except Exception as e:
            self.consola.append(f"⚠️ Error en extracción técnica ({os.path.basename(ruta)}): {e}")
            return None

    # --- FUNCIÓN: ELIMINAR PROYECTO ---
    def mostrar_menu_contextual(self, pos):
        menu = QMenu()
        accion_eliminar = QAction("❌ Eliminar Proyecto de la lista", self)
        accion_eliminar.triggered.connect(self.eliminar_proyecto_seleccionado)
        menu.addAction(accion_eliminar)
        menu.exec(self.tabla_metadatos.mapToGlobal(pos))

    def eliminar_proyecto_seleccionado(self):
        fila = self.tabla_metadatos.currentRow()
        if fila < 0: return
        
        nombre = self.tabla_metadatos.item(fila, 0).text().replace("⚠️ ", "")
        ruta = self.tabla_metadatos.item(fila, 9).text()
        
        confirmar = QMessageBox.question(self, "Eliminar", f"¿Quitar '{nombre}' de la lista?\n(No borrará el archivo .blend del disco)")
        
        if confirmar == QMessageBox.Yes:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM proyectos WHERE carpeta = ?", (ruta,))
            conn.commit()
            conn.close()
            self.cargar_datos_desde_db()
            self.consola.append(f"🗑️ Proyecto eliminado: {nombre}")

    # --- LÓGICA DE CARGA Y ESTILOS ---
    def _aplicar_estilo_alerta(self, item, n_sync, existe, es_nombre=False):
        if not existe:
            item.setBackground(QColor("#c0392b"))
            if es_nombre: item.setText(f"⚠️ {item.text()}")
        elif n_sync:
            item.setBackground(QColor("#2c3e50"))
            item.setForeground(QColor("#f39c12"))
            if es_nombre: item.setText(f"⚠️ {item.text()}")

    def cargar_datos_desde_db(self):
        if not os.path.exists(self.db_path): return

        # Limpiar tablas para evitar duplicados visuales
        self.tabla_metadatos.setRowCount(0)
        self.tabla_renderizar.setRowCount(0)

        conn = sqlite3.connect(self.db_path)
        # Query optimizado: 16 columnas en total (f[0] al f[15])
        query = """SELECT 
                    p.carpeta,          -- f[0]
                    p.blender_version,  -- f[1]
                    m.escena,           -- f[2]
                    m.viewlayer,        -- f[3]
                    m.camara,           -- f[4]
                    m.f_inicio,         -- f[5]
                    m.f_final,          -- f[6]
                    m.fps,              -- f[7]
                    m.res_x,            -- f[8]
                    m.res_y,            -- f[9]
                    p.id,               -- f[10]
                    p.fecha_mod,        -- f[11]
                    r.motor,            -- f[12]
                    r.dispositivo,      -- f[13]
                    r.formato,          -- f[14]
                    r.nombre_out        -- f[15]
                FROM proyectos p
                LEFT JOIN metadatos m ON p.id = m.id_proyecto 
                LEFT JOIN renderizado r ON p.id = r.id_proyecto"""
    
        filas = conn.execute(query).fetchall()
        conn.close()

        for f in filas:
            ruta_archivo = f[0]
            id_proyecto = f[10] # Antes f[14], ahora f[10]
            fecha_db = str(f[11])[:16] if f[11] else "" # p.fecha_mod
    
            existe = os.path.exists(ruta_archivo) if ruta_archivo else False
            n_sync = False

            if existe:
                mt = os.path.getmtime(ruta_archivo)
                fd = datetime.datetime.fromtimestamp(mt).strftime('%d/%m/%Y %H:%M')
                if not fecha_db or fd != fecha_db: 
                    n_sync = True

            self._insertar_filas(f, n_sync, existe)


    def _insertar_filas(self, f, n_sync, existe):
        row = self.tabla_metadatos.rowCount()
        self.tabla_metadatos.insertRow(row)
        self.tabla_renderizar.insertRow(row)

        ruta_completa = f[0] if f[0] else ""
        nombre_blend = os.path.basename(ruta_completa) if ruta_completa else "Sin nombre"
        version_blend = f[1] if f[1] else "---"

        # --- TABLA METADATOS (10 columnas) ---
        datos_m = [
            nombre_blend,                      # Col 0: Nombre
            version_blend,                     # Col 1: Versión
            f[2] or "---",                     # Col 2: Escena
            f[3] or "---",                     # Col 3: ViewLayer
            f[4] or "---",                     # Col 4: Cámara
            f[5] if f[5] is not None else 1,   # Col 5: Inicio
            f[6] if f[6] is not None else 250, # Col 6: Fin
            f[7] or 0,                         # Col 7: FPS
            f[8] or 0,                         # Col 8: Res X
            f[9] or 0,                         # Col 9: Res Y
            f[0]                               # Col 10: Ruta
        ]

        for i, v in enumerate(datos_m):
            item = QTableWidgetItem(str(v))
            item.setTextAlignment(Qt.AlignCenter)
            self._aplicar_estilo_alerta(item, n_sync, existe, es_nombre=(i==0))
            self.tabla_metadatos.setItem(row, i, item)

        # --- TABLA RENDERIZAR (Acciones y Configuración) ---
        # Col 0: Checkbox
        chk = QCheckBox()
        chk.setChecked(existe)
        self.tabla_renderizar.setCellWidget(row, 0, chk)

        # Datos estáticos en tabla render
        out_name = f[15] if f[15] else (os.path.splitext(nombre_blend)[0] if ruta_completa else "output")

        cols_r = {
            1: nombre_blend, 
            2: version_blend, 
            5: "render", # ruta_output (puedes cambiarlo por f[índice] si lo añades al SELECT)
            6: out_name, 
            8: str(f[5] or 1), # f_start
            9: str(f[6] or 1)  # f_end
        }

        for c, t in cols_r.items():
            item = QTableWidgetItem(str(t))
            item.setTextAlignment(Qt.AlignCenter)
            self._aplicar_estilo_alerta(item, n_sync, existe, es_nombre=(c==1))
            self.tabla_renderizar.setItem(row, c, item)

        # ComboBoxes con índices actualizados
        combos = [
            (3, ["EEVEE", "CYCLES"], f[12]),      # Col 3: Motor (f[12])
            (4, ["CPU", "CUDA", "OPTIX", "HIP"], f[13]), # Col 4: Dispositivo (f[13])
            (7, ["PNG", "JPEG", "EXR", "AVI_JPEG"], f[14]) # Col 7: Formato (f[14])
        ]

        for col, opts, cur in combos:
            cb = QComboBox()
            cb.addItems(opts)
            val_defecto = "CUDA" if col == 4 else (opts[0] if opts else "")
            cb.setCurrentText(str(cur) if cur and str(cur) != "None" else val_defecto)
            self.tabla_renderizar.setCellWidget(row, col, cb)

        # Control de Progreso y Botón (usando f[10] que es el ID)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setStyleSheet("QProgressBar { text-align: center; border-radius: 5px; background: #333; } "
                        "QProgressBar::chunk { background-color: #2980b9; }")
        self.tabla_renderizar.setCellWidget(row, 10, bar)

        # --- Dentro de _insertar_filas ---
        id_proy = f[10] # El ID según tu estructura de SELECT
        btn_abort = QPushButton("🛑 Abort")
        btn_abort.setEnabled(False) # Inicia deshabilitado

        # Usamos un lambda para pasar el ID específico de esa fila
        btn_abort.clicked.connect(lambda _, id_p=id_proy: self.abortar_render_especifico(id_p))

        self.tabla_renderizar.setCellWidget(row, 11, btn_abort)


    def detectar_mejor_dispositivo(self, exe):
        """Consulta a Blender qué dispositivos de alto rendimiento están disponibles"""
        # Script que prueba los 3 motores principales de GPU
        script_check = (
            "import bpy; "
            "prefs = bpy.context.preferences.addons['cycles'].preferences; "
            "print('OPTIX:' + str(len(prefs.get_devices_for_type('OPTIX')))); "
            "print('CUDA:' + str(len(prefs.get_devices_for_type('CUDA')))); "
            "print('HIP:' + str(len(prefs.get_devices_for_type('HIP'))))"
        )
        
        try:
            res = subprocess.run([exe, "-b", "--python-expr", script_check], 
                                 capture_output=True, text=True, timeout=15,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            output = res.stdout
            
            # Prioridad de selección automática
            if "OPTIX:0" not in output and "OPTIX:" in output: return "OPTIX" # NVIDIA RTX
            if "CUDA:0" not in output and "CUDA:" in output: return "CUDA"   # NVIDIA GTX
            if "HIP:0" not in output and "HIP:" in output: return "HIP"     # AMD Radeon
            
        except Exception as e:
            self.consola.append(f"⚠️ Error en auto-detección: {e}")
            
        return "CPU"

    # --- RENDERIZADO BATCH Y CONSOLA ---
    def leer_consola_blender(self):
        # ... (Tu lógica existente para la consola y la barra de progreso)
        data = self.proceso_render.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        self.consola.insertPlainText(data)
        self.consola.ensureCursorVisible()

        # ... (Lógica Fra:X / Sample:X existente...)

        # --- NUEVA LÓGICA DE DETECCIÓN DE IMAGEN ---
        # Blender imprime: Saved: 'E:\ruta\archivo_001.png'
        if "Saved: '" in data and self.proceso_actual_row != -1:
            try:
                # Extraer la ruta que está entre comillas simples
                ruta_completa_cruda = data.split("Saved: '")[1].split("'")[0]
                # Normalizar ruta (por si acaso Blender usa / y Windows \)
                ruta_completa = os.path.normpath(ruta_completa_cruda)
                
                # Verificar si el archivo realmente existe (a veces tarda unos ms)
                if os.path.exists(ruta_completa):
                    self.actualizar_panel_preview(ruta_completa)
            except Exception as e:
                pass # Fallo silencioso si el parseo de consola cambia en Blender 5.x

        # Limitar la cantidad de texto en consola para evitar saturar la memoria
        if self.consola.blockCount() > 500:
            cursor = self.consola.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar() # Borra el salto de línea sobrante


    def leer_errores_blender(self):
        self.consola.insertPlainText(f"⚠️ {self.proceso_render.readAllStandardError().data().decode('utf-8', errors='ignore')}")

    def preparar_cola_batch(self):
        self.cola_render = []
        # Deshabilitar el botón principal para evitar clics dobles
        self.btn_batch.setEnabled(False)
        
        for r in range(self.tabla_renderizar.rowCount()):
            chk = self.tabla_renderizar.cellWidget(r, 0)
            if chk and chk.isChecked():
                # Función segura para capturar frames de la tabla renderizar
                def safe_int(col, default=1):
                    item = self.tabla_renderizar.item(r, col)
                    val = item.text() if item else ""
                    return val if val.isdigit() else str(default)

                # IMPORTANTE: La ruta real del archivo está en f[0], 
                # que corresponde a la columna de 'Ruta' oculta o visible en la UI.
                # Según tu carga de datos, f[0] es la ruta completa.
                self.cola_render.append({
                    "fila": r, 
                    "ruta": self.tabla_metadatos.item(r, 10).text() if self.tabla_metadatos.item(r, 10) else "", # Ajustar al índice real de 'Ruta'
                    "v": self.tabla_renderizar.item(r, 2).text(),
                    "m": self.tabla_renderizar.cellWidget(r, 3).currentText(), 
                    "d": self.tabla_renderizar.cellWidget(r, 4).currentText(),
                    "out": self.tabla_renderizar.item(r, 5).text(), 
                    "nom": self.tabla_renderizar.item(r, 6).text(),
                    "f": self.tabla_renderizar.cellWidget(r, 7).currentText(), 
                    "s": safe_int(8, 1),
                    "e": safe_int(9, 1)
                })

        if self.cola_render:
            self.procesar_siguiente_en_cola()
        else:
            self.btn_batch.setEnabled(True)
            self.consola.append("⚠️ No hay proyectos seleccionados para renderizar.")


    def procesar_siguiente_en_cola(self):
        if not self.cola_render:
            self.consola.append("\n✅ BATCH FINALIZADO.")
            self.btn_batch.setEnabled(True)
            return
            
        t = self.cola_render.pop(0)
        self.proceso_actual_row = t["fila"]
        
        # 1. Obtener ejecutable de Blender
        conn = sqlite3.connect(self.db_path)
        v_limpia = t["v"].replace("Blender ", "")[:3]
        exe_row = conn.execute("SELECT ruta FROM ejecutables WHERE version LIKE ? ORDER BY version DESC", 
                            (f"%{v_limpia}%",)).fetchone()
        conn.close()

        if not exe_row or not os.path.exists(t["ruta"]):
            self.consola.append(f"❌ Error: Archivo o Blender no encontrado para fila {t['fila'] + 1}")
            self.procesar_siguiente_en_cola()
            return
        
        exe = exe_row[0]
        dispositivo_final = t["d"]

        # 2. Configurar Salida
        carpeta_blend = os.path.dirname(t["ruta"])
        subcarpeta = t["out"].strip() if t["out"].strip() else "render"
        ruta_final_folder = os.path.join(carpeta_blend, subcarpeta)
        os.makedirs(ruta_final_folder, exist_ok=True)

        nombre_file = t["nom"].strip() if t["nom"].strip() else os.path.splitext(os.path.basename(t["ruta"]))[0]
        path_salida_completo = os.path.join(ruta_final_folder, f"{nombre_file}_###")

        # 3. SCRIPT PYTHON (Corregido con comillas triples para evitar SyntaxError)
        # 3. SCRIPT PYTHON (Optimizado para Blender 4.x/5.x)
        python_cmd = f"""
                    import bpy
                    import sys

                    scene = bpy.context.scene
                    scene.render.engine = 'CYCLES' if '{t["m"]}' == 'CYCLES' else 'BLENDER_EEVEE_NEXT'

                    if scene.render.engine == 'CYCLES':
                        cprefs = bpy.context.preferences.addons['cycles'].preferences
                        cprefs.get_devices()
                        
                        # Configurar tipo de dispositivo (CUDA, OPTIX, HIP, METAL, ONEAPI)
                        device_type = '{dispositivo_final}'
                        if device_type != 'CPU':
                            cprefs.compute_device_type = device_type
                            for d in cprefs.devices:
                                d.use = (d.type == device_type)
                            scene.cycles.device = 'GPU'
                        else:
                            scene.cycles.device = 'CPU'
                    """

        args = [
            "-b", t["ruta"],
            "--python-expr", python_cmd,
            "-o", path_salida_completo,
            "-F", t["f"],
            "-s", str(t["s"]),
            "-e", str(t["e"]),
            "-a"
        ]

        # 4. Actualizar UI y Lanzar
        bar = self.tabla_renderizar.cellWidget(t["fila"], 10)
        if bar:
            bar.setFormat("RENDERING... %p%")
            bar.setValue(0)
        
        btn_abort = self.tabla_renderizar.cellWidget(t["fila"], 11)
        if btn_abort:
            btn_abort.setEnabled(True)
            btn_abort.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        
        self.consola.append(f"🎬 Renderizando: {os.path.basename(t['ruta'])}")
        self.proceso_render.start(exe, args)

                # --- Dentro de procesar_siguiente_en_cola ---
        # Localizamos el botón en la columna 11 de la fila actual
        btn_abort = self.tabla_renderizar.cellWidget(self.proceso_actual_row, 11)

        if btn_abort:
            btn_abort.setEnabled(True)
            # Cambiamos el estilo para que el usuario note que ya puede usarlo
            btn_abort.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")


    def al_finalizar_render_actual(self, exit_code):
        row = self.proceso_actual_row
        if row == -1: return

        bar = self.tabla_renderizar.cellWidget(row, 10)
        btn_abort = self.tabla_renderizar.cellWidget(row, 11)
        
        if btn_abort:
            btn_abort.setEnabled(False)
            btn_abort.setStyleSheet("background-color: #7f8c8d; color: white;")

        if bar:
            status_exito = (exit_code == 0)
            bar.setValue(100)
            
            if status_exito:
                bar.setFormat("HECHO ✅")
                color = "#27ae60"
            else:
                # Si el usuario abortó, el texto ya debería decir SALTADO/ABORTADO
                if bar.text() == "SALTADO/ABORTADO":
                    color = "#e67e22"
                else:
                    bar.setFormat("ERROR ❌")
                    color = "#c0392b"
            
            bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }} "
                            f"QProgressBar {{ text-align: center; color: white; font-weight: bold; }}")

        self.proceso_actual_row = -1
        self.procesar_siguiente_en_cola()


    def sincronizar_todo_desde_principal(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. Obtener los proyectos registrados
        proyectos = cursor.execute("SELECT id, carpeta, blender_version FROM proyectos").fetchall()

        for id_proy, ruta, version_db in proyectos:
            if not os.path.exists(ruta): 
                continue

            # 2. Localizar el ejecutable de Blender para la extracción
            exe_row = cursor.execute("SELECT ruta FROM ejecutables LIMIT 1").fetchone()
            if not exe_row: 
                continue
    
            # 3. EXTRACCIÓN de datos desde el archivo .blend
            # Se asume que obtener_metadata_pro devuelve un diccionario con las claves correctas
            nuevos_datos = self.obtener_metadata_pro(exe_row[0], ruta)
    
            if nuevos_datos:
                print(f"DEBUG: Sincronizando ID {id_proy} - Escena: {nuevos_datos.get('active_scene')}")
        
                try:
                    # Actualizar Versión en la tabla Proyectos
                    cursor.execute("UPDATE proyectos SET blender_version=? WHERE id=?", 
                                (nuevos_datos.get('version_blender'), id_proy))
            
                    # 4. UPSERT Metadatos: Ahora con viewlayer, f_inicio y f_final
                    cursor.execute("""
                        INSERT INTO metadatos (id_proyecto, escena, viewlayer, camara, f_inicio, f_final, fps, res_x, res_y)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id_proyecto) DO UPDATE SET
                            escena=excluded.escena, 
                            viewlayer=excluded.viewlayer, 
                            camara=excluded.camara,
                            f_inicio=excluded.f_inicio, 
                            f_final=excluded.f_final, 
                            fps=excluded.fps, 
                            res_x=excluded.res_x, 
                            res_y=excluded.res_y
                    """, (
                        id_proy, 
                        nuevos_datos.get('active_scene', 'Scene'), 
                        nuevos_datos.get('view_layer', 'N/A'),  # Nuevo campo
                        nuevos_datos.get('active_camera', 'Camera'),
                        nuevos_datos.get('frame_start', 1),    # f_inicio
                        nuevos_datos.get('frame_end', 250),    # f_final
                        nuevos_datos.get('frame_rate', 24),
                        nuevos_datos.get('resolution_x', 1920), 
                        nuevos_datos.get('resolution_y', 1080)
                    ))
            
                    # 5. UPSERT Renderizado (Mantenemos f_start y f_end para la cola de renderizado)
                    cursor.execute("""
                        INSERT INTO renderizado (id_proyecto, motor, dispositivo, formato, f_start, f_end, ruta_output, nombre_out)
                        VALUES (?, 'CYCLES', 'CUDA', 'PNG', ?, ?, 'render', ?)
                        ON CONFLICT(id_proyecto) DO UPDATE SET
                            f_start=excluded.f_start, 
                            f_end=excluded.f_end
                    """, (
                        id_proy, 
                        nuevos_datos.get('frame_start', 1), 
                        nuevos_datos.get('frame_end', 250), 
                        os.path.splitext(os.path.basename(ruta))[0]
                    ))
            
                except Exception as e:
                    print(f"Error sincronizando ID {id_proy}: {e}")

        conn.commit()
        conn.close()

        # --- PASO CRÍTICO: RECALIBRACIÓN DE VERSIONES ---
        # Invocamos la función de corrección aquí para arreglar el problema de 
        # 'Versiones cambiadas.png' antes de refrescar la interfaz.
        self.corregir_asignacion_versiones()

        # 6. Refrescar la interfaz visual con los datos ya ordenados
        self.cargar_datos_desde_db()
        self.consola.append("✅ Sincronización completa: Datos técnicos y versiones corregidas.")
        
        # 6. Refrescar la interfaz visual
        self.cargar_datos_desde_db()


    def verificar_cambios_al_inicio(self):
        self.cargar_datos_desde_db()

    def abrir_con_blender_desde_tabla(self, item):
        tabla = item.tableWidget()
        fila = item.row()
        columna = item.column()
        
        # Identificar la tabla para saber dónde buscar la versión
        es_tabla_meta = (tabla == self.tabla_metadatos)
        
        # IMPORTANTE: La ruta absoluta está en la Columna 10 de Metadatos
        item_ruta = self.tabla_metadatos.item(fila, 10)
        if not item_ruta: return
        ruta_blend = item_ruta.text()

        # Solo abrir si se hace clic en Nombre (0/1) o Ruta (10)
        if es_tabla_meta and columna not in [0, 10]: return
        if not es_tabla_meta and columna != 1: return

        if not os.path.exists(ruta_blend):
            QMessageBox.warning(self, "Error", f"El archivo no existe en:\n{ruta_blend}")
            return

        # Obtener versión para buscar el ejecutable correcto
        version_texto = self.tabla_metadatos.item(fila, 1).text() if es_tabla_meta else self.tabla_renderizar.item(fila, 2).text()
        match = re.search(r"(\d+\.\d+)", version_texto) # Buscamos 4.2, 4.5, etc.
        v_search = match.group(1) if match else "4.2"

        conn = sqlite3.connect(self.db_path)
        # Buscamos por versión parecida o la más reciente
        res = conn.execute("SELECT ruta FROM ejecutables WHERE version LIKE ? ORDER BY version DESC", 
                        (f"%{v_search}%",)).fetchone()
        if not res:
            res = conn.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
        conn.close()

        if res:
            try:
                self.consola.append(f"🚀 Abriendo: {os.path.basename(ruta_blend)}")
                subprocess.Popen([res[0], ruta_blend])
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo lanzar Blender: {e}")
        else:
            QMessageBox.warning(self, "Configuración", "Registra un ejecutable de Blender en Preferencias.")


    def mostrar_menu_contextual(self, pos):
        tabla_activa = self.sender()
        item = tabla_activa.itemAt(pos)
        if not item: return

        fila = item.row()
        menu = QMenu()
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #555; }")

        accion_abrir = QAction("🚀 Abrir en Blender", self)
        accion_abrir.triggered.connect(lambda: self.abrir_con_blender_desde_tabla(item))
        menu.addAction(accion_abrir)

        menu.addSeparator()

        accion_eliminar = QAction("❌ Eliminar Proyecto", self)
        # Pasamos la fila para que la función de borrado sepa qué registro tocar
        accion_eliminar.triggered.connect(lambda: self.eliminar_proyecto_global(fila))
        menu.addAction(accion_eliminar)

        menu.exec(tabla_activa.mapToGlobal(pos))


    def eliminar_proyecto_global(self, fila):
        # La ruta es nuestra llave primaria lógica en la UI (Columna 10)
        item_ruta = self.tabla_metadatos.item(fila, 10)
        if not item_ruta: return
        
        ruta_blend = item_ruta.text()
        nombre = os.path.basename(ruta_blend)

        confirmar = QMessageBox.question(
            self, "Eliminar", f"¿Quitar '{nombre}' del gestor?\n\nEsto borrará toda su configuración.",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirmar == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(self.db_path)
                # CRÍTICO: Activar llaves foráneas para que funcione el ON DELETE CASCADE
                conn.execute("PRAGMA foreign_keys = ON") 
                
                # Borramos de la tabla padre (proyectos)
                conn.execute("DELETE FROM proyectos WHERE carpeta = ?", (ruta_blend,))
                
                conn.commit()
                conn.close()

                # Recargar la interfaz para reflejar los cambios
                self.cargar_datos_desde_db() 
                self.consola.append(f"🗑️ Eliminado: {nombre}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error de DB", f"No se pudo eliminar: {e}")

    def leer_consola_blender(self):
        data = self.proceso_render.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        self.consola.insertPlainText(data)
        self.consola.ensureCursorVisible()

        if self.proceso_actual_row == -1:
            return

        bar = self.tabla_renderizar.cellWidget(self.proceso_actual_row, 10)
        if not bar:
            return

        # --- PROCESAMIENTO DE ANIMACIÓN (Fra:XX) ---
        if "Fra:" in data:
            try:
                # Extraer solo los números de la parte del frame
                parte = data.split("Fra:")[1].split("|")[0].split(" ")[0].strip()
                num_extraido = ''.join(filter(str.isdigit, parte))
                
                if num_extraido: # Solo si hay algo que convertir
                    frame_actual = int(num_extraido)
                    
                    # Obtener rangos con validación de seguridad
                    item_ini = self.tabla_renderizar.item(self.proceso_actual_row, 8)
                    item_fin = self.tabla_renderizar.item(self.proceso_actual_row, 9)
                    
                    f_ini = int(item_ini.text()) if item_ini and item_ini.text().isdigit() else 1
                    f_fin = int(item_fin.text()) if item_fin and item_fin.text().isdigit() else 1
                    
                    total_frames = (f_fin - f_ini) + 1
                    if total_frames <= 0: total_frames = 1
                    
                    progreso_raw = ((frame_actual - f_ini + 1) / total_frames) * 100
                    progreso = int(min(max(progreso_raw, 0), 100))
                    
                    bar.setFormat("%p%") 
                    bar.setValue(progreso)
                    bar.setStyleSheet("QProgressBar::chunk { background-color: #f39c12; }")
            except Exception as e:
                print(f"Error en frames: {e}")

        # --- PROCESAMIENTO DE MUESTRAS (Sample X/X) ---
        elif "Sample" in data:
            try:
                # Limpiamos la línea para evitar el error de base 10
                linea_sample = data.split("Sample")[1].strip()
                if "/" in linea_sample:
                    parte_actual = linea_sample.split("/")[0].strip()
                    parte_total = linea_sample.split("/")[1].split(" ")[0].strip()
                    
                    # Solo convertimos si ambos son dígitos
                    if parte_actual.isdigit() and parte_total.isdigit():
                        s_act = int(parte_actual)
                        s_tot = int(parte_total)
                        
                        progreso_s = int((s_act / s_tot) * 100)
                        bar.setFormat(f"Muestras: {progreso_s}%")
                        bar.setValue(progreso_s)
            except Exception as e:
                # Silenciamos errores menores de parsing de samples
                pass
    
    def abortar_render_especifico(self, id_proyecto):
        """
        Función que se activa al presionar el botón de la tabla.
        """
        if self.proceso_render and self.proceso_render.state() == QProcess.Running:
            # 1. Detener el proceso de Blender inmediatamente
            self.proceso_render.kill() 
            
            # 2. Informar en la consola
            self.consola.append(f"⚠️ Renderizado del proyecto {id_proyecto} abortado por el usuario.")
            
            # 3. Marcar visualmente la barra de progreso
            row = self.proceso_actual_row
            bar = self.tabla_renderizar.cellWidget(row, 10)
            if bar:
                bar.setFormat("SALTADO/ABORTADO")
                bar.setValue(100)
                bar.setStyleSheet("QProgressBar::chunk { background-color: #e67e22; }")

    def actualizar_panel_preview(self, ruta_archivo):
        """Carga, escala la imagen y actualiza el pie de foto"""
        try:
            # 1. Carga eficiente con QImageReader
            reader = QImageReader(ruta_archivo)
            if not reader.canRead(): return # Evitar errores con archivos corruptos

            pixmap = QPixmap.fromImageReader(reader)
            
            # 2. ESCALADO MANUAL INTELIGENTE (Mantenimiento de Proporción)
            # Obtenemos el tamaño actual del GroupBox
            w_disponible = self.grupo_preview.width() - 20 # Restar márgenes internos
            h_disponible = self.grupo_preview.height() - 80 # Espacio para imagen + pie foto

            if w_disponible > 0 and h_disponible > 0:
                pixmap_escalado = pixmap.scaled(
                    w_disponible, h_disponible,
                    Qt.KeepAspectRatio,        # Clave: NO deformar
                    Qt.SmoothTransformation   # Alta calidad de escalado
                )
                self.lbl_preview.setPixmap(pixmap_escalado)
                # Quitar borde punteado una vez que hay imagen
                self.lbl_preview.setStyleSheet("border: 1px solid #777; background: #000;") 

            # 3. ACTUALIZAR PIE DE FOTO
            nombre_archivo = os.path.basename(ruta_archivo)
            directorio = os.path.dirname(ruta_archivo)
            
            self.lbl_caption_name.setText(nombre_archivo)
            self.lbl_caption_path.setText(f"📂 {directorio}")

        except Exception as e:
            self.consola.append(f"⚠️ Fallo al cargar preview: {e}")


    def corregir_asignacion_versiones(self):
        """
        Recalibra cada proyecto asegurando que la versión detectada 
        se asigne a su ruta específica en la base de datos.
        """
        for fila in range(self.tabla_metadatos.rowCount()):
            # 1. Obtener la ruta (La única verdad absoluta)
            item_ruta = self.tabla_metadatos.item(fila, 10) # Columna de la ruta completa
            if not item_ruta: continue
            ruta_abs = item_ruta.text()

            # 2. Extraer versión real del archivo físico
            version_detectada = self.extraer_version_desde_blend(ruta_abs)
            
            # 3. Actualizar la base de datos usando la RUTA como filtro único
            try:
                conn = sqlite3.connect(self.db_path)
                # Actualizamos la tabla metadatos vinculándola por la ruta en la tabla proyectos
                conn.execute("""
                    UPDATE metadatos 
                    SET version = ? 
                    WHERE id_proyecto = (SELECT id FROM proyectos WHERE carpeta = ?)
                """, (version_detectada, ruta_abs))
                conn.commit()
                conn.close()
                
                # 4. Reflejar el cambio en la UI inmediatamente
                self.tabla_metadatos.item(fila, 1).setText(version_detectada)
                
            except Exception as e:
                self._log(f"❌ Error de asignación en {os.path.basename(ruta_abs)}: {e}")

        self.cargar_datos_desde_db() # Refresca ambas tablas (Meta y Render)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'pixmap_actual') and not self.pixmap_actual.isNull():
            self.lbl_preview.setPixmap(self.pixmap_actual.scaled(
                self.lbl_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))