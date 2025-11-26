import os
import json
import hashlib
import urllib.request
import logging

from PyQt5 import QtCore, QtWidgets, QtGui


class UpdateWorker(QtCore.QObject):
    progress_changed = QtCore.pyqtSignal(int)      # 0–100
    status_changed = QtCore.pyqtSignal(str)
    log_message = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(bool)

    def __init__(self, mode, config, parent=None,base_dir=None):
        super().__init__(parent)
        self.mode = mode  # "update" ou "fullcheck"
        self.config = config
        self._cancelled = False
        self.base_dir = base_dir or os.getcwd()

    @QtCore.pyqtSlot()
    def _get_game_root(self):
        """
        Pasta raiz onde os arquivos do jogo/patch devem ir.
        - Se game_folder for absoluto, usa direto
        - Se for relativo (incluindo "."), é relativo à pasta do launcher (base_dir)
        """
        paths = self.config.get("paths", {})
        game_folder = paths.get("game_folder", ".").strip()

        if os.path.isabs(game_folder):
            return os.path.normpath(game_folder)

        # relativo -> dentro da pasta do launcher
        return os.path.normpath(os.path.join(self.base_dir, game_folder))

    def run(self):
        try:
            self._run_internal()
            if not self._cancelled:
                self.finished.emit(True)
        except Exception as e:
            self.log_message.emit(f"Erro: {e}")
            self.finished.emit(False)

    def cancel(self):
        self._cancelled = True

    # -------------------- Lógica interna --------------------

    def _run_internal(self):
        paths = self.config.get("paths", {})

        if self.mode == "update":
            url = paths.get("update_json")
        else:
            url = paths.get("fullcheck_json")

        if not url:
            raise RuntimeError("URL de JSON de atualização não configurada.")

        self.status_changed.emit(f"Baixando lista de arquivos ({self.mode})...")
        self.log_message.emit(f"Baixando JSON: {url}")

        data = self._download_json(url)

        files = data.get("files", [])
        base_url = data.get("base_url", "")

        if not files:
            self.log_message.emit("Nenhum arquivo para processar.")
            self.progress_changed.emit(100)
            return

        total = len(files)
        game_root = self._get_game_root()  # <- usa base_dir + game_folder

        for idx, info in enumerate(files, start=1):
            if self._cancelled:
                self.log_message.emit("Atualização cancelada.")
                return
            # caminho relativo vindo do JSON
            rel_path = info["path"].replace("/", os.sep)
            # remove barras iniciais pra não “escapar” da pasta do launcher
            rel_path = rel_path.lstrip("\\/")

            expected_sha1 = info.get("sha1", "").lower().strip()
            file_url = info.get("url")

            if not file_url:
                # monta URL com base_url
                file_url = base_url.rstrip("/") + "/" + info["path"].lstrip("/")

            # SEMPRE dentro de game_root
            local_path = os.path.normpath(os.path.join(game_root, rel_path))

            msg_prefix = f"[{idx}/{total}] {rel_path}"
            self.status_changed.emit(f"Verificando {msg_prefix}...")
            self.log_message.emit(f"Verificando arquivo: {rel_path}")

            need_download = False

            if not os.path.isfile(local_path):
                self.log_message.emit(" - Arquivo não existe, será baixado.")
                need_download = True
            elif expected_sha1:
                local_sha1 = self._calc_sha1(local_path)
                if local_sha1.lower() != expected_sha1:
                    self.log_message.emit(" - Hash diferente, será baixado novamente.")
                    need_download = True
                else:
                    self.log_message.emit(" - OK (hash confere).")

            if need_download:
                size_bytes = info.get("size", 0)
                if size_bytes:
                    size_mb = size_bytes / (1024 * 1024)
                    size_text = f" ({size_mb:.2f} MB)"
                else:
                    size_text = ""

                self.status_changed.emit(f"Baixando: {rel_path}{size_text}...")
                self._ensure_dir(local_path)
                self._download_file(file_url, local_path)

            progress = int(idx * 100 / total)
            self.progress_changed.emit(progress)

        self.status_changed.emit(f"Verificando: {rel_path} ({idx}/{total})...")
        self.log_message.emit("Processo concluído com sucesso.")
        self.progress_changed.emit(100)

    # -------------------- Helpers de rede / arquivos --------------------

    def _download_json(self, url):
        with urllib.request.urlopen(url) as resp:
            content = resp.read().decode("utf-8")
        return json.loads(content)

    def _download_file(self, url, dest_path, chunk_size=1024 * 128):
        self.log_message.emit(f"   -> Baixando de {url}")
        with urllib.request.urlopen(url) as resp, open(dest_path, "wb") as f:
            while True:
                if self._cancelled:
                    self.log_message.emit("Download cancelado.")
                    return
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)

    def _ensure_dir(self, file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

    def _calc_sha1(self, file_path, chunk_size=1024 * 1024):
        h = hashlib.sha1()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()


class UpdaterWindow(QtWidgets.QDialog):
    # SINAIS EXTERNOS PARA O MAINWINDOW
    progress_changed = QtCore.pyqtSignal(int)
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self, mode, config, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.config = config

        self.thread = None
        self.worker = None
        self.result_ok = None  # para o caller saber o resultado

        self._setup_ui()
        self._start_worker()

    def _setup_ui(self):
        if self.mode == "update":
            self.setWindowTitle("Atualizar Cliente")
        else:
            self.setWindowTitle("Full Check do Cliente")

        self.resize(600, 400)

        layout = QtWidgets.QVBoxLayout(self)

        self.lbl_status = QtWidgets.QLabel("Iniciando...")
        layout.addWidget(self.lbl_status)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.txt_log = QtWidgets.QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)

        button_layout = QtWidgets.QHBoxLayout()

        self.btn_cancel = QtWidgets.QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.btn_cancel)

        self.btn_close = QtWidgets.QPushButton("Fechar")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_close)

        layout.addLayout(button_layout)

    def _start_worker(self):
        self.thread = QtCore.QThread(self)
        self.worker = UpdateWorker(self.mode, self.config)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        # em vez de ligar direto, usamos handlers que repassam o sinal
        self.worker.progress_changed.connect(self._on_worker_progress)
        self.worker.status_changed.connect(self._on_worker_status)
        self.worker.log_message.connect(self._append_log)
        self.worker.finished.connect(self._on_finished)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    # ------- handlers que atualizam a UI e repassam o sinal --------

    def _on_worker_progress(self, value: int):
        self.progress.setValue(value)
        self.progress_changed.emit(value)

    def _on_worker_status(self, text: str):
        self.lbl_status.setText(text)
        self.status_changed.emit(text)

    # ---------------------------------------------------------------

    def _append_log(self, text):
        self.txt_log.append(text)
        logging.info(text)

    def _on_finished(self, ok):
        self.result_ok = ok

        if ok:
            self.lbl_status.setText("Concluído.")
        else:
            self.lbl_status.setText("Finalizado com erros.")
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

    def _on_cancel(self):
        if self.worker:
            self.worker.cancel()
        self.btn_cancel.setEnabled(False)
        self._append_log("Cancelamento solicitado...")
