import sys
import os
from cx_Freeze import setup, Executable 

# Archivos adicionales (Scripts, iconos, carpetas de BBDD)
archivos_adicionales = [
    ("info_archivo_blend.py", "info_archivo_blend.py"),
    # Si tienes un icono, descomenta la siguiente línea:
     ("tu_icono.ico", "tu_icono.ico"), 
]

## Configuración de la Base para Windows
# Win32GUI oculta la consola negra al abrir el programa.
base = None
if sys.platform == "win32":
    base = "Win32GUI" 

setup(
    name="jc_render_app",
    version="0.1.2",
    description="Aplicación de Render de Blender",
    options={
        "build_exe": {
            "include_files": archivos_adicionales,
            # Es mejor incluir PySide6 completo para evitar que falten librerías internas (plugins de Qt)
            "packages": ["os", "sys", "json", "sqlite3", "PySide6", "subprocess"],
            "excludes": ["tkinter", "unittest"], # Reduce el peso del EXE
        }
    },
    executables=[
        Executable(
            "jc_render.py", 
            base=base,          # 🟢 CORREGIDO: Usa la variable definida arriba
            target_name="jc_render.exe",
            icon="tu_icono.ico" # ⚠️ Asegúrate de que el archivo existe o comenta esta línea
        )
    ]
)