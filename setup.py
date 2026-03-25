import sys
from cx_Freeze import setup, Executable

# Definición de la base para evitar el error de Python 3.13
base = None
if sys.platform == "win32":
    base = "gui"

archivos_adicionales = [
    ("info_archivo_blend.py", "info_archivo_blend.py"),
    ("jc_render.ico", "jc_render.ico")
]

build_exe_options = {
    "include_files": archivos_adicionales,
    "packages": ["os", "sys", "json", "sqlite3", "PySide6", "subprocess"],
    "include_msvcr": True,
    #ESTO ES CLAVE: Evita que las librerías se metan en un .zip interno
    # permitiendo que BASE_DIR funcione siempre.
    "zip_include_packages": [], 
    "zip_exclude_packages": ["*"],
}

setup(
    name="jc_render_app",
    version="0.1.4",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "jc_render.py",
            base=base, # Aquí pasamos la variable
            target_name="jc_render.exe",
            icon="jc_render.ico"
        )
    ]
)