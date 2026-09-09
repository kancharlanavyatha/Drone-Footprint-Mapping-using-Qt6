import os
import subprocess

def build_qgis_project():
    qgis_python = r'C:\Program Files\QGIS 3.44.12\bin\python-qgis-ltr.bat'
    builder_script = os.path.join(os.path.dirname(__file__), 'step6_qgis_project_builder.py')
    
    if os.path.exists(qgis_python) and os.path.exists(builder_script):
        print('[Step 6] Generating Pre-configured QGIS Project...')
        res = subprocess.run([qgis_python, builder_script], capture_output=True, text=True)
        if res.returncode == 0:
            print(' -> Successfully created Brighton_Beach_Project.qgz')
        else:
            print(' -> Warning during QGIS project creation:', res.stderr)

if __name__ == '__main__':
    build_qgis_project()
