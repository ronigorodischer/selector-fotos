"""Install the app in a local virtual environment; no administrator privileges."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description='Instalar Selector local')
    parser.add_argument('--check',action='store_true',help='Verificar la instalación sin descargar nada')
    args=parser.parse_args()
    if not (3,11)<=sys.version_info[:2]<(3,14) or struct.calcsize('P')!=8:
        raise RuntimeError('Instala Python 3.11, 3.12 o 3.13 de 64 bits desde https://www.python.org/downloads/ .')
    env=ROOT/'.venv'
    python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        if args.check:raise RuntimeError('Falta la instalación. Ejecuta primero Instalar.cmd o bash Instalar.sh.')
        print('Creando entorno aislado...',flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    if not args.check:
        subprocess.run([str(python),'-m','pip','install','--upgrade','pip'],check=True)
        subprocess.run([str(python),'-m','pip','install','--only-binary=:all:','-r',str(ROOT/'requirements.txt')],check=True)
    (ROOT/'data').mkdir(exist_ok=True)
    subprocess.run([str(python),str(ROOT/'check_install.py')],cwd=ROOT,check=True)
    print('Listo. Abre Iniciar.cmd (Windows) o ejecuta bash Iniciar.sh (macOS/Linux).')


if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'No se pudo completar la instalación: {exc}',file=sys.stderr)
        sys.exit(1)
