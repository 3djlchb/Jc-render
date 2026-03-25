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
        
        # --- CORRECCIÓN DE RUTA PARA .EXE COMPILADO ---
        if getattr(sys, 'frozen', False):
            # Ruta cuando es un ejecutable (.exe)
            base_dir = os.path.dirname(sys.executable)
        else:
            # Ruta cuando es un script de Python (.py)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.db_path = os.path.join(base_dir, 'bbdd', 'config.db')
        
        # Asegurar que la carpeta 'bbdd' existe antes de inicializar la BD
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._inicializar_bd()

        # PERSISTENCIA: Recordar la última carpeta explorada
        self.ultima_ruta_explorada = ""

        layout_principal = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # --- PESTAÑAS ---
        self.tab_exe = QWidget()
        self._setup_tab_exe(QVBoxLayout(self.tab_exe))
        self.tab_blend = QWidget()
        self._setup_tab_blend(QVBoxLayout(self.tab_blend))

        self.tabs.addTab(self.tab_exe, "🚀 1. Versiones Blender")
        self.tabs.addTab(self.tab_blend, "📦 2. Archivos .blend")
        
        layout_principal.addWidget(self.tabs)

        # --- CONSOLA DE DEPURACIÓN ---
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

    def _inicializar_bd(self):
        if not os.path.exists('bbdd'): os.makedirs('bbdd')
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS ejecutables (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            ruta TEXT UNIQUE, 
            version TEXT,
            tipo_instalacion TEXT DEFAULT 'DESCONOCIDO')""")

        cursor.execute("CREATE TABLE IF NOT EXISTS proyectos (id INTEGER PRIMARY KEY AUTOINCREMENT, carpeta TEXT UNIQUE, blender_version TEXT, fecha_mod TEXT)")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS metadatos (
            id_proyecto INTEGER, escena TEXT, camara TEXT, 
            res_x INTEGER, res_y INTEGER, fps INTEGER,
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS renderizado (
            id_proyecto INTEGER, motor TEXT, dispositivo TEXT, 
            formato TEXT, f_start INTEGER, f_end INTEGER, ruta_output TEXT,
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
        conn.commit()
        conn.close()

    def extraer_version_desde_blend(self, ruta_blend):
        self._log(f"🕵️ Analizando ADN profundo: {os.path.basename(ruta_blend)}")
        try:
            with open(ruta_blend, 'rb') as f:
                data_head = f.read(12)
                if data_head.startswith(b'BLENDER-'):
                    v_raw = data_head[9:12].decode('utf-8', errors='ignore')
                    versiones = {"501": "Blender 5.0.1", "510": "Blender 5.1.0", "405": "Blender 4.5.8 LTS"}
                    return versiones.get(v_raw, f"Blender {v_raw[0]}.{v_raw[1]}.{v_raw[2]}")

                f.seek(0)
                data_large = f.read(8192)
                patterns = {b'5.0.1': "Blender 5.0.1", b'5.1.0': "Blender 5.1.0", b'4.5.8': "Blender 4.5.8 LTS"}
                for p, n in patterns.items():
                    if p in data_large: return n
        except Exception as e:
            self._log(f"⚠️ Error ADN Profundo: {e}")
        return "Desconocida"

    def seleccionar_y_guardar_automatico(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Registrar .blend", self.ultima_ruta_explorada, "Archivos (*.blend)")
        if not ruta: return
        self.ultima_ruta_explorada = os.path.dirname(ruta)

        version_dna = self.extraer_version_desde_blend(ruta)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        match_version = re.search(r"(\d+\.\d+\.\d+)", version_dna)
        v_search = match_version.group(1) if match_version else "NONEXISTENT"

        cursor.execute("SELECT ruta, version FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",))
        res_exe = cursor.fetchone()

        if not res_exe:
            cursor.execute("SELECT ruta, version FROM ejecutables ORDER BY version DESC LIMIT 1")
            res_exe = cursor.fetchone()
            if res_exe:
                msg = f"ADN dice {version_dna}. No encontré un motor exacto. ¿Vincular a {res_exe[1]}?"
                if QMessageBox.question(self, "Confirmar Vinculación", msg) == QMessageBox.No:
                    conn.close(); return
            else:
                QMessageBox.critical(self, "Error", "No hay motores registrados."); conn.close(); return

        exe_path, version_motor_db = res_exe

        try:
            info_real = self.parent().contenido.obtener_metadata_pro(exe_path, ruta)
            if not info_real: raise Exception("El motor no devolvió metadatos.")

            version_final = info_real.get('blender_version', version_motor_db)
            fecha_mod = datetime.datetime.fromtimestamp(os.path.getmtime(ruta)).strftime('%d/%m/%Y %H:%M')
            
            cursor.execute("INSERT INTO proyectos (carpeta, blender_version, fecha_mod) VALUES (?, ?, ?)", 
                         (ruta, version_final, fecha_mod))
            id_pro = cursor.lastrowid

            cursor.execute("INSERT INTO metadatos (id_proyecto, escena, camara, res_x, res_y, fps) VALUES (?, ?, ?, ?, ?, ?)",
                          (id_pro, info_real.get('active_scene', 'Scene'), info_real.get('active_camera', 'Camera'),
                           info_real.get('resolution_x', 1920), info_real.get('resolution_y', 1080), info_real.get('frame_rate', 24)))

            cursor.execute("INSERT INTO renderizado (id_proyecto, motor, dispositivo, formato, f_start, f_end, ruta_output) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (id_pro, 'CYCLES', 'OPTIX', 'PNG', info_real.get('frame_start', 1), info_real.get('frame_end', 250), ""))

            conn.commit()
            self._log(f"✅ Registrado: {os.path.basename(ruta)}")
        except sqlite3.IntegrityError:
             QMessageBox.information(self, "Aviso", "El archivo ya existe en el gestor.")
        except Exception as e:
            self._log(f"❌ Error al registrar: {e}")
        finally:
            conn.close()
            self.actualizar_vistas_tablas()
            if self.parent() and hasattr(self.parent(), 'contenido'):
                self.parent().contenido.cargar_datos_desde_db()

    def sincronizar_todos_los_proyectos(self):
        self._log("🔄 Iniciando sincronización global...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        proyectos = cursor.execute("SELECT id, carpeta, fecha_mod, blender_version FROM proyectos").fetchall()
        
        actualizados = 0
        for id_pro, ruta, fecha_en_db, version_en_db in proyectos:
            if not os.path.exists(ruta): continue

            mtime = os.path.getmtime(ruta)
            fecha_disco = datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')
            
            if fecha_disco != str(fecha_en_db)[:16]:
                self._log(f"🔨 Sincronizando: {os.path.basename(ruta)}")
                version_dna = self.extraer_version_desde_blend(ruta)
                v_num = re.search(r"(\d+\.\d+\.\d+)", version_dna)
                v_search = v_num.group(1) if v_num else "5.0.1"
                
                cursor.execute("SELECT ruta FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",))
                res_exe = cursor.fetchone() or cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()

                if res_exe:
                    try:
                        info = self.parent().contenido.obtener_metadata_pro(res_exe[0], ruta)
                        if info and isinstance(info, dict):
                            v_final = info.get('blender_version', version_en_db)
                            cursor.execute("UPDATE proyectos SET fecha_mod = ?, blender_version = ? WHERE id = ?", (fecha_disco, v_final, id_pro))
                            cursor.execute("UPDATE metadatos SET escena=?, camara=?, res_x=?, res_y=?, fps=? WHERE id_proyecto=?",
                                (info.get('active_scene', 'Scene'), info.get('active_camera', 'Camera'), 
                                 info.get('resolution_x', 1920), info.get('resolution_y', 1080), info.get('frame_rate', 24), id_pro))
                            cursor.execute("UPDATE renderizado SET f_start=?, f_end=? WHERE id_proyecto=?", (info.get('frame_start', 1), info.get('frame_end', 250), id_pro))
                            actualizados += 1
                    except Exception as e: self._log(f"❌ Error en {os.path.basename(ruta)}: {e}")

        conn.commit()
        conn.close()
        self.actualizar_vistas_tablas()
        if self.parent() and hasattr(self.parent(), 'contenido'):
            self.parent().contenido.cargar_datos_desde_db()
        QMessageBox.information(self, "Sincronización", f"Sincronización finalizada.\nActualizados: {actualizados}")

    def actualizar_vistas_tablas(self):
        conn = sqlite3.connect(self.db_path)
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

    def guardar_ejecutable(self):
        ruta = self.ent_exe.text()
        if not os.path.exists(ruta): return
        tipo = "VINCULADO" if "Program Files" in ruta else "PORTABLE"
        try:
            res = subprocess.run([ruta, "-v"], capture_output=True, text=True, timeout=5)
            version_line = res.stdout.splitlines()[0]
            conn = sqlite3.connect(self.db_path)
            conn.execute("INSERT INTO ejecutables (ruta, version, tipo_instalacion) VALUES (?, ?, ?)", (ruta, version_line, tipo))
            conn.commit(); conn.close()
            self._log(f"✅ Motor guardado: {version_line}")
            self.actualizar_vistas_tablas()
        except Exception as e: QMessageBox.critical(self, "Error", f"Error de motor: {e}")


    def abrir_con_blender(self, item):
        # Solo actuar si es la columna de la ruta (Índice 1)
        if item.column() != 1:
            return

        ruta_blend = item.text()
        if not os.path.exists(ruta_blend):
            QMessageBox.warning(self, "Error", "El archivo .blend no existe en esa ruta.")
            return

        # Obtener la fila actual para saber la versión
        fila = item.row()
        version_proyecto = self.tabla_blend.item(fila, 2).text() # Columna de Versión

        # Extraer el número de versión (ej: "3.6.0") para buscar el motor
        match = re.search(r"(\d+\.\d+\.\d+)", version_proyecto)
        v_search = match.group(1) if match else ""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Buscar el ejecutable que coincida con la versión
        cursor.execute("SELECT ruta FROM ejecutables WHERE version LIKE ?", (f"%{v_search}%",))
        res = cursor.fetchone()
        
        # Si no hay coincidencia exacta, buscar el más reciente
        if not res:
            cursor.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1")
            res = cursor.fetchone()
        
        conn.close()

        if res:
            exe_path = res[0]
            try:
                self._log(f"🚀 Abriendo: {os.path.basename(ruta_blend)} con Blender {v_search}")
                # Popen permite abrir Blender sin bloquear la interfaz de tu programa
                subprocess.Popen([exe_path, ruta_blend])
            except Exception as e:
                QMessageBox.critical(self, "Error de Apertura", f"No se pudo iniciar Blender: {e}")
        else:
            QMessageBox.warning(self, "Configuración Faltante", "No hay motores de Blender registrados para abrir este archivo.")


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
        # --- NUEVA LÍNEA AQUÍ ---
        self.tabla_blend.itemDoubleClicked.connect(self.abrir_con_blender)
        # ------------------------
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
        conn = sqlite3.connect(self.db_path)
        conn.execute(f"DELETE FROM {db_table} WHERE id = ?", (id_reg,))
        conn.commit(); conn.close()
        self.actualizar_vistas_tablas()
        if self.parent() and hasattr(self.parent(), 'contenido'): self.parent().contenido.cargar_datos_desde_db()