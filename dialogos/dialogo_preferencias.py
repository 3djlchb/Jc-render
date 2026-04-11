import sqlite3
import os
import datetime
import subprocess
import re
import sys

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, 
                               QLineEdit, QPushButton, QFormLayout, QHBoxLayout, 
                               QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem, 
                               QHeaderView, QLabel, QTextEdit)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

class PreferenciasDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestor Inteligente de Blender - Configuración Pro")
        self.resize(1100, 850)
        
        # --- MEJORA 1: NORMALIZACIÓN DE RUTAS (Vital para Linux/Windows) ---
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            actual_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(actual_dir) 
        
        # Estandarizamos separadores de carpeta para evitar errores en SQLite
        self.db_path = os.path.join(base_dir, 'bbdd', 'config.db').replace("\\", "/")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._inicializar_bd()
        self.ultima_ruta_explorada = ""

        # UI SETUP
        layout_principal = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.tab_exe = QWidget()
        self._setup_tab_exe(QVBoxLayout(self.tab_exe))
        self.tab_blend = QWidget()
        self._setup_tab_blend(QVBoxLayout(self.tab_blend))

        self.tabs.addTab(self.tab_exe, "🚀 1. Versiones Blender")
        self.tabs.addTab(self.tab_blend, "📦 2. Archivos .blend")
        
        layout_principal.addWidget(self.tabs)
        layout_principal.addWidget(QLabel("📟 Monitor de ADN e Integridad:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(150)
        self.log_output.setStyleSheet("background-color: #1e1e1e; color: #a6e22e; font-family: 'Consolas'; font-size: 11px;")
        layout_principal.addWidget(self.log_output)

        self.actualizar_vistas_tablas()

    def _log(self, mensaje):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {mensaje}")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _inicializar_bd(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. Tabla de Motores
        cursor.execute("""CREATE TABLE IF NOT EXISTS ejecutables (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            ruta TEXT UNIQUE, 
            version TEXT,
            tipo_instalacion TEXT DEFAULT 'DESCONOCIDO')""")

        # 2. Tabla de Proyectos
        cursor.execute("""CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            carpeta TEXT UNIQUE, 
            blender_version TEXT, 
            fecha_mod TEXT)""")
        
        # 3. Tabla de Metadatos
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
        )""")
        
        # 4. Tabla de Renderizado
        cursor.execute("""CREATE TABLE IF NOT EXISTS renderizado (
            id_proyecto INTEGER PRIMARY KEY, 
            motor TEXT, 
            dispositivo TEXT, 
            formato TEXT, 
            f_start INTEGER, 
            f_end INTEGER, 
            ruta_output TEXT,
            nombre_out TEXT,
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
        
        conn.commit()
        conn.close()

    # --- MEJORA 2: ADN PROFUNDO MÁS ROBUSTO ---
    def extraer_version_desde_blend(self, ruta_blend):
        try:
            with open(ruta_blend, 'rb') as f:
                data_head = f.read(12)
                if data_head.startswith(b'BLENDER-'):
                    v_raw = data_head[9:12].decode('utf-8', errors='ignore')
                    v_major = v_raw[0]
                    v_minor = v_raw[1]
                    v_patch = v_raw[2]
                    
                    # Normalizamos para que coincida con lo detectado por 'blender -v'
                    if v_major == "4" and v_minor == "5":
                        return f"Blender 4.5.{v_patch} LTS"
                    return f"Blender {v_major}.{v_minor}.{v_patch}"
        except Exception:
            pass
        return "Blender 4.5.8 LTS"

    def seleccionar_y_guardar_automatico(self):
        # Filtro corregido para soportar tanto archivos con espacios como Linux
        ruta, _ = QFileDialog.getOpenFileName(self, "Registrar .blend", self.ultima_ruta_explorada, "Archivos (*.blend)")
        if not ruta: return
        
        # Normalización de ruta absoluta para evitar error "Archivo no existe"
        ruta = os.path.abspath(ruta).replace("\\", "/")
        self.ultima_ruta_explorada = os.path.dirname(ruta)

        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Verificar duplicados por ruta normalizada
            if cursor.execute("SELECT id FROM proyectos WHERE carpeta = ?", (ruta,)).fetchone():
                QMessageBox.information(self, "Aviso", "El archivo ya está registrado.")
                return

            # 2. ADN y Motor
            version_dna = self.extraer_version_desde_blend(ruta)
            match_v = re.search(r"(\d+\.\d+)", version_dna)
            v_search = match_v.group(1) if match_v else "4.5"
            
            # Buscar ejecutable compatible
            res_exe = cursor.execute("SELECT ruta FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",)).fetchone()
            if not res_exe:
                res_exe = cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()

            if not res_exe:
                raise Exception("Debe registrar al menos un ejecutable de Blender primero.")

            # 3. EXTRACCIÓN REAL (Uso de comillas en ruta para espacios)
            if not self.parent() or not hasattr(self.parent(), 'contenido'):
                raise Exception("Fallo de enlace con el script principal.")
                
            info_real = self.parent().contenido.obtener_metadata_pro(res_exe[0], ruta)
            
            if not info_real:
                raise Exception(f"No se pudo leer el ADN de: {os.path.basename(ruta)}")

            # 4. INSERTAR DATOS
            fecha_mod = datetime.datetime.fromtimestamp(os.path.getmtime(ruta)).strftime('%d/%m/%Y %H:%M')
            
            cursor.execute("INSERT INTO proyectos (carpeta, blender_version, fecha_mod) VALUES (?, ?, ?)", 
                         (ruta, info_real.get('version_blender', version_dna), fecha_mod))
            id_pro = cursor.lastrowid

            cursor.execute("""INSERT INTO metadatos (id_proyecto, escena, viewlayer, camara, f_inicio, f_final, fps, res_x, res_y) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (id_pro, info_real.get('active_scene', 'Scene'), info_real.get('view_layer', 'N/A'), 
                           info_real.get('active_camera', 'Camera'), info_real.get('frame_start', 1),
                           info_real.get('frame_end', 250), info_real.get('frame_rate', 24),
                           info_real.get('resolution_x', 1920), info_real.get('resolution_y', 1080)))

            cursor.execute("""INSERT INTO renderizado (id_proyecto, motor, dispositivo, formato, f_start, f_end, ruta_output, nombre_out) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (id_pro, 'CYCLES', 'OPTIX', 'PNG', info_real.get('frame_start', 1), 
                           info_real.get('frame_end', 250), "render", os.path.splitext(os.path.basename(ruta))[0]))

            conn.commit()
            self._log(f"✅ Registrado: {os.path.basename(ruta)}")
            
        except Exception as e:
            if conn: conn.rollback()
            self._log(f"❌ Error: {e}")
            QMessageBox.critical(self, "Error de Registro", str(e))
        finally:
            conn.close()
            self.actualizar_vistas_tablas()
            if self.parent() and hasattr(self.parent(), 'contenido'):
                self.parent().contenido.cargar_datos_desde_db()

    def sincronizar_todos_los_proyectos(self):
        self._log("🔄 Iniciando sincronización global...")
        conn = self._get_connection()
        cursor = conn.cursor()
    
        # Obtener proyectos registrados
        proyectos = cursor.execute("SELECT id, carpeta, blender_version FROM proyectos").fetchall()
    
        actualizados = 0
        for id_pro, ruta, version_db in proyectos:
            if not os.path.exists(ruta): 
                continue

            # Extraer fecha de modificación del archivo
            mtime = os.path.getmtime(ruta)
            fecha_disco = datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')
        
            # Localizar el ejecutable de Blender más reciente
            cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1")
            res_exe = cursor.fetchone()
        
            if res_exe:
                try:
                    # Llamada al extractor de metadatos
                    info = self.parent().contenido.obtener_metadata_pro(res_exe[0], ruta)
                    if info:
                        # 1. Actualizar tabla Proyectos
                        cursor.execute("UPDATE proyectos SET fecha_mod = ?, blender_version = ? WHERE id = ?", 
                                    (fecha_disco, info.get('version_blender', version_db), id_pro))
                    
                        # 2. UPSERT Metadatos: Ajustado a la estructura de 9 campos
                        # Campos: id_proyecto, escena, viewlayer, camara, f_inicio, f_final, fps, res_x, res_y
                        cursor.execute("""INSERT OR REPLACE INTO metadatos 
                                        (id_proyecto, escena, viewlayer, camara, f_inicio, f_final, fps, res_x, res_y)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                                        (id_pro, 
                                        info.get('active_scene', 'Scene'), 
                                        info.get('view_layer', 'N/A'),     # Nuevo campo
                                        info.get('active_camera', 'Camera'), 
                                        info.get('frame_start', 1),        # f_inicio
                                        info.get('frame_end', 250),        # f_final
                                        info.get('frame_rate', 24),
                                        info.get('resolution_x', 1920), 
                                        info.get('resolution_y', 1080)))
                    
                        # 3. Actualizar Renderizado (Cola de render)
                        # Sincronizamos f_start y f_end con los nuevos valores del archivo .blend
                        cursor.execute("""UPDATE renderizado SET f_start = ?, f_end = ? WHERE id_proyecto = ?""",
                                        (info.get('frame_start', 1), info.get('frame_end', 250), id_pro))
                    
                        actualizados += 1
                except Exception as e:
                    self._log(f"⚠️ Error en {os.path.basename(ruta)}: {e}")

        conn.commit()
        conn.close()
    
        # Refrescar vistas
        self.actualizar_vistas_tablas()
        if self.parent() and hasattr(self.parent(), 'contenido'):
            self.parent().contenido.cargar_datos_desde_db()
        
        self._log(f"✅ Sincronización finalizada. {actualizados} proyectos actualizados.")
        QMessageBox.information(self, "Éxito", f"Se han sincronizado {actualizados} proyectos.")


    def actualizar_vistas_tablas(self):
        conn = self._get_connection()
        cur = conn.cursor()
        
        # TABLA EJECUTABLES
        self.tabla_exe.setRowCount(0)
        for r_idx, r_data in enumerate(cur.execute("SELECT id, ruta, version, tipo_instalacion FROM ejecutables").fetchall()):
            self.tabla_exe.insertRow(r_idx)
            for c_idx, val in enumerate(r_data):
                item = QTableWidgetItem(str(val))
                if c_idx == 3:
                    if val == "VINCULADO": item.setBackground(QColor("#27ae60")); item.setForeground(QColor("white"))
                    elif val == "PORTABLE": item.setBackground(QColor("#f1c40f")); item.setForeground(QColor("black"))
                self.tabla_exe.setItem(r_idx, c_idx, item)

        # TABLA PROYECTOS
        self.tabla_blend.setRowCount(0)
        proyectos = cur.execute("SELECT id, carpeta, blender_version, fecha_mod FROM proyectos").fetchall()
        for r_idx, r_data in enumerate(proyectos):
            id_pro, ruta, version, fecha_db = r_data
            self.tabla_blend.insertRow(r_idx)
            necesita_sync = False
            existe = os.path.exists(ruta)
            if existe:
                mtime = os.path.getmtime(ruta)
                fecha_disco = datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')
                if fecha_disco != str(fecha_db)[:16]: necesita_sync = True

            for c_idx, val in enumerate(r_data):
                texto = str(val)
                if c_idx == 3:
                    if not existe: texto = "🚫 NO ENCONTRADO"
                    elif necesita_sync: texto = f"⚠️ {texto} (Pendiente)"
                item = QTableWidgetItem(texto)
                if not existe: item.setBackground(QColor("#c0392b")); item.setForeground(QColor("white"))
                elif necesita_sync: item.setBackground(QColor("#2c3e50")); item.setForeground(QColor("#f39c12"))
                self.tabla_blend.setItem(r_idx, c_idx, item)
        conn.close()

    # --- MEJORA 3: GUARDADO DE EJECUTABLE CON REGEX ESTRICTO ---
    def guardar_ejecutable(self):
        ruta = self.ent_exe.text().strip().replace("\\", "/")
        if not os.path.exists(ruta): 
            QMessageBox.warning(self, "Error", "La ruta del ejecutable no es válida.")
            return

        tipo = "VINCULADO" if any(p in ruta.lower() for p in ["program files", "/usr/bin", "/opt"]) else "PORTABLE"
        
        try:
            res = subprocess.run([ruta, "-v"], capture_output=True, text=True, timeout=5)
            lineas = res.stdout.splitlines()
            if not lineas: raise Exception("Blender no respondió.")
            
            # Extraemos la versión (ej: 4.5.8 o 5.1.0)
            match = re.search(r"(\d+\.\d+\.\d+)", lineas[0])
            version_limpia = match.group(1) if match else "Desconocida"
            
            # Formateo idéntico al ADN para evitar cruces
            version_final = f"Blender {version_limpia} LTS" if version_limpia.startswith("4.5") else f"Blender {version_limpia}"

            conn = self._get_connection()
            conn.execute("INSERT OR REPLACE INTO ejecutables (ruta, version, tipo_instalacion) VALUES (?, ?, ?)", 
                        (ruta, version_final, tipo))
            conn.commit()
            conn.close()
            
            self._log(f"✅ Motor guardado: {version_final}")
            self.actualizar_vistas_tablas()
            
        except Exception as e: 
            QMessageBox.critical(self, "Error", f"No se pudo validar: {e}")

    # ... [Resto de funciones _setup_tab y eliminar_registro se mantienen igual] ...

    def abrir_con_blender(self, item):
        if item.column() != 1: return
        ruta_blend = item.text()
        if not os.path.exists(ruta_blend): return

        fila = item.row()
        version_proyecto = self.tabla_blend.item(fila, 2).text()
        match = re.search(r"(\d+\.\d+\.\d+)", version_proyecto)
        v_search = match.group(1) if match else ""

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ruta FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",))
        res = cursor.fetchone() or cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
        conn.close()

        if res:
            try:
                self._log(f"🚀 Abriendo: {os.path.basename(ruta_blend)}")
                subprocess.Popen([res[0], ruta_blend])
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _setup_tab_exe(self, layout):
        form = QFormLayout()
        self.ent_exe = QLineEdit()
        btn_buscar = QPushButton("Examinar...")
        btn_buscar.clicked.connect(lambda: self._abrir_explorador(self.ent_exe, "*.exe"))
        h_layout = QHBoxLayout(); h_layout.addWidget(self.ent_exe); h_layout.addWidget(btn_buscar)
        form.addRow("Ruta de Blender:", h_layout); layout.addLayout(form)
        btns = QHBoxLayout()
        btn_s = QPushButton("💾 Guardar Versión"); btn_s.setFixedHeight(35); btn_s.setStyleSheet("background-color: #286c19; color: white;")
        btn_s.clicked.connect(self.guardar_ejecutable)
        btn_d = QPushButton("🗑️ Eliminar"); btn_d.setFixedHeight(35); btn_d.setStyleSheet("background-color: #a93226; color: white;")
        btn_d.clicked.connect(lambda: self.eliminar_registro(self.tabla_exe, "ejecutables"))
        btns.addWidget(btn_s); btns.addWidget(btn_d); layout.addLayout(btns)
        self.tabla_exe = QTableWidget(); self.tabla_exe.setColumnCount(4)
        self.tabla_exe.setHorizontalHeaderLabels(["ID", "Ruta", "Versión Exacta", "Tipo"])
        self.tabla_exe.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.tabla_exe)

    def _setup_tab_blend(self, layout):
        btns = QHBoxLayout()
        btn_a = QPushButton("➕ Registrar Archivo .blend"); btn_a.setFixedHeight(40); btn_a.setStyleSheet("background-color: #2874a6; color: white;")
        btn_a.clicked.connect(self.seleccionar_y_guardar_automatico)
        btn_y = QPushButton("🔄 Sincronizar Proyectos"); btn_y.setFixedHeight(40); btn_y.setStyleSheet("background-color: #d68910; color: white;")
        btn_y.clicked.connect(self.sincronizar_todos_los_proyectos)
        btns.addWidget(btn_a); btns.addWidget(btn_y); layout.addLayout(btns)
        self.tabla_blend = QTableWidget(); self.tabla_blend.setColumnCount(4)
        self.tabla_blend.setHorizontalHeaderLabels(["ID", "Ruta del .blend", "Versión Sincronizada", "Modificación"])
        self.tabla_blend.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_blend.itemDoubleClicked.connect(self.abrir_con_blender)
        layout.addWidget(self.tabla_blend)
        btn_del = QPushButton("🗑️ Eliminar Proyecto"); btn_del.clicked.connect(lambda: self.eliminar_registro(self.tabla_blend, "proyectos"))
        layout.addWidget(btn_del)

    def _abrir_explorador(self, line_edit, ext):
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar", self.ultima_ruta_explorada, f"Archivos ({ext})")
        if ruta: 
            line_edit.setText(ruta)
            self.ultima_ruta_explorada = os.path.dirname(ruta)

    def eliminar_registro(self, tabla, db_table):
        fila = tabla.currentRow()
        if fila == -1: return
        id_reg = tabla.item(fila, 0).text()
        conn = self._get_connection()
        conn.execute(f"DELETE FROM {db_table} WHERE id = ?", (id_reg,))
        conn.commit(); conn.close()
        self.actualizar_vistas_tablas()
        if self.parent() and hasattr(self.parent(), 'contenido'): 
            self.parent().contenido.cargar_datos_desde_db()