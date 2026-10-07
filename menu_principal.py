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

        self.tabla_renderizar.itemChanged.connect(self.on_render_item_changed)
        
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


    def extraer_version_desde_blend(self, ruta_blend):
        """
        Extrae la versión real del ADN del archivo .blend.
        Compatible con Blender 4.x y 5.x.
        """
        try:
            if not os.path.exists(ruta_blend):
                return "Desconocida"

            with open(ruta_blend, 'rb') as f:
                data_head = f.read(12) # BLENDER-vVv
                print(data_head)
                
                if data_head.startswith(b'BLENDER'):
                    # Los bytes 9, 10 y 11 son la versión
                    # v9 = Major, v10 = Minor, v11 = Patch/Sub
                    v9 = chr(data_head[9])  # '5'
                    v10 = chr(data_head[10]) # '1'
                    v11 = chr(data_head[11]) # '1'

                    # Caso especial para tu versión estable 4.5.8
                    if v9 == "4" and v10 == "5":
                        return f"Blender 4.5.{v11} LTS"
                    
                    # Para Blender 5.x y futuros
                    return f"Blender {v9}.{v10}.{v11}"
                    
        except Exception as e:
            if hasattr(self, '_log'):
                self._log(f"⚠️ Error ADN en {os.path.basename(ruta_blend)}: {e}")
        
        return "Blender Desconocido"

    def obtener_metadata_pro(self, exe_manual, ruta):
        """
        Extrae metadatos técnicos (versión, escena, motor) asegurando independencia total.
        Optimizado para entornos Windows y Linux.
        """
        # --- 1. RESET Y PREPARACIÓN ---
        datos_finales = None
        version_detectada_adn = self.extraer_version_desde_blend(ruta)
        nombre_version_db = f"Blender {version_detectada_adn}" # Fallback por defecto
        ejecutable_a_usar = exe_manual

        # Determinar ruta del script extractor (independiente de si es .py o .exe)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        script_extractor = os.path.join(base_dir, "info_archivo_blend.py")

        try:
            # --- 2. BÚSQUEDA DE BINARIO EN BASE DE DATOS ---
            conn = sqlite3.connect(self.db_path)
            
            # Si no hay ejecutable manual, buscamos el que coincida con el ADN del archivo
            if not ejecutable_a_usar or not os.path.exists(ejecutable_a_usar):
                filtro = f"%{version_detectada_adn}%"
                res = conn.execute(
                    "SELECT ruta, version FROM ejecutables WHERE version LIKE ? ORDER BY version DESC", 
                    (filtro,)
                ).fetchone()
                
                if res:
                    ejecutable_a_usar = res[0]
                    nombre_version_db = res[1]
                else:
                    # Fallback: Usar el último Blender registrado si no hay coincidencia exacta
                    last = conn.execute("SELECT ruta, version FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
                    if last:
                        ejecutable_a_usar, nombre_version_db = last
            else:
                # Si el exe ya existe (manual), recuperamos su nombre real de la DB para la UI
                res_name = conn.execute("SELECT version FROM ejecutables WHERE ruta = ?", (ejecutable_a_usar,)).fetchone()
                if res_name:
                    nombre_version_db = res_name[0]
            
            conn.close()

            # Validación de seguridad: si no hay ejecutable, no podemos continuar
            if not ejecutable_a_usar or not os.path.exists(ejecutable_a_usar):
                return {"version_blender": "Binario no configurado", "active_scene": "N/A"}

            # --- 3. EJECUCIÓN DEL SUBPROCESO (Blender en modo Background) ---
            # En Windows 11 usamos CREATE_NO_WINDOW para evitar el molesto parpadeo del CMD
            resultado = subprocess.run(
                [ejecutable_a_usar, "-b", ruta, "--python", script_extractor],
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='ignore',
                timeout=25,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # --- 4. PARSEO DE DATOS JSON ---
            if resultado.stdout:
                # Buscamos la línea que contiene nuestro tag de datos (leemos desde el final)
                for linea in reversed(resultado.stdout.splitlines()):
                    linea = linea.strip()
                    if "JCRENDER_DATA:" in linea:
                        try:
                            json_str = linea.split("JCRENDER_DATA:")[1]
                            datos_finales = json.loads(json_str)
                            
                            # Prioridad de etiquetado de versión:
                            # 1. Versión específica devuelta por el script (ej. 4.5.8)
                            # 2. Nombre guardado en la DB
                            v_interna = datos_finales.get('version_blender')
                            if v_interna and len(str(v_interna)) > 2:
                                datos_finales['version_blender'] = f"Blender {v_interna}"
                            else:
                                datos_finales['version_blender'] = nombre_version_db

                            print(f"DEBUG: {os.path.basename(ruta)} detectado como {datos_finales['version_blender']}")
                            return datos_finales
                        except Exception as e:
                            print(f"Error parseando JSON: {e}")
                            continue
            
            # Si llegamos aquí, el subproceso falló o no devolvió el tag
            return {
                "version_blender": nombre_version_db, 
                "active_scene": "Error lectura",
                "engine": "Desconocido"
            }

        except Exception as e:
            print(f"Error crítico de metadatos en {os.path.basename(ruta)}: {e}")
            return {
                "version_blender": "Error ADN", 
                "active_scene": "N/A"
            }
        
    
    # --- FUNCIÓN: ELIMINAR PROYECTO ---
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
        if not os.path.exists(self.db_path): 
            return

        # 1. BLOQUEO DE SEÑALES
        # Evita que on_render_item_changed se ejecute mientras cargamos datos
        self.tabla_renderizar.blockSignals(True)
        self.tabla_metadatos.blockSignals(True)

        try:
            # Limpieza total antes de cargar
            self.tabla_metadatos.setRowCount(0)
            self.tabla_renderizar.setRowCount(0)

            conn = sqlite3.connect(self.db_path)
            # Seleccionamos explícitamente las columnas para mantener el orden de f[index]
            query = """SELECT 
                        p.carpeta, p.blender_version, m.escena, m.viewlayer, m.camara, 
                        m.f_inicio, m.f_final, m.fps, m.res_x, m.res_y, 
                        p.id, p.fecha_mod, r.motor, r.dispositivo, r.formato, r.nombre_out 
                    FROM proyectos p
                    LEFT JOIN metadatos m ON p.id = m.id_proyecto 
                    LEFT JOIN renderizado r ON p.id = r.id_proyecto
                    ORDER BY p.id ASC"""
            
            filas = conn.execute(query).fetchall()
            conn.close()

            for f in filas:
                # Verificación de sincronización (DNA monitor)
                ruta = f[0]
                existe = os.path.exists(ruta) if ruta else False
                n_sync = False
                
                if existe:
                    mt = os.path.getmtime(ruta)
                    fd = datetime.datetime.fromtimestamp(mt).strftime('%d/%m/%Y %H:%M')
                    fecha_db = str(f[11])[:16] if f[11] else ""
                    # Si la fecha de modificación del archivo es distinta a la DB, marcar alerta
                    if not fecha_db or fd != fecha_db: 
                        n_sync = True

                # Inserta la fila en ambas tablas visuales
                self._insertar_filas(f, n_sync, existe)

        except Exception as e:
            if hasattr(self, 'consola'):
                self.consola.append(f"❌ Error al cargar base de datos: {e}")
            print(f"Error crítico en carga: {e}")

        finally:
            # 2. DESBLOQUEO DE SEÑALES
            # Ahora que la tabla está lista, permitimos que los cambios del usuario se guarden
            self.tabla_renderizar.blockSignals(False)
            self.tabla_metadatos.blockSignals(False)


    def _insertar_filas(self, f, n_sync, existe):
        # 1. Crear la fila en ambas tablas al mismo tiempo
        row = self.tabla_metadatos.rowCount()
        self.tabla_metadatos.insertRow(row)
        self.tabla_renderizar.insertRow(row)

        # 2. Variables de datos seguras basándonos en tu Query SQL de cargar_datos_desde_db
        # f[0]=carpeta(ruta), f[1]=version, f[2]=escena, f[10]=id_proyecto
        ruta_full = str(f[0]) if f[0] else ""
        nombre_b = os.path.basename(ruta_full) if ruta_full else "Sin nombre"
        version_b = str(f[1]) if f[1] else "---"
        id_proy = f[10]

        # --- LLENAR TABLA METADATOS ---
        datos_metadatos = [
            nombre_b,           # 0
            version_b,          # 1
            f[2] or "---",      # 2: Escena
            f[3] or "---",      # 3: ViewLayer
            f[4] or "---",      # 4: Cámara
            f[5] or 1,          # 5: Inicio
            f[6] or 1,          # 6: Fin
            f[7] or 0,          # 7: FPS
            f[8] or 0,          # 8: Res X
            f[9] or 0,          # 9: Res Y
            ruta_full           # 10: RUTA ABSOLUTA (Vital para Batch)
        ]

        for col_m, valor in enumerate(datos_metadatos):
            item = QTableWidgetItem(str(valor))
            item.setTextAlignment(Qt.AlignCenter)
            # Aplicar alertas visuales si el archivo se movió o cambió
            self._aplicar_estilo_alerta(item, n_sync, existe, es_nombre=(col_m==0))
            self.tabla_metadatos.setItem(row, col_m, item)

        # --- LLENAR TABLA RENDERIZAR ---
        # Col 0: Checkbox de selección
        chk = QCheckBox()
        chk.setChecked(existe)
        self.tabla_renderizar.setCellWidget(row, 0, chk)

        # Columnas de texto
        nombre_out_val = f[15] if f[15] else os.path.splitext(nombre_b)[0]
        
        mapping_render = {
            1: nombre_b, 
            2: version_b, 
            5: "render", 
            6: nombre_out_val, 
            8: str(f[5] or 1), 
            9: str(f[6] or 1)
        }

        for col_r, txt in mapping_render.items():
            it_r = QTableWidgetItem(str(txt))
            it_r.setTextAlignment(Qt.AlignCenter)
            self.tabla_renderizar.setItem(row, col_r, it_r)

        # Widgets de ComboBox (Motor, Disp, Formato)
        self._crear_combos_en_fila(row, f[12], f[13], f[14])

        # BARRA DE PROGRESO (Columna 10)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setAlignment(Qt.AlignCenter)
        bar.setFormat("ESPERANDO...")
        # Estilo para visibilidad en Linux Mint Dark
        bar.setStyleSheet("""
            QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #27ae60; }
        """)
        self.tabla_renderizar.setCellWidget(row, 10, bar)

        # BOTÓN ABORTAR (Columna 11)
        btn_abort = QPushButton("🛑 Abort")
        btn_abort.setEnabled(False)
        # Usamos el ID de la base de datos (f[10]) para identificar el proceso
        btn_abort.clicked.connect(lambda _, r=row: self.abortar_render_especifico(r))
        self.tabla_renderizar.setCellWidget(row, 11, btn_abort)
        

    def _crear_combos_en_fila(self, row, motor, disp, fmt):
        # Definimos los combos con su columna, opciones, valor actual y nombre del campo en la DB
        combos_def = [
            (3, ["EEVEE", "CYCLES"], motor, "motor"),
            (4, ["CPU", "CUDA", "OPTIX", "HIP"], disp, "dispositivo"),
            (7, ["PNG", "JPEG", "EXR", "AVI_JPEG"], fmt, "formato") # <--- Campo Formato
        ]
        
        for c, opts, curr, campo in combos_def:
            cb = QComboBox()
            cb.addItems(opts)
            
            # Establecer valor actual
            if curr and str(curr) != "None":
                cb.setCurrentText(str(curr))
            else:
                # Valores por defecto inteligentes
                default = "CUDA" if c == 4 else opts[0]
                cb.setCurrentText(default)
            
            # CONEXIÓN CRUCIAL: Al cambiar el combo, se guarda en la DB inmediatamente
            # Usamos r=row y fld=campo para capturar los valores correctos en el closure
            cb.currentTextChanged.connect(lambda texto, r=row, fld=campo: self.actualizar_dato_render_db(r, fld, texto))
            
            self.tabla_renderizar.setCellWidget(row, c, cb)


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
    

    # --- AÑADE ESTOS MÉTODOS DENTRO DE LA CLASE MenuPrincipal ---

    def on_render_item_changed(self, item):
        """Detecta cambios manuales del usuario en la tabla de renderizado"""
        # 1. Bloqueo de seguridad interno para evitar rebotes
        # (Opcional, si notas que se dispara dos veces)
        
        row = item.row()
        col = item.column()
        nuevo_texto = item.text().strip() # Eliminamos espacios accidentales

        # 2. Mapeo Extendido (Ajustado a No aparecen.png)
        # Col 5: Carpeta Out -> campo 'ruta_output'
        # Col 6: Nombre Out  -> campo 'nombre_out'
        # Col 8: Desde       -> campo 'f_inicio'
        # Col 9: Hasta       -> campo 'f_final'
        mapeo = {
            5: "ruta_output", 
            6: "nombre_out", 
            8: "f_inicio",   
            9: "f_final"
        }

        if col in mapeo:
            campo_db = mapeo[col]
            
            # 3. Validación de integridad para Frames (Columnas 8 y 9)
            if col in [8, 9]:
                if not nuevo_texto.isdigit():
                    # Si el usuario borra el frame o pone letras, no guardamos
                    return 

            # 4. Ejecutar la actualización en la base de datos
            self.actualizar_dato_render_db(row, campo_db, nuevo_texto)


    def actualizar_dato_render_db(self, row, campo, valor):
        try:
            # Extraer ID de la columna 10 de metadatos
            item_id = self.tabla_metadatos.item(row, 10)
            if not item_id: return
            id_proyecto = item_id.text()

            # Decidir tabla según el campo
            # f_inicio y f_final están en metadatos, el resto en renderizado
            tabla_db = "metadatos" if campo in ["f_inicio", "f_final"] else "renderizado"

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Actualización inmediata
            query = f"UPDATE {tabla_db} SET {campo} = ? WHERE id_proyecto = ?"
            cursor.execute(query, (valor, id_proyecto))
            
            conn.commit()
            conn.close()
            # Consola de depuración opcional
            # print(f"DB Guardada: {campo} -> {valor}")
            
        except Exception as e:
            print(f"Error al guardar en tiempo real: {e}")


    def leer_consola_blender(self):
        data = self.proceso_render.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        self.consola.insertPlainText(data)
        self.consola.ensureCursorVisible()

        if self.proceso_actual_row == -1:
            return

        bar = self.tabla_renderizar.cellWidget(self.proceso_actual_row, 10)
        if not bar:
            return

        # --- 1. PROCESAMIENTO DE ANIMACIÓN (Prioridad Alta) ---
        if "Fra:" in data:
            try:
                # Extraer frame actual con regex para evitar errores de split
                import re
                match = re.search(r"Fra:(\d+)", data)
                if match:
                    frame_actual = int(match.group(1))
                    
                    item_ini = self.tabla_renderizar.item(self.proceso_actual_row, 8)
                    item_fin = self.tabla_renderizar.item(self.proceso_actual_row, 9)
                    
                    f_ini = int(item_ini.text()) if item_ini and item_ini.text().isdigit() else 1
                    f_fin = int(item_fin.text()) if item_fin and item_fin.text().isdigit() else 1
                    
                    total_frames = (f_fin - f_ini) + 1
                    if total_frames <= 0: total_frames = 1
                    
                    progreso_global = int(((frame_actual - f_ini + 1) / total_frames) * 100)
                    progreso_global = min(max(progreso_global, 0), 100)
                    
                    # Actualizamos el valor de la barra con el progreso REAL del proyecto
                    bar.setValue(progreso_global)
                    # Forzamos que el texto sea visible y centrado
                    bar.setAlignment(Qt.AlignCenter) 
                    
            except Exception as e:
                print(f"Error en frames: {e}")

        # --- 2. PROCESAMIENTO DE MUESTRAS (Información Detallada) ---
        # Usamos IF (no elif) para que el texto se actualice sin interrumpir el valor de la barra
        if "Sample" in data:
            try:
                linea_sample = data.split("Sample")[1].strip()
                if "/" in linea_sample:
                    partes = linea_sample.split("/")
                    s_act = int(''.join(filter(str.isdigit, partes[0])))
                    s_tot = int(''.join(filter(str.isdigit, partes[1].split()[0])))
                    
                    # Solo cambiamos el FORMATO del texto, no el VALUE de la barra
                    # Así el color de la barra representa el avance total, 
                    # pero el texto te dice qué tan avanzado va el frame actual.
                    porcentaje_sample = int((s_act / s_tot) * 100)
                    bar.setFormat(f"Proy: %p% | Frame: {porcentaje_sample}%")
                    
            except:
                pass

    def procesar_salida_consola(self, linea, fila_tabla, f_inicio, f_final):
        # Buscamos el patrón "Fra:X" en la salida de Blender
        match = re.search(r"Fra:(\d+)", linea)
        
        if match:
            frame_actual = int(match.group(1))
            total_frames = (f_final - f_inicio) + 1
            
            # Calcular porcentaje
            if total_frames > 0:
                progreso_num = int(((frame_actual - f_inicio + 1) / total_frames) * 100)
                # Asegurar que no exceda 100%
                progreso_num = min(100, max(0, progreso_num))
                
                # Actualizar la UI
                self.actualizar_barra_progreso_ui(fila_tabla, progreso_num)

    def actualizar_barra_progreso_ui(self, fila, valor):
        # Acceder al widget de la columna 10 (PROGRESO)
        widget = self.tabla_renderizar.cellWidget(fila, 10)
        if isinstance(widget, QProgressBar):
            widget.setValue(valor)
            widget.setFormat(f"RENDERING... {valor}%")

    
    def leer_errores_blender(self):
        self.consola.insertPlainText(f"⚠️ {self.proceso_render.readAllStandardError().data().decode('utf-8', errors='ignore')}")

    def preparar_cola_batch(self):
        self.cola_render = []
        self.btn_batch.setEnabled(False)

        # --- FUNCIONES AUXILIARES (Definidas fuera del loop para mayor velocidad) ---
        def get_text_safe(tabla, row, col, default=""):
            item = tabla.item(row, col)
            return item.text().strip() if item else default

        def safe_int(tabla, row, col, default=1):
            val = get_text_safe(tabla, row, col)
            return int(val) if val.isdigit() else default

        for r in range(self.tabla_renderizar.rowCount()):
            # Columna 0 tiene el Checkbox de selección
            chk = self.tabla_renderizar.cellWidget(r, 0)
            
            if chk and chk.isChecked():
                # --- CAPTURA DE WIDGETS (ComboBoxes) ---
                cb_motor = self.tabla_renderizar.cellWidget(r, 3)
                cb_disp  = self.tabla_renderizar.cellWidget(r, 4)
                cb_form  = self.tabla_renderizar.cellWidget(r, 7)

                try:
                    # OBTENCIÓN DE LA RUTA REAL: 
                    # Según tu _insertar_filas anterior, la ruta absoluta está en la Col 10
                    # de la tabla_metadatos.
                    ruta_completa = get_text_safe(self.tabla_metadatos, r, 10)

                    # VALIDACIÓN CRÍTICA: Si la ruta no existe, avisar antes de empezar
                    if not os.path.exists(ruta_completa):
                        self.consola.append(f"❌ Error fila {r+1}: El archivo .blend no existe en la ruta.")
                        continue

                    self.cola_render.append({
                        "fila": r, 
                        "ruta": ruta_completa,
                        "v":    get_text_safe(self.tabla_renderizar, r, 2, "4.5.8 LTS"),
                        "m":    cb_motor.currentText() if cb_motor else "CYCLES", 
                        "d":    cb_disp.currentText() if cb_disp else "CUDA",
                        "out":  get_text_safe(self.tabla_renderizar, r, 5, "render"), 
                        "nom":  get_text_safe(self.tabla_renderizar, r, 6, "output"),
                        "f":    cb_form.currentText() if cb_form else "PNG", 
                        "s":    safe_int(self.tabla_renderizar, r, 8, 1), # Frame Inicio
                        "e":    safe_int(self.tabla_renderizar, r, 9, 1)  # Frame Final
                    })
                except Exception as e:
                    if hasattr(self, 'consola'):
                        self.consola.append(f"❌ Error al capturar fila {r+1}: {e}")
                    continue

        # --- INICIO DE PROCESO ---
        if self.cola_render:
            self.consola.append(f"🚀 Iniciando cola de render: {len(self.cola_render)} proyectos.")
            
            # Resetear el progreso visual
            for item in self.cola_render:
                pbar = self.tabla_renderizar.cellWidget(item['fila'], 10)
                if pbar: 
                    pbar.setValue(0)
                    pbar.setFormat("EN COLA...")
                    
            self.procesar_siguiente_en_cola()
        else:
            self.btn_batch.setEnabled(True)
            self.consola.append("⚠️ No hay proyectos válidos o seleccionados para renderizar.")


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
        nombre_file_2 = 'img'
        path_salida_completo = os.path.join(ruta_final_folder, f"{nombre_file}_#####")

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
        self.tabla_renderizar.blockSignals(True) # Evitar bucles
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            proyectos = cursor.execute("SELECT id, carpeta FROM proyectos").fetchall()

            for id_proy, ruta in proyectos:
                if not os.path.exists(ruta): continue
                
                exe_row = cursor.execute("SELECT ruta FROM ejecutables LIMIT 1").fetchone()
                if not exe_row: continue
        
                nuevos_datos = self.obtener_metadata_pro(exe_row[0], ruta)
        
                if nuevos_datos:
                    # A. ACTUALIZACIÓN TÉCNICA (Lo que SIEMPRE debe sincronizarse)
                    cursor.execute("""
                        UPDATE metadatos SET 
                            escena=?, viewlayer=?, camara=?, fps=?, res_x=?, res_y=?
                        WHERE id_proyecto=?
                    """, (nuevos_datos.get('active_scene'), nuevos_datos.get('view_layer'),
                        nuevos_datos.get('active_camera'), nuevos_datos.get('frame_rate'),
                        nuevos_datos.get('resolution_x'), nuevos_datos.get('resolution_y'), id_proy))

                    # B. PROTECCIÓN DE TUS CAMBIOS (Lo que NO debe sobrescribirse)
                    # Al usar DO NOTHING, si el proyecto ya existe, no toca tus Frames ni tu Motor
                    cursor.execute("""
                        INSERT INTO renderizado (id_proyecto, motor, dispositivo, formato, nombre_out, ruta_output)
                        VALUES (?, 'CYCLES', 'OPTIX', 'PNG', ?, 'render')
                        ON CONFLICT(id_proyecto) DO NOTHING
                    """, (id_proy, os.path.splitext(os.path.basename(ruta))[0]))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error en sincronización: {e}")
        finally:
            self.cargar_datos_desde_db()
            self.tabla_renderizar.blockSignals(False)


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
                # Save the detected version in proyectos using the file path
                conn.execute("""
                    UPDATE proyectos
                    SET blender_version = ?
                    WHERE carpeta = ?
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
            

    def actualizar_ui_con_metadata(self, ruta_archivo, datos):
        """
        Busca la fila exacta que corresponde a la ruta y actualiza SOLO esa fila.
        """
        if not datos:
            return

        # Buscamos en qué fila está este archivo realmente
        fila_destino = -1
        for row in range(self.tabla_pro.rowCount()):
            # Suponiendo que la ruta completa está guardada en una columna (puedes tenerla oculta)
            # o que el nombre del archivo coincide.
            item_archivo = self.tabla_pro.item(row, 0) # Columna Nombre
            if item_archivo and os.path.basename(ruta_archivo) == item_archivo.text():
                fila_destino = row
                break
        
        if fila_destino != -1:
            # Ahora insertamos los datos asegurándonos de que es la fila correcta
            self.tabla_pro.setItem(fila_destino, 1, QTableWidgetItem(datos['version_blender']))
            self.tabla_pro.setItem(fila_destino, 2, QTableWidgetItem(datos.get('active_scene', 'N/A')))
            # ... resto de columnas
        else:
            # Si no existe, podrías crear la fila, pero esto evita que se crucen datos
            print(f"Error: No se encontró la fila para {ruta_archivo}")