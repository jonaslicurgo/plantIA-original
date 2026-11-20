from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
REQUIREMENTS_FILE = PROJECT_DIR / "requirements.txt"
DEFAULT_PORT = int(os.getenv("PLANTIA_PORT", "8000"))

APP_DATA_DIR = Path.home() / ".plantia"


def get_venv_dir() -> Path:
    override = os.environ.get("PLANTIA_VENV")
    if override:
        return Path(override)
    local = PROJECT_DIR / ".venv"
    if os.access(PROJECT_DIR, os.W_OK):
        return local
    data_home = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    return data_home / "plantia" / ".venv"


def get_venv_python() -> Path:
    venv_dir = get_venv_dir()
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def is_running_in_venv() -> bool:
    if not get_venv_dir().exists():
        return False
    return Path(sys.prefix).resolve() == get_venv_dir().resolve()


def create_venv() -> None:
    venv_dir = get_venv_dir()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Creando entorno virtual en {venv_dir} …")
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        cwd=PROJECT_DIR,
    )
    print("Entorno virtual creado.")


def ensure_venv() -> Path:
    venv_python = get_venv_python()
    if not venv_python.exists():
        create_venv()
        venv_python = get_venv_python()
    if not venv_python.exists():
        raise RuntimeError("No se pudo crear el entorno virtual.")
    return venv_python


def install_dependencies(venv_python: Path) -> None:
    print("Instalando dependencias en el entorno virtual …")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-q", "--upgrade", "pip"],
        check=True,
        cwd=PROJECT_DIR,
    )
    subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "-q",
            "-r",
            str(REQUIREMENTS_FILE),
        ],
        check=True,
        cwd=PROJECT_DIR,
    )
    print("Dependencias instaladas correctamente.")


def launch_app() -> int:
    import uvicorn

    port = int(os.getenv("PLANTIA_PORT", str(DEFAULT_PORT)))

    host = os.getenv("PLANET_BIND_HOST", "127.0.0.1")
    if host in {"127.0.0.1", "::1"}:
        os.environ.setdefault("PLANET_INSECURE_LOCAL_HTTP", "1")
    print(f"Iniciando PLANET-IA en http://localhost:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
    return 0


def has_configured_api_key() -> bool:
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


def main() -> int:
    os.chdir(PROJECT_DIR)
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))

    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        example = PROJECT_DIR / ".env.example"
        if example.exists():
            if not has_configured_api_key():
                print(
                    "Aviso: no existe .env. Copia .env.example a .env y añade tu GEMINI_API_KEY "
                    "La clave se configura exclusivamente en el servidor.",
                    file=sys.stderr,
                )

    if is_running_in_venv():
        try:
            return launch_app()
        except Exception as exc:
            import traceback

            print(f"Error al iniciar PlantIA: {exc}", file=sys.stderr)
            traceback.print_exc()
            return 1

    try:
        venv_python = ensure_venv()
        install_dependencies(venv_python)

        print("Iniciando PlantIA …")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_DIR)
        os.environ.update(env)
        argv = [str(venv_python), str(__file__), *sys.argv[1:]]
        os.execv(str(venv_python), argv)
        return 1

    except subprocess.CalledProcessError as exc:
        print(f"Error al preparar el entorno: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
