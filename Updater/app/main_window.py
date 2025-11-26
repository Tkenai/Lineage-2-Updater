import os
import json
import logging
import sys
import urllib.request

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMessageBox

from app.updater_window import UpdaterWindow, UpdateWorker

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, config_path, base_dir):
        super().__init__()

        self.config_path = config_path
        self.base_dir = base_dir            # <-- SEM sobrescrever depois
        self.config = self._load_config()

        # >>> NOVO: resolve caminho dos assets dependendo se está congelado ou não
        if hasattr(sys, "_MEIPASS"):
            assets_root = os.path.join(sys._MEIPASS, "assets")
        else:
            assets_root = os.path.join(self.base_dir, "assets")

        self.background_path = os.path.join(assets_root, "launcher_bg.png")
        logging.info(f"Background path: {self.background_path}")
        
        self._dragging = False
        self._drag_pos = QtCore.QPoint()
        self._fade_anim = None
        self._log_window = None
        self._auto_thread = None
        self._auto_worker = None
        self._manual_thread = None
        self._manual_worker = None

        self._setup_window()
        self._init_ui()
        self._connect_signals()

        # Play começa desabilitado até rodar o update automático
        self.btn_play.setEnabled(False)
        QtCore.QTimer.singleShot(200, self._auto_update_on_start)


    def _run_update_silent(self, mode: str):
        """Roda update ou fullcheck sem abrir janela, usando só a barra de baixo."""
        paths = self.config.get("paths", {})

        if mode == "update":
            json_url = paths.get("update_json")
            if not json_url:
                QMessageBox.warning(
                    self,
                    "Atualizar Cliente",
                    "URL de update_json não configurada em config.json.",
                )
                return
            logging.info("Iniciando atualização manual (silent)...")
            status_inicio = "Verificando atualizações do cliente..."
        else:
            json_url = paths.get("fullcheck_json")
            if not json_url:
                QMessageBox.warning(
                    self,
                    "Full Check",
                    "URL de fullcheck_json não configurada em config.json.",
                )
                return
            logging.info("Iniciando full check manual (silent)...")
            status_inicio = "Executando verificação completa dos arquivos..."

        self.lbl_status.setText(status_inicio)
        self.progress_bar.setValue(0)
        self.btn_play.setEnabled(False)

        # se já tiver um manual rodando, ignora
        if self._manual_thread is not None and self._manual_thread.isRunning():
            QMessageBox.information(
                self,
                "Atualização em andamento",
                "Já existe um processo de atualização/verificação em andamento.",
            )
            return

        self._manual_thread = QtCore.QThread(self)
        self._manual_worker = UpdateWorker(
            mode=mode,
            config=self.config,
            base_dir=self.base_dir,  # <- pasta do EXE
        )
        self._manual_worker.moveToThread(self._manual_thread)

        self._manual_thread.started.connect(self._manual_worker.run)
        self._manual_worker.progress_changed.connect(self.progress_bar.setValue)
        self._manual_worker.status_changed.connect(self.lbl_status.setText)
        self._manual_worker.log_message.connect(logging.info)
        self._manual_worker.finished.connect(
            lambda ok, m=mode: self._on_manual_update_finished(m, ok)
        )

        self._manual_worker.finished.connect(self._manual_thread.quit)
        self._manual_worker.finished.connect(self._manual_worker.deleteLater)
        self._manual_thread.finished.connect(self._manual_thread.deleteLater)

        self._manual_thread.start()

    # -------------------- Setup janela --------------------
    def _setup_window(self):
        self.setWindowTitle("Lineage 2 Grand Crusade Launcher")
        self.setFixedSize(1024, 768)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Janela sem borda (frameless)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Window
            | QtCore.Qt.WindowSystemMenuHint
        )

    # -------------------- UI --------------------
    def _init_ui(self):
        central = QtWidgets.QWidget(self)
        central.setObjectName("centralWidget")
        central.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        central.setStyleSheet("background: transparent;")
        self.setStyleSheet("background-color: transparent;")
        self.setCentralWidget(central)

        # BACKGROUND cobrindo TODA a janela
        self.bg_label = QtWidgets.QLabel(central)
        self.bg_label.setObjectName("bgLabel")
        self.bg_label.setScaledContents(True)
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        self.bg_label.setStyleSheet("background: transparent;")
        self._load_background()
        # garante que fique sempre atrás dos outros widgets
        self.bg_label.lower()

        # LAYOUT PRINCIPAL por cima do background
        self.main_layout = QtWidgets.QVBoxLayout(central)
        self.main_layout.setContentsMargins(30, 20, 30, 30)
        self.main_layout.setSpacing(10)

        # ---- BARRA SUPERIOR (título + botões janela) ----
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(10)
        top_layout.setContentsMargins(20, 25, 20, 0)

        # ---- LADO ESQUERDO (apenas o título) ----
        left_header = QtWidgets.QHBoxLayout()

        self.lbl_title = QtWidgets.QLabel("Lineage 2 Grand Crusade")
        title_font = QtGui.QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        self.lbl_title.setFont(title_font)
        self.lbl_title.setStyleSheet("color: white; background: transparent;")
        self.lbl_title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # Glow do título
        effect = QtWidgets.QGraphicsDropShadowEffect()
        effect.setBlurRadius(18)
        effect.setOffset(0, 0)
        effect.setColor(QtGui.QColor(0, 0, 0, 220))
        self.lbl_title.setGraphicsEffect(effect)

        left_header.addWidget(self.lbl_title)
        left_header.addStretch()

        # ---- LADO DIREITO (botões) ----
        right_header = QtWidgets.QHBoxLayout()
        right_header.setSpacing(5)

        self.btn_log = QtWidgets.QPushButton("☰")
        self._style_window_button(self.btn_log)

        self.btn_min = QtWidgets.QPushButton("–")
        self.btn_close_win = QtWidgets.QPushButton("✕")

        self._style_window_button(self.btn_min)
        self._style_window_button(self.btn_close_win, is_close=True)

        right_header.addWidget(self.btn_log)
        right_header.addWidget(self.btn_min)
        right_header.addWidget(self.btn_close_win)

        # ---- Juntar no top_layout ----
        top_layout.addLayout(left_header)
        top_layout.addLayout(right_header)

        self.main_layout.addLayout(top_layout)

        # espaço central (fica só a imagem)
        self.main_layout.addStretch(1)

        # ---- ÁREA DE NOTÍCIAS ----
        self.news_frame = QtWidgets.QFrame()
        self.news_frame.setObjectName("newsFrame")
        self.news_frame.setStyleSheet(
            """
            QFrame#newsFrame {
                background-color: rgba(0, 0, 0, 140);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
            """
        )
        news_layout = QtWidgets.QVBoxLayout(self.news_frame)
        news_layout.setContentsMargins(12, 10, 12, 10)
        news_layout.setSpacing(6)

        lbl_news_title = QtWidgets.QLabel("Notícias")
        news_title_font = QtGui.QFont()
        news_title_font.setPointSize(11)
        news_title_font.setBold(True)
        lbl_news_title.setFont(news_title_font)
        lbl_news_title.setStyleSheet("color: #ffcc80;")
        news_layout.addWidget(lbl_news_title)

        self.news_view = QtWidgets.QTextBrowser()
        self.news_view.setStyleSheet(
            """
            QTextBrowser {
                background: transparent;
                color: #f5f5f5;
                border: none;
            }
            """
        )
        self.news_view.setOpenExternalLinks(True)
        self.news_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.news_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.news_view.setMinimumHeight(120)
        self.news_view.setMaximumHeight(160)
        news_layout.addWidget(self.news_view)

        self.main_layout.addWidget(self.news_frame, stretch=0)

        # Carrega notícias
        self._load_news()

        # ---- PAINEL INFERIOR ----
        self.bottom_frame = QtWidgets.QFrame()
        self.bottom_frame.setObjectName("bottomFrame")
        self.bottom_frame.setStyleSheet(
            """
            QFrame#bottomFrame {
                background-color: rgba(0, 0, 0, 170);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 45);
            }
            """
        )

        bottom_layout = QtWidgets.QVBoxLayout(self.bottom_frame)
        bottom_layout.setContentsMargins(20, 15, 20, 15)
        bottom_layout.setSpacing(10)

        self.lbl_status = QtWidgets.QLabel("Todos os arquivos estão atualizados.")
        self.lbl_status.setStyleSheet("color: #dddddd;")
        self.lbl_status.setAlignment(QtCore.Qt.AlignLeft)
        bottom_layout.addWidget(self.lbl_status)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background-color: rgba(255, 255, 255, 20);
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #ff9800;
                border-radius: 4px;
            }
            """
        )
        bottom_layout.addWidget(self.progress_bar)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(15)

        self.btn_update = QtWidgets.QPushButton("Atualizar Cliente")
        self.btn_fullcheck = QtWidgets.QPushButton("Full Check")
        self.btn_play = QtWidgets.QPushButton("JOGAR")
        self.btn_exit = QtWidgets.QPushButton("Fechar")

        play_effect = QtWidgets.QGraphicsDropShadowEffect()
        play_effect.setBlurRadius(25)
        play_effect.setOffset(0, 0)
        play_effect.setColor(QtGui.QColor(255, 152, 0, 180))
        self.btn_play.setGraphicsEffect(play_effect)

        self._style_secondary_button(self.btn_update)
        self._style_secondary_button(self.btn_fullcheck)
        self._style_primary_button(self.btn_play)
        self._style_secondary_button(self.btn_exit)

        buttons_layout.addWidget(self.btn_update)
        buttons_layout.addWidget(self.btn_fullcheck)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.btn_play)
        buttons_layout.addWidget(self.btn_exit)

        bottom_layout.addLayout(buttons_layout)

        self.main_layout.addWidget(self.bottom_frame)




    # ----- estilos -----

    def _style_window_button(self, btn: QtWidgets.QPushButton, is_close=False):
        btn.setFixedSize(30, 24)
        btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        if is_close:
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: rgba(255, 74, 74, 200);
                    color: white;
                    border-radius: 10px;
                    border: none;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 120, 120, 230);
                }
                QPushButton:pressed {
                    background-color: rgba(200, 50, 50, 255);
                }
                """
            )
        else:
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: rgba(255, 255, 255, 40);
                    color: #f5f5f5;
                    border-radius: 10px;
                    border: none;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 80);
                    color: #222222;
                }
                QPushButton:pressed {
                    background-color: rgba(220, 220, 220, 120);
                }
                """
            )

    def _style_primary_button(self, btn: QtWidgets.QPushButton):
        btn.setMinimumHeight(42)
        btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: #ff9800;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border-radius: 18px;
                padding: 8px 24px;
                border: 1px solid #ffb74d;
            }
            QPushButton:hover {
                background-color: #ffb74d;                
            }
            QPushButton:pressed {
                background-color: #f57c00;                
            }
            QPushButton:disabled {
                background-color: #666666;
                border-color: #666666;
                color: #cccccc;                
            }
            """
        )

    def _style_secondary_button(self, btn: QtWidgets.QPushButton):
        btn.setMinimumHeight(32)
        btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: #f5f5f5;
                font-size: 12px;
                border-radius: 14px;
                padding: 6px 16px;
                border: 1px solid rgba(255, 255, 255, 80);
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 60);
                color: #222222;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 90);
                color: #111111;
            }
            QPushButton:disabled {
                background-color: #555555;
                border-color: #555555;
                color: #bbbbbb;
            }
            """
        )

    # -------------------- Background / notícias --------------------

    def _load_background(self):
        if os.path.isfile(self.background_path):
            pix = QtGui.QPixmap(self.background_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    self.size(),
                    QtCore.Qt.KeepAspectRatioByExpanding,
                    QtCore.Qt.SmoothTransformation,
                )
                self.bg_label.setPixmap(scaled)
        else:
            # fallback degrade
            palette = self.palette()
            gradient = QtGui.QLinearGradient(0, 0, 0, self.height())
            gradient.setColorAt(0.0, QtGui.QColor("#fff"))
            gradient.setColorAt(1.0, QtGui.QColor("#fff"))
            brush = QtGui.QBrush(gradient)
            palette.setBrush(QtGui.QPalette.Window, brush)
            self.setPalette(palette)

    def _load_news(self):
        paths = self.config.get("paths", {})
        news_url = paths.get("news_url")
        if not news_url:
            self.news_view.setPlainText("Nenhuma notícia configurada.")
            return

        try:
            with urllib.request.urlopen(news_url, timeout=3) as resp:
                content = resp.read().decode("utf-8", errors="ignore").strip()
        except Exception as e:
            logging.warning(f"Falha ao carregar notícias: {e}")
            self.news_view.setPlainText("Não foi possível carregar as notícias.")
            # MUITO IMPORTANTE: simplesmente retorna, sem levantar erro
            return

        # se parecer JSON, podemos tratar depois; por enquanto, assume HTML/texto
        if content.startswith("{") or content.startswith("["):
            self.news_view.setPlainText(content)
        else:
            self.news_view.setHtml(content)


    # -------------------- Eventos da janela --------------------

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        # background sempre ocupando a janela inteira
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        self._load_background()

    def showEvent(self, event: QtGui.QShowEvent):
        super().showEvent(event)
        # fade-in
        self.setWindowOpacity(0.0)
        anim = QtCore.QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(350)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        self._fade_anim = anim
        anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

    # drag da janela
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            child = self.childAt(event.pos())
            if isinstance(child, QtWidgets.QAbstractButton):
                return super().mousePressEvent(event)
            self._dragging = True
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._dragging and event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        self._dragging = False
        return super().mouseReleaseEvent(event)

    # -------------------- Sinais --------------------

    def _connect_signals(self):
        self.btn_exit.clicked.connect(self.close)
        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.btn_fullcheck.clicked.connect(self._on_fullcheck_clicked)

        self.btn_close_win.clicked.connect(self.close)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_log.clicked.connect(self._on_log_clicked)

    # -------------------- Config --------------------

    def _load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro de configuração",
                f"Não foi possível carregar o arquivo de configuração:\n{e}",
            )
            raise

    # -------------------- Auto update ao iniciar --------------------
    def _auto_update_on_start(self):
        """Executa atualização automática ao abrir o launcher.
        Agora de forma silenciosa (sem abrir janela), usando só a barra de baixo.
        """
        paths = self.config.get("paths", {})
        if not paths.get("update_json"):
            self.lbl_status.setText(
                "Atualização automática desabilitada (URL não configurada)."
            )
            self.btn_play.setEnabled(True)
            return

        try:
            logging.info("Rodando atualização automática ao iniciar launcher...")
            self.lbl_status.setText("Verificando atualizações do cliente...")
            self.progress_bar.setValue(0)
            self.btn_play.setEnabled(False)

            # cria thread + worker para UPDATE silencioso
            self._auto_thread = QtCore.QThread(self)
            self._auto_worker = UpdateWorker(
                mode="update",
                config=self.config,
                base_dir=self.base_dir
            )
            self._auto_worker.moveToThread(self._auto_thread)

            # quando a thread começar, roda o worker
            self._auto_thread.started.connect(self._auto_worker.run)

            # conecta sinais do worker diretamente ao painel inferior e ao log
            self._auto_worker.progress_changed.connect(self.progress_bar.setValue)
            self._auto_worker.status_changed.connect(self.lbl_status.setText)
            self._auto_worker.log_message.connect(logging.info)
            self._auto_worker.finished.connect(self._on_auto_update_finished)

            # limpeza da thread/worker
            self._auto_worker.finished.connect(self._auto_thread.quit)
            self._auto_worker.finished.connect(self._auto_worker.deleteLater)
            self._auto_thread.finished.connect(self._auto_thread.deleteLater)

            self._auto_thread.start()

        except Exception as e:
            logging.exception(f"Erro na atualização automática: {e}")
            self.lbl_status.setText(
                "Falha na atualização automática. Tente atualizar manualmente."
            )
            self.btn_play.setEnabled(True)
    def _on_auto_update_finished(self, ok: bool):
        """Chamado quando o auto-update termina (com sucesso ou erro)."""
        if ok:
            self.lbl_status.setText("Verificação concluída com sucesso.")
        else:
            self.lbl_status.setText(
                "Atualização automática finalizada com erros. Verifique o log."
            )

        # garante barra cheia no fim
        self.progress_bar.setValue(100)
        # libera o botão JOGAR
        self.btn_play.setEnabled(True)



    # -------------------- Ações dos botões --------------------

    def _on_update_clicked(self):
        self._run_update_silent("update")

    def _on_fullcheck_clicked(self):
        self._run_update_silent("fullcheck")

    def _on_play_clicked(self):
        paths = self.config.get("paths", {})
        game_folder = paths.get("game_folder", ".")
        exe_rel = paths.get("exe", "")

        try:
            # 1) Valida config
            if not exe_rel:
                raise RuntimeError(
                    "Caminho do executável do jogo (paths.exe) não está configurado em config.json."
                )

            # 2) Resolve pasta raiz do jogo
            if os.path.isabs(game_folder):
                root = os.path.normpath(game_folder)
            else:
                # sempre relativo à pasta do launcher
                root = os.path.normpath(os.path.join(self.base_dir, game_folder))

            # 3) Caminho final do executável
            exe_path = os.path.normpath(os.path.join(root, exe_rel))
            logging.info(f"Executável esperado do jogo: {exe_path}")

            # 4) Garante que o arquivo existe
            if not os.path.isfile(exe_path):
                raise FileNotFoundError(f"Executável do jogo não encontrado:\n{exe_path}")

            # 5) Tenta iniciar o jogo
            ok = QtCore.QProcess.startDetached(exe_path, [], os.path.dirname(exe_path))
            if not ok:
                # startDetached não lançou exceção, mas o Windows recusou iniciar
                raise RuntimeError(
                    "O Windows não conseguiu iniciar o executável (QProcess.startDetached retornou False)."
                )

            logging.info("Processo do jogo iniciado com sucesso.")
            self.showMinimized()

        except Exception as e:
            logging.exception("Erro ao iniciar o jogo")
            err_text = str(e) or repr(e)
            QMessageBox.critical(
                self,
                "Erro ao iniciar",
                f"Não foi possível iniciar o jogo:\n\n{err_text}",
            )


    def _on_log_clicked(self):
        # abre/fecha a janela de log
        if self._log_window is None:
            self._log_window = LogWindow(parent=self, base_dir=self.base_dir)

        if self._log_window.isVisible():
            self._log_window.hide()
        else:
            self._log_window.reload_log()
            # posiciona a janela perto do launcher
            geo = self.geometry()
            self._log_window.move(geo.right() + 10, geo.top() + 40)
            self._log_window.show()
            self._log_window.raise_()
            self._log_window.activateWindow()
    def _on_manual_update_finished(self, mode: str, ok: bool):
        if mode == "update":
            if ok:
                self.lbl_status.setText("Atualização concluída.")
            else:
                self.lbl_status.setText(
                    "Atualização concluída com erros ou cancelada. Verifique o log."
                )
        else:
            if ok:
                self.lbl_status.setText("Full check concluído.")
            else:
                self.lbl_status.setText(
                    "Full check concluído com erros ou cancelado. Verifique o log."
                )

        self.progress_bar.setValue(100)
        self.btn_play.setEnabled(True)

        self._manual_thread = None
        self._manual_worker = None


class LogWindow(QtWidgets.QDialog):
    def __init__(self, parent=None, base_dir=None):
        super().__init__(parent)
        self.base_dir = base_dir or os.getcwd()
        self.setWindowTitle("Log do Launcher")
        self.resize(900, 550)

        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowSystemMenuHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        # <<< ESTILO CLARO PARA O LOG >>>
        self.setStyleSheet("""
                QDialog {
                    background-color: #f0f0f0;
                }
                QPlainTextEdit {
                    background-color: #ffffff;
                    color: #222222;
                    border: 1px solid #bbbbbb;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 14px;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    border-radius: 6px;
                    border: 1px solid #b0b0b0;
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background-color: #f5f5f5;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
                """)

        layout = QtWidgets.QVBoxLayout(self)

        self.txt_log = QtWidgets.QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)

        button_layout = QtWidgets.QHBoxLayout()
        self.btn_reload = QtWidgets.QPushButton("Atualizar")
        self.btn_close = QtWidgets.QPushButton("Fechar")

        button_layout.addWidget(self.btn_reload)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_close)

        layout.addLayout(button_layout)

        self.btn_reload.clicked.connect(self.reload_log)
        self.btn_close.clicked.connect(self.close)

    def reload_log(self):
        log_path = os.path.join(self.base_dir, "logs", "launcher.log")
        if not os.path.isfile(log_path):
            self.txt_log.setPlainText("Arquivo de log não encontrado:\n" + log_path)
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            self.txt_log.setPlainText(f"Erro ao abrir o log:\n{e}")
            return

        self.txt_log.setPlainText(content)
        self.txt_log.moveCursor(QtGui.QTextCursor.End)
