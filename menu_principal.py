import os
import re 
import sqlite3
import json
import subprocess
import datetime
import sys 

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                               QTextEdit, QCheckBox, QGroupBox, QComboBox, QMessageBox,
                               QPushButton, QHBoxLayout, QProgressBar, QApplication, QMenu,
                               QLabel, QSplitter, QSizePolicy)
from PySide6.QtCore import Qt, QProcess, QTimer, Slot
from PySide6.QtGui import (QColor, QAction, QPixmap, QImageReader)


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
        cursor.execute("PRAGMA foreign_keys = ON") # Habilitar borrado en cascada
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, carpeta TEXT UNIQUE, 
            blender_version TEXT, fecha_mod TEXT)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS metadatos (
            id_proyecto INTEGER, escena TEXT, camara TEXT, res_x INTEGER, res_y INTEGER, fps INTEGER,
            FOREIGN KEY(id_proyecto) REFERENCES proyectos(id) ON DELETE CASCADE)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS renderizado (
            id_proyecto INTEGER, motor TEXT, dispositivo TEXT, formato TEXT, 
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
        self.tabla_metadatos = QTableWidget(0, 10)
        self.tabla_metadatos.setHorizontalHeaderLabels([
            "Nombre", "Versión", "Escena", "Cámara", "Inicio", "Fin", "FPS", "Res X", "Res Y", "Ruta"
        ])
        
        self.tabla_metadatos.itemDoubleClicked.connect(self.abrir_con_blender_desde_tabla) # <--- AÑADIR ESTO

        # --- Para Tabla Metadatos ---
        self.tabla_metadatos.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla_metadatos.customContextMenuRequested.connect(self.mostrar_menu_contextual)
        self.tabla_metadatos.itemDoubleClicked.connect(self.abrir_con_blender_desde_tabla)

        anchos_meta = [200, 100, 100, 180, 55, 55, 55, 55, 55, 300]
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

    def obtener_metadata_pro(self, exe, ruta):
        # DETECCIÓN DE RUTA PARA COMPILADO
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(__file__)

        script_extractor = os.path.join(base_dir, "info_archivo_blend.py")
        
        if not os.path.exists(script_extractor):
            self.consola.append(f"❌ Error: No se encuentra '{script_extractor}'")
            return None

        try:
            # Ejecutamos Blender en modo background (-b) con el script (-P)
            resultado = subprocess.run(
                [exe, "-b", ruta, "-P", script_extractor],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW # Evita que parpadee una consola CMD
            )

            # Buscamos la línea que contiene el JSON en la salida de Blender
            for linea in resultado.stdout.splitlines():
                if linea.strip().startswith('{') and linea.strip().endswith('}'):
                    return json.loads(linea)
            
            return None
        except Exception as e:
            self.consola.append(f"⚠️ Fallo en análisis de ADN: {e}")
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
        conn = sqlite3.connect(self.db_path)
        query = """SELECT p.carpeta, p.blender_version, m.escena, m.camara, m.res_x, m.res_y, m.fps,
                          r.motor, r.dispositivo, r.formato, r.f_start, r.f_end, r.ruta_output,
                          p.id, p.fecha_mod, r.nombre_out FROM proyectos p
                   JOIN metadatos m ON p.id = m.id_proyecto JOIN renderizado r ON p.id = r.id_proyecto"""
        filas = conn.execute(query).fetchall()
        conn.close()

        self.tabla_metadatos.setRowCount(0)
        self.tabla_renderizar.setRowCount(0)
        for f in filas:
            existe = os.path.exists(f[0])
            n_sync = False
            if existe:
                mt = os.path.getmtime(f[0])
                fd = datetime.datetime.fromtimestamp(mt).strftime('%d/%m/%Y %H:%M')
                if fd != str(f[14])[:16]: n_sync = True
            self._insertar_filas(f, n_sync, existe)

    def _insertar_filas(self, f, n_sync, existe):
        row = self.tabla_metadatos.rowCount()
        self.tabla_metadatos.insertRow(row)
        self.tabla_renderizar.insertRow(row)
        
        # Metadatos
        datos_m = [os.path.basename(f[0]), f[1], f[2], f[3], f[10], f[11], f[6], f[4], f[5], f[0]]
        for i, v in enumerate(datos_m):
            item = QTableWidgetItem(str(v))
            item.setTextAlignment(Qt.AlignCenter)
            self._aplicar_estilo_alerta(item, n_sync, existe, es_nombre=(i==0))
            self.tabla_metadatos.setItem(row, i, item)

        # Render
        chk = QCheckBox(); chk.setChecked(True)
        self.tabla_renderizar.setCellWidget(row, 0, chk)
        cols_r = {1: os.path.basename(f[0]), 2: f[1], 5: f[12], 6: f[15] or os.path.splitext(os.path.basename(f[0]))[0], 8: str(f[10]), 9: str(f[11]), 10: "LISTO"}
        for c, t in cols_r.items():
            item = QTableWidgetItem(str(t))
            item.setTextAlignment(Qt.AlignCenter)
            self._aplicar_estilo_alerta(item, n_sync, existe, es_nombre=(c==1))
            self.tabla_renderizar.setItem(row, c, item)
            
        # Busca esta línea en tu función _insertar_filas:
        for col, opts, cur in [(3, ["EEVEE", "CYCLES"], f[7]), 
                                (4, ["CPU", "CUDA", "OPTIX", "HIP"], f[8]), # <-- Añadimos HIP aquí
                                (7, ["PNG", "JPEG", "EXR", "AVI_JPEG"], f[9])]:
            cb = QComboBox()
            cb.addItems(opts)
    
            # Lógica para establecer el valor por defecto o el guardado en DB
            if col == 4: # Si es la columna de Dispositivo (índice 4)
                # Si en la DB no hay nada (None), ponemos CUDA por defecto
                texto_a_poner = cur if cur else "CUDA"
                cb.setCurrentText(texto_a_poner)
            else:
                cb.setCurrentText(str(cur))
        
            self.tabla_renderizar.setCellWidget(row, col, cb)

        # --- Dentro de _insertar_filas ---
        # Columna 10: Barra de Progreso
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setStyleSheet("QProgressBar { text-align: center; border-radius: 5px; background: #333; } "
                    "QProgressBar::chunk { background-color: #2980b9; }")
        self.tabla_renderizar.setCellWidget(row, 10, bar)

        # Columna 11: Botón Abortar
        btn_abort = QPushButton("🛑 Abort")
        btn_abort.setEnabled(False) # Solo se activa al renderizar
        btn_abort.setStyleSheet("background-color: #7f8c8d; color: white; border-radius: 3px;")
        btn_abort.clicked.connect(lambda r=row: self.abortar_render_especifico(r))
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


    def leer_errores_blender(self):
        self.consola.insertPlainText(f"⚠️ {self.proceso_render.readAllStandardError().data().decode('utf-8', errors='ignore')}")

    def preparar_cola_batch(self):
        self.cola_render = []
        for r in range(self.tabla_renderizar.rowCount()):
            if self.tabla_renderizar.cellWidget(r, 0).isChecked():
                self.cola_render.append({
                    "fila": r, "ruta": self.tabla_metadatos.item(r, 9).text(), "v": self.tabla_renderizar.item(r, 2).text(),
                    "m": self.tabla_renderizar.cellWidget(r, 3).currentText(), "d": self.tabla_renderizar.cellWidget(r, 4).currentText(),
                    "out": self.tabla_renderizar.item(r, 5).text(), "nom": self.tabla_renderizar.item(r, 6).text(),
                    "f": self.tabla_renderizar.cellWidget(r, 7).currentText(), "s": self.tabla_renderizar.item(r, 8).text(), "e": self.tabla_renderizar.item(r, 9).text()
                })
        if self.cola_render: self.procesar_siguiente_en_cola()

    def procesar_siguiente_en_cola(self):
        if not self.cola_render:
            self.consola.append("\n✅ BATCH FINALIZADO.")
            self.btn_batch.setEnabled(True)
            return
            
        t = self.cola_render.pop(0)
        self.proceso_actual_row = t["fila"]
        
        # 1. Obtener ejecutable
        conn = sqlite3.connect(self.db_path)
        v_limpia = t["v"].replace("Blender ", "")[:3]
        exe_row = conn.execute("SELECT ruta FROM ejecutables WHERE version LIKE ? ORDER BY version DESC", (f"%{v_limpia}%",)).fetchone()
        conn.close()

        if not exe_row:
            self.consola.append(f"❌ Error: No se encontró Blender para {t['v']}")
            self.procesar_siguiente_en_cola()
            return
        
        exe = exe_row[0]

        # 2. VALIDACIÓN DINÁMICA (NVIDIA / AMD / CPU)
        dispositivo_final = t["d"]
        if t["m"] == "CYCLES":
            sugerido = self.detectar_mejor_dispositivo(exe)
            # Si el usuario dejó algo incompatible o queremos optimizar
            if dispositivo_final not in ["OPTIX", "CUDA", "HIP"]:
                dispositivo_final = sugerido
            
            self.consola.append(f"🎯 Hardware detectado: {sugerido} | Usando: {dispositivo_final}")

        # 3. Configurar Salida
        carpeta_blend = os.path.dirname(t["ruta"])
        subcarpeta = t["out"].strip() if t["out"].strip() else "render"
        ruta_final_folder = os.path.join(carpeta_blend, subcarpeta)
        os.makedirs(ruta_final_folder, exist_ok=True)

        nombre_file = t["nom"].strip() if t["nom"].strip() else os.path.splitext(os.path.basename(t["ruta"]))[0]
        path_salida_completo = os.path.join(ruta_final_folder, f"{nombre_file}_###")

        # 4. SCRIPT PYTHON MULTI-PLATAFORMA
        # Este bloque configura Cycles tanto para NVIDIA (CUDA/OPTIX) como para AMD (HIP)
        # Script Python "Limpio" sin puntos y coma (evita SyntaxError)
        python_cmd = (
            "import bpy\n"
            "bpy.context.scene.render.engine = 'CYCLES'\n"
            "prefs = bpy.context.preferences.addons['cycles'].preferences\n"
            f"prefs.compute_device_type = '{dispositivo_final}'\n"
            "prefs.get_devices()\n"
            f"for d in prefs.devices: d.use = (d.type == '{dispositivo_final}')\n"
            f"bpy.context.scene.cycles.device = 'GPU' if '{dispositivo_final}' != 'CPU' else 'CPU'"
        )

        args = [
            "-b", t["ruta"],
            "--python-expr", python_cmd,
            "-o", path_salida_completo,
            "-F", t["f"],
            "-s", str(t["s"]),
            "-e", str(t["e"]),
            "-a"
        ]

        # 5. Lanzar proceso
        item_estado = self.tabla_renderizar.item(t["fila"], 10)
        item_estado.setText("RENDERING...")
        item_estado.setBackground(QColor("#d68910"))

        # --- Dentro de procesar_siguiente_en_cola, antes de self.proceso_render.start ---
        btn = self.tabla_renderizar.cellWidget(self.proceso_actual_row, 11)
        if btn:
            btn.setEnabled(True)
            btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        
        self.proceso_render.start(exe, args)

    def al_finalizar_render_actual(self, exit_code):
        # Obtener el widget de la barra de progreso de la fila actual
        bar = self.tabla_renderizar.cellWidget(self.proceso_actual_row, 10)
    
        if bar:
            # 1. Resetear el valor para limpiar el solapamiento visual
            bar.setValue(0) 
        
            # 2. Definir éxito basado en exit_code o existencia de archivo
            exito = (exit_code == 0)
        
            texto = "HECHO" if exito else "ERROR"
            color = "#27ae60" if exito else "#c0392b"
        
            # 3. Aplicar el nuevo estilo sin que se encime con el porcentaje
            bar.setFormat(texto)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid grey;
                    border-radius: 2px;
                    text-align: center;
                    background-color: #2c3e50;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                }}
            """)

        # Continuar con el siguiente render
        self.procesar_siguiente_en_cola()


    def sincronizar_todo_desde_principal(self):
        """Escanea el disco en busca de cambios y luego refresca las tablas"""
        self.consola.append("🔍 Iniciando sincronización de archivos en disco...")
        self.btn_sync.setEnabled(False) # Bloqueamos para evitar clics dobles
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. Obtener las rutas base que el usuario configuró en preferencias
            # Asumimos que guardas las rutas a buscar en una tabla 'config_rutas' o similar
            # Si no, podemos obtener las carpetas de los proyectos actuales para re-escanearlas
            proyectos_actuales = cursor.execute("SELECT carpeta FROM proyectos").fetchall()
            
            # 2. Lógica de re-escaneo (Verificar si los archivos existen y sus fechas)
            for (ruta,) in proyectos_actuales:
                if os.path.exists(ruta):
                    mtime = os.path.getmtime(ruta)
                    fecha_mod = datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')
                    
                    # Actualizamos la fecha de modificación en la DB si cambió
                    cursor.execute("UPDATE proyectos SET fecha_mod = ? WHERE carpeta = ?", (fecha_mod, ruta))
                else:
                    self.consola.append(f"⚠️ Archivo no encontrado: {os.path.basename(ruta)}")

            conn.commit()
            conn.close()
            
            # 3. Refrescar la interfaz
            self.cargar_datos_desde_db()
            self.consola.append("✅ Sincronización completada y vista actualizada.")
            
        except Exception as e:
            self.consola.append(f"❌ Error durante la sincronización: {e}")
        
        finally:
            self.btn_sync.setEnabled(True)


    def verificar_cambios_al_inicio(self):
        self.cargar_datos_desde_db()

    def abrir_con_blender_desde_tabla(self, item):
        # 1. Identificar en qué columna se hizo clic y en qué tabla
        tabla = item.tableWidget()
        columna = item.column()
        fila = item.row()
        
        # Solo permitimos el doble clic en la columna del Nombre (Col 0 en Meta, Col 1 en Render)
        # O en la columna de la Ruta completa (Col 9 en Meta)
        es_tabla_meta = (tabla == self.tabla_metadatos)
        
        if es_tabla_meta:
            if columna not in [0, 9]: return
            ruta_blend = self.tabla_metadatos.item(fila, 9).text()
            version_texto = self.tabla_metadatos.item(fila, 1).text()
        else: # Tabla Renderizado
            if columna != 1: return
            # En la tabla render no hay columna de ruta completa, la buscamos en la de metadatos (misma fila)
            ruta_blend = self.tabla_metadatos.item(fila, 9).text()
            version_texto = self.tabla_renderizar.item(fila, 2).text()

        if not os.path.exists(ruta_blend):
            QMessageBox.warning(self, "Error", "El archivo .blend ya no existe en esa ubicación.")
            return

        # 2. Buscar el ejecutable correspondiente en la DB
        match = re.search(r"(\d+\.\d+\.\d+)", version_texto)
        v_search = match.group(1) if match else "5.0.1"

        conn = sqlite3.connect(self.db_path)
        # Buscamos la versión más parecida
        res = conn.execute("SELECT ruta FROM ejecutables WHERE version LIKE ? ORDER BY version DESC", 
                           (f"%{v_search}%",)).fetchone()
        
        # Si no existe esa versión exacta, traer la más reciente disponible
        if not res:
            res = conn.execute("SELECT ruta FROM ejecutables ORDER BY version DESC LIMIT 1").fetchone()
        conn.close()

        if res:
            exe_path = res[0]
            try:
                self.consola.append(f"🚀 Iniciando Blender para: {os.path.basename(ruta_blend)}")
                subprocess.Popen([exe_path, ruta_blend])
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo abrir Blender: {e}")
        else:
            QMessageBox.warning(self, "Configuración", "No hay ejecutables de Blender registrados en Preferencias.")


    def mostrar_menu_contextual(self, pos):
        tabla_activa = self.sender()
        item = tabla_activa.itemAt(pos)
        if not item: return

        fila = item.row() # Obtenemos el índice de la fila
        menu = QMenu()

        # Abrir...
        accion_abrir = QAction("🚀 Abrir en Blender", self)
        accion_abrir.triggered.connect(lambda: self.abrir_con_blender_desde_tabla(item))
        menu.addAction(accion_abrir)

        menu.addSeparator()

        # Eliminar...
        accion_eliminar = QAction("❌ Eliminar de todas las tablas", self)
        # Aquí conectamos a la función global usando la fila detectada
        accion_eliminar.triggered.connect(lambda: self.eliminar_proyecto_global(fila))
        menu.addAction(accion_eliminar)

        menu.exec(tabla_activa.mapToGlobal(pos))


    def eliminar_proyecto_global(self, fila):
        # 1. Obtener la ruta única (fuente de verdad) de la tabla de metadatos
        # Aunque hagas clic en la tabla de renderizado, usamos el índice de fila 
        # para sacar la ruta de la tabla de metadatos (Columna 9)
        item_ruta = self.tabla_metadatos.item(fila, 9)
        if not item_ruta: return
        
        ruta_blend = item_ruta.text()
        nombre = os.path.basename(ruta_blend)

        # 2. Confirmación de seguridad
        confirmar = QMessageBox.question(
            self, "Eliminar Proyecto",
            f"¿Deseas quitar '{nombre}' del gestor?\n\n"
            "Se eliminarán sus metadatos y configuración de renderizado de todas las listas.",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirmar == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(self.db_path)
                # IMPORTANTE: Sin esta línea, el ON DELETE CASCADE no se activa en SQLite
                conn.execute("PRAGMA foreign_keys = ON") 
                
                # 3. Borrado en la tabla principal
                conn.execute("DELETE FROM proyectos WHERE carpeta = ?", (ruta_blend,))
                
                conn.commit()
                conn.close()

                # 4. Refresco total de la UI
                self.cargar_datos_desde_db() 
                self.consola.append(f"🗑️ Proyecto eliminado de la base de datos: {nombre}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar el registro: {e}")


    def leer_consola_blender(self):
        data = self.proceso_render.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        self.consola.insertPlainText(data)
        self.consola.ensureCursorVisible()

        # 1. Verificar si estamos en un proceso activo
        if self.proceso_actual_row == -1:
            return

        # 2. Identificar el widget de la barra de progreso
        bar = self.tabla_renderizar.cellWidget(self.proceso_actual_row, 10)
        if not bar:
            return

        # --- LÓGICA DE ACTUALIZACIÓN DE PROGRESO ---
        if "Fra:" in data:
            try:
                # Extraer número después de "Fra:" (Blender 4.x y 5.x)
                # Usamos un split más robusto para evitar errores de sintaxis
                parte = data.split("Fra:")[1].split("|")[0].split(" ")[0].strip()
                frame_actual = int(''.join(filter(str.isdigit, parte)))
            
                # Obtener rango desde la tabla (columnas 8 y 9: Desde/Hasta)
                f_ini = int(self.tabla_renderizar.item(self.proceso_actual_row, 8).text())
                f_fin = int(self.tabla_renderizar.item(self.proceso_actual_row, 9).text())
            
                total_frames = (f_fin - f_ini) + 1
                if total_frames <= 0: total_frames = 1
                
                # Cálculo de progreso real
                progreso_raw = ((frame_actual - f_ini + 1) / total_frames) * 100
                progreso = int(min(max(progreso_raw, 0), 100))
            
                # --- SOLUCIÓN AL SOLAPAMIENTO ---
                # Forzamos que la barra solo muestre el número % mientras renderiza
                bar.setFormat("%p%") 
                bar.setValue(progreso)
                
                # Aplicamos color naranja de "Procesando" para diferenciarlo del verde final
                bar.setStyleSheet("QProgressBar::chunk { background-color: #f39c12; }")
                
            except Exception as e:
                print(f"Error parseando consola: {e}")

        # --- DETECCIÓN DE MUESTRAS (SAMPLES) PARA RENDER DE UN SOLO FRAME ---
        elif "Sample" in data:
            try:
                # Ejemplo: "Sample 450/512"
                partes = data.split("Sample ")[1].split("/")[0]
                sample_actual = int(partes)
                total_samples = int(data.split("/")[1].split(" ")[0])
                
                progreso_s = int((sample_actual / total_samples) * 100)
                bar.setFormat(f"Renderizado... {progreso_s}%")
                bar.setValue(progreso_s)
            except:
                pass


    def abortar_render_especifico(self, fila):
        # Solo actuamos si el proceso que se quiere abortar es el que está corriendo
        if self.proceso_render.state() == QProcess.Running and fila == self.proceso_actual_row:
            confirmar = QMessageBox.warning(self, "Abortar Render", 
                "¿Deseas saltar este archivo y continuar con el resto de la cola?", 
                QMessageBox.Yes | QMessageBox.No)
        
            if confirmar == QMessageBox.Yes:
                self.consola.append(f"\n🛑 ABORTANDO: {self.tabla_renderizar.item(fila, 1).text()}")
            
                # Matamos el proceso actual
                self.proceso_render.kill() 
            
                # NOTA: NO vaciamos self.cola_render = [] 
                # Al morir el proceso, se disparará 'al_finalizar_render_actual' 
                # y esa función llamará automáticamente al siguiente.

                # Visualmente marcamos como abortado
                bar = self.tabla_renderizar.cellWidget(fila, 10)
                if bar:
                    bar.setFormat("SALTADO/ABORTADO")
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