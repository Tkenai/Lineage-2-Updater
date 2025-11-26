import os
import sys
import json
import logging

from PyQt5.QtWidgets import QApplication, QMessageBox

from app.main_window import MainWindow
from app.windows_privileges import ensure_admin_privileges

LOGGING_ENABLED = True

# ----------------- CONFIG PADRÃO GERADA AUTOMATICAMENTE -----------------

DEFAULT_CONFIG = {
    "paths": {
        "update_json": "http://192.168.15.57:8080/l2updater/update_json_url.json",
        "fullcheck_json": "http://192.168.15.57:8080/l2updater/fullcheck.json",
        # raiz = pasta onde está o EXE
        "game_folder": ".",
        "exe": "system-e/l2.exe",
        "news_url": "http://192.168.15.57:8080/news/launcher_news.html",
    }
}


def ensure_default_config(config_path: str):
    """
    Se o config.json não existir, cria com DEFAULT_CONFIG.
    Se existir, não altera nada.
    """
    if os.path.isfile(config_path):
        return

    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        logging.info(f"config.json não encontrado. Arquivo padrão gerado em: {config_path}")
    except Exception:
        logging.exception("Falha ao gerar config.json padrão")
        QMessageBox.critical(
            None,
            "Erro",
            f"Não foi possível criar o arquivo de configuração:\n{config_path}",
        )
        sys.exit(1)

# ------------------------------------------------------------------------


def setup_logging():
    logs_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file_path = os.path.join(logs_dir, "launcher.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.info("Logging iniciado.")


def get_base_path():
    """
    Quando empacotado com PyInstaller:
        - sys.executable = caminho do EXE
    Em modo desenvolvimento:
        - usa o caminho do arquivo main.py
    """
    if hasattr(sys, "frozen"):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))


def main():
    # Garante privilégios administrativos no Windows (se possível)
    ensure_admin_privileges()

    if LOGGING_ENABLED:
        setup_logging()

    app = QApplication(sys.argv)

    base_path = get_base_path()
    config_path = os.path.join(base_path, "config.json")

    # 🔹 GARANTE QUE O config.json EXISTA (CRIA SE PRECISAR)
    ensure_default_config(config_path)

    if not os.path.isfile(config_path):
        QMessageBox.critical(
            None,
            "Erro",
            f"Arquivo de configuração não encontrado:\n{config_path}",
        )
        sys.exit(1)

    try:
        window = MainWindow(config_path=config_path, base_dir=base_path)
    except Exception:
        logging.exception("Falha ao iniciar a janela principal")
        QMessageBox.critical(
            None,
            "Erro",
            "Falha ao iniciar o launcher. Verifique o arquivo de configuração.",
        )
        sys.exit(1)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
