import sys
from cx_Freeze import setup, Executable 

archivos_adicionales = [
    # (Ruta del archivo original, Nombre que tendrá dentro del paquete EXE)
    # Se recomienda usar el mismo nombre para simplificar la vida
    ("info_archivo_blend.py", "info_archivo_blend.py"),
]

## Base (requerida para aplicaciones GUI en Windows)
base = None
if sys.platform == "win32":
    base = "Win32GUI" # Para aplicaciones PySide/PyQt

setup(
    name="jc_render_app",
    version="0.1.2",
    description="Aplicación de Render de Blender",
    options={
        "build_exe": {
            # 🟢 PASO CLAVE 1: Incluir el script como archivo de datos
            "include_files": archivos_adicionales,
            # Asegúrate de incluir los módulos necesarios
            "packages": ["os", "sys", "json", "PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui"],
            # Puedes añadir más opciones si es necesario
        }
    },
    executables=[
        Executable("jc_render.py", base="gui", icon="tu_icono.ico")
    ]
)