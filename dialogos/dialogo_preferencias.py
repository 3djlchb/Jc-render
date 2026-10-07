import sqlite3
import os
import datetime
import subprocess
import re
import sys
import zstandard as zstd

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, QMenu, 
                               QLineEdit, QPushButton, QFormLayout, QHBoxLayout, 
                               QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem, 
                               QHeaderView, QLabel, QTextEdit)
from PySide6.QtCore import Qt
from app_paths import get_database_path
from PySide6.QtGui import (QColor, QAction)

class PreferenciasDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestor Inteligente de Blender - Configuración Pro")
        self.resize(1200, 850)
        
        self.db_path = get_database_path()
        
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
        cursor.execute("""CREATE TABLE IF NOT EXISTS ejecutables (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            ruta TEXT UNIQUE, 
            version TEXT,
            tipo_instalacion TEXT DEFAULT 'DESCONOCIDO')""")

        cursor.execute("""CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            carpeta TEXT UNIQUE, 
            blender_version TEXT, 
            fecha_mod TEXT)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS metadatos (
            id_proyecto INTEGER PRIMARY KEY, 
            escena TEXT, viewlayer TEXT, camara TEXT,
            f_inicio INTEGER, f_final INTEGER, fps INTEGER, 
            res_x INTEGER, res_y INTEGER, 
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS renderizado (
            id_proyecto INTEGER PRIMARY KEY, 
            motor TEXT, dispositivo TEXT, formato TEXT, 
            f_start INTEGER, f_end INTEGER, ruta_output TEXT, nombre_out TEXT,
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
        
        conn.commit()
        conn.close()


    def extraer_version_desde_blend(self, ruta_blend):
        try:
            with open(ruta_blend, 'rb') as f:
                # Leemos el inicio para verificar si es Zstd o Plano
                encabezado_inicial = f.read(4)
                
                # Caso A: Archivo COMPRIMIDO (Zstandard)
                if encabezado_inicial == b'\x28\xb5\x2f\xfd':
                    f.seek(0)
                    dctx = zstd.ZstdDecompressor()
                    # Descomprimimos solo lo necesario para llegar al header de Blender
                    with dctx.stream_reader(f) as reader:
                        data = reader.read(12)
                else:
                    # Caso B: Archivo NO comprimido
                    f.seek(0)
                    data = f.read(12)

                # Ahora procesamos los bytes como siempre
                if data.startswith(b'BLENDER-'):
                    v_major = chr(data[9])
                    v_minor = chr(data[10])
                    v_patch = chr(data[11])
                    
                    if v_major == "4" and v_minor == "5":
                        return f"Blender 4.5.{v_patch} LTS"
                    return f"Blender {v_major}.{v_minor}.{v_patch}"

        except Exception as e:
            print(f"Error detectando ADN: {e}")
        
        return "Blender 4.5.8 LTS" # Fallback

    def seleccionar_y_guardar_automatico(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Registrar .blend", self.ultima_ruta_explorada, "Archivos (*.blend)")
        if not ruta: return
        
        ruta = os.path.abspath(ruta).replace("\\", "/")
        self.ultima_ruta_explorada = os.path.dirname(ruta)

        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if cursor.execute("SELECT id FROM proyectos WHERE carpeta = ?", (ruta,)).fetchone():
                QMessageBox.information(self, "Aviso", "El archivo ya está registrado.")
                return

            # Buscamos ejecutable basado en el ADN
            version_dna = self.extraer_version_desde_blend(ruta)
            # Extraer solo X.Y para búsqueda en DB
            match_v = re.search(r"(\d+\.\d+)", version_dna)
            v_search = match_v.group(1) if match_v else "4.5"
            
            res_exe = cursor.execute("SELECT ruta FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",)).fetchone()
            if not res_exe:
                res_exe = cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()

            if not res_exe:
                raise Exception("Registre un ejecutable de Blender en la pestaña 1.")

            # Extracción real mediante el script del padre
            info_real = self.parent().contenido.obtener_metadata_pro(res_exe[0], ruta)
            
            if not info_real:
                raise Exception(f"No se pudo analizar: {os.path.basename(ruta)}")

            fecha_mod = datetime.datetime.fromtimestamp(os.path.getmtime(ruta)).strftime('%d/%m/%Y %H:%M')
            v_final = info_real.get('version_blender', version_dna)

            cursor.execute("INSERT INTO proyectos (carpeta, blender_version, fecha_mod) VALUES (?, ?, ?)", 
                         (ruta, v_final, fecha_mod))
            id_pro = cursor.lastrowid

            cursor.execute("""INSERT INTO metadatos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (id_pro, info_real.get('active_scene', 'Scene'), info_real.get('view_layer', 'N/A'), 
                           info_real.get('active_camera', 'Camera'), info_real.get('frame_start', 1),
                           info_real.get('frame_end', 250), info_real.get('frame_rate', 24),
                           info_real.get('resolution_x', 1920), info_real.get('resolution_y', 1080)))

            cursor.execute("""INSERT INTO renderizado VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (id_pro, 'CYCLES', 'OPTIX', 'PNG', info_real.get('frame_start', 1), 
                           info_real.get('frame_end', 250), "render", os.path.splitext(os.path.basename(ruta))[0]))

            conn.commit()
            self._log(f"✅ Registrado: {os.path.basename(ruta)} ({v_final})")
            
        except Exception as e:
            if conn: conn.rollback()
            self._log(f"❌ Error: {e}")
            QMessageBox.critical(self, "Error", str(e))
        finally:
            conn.close()
            self.actualizar_vistas_tablas()
            if self.parent(): self.parent().contenido.cargar_datos_desde_db()

    def sincronizar_todos_los_proyectos(self):
        self._log("🔄 Iniciando sincronización...")
        conn = self._get_connection()
        cursor = conn.cursor()
        proyectos = cursor.execute("SELECT id, carpeta FROM proyectos").fetchall()
    
        actualizados = 0
        for id_pro, ruta in proyectos:
            if not os.path.exists(ruta): continue

            # Usar el mejor ejecutable para este archivo
            version_dna = self.extraer_version_desde_blend(ruta)
            match_v = re.search(r"(\d+\.\d+)", version_dna)
            v_search = match_v.group(1) if match_v else "4.5"
            
            res_exe = cursor.execute("SELECT ruta FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",)).fetchone()
            if not res_exe: 
                res_exe = cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
        
            if res_exe:
                try:
                    info = self.parent().contenido.obtener_metadata_pro(res_exe[0], ruta)
                    if info:
                        fecha_disco = datetime.datetime.fromtimestamp(os.path.getmtime(ruta)).strftime('%d/%m/%Y %H:%M')
                        
                        cursor.execute("UPDATE proyectos SET fecha_mod = ?, blender_version = ? WHERE id = ?", 
                                    (fecha_disco, info.get('version_blender'), id_pro))
                    
                        cursor.execute("""INSERT OR REPLACE INTO metadatos 
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                                        (id_pro, info.get('active_scene'), info.get('view_layer'), 
                                         info.get('active_camera'), info.get('frame_start'), info.get('frame_end'),
                                         info.get('frame_rate'), info.get('resolution_x'), info.get('resolution_y')))
                    
                        actualizados += 1
                except Exception as e:
                    self._log(f"⚠️ Fallo en {os.path.basename(ruta)}: {e}")

        conn.commit()
        conn.close()
        self.actualizar_vistas_tablas()
        if self.parent(): self.parent().contenido.cargar_datos_desde_db()
        self._log(f"✅ Sincronizados {actualizados} proyectos.")

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
                    item.setBackground(QColor("#27ae60") if val == "VINCULADO" else QColor("#f1c40f"))
                    item.setForeground(QColor("white" if val == "VINCULADO" else "black"))
                self.tabla_exe.setItem(r_idx, c_idx, item)

        # TABLA PROYECTOS
        self.tabla_blend.setRowCount(0)
        proyectos = cur.execute("SELECT id, carpeta, blender_version, fecha_mod FROM proyectos").fetchall()
        for r_idx, r_data in enumerate(proyectos):
            id_pro, ruta, version, fecha_db = r_data
            self.tabla_blend.insertRow(r_idx)
            
            existe = os.path.exists(ruta)
            necesita_sync = False
            if existe:
                f_disco = datetime.datetime.fromtimestamp(os.path.getmtime(ruta)).strftime('%d/%m/%Y %H:%M')
                if f_disco != fecha_db: necesita_sync = True

            for c_idx, val in enumerate(r_data):
                texto = str(val)
                if c_idx == 3 and not existe: texto = "🚫 NO ENCONTRADO"
                item = QTableWidgetItem(texto)
                
                if not existe: 
                    item.setBackground(QColor("#c0392b")); item.setForeground(QColor("white"))
                elif necesita_sync and c_idx == 3:
                    item.setBackground(QColor("#d35400")); item.setForeground(QColor("white"))
                
                self.tabla_blend.setItem(r_idx, c_idx, item)
        conn.close()

    def guardar_ejecutable(self):
        ruta = self.ent_exe.text().strip().replace("\\", "/")
        if not os.path.exists(ruta): return

        tipo = "VINCULADO" if any(p in ruta.lower() for p in ["program files", "/usr/bin", "/opt"]) else "PORTABLE"
        
        try:
            # En Windows, Blender -v es rápido y seguro
            res = subprocess.run([ruta, "-v"], capture_output=True, text=True, timeout=5, creationflags=0x08000000)
            match = re.search(r"Blender (\d+\.\d+\.\d+)", res.stdout)
            version_limpia = match.group(1) if match else "Desconocida"
            version_final = f"Blender {version_limpia} LTS" if version_limpia.startswith("4.5") else f"Blender {version_limpia}"

            conn = self._get_connection()
            conn.execute("INSERT OR REPLACE INTO ejecutables (ruta, version, tipo_instalacion) VALUES (?, ?, ?)", 
                        (ruta, version_final, tipo))
            conn.commit()
            conn.close()
            
            self._log(f"✅ Motor guardado: {version_final}")
            self.actualizar_vistas_tablas()
        except Exception as e: 
            QMessageBox.critical(self, "Error", f"Fallo al validar motor: {e}")

    def eliminar_registro(self, tabla, db_table):
        fila = tabla.currentRow()
        if fila == -1: return
        id_reg = tabla.item(fila, 0).text()
        conn = self._get_connection()
        conn.execute(f"DELETE FROM {db_table} WHERE id = ?", (id_reg,))
        conn.commit(); conn.close()
        self.actualizar_vistas_tablas()
        if self.parent(): self.parent().contenido.cargar_datos_desde_db()

    def abrir_con_blender(self, item):
        if item.column() != 1: return
        ruta_blend = item.text()
        fila = item.row()
        version_proyecto = self.tabla_blend.item(fila, 2).text()
        
        conn = self._get_connection()
        # Buscamos el ejecutable que coincida con la versión del proyecto
        res = conn.execute("SELECT ruta FROM ejecutables WHERE version = ?", (version_proyecto,)).fetchone()
        if not res:
            res = conn.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
        conn.close()

        if res and os.path.exists(ruta_blend):
            subprocess.Popen([res[0], ruta_blend])

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
        self.tabla_exe.setColumnWidth(0, 20)
        self.tabla_exe.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_exe.setColumnWidth(2, 120)
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
        self.tabla_blend.setColumnWidth(0, 20)
        self.tabla_blend.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_blend.setColumnWidth(2, 120)

        self.tabla_blend.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla_blend.customContextMenuRequested.connect(self.menu_contextual_tabla_blend)
        self.tabla_blend.itemDoubleClicked.connect(self.abrir_con_blender)
        layout.addWidget(self.tabla_blend)
        
        btn_del = QPushButton("🗑️ Eliminar Proyecto"); btn_del.clicked.connect(lambda: self.eliminar_registro(self.tabla_blend, "proyectos"))
        layout.addWidget(btn_del)

    def _abrir_explorador(self, line_edit, ext):
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar", self.ultima_ruta_explorada, f"Archivos ({ext})")
        if ruta: 
            line_edit.setText(ruta)
            self.ultima_ruta_explorada = os.path.dirname(ruta)


    def menu_contextual_tabla_blend(self, pos):
        tabla_activa = self.sender()
        item = tabla_activa.itemAt(pos)
        if not item: return
        menu = QMenu()

        '''
        accion_abrir = QAction("🚀 Abrir en Blender", self)
        accion_abrir.triggered.connect(lambda: self.abrir_con_blender(item))
        menu.addAction(accion_abrir)

        menu.addSeparator()
        '''

        accion_eliminar = QAction("❌ Eliminar proyecto", self)
        accion_eliminar.triggered.connect(lambda: self.eliminar_registro(self.tabla_blend, "proyectos"))
        menu.addAction(accion_eliminar)
        menu.exec(self.tabla_blend.mapToGlobal(pos))


    def eliminar_registro(self, tabla, db_table):
        """
        Elimina un registro de la base de datos y refresca todas las vistas.
        Soporta eliminación de ejecutables y proyectos.
        """
        fila = tabla.currentRow()
        if fila == -1:
            QMessageBox.warning(self, "Aviso", "Por favor, selecciona una fila para eliminar.")
            return

        # Obtenemos el ID y el nombre (para el mensaje de confirmación)
        id_reg = tabla.item(fila, 0).text()
        nombre_reg = tabla.item(fila, 1).text()
        archivo = os.path.basename(nombre_reg)

        # Preguntar antes de borrar (Mejora de UX)
        confirmar = QMessageBox.question(
            self, 
            "Confirmar eliminación", 
            f"¿Estás seguro de que deseas eliminar '{archivo}' de la base de datos?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirmar == QMessageBox.Yes:
            try:
                conn = self._get_connection()
                # El DELETE CASCADE se encargará de borrar metadatos y renderizado 
                # automáticamente si la tabla está bien configurada con Foreign Keys.
                conn.execute(f"DELETE FROM {db_table} WHERE id = ?", (id_reg,))
                conn.commit()
                conn.close()

                self._log(f"🗑️ Eliminado de {db_table}: {archivo}")
                
                # Refrescar la tabla local del diálogo
                self.actualizar_vistas_tablas()
                
                # Refrescar la interfaz principal (si existe el enlace)
                if self.parent() and hasattr(self.parent(), 'contenido'): 
                    self.parent().contenido.cargar_datos_desde_db()
                    
            except Exception as e:
                self._log(f"❌ Error al eliminar: {e}")
                QMessageBox.critical(self, "Error", f"No se pudo eliminar el registro: {e}")