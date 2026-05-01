from __future__ import annotations

import sys
import webbrowser

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget

from api import DesktopAPI
from storage import load_state, save_state


class LoginDialog(QDialog):
    def __init__(self, base_url: str, username: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Client SGI - Login")
        self.base_url_input = QLineEdit(base_url)
        self.username_input = QLineEdit(username)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.submit_btn = QPushButton("Entrar")
        self.submit_btn.clicked.connect(self.accept)

        form = QFormLayout()
        form.addRow("Base URL", self.base_url_input)
        form.addRow("Usuário", self.username_input)
        form.addRow("Senha", self.password_input)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.submit_btn)

    @property
    def credentials(self):
        return (
            self.base_url_input.text().strip(),
            self.username_input.text().strip(),
            self.password_input.text(),
        )


class MainWindow(QMainWindow):
    POLL_INTERVAL_MS = 30000

    def __init__(self):
        super().__init__()
        self.state = load_state()
        self.api = DesktopAPI(self.state.get("base_url", "https://sgi.seds.sp.gov.br"), self.state.get("token", ""))
        self.last_notification_id = int(self.state.get("since_id") or 0)
        self.pending_popup_id = None
        self.pending_popup_url = ""
        self.setWindowTitle("Client SGI")
        self.resize(520, 360)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setPlaceholderText("Nenhuma notificação recebida ainda.")

        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.addWidget(self.status_box)
        self.setCentralWidget(wrapper)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon())
        self.tray.setToolTip("Client SGI")
        self.tray.messageClicked.connect(self._on_tray_message_clicked)
        self.tray.activated.connect(self._on_tray_activated)
        self._build_tray_menu()
        self.tray.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_notifications)

        if not self.api.token:
            self.prompt_login()
        else:
            self.timer.start(self.POLL_INTERVAL_MS)
            self._append_status("Sessão restaurada.")

    def _build_tray_menu(self):
        menu = QMenu()
        open_action = QAction("Abrir", self)
        open_action.triggered.connect(self.showNormal)
        menu.addAction(open_action)

        refresh_action = QAction("Recarregar", self)
        refresh_action.triggered.connect(self.poll_notifications)
        menu.addAction(refresh_action)

        login_action = QAction("Login", self)
        login_action.triggered.connect(self.prompt_login)
        menu.addAction(login_action)

        logout_action = QAction("Sair da sessão", self)
        logout_action.triggered.connect(self.logout)
        menu.addAction(logout_action)

        exit_action = QAction("Fechar", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)

    def _append_status(self, text: str):
        existing = self.status_box.toPlainText().strip()
        chunk = text.strip()
        self.status_box.setPlainText(f"{chunk}\n\n{existing}".strip())

    def prompt_login(self):
        dialog = LoginDialog(
            self.state.get("base_url", "https://sgi.seds.sp.gov.br"),
            self.state.get("username", ""),
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        base_url, username, password = dialog.credentials
        try:
            self.api.base_url = base_url.rstrip("/")
            payload = self.api.login(username, password)
        except Exception as exc:
            QMessageBox.critical(self, "Falha no login", str(exc))
            return

        self.state["base_url"] = base_url
        self.state["token"] = payload["token"]
        self.state["username"] = username
        save_state(self.state)
        self.timer.start(self.POLL_INTERVAL_MS)
        self._append_status(f"Login realizado para {payload['user']['full_name']}.")
        self.poll_notifications()

    def logout(self):
        try:
            self.api.logout()
        except Exception:
            pass
        self.state["token"] = ""
        save_state(self.state)
        self.timer.stop()
        self._append_status("Sessão encerrada.")

    def poll_notifications(self):
        if not self.api.token:
            return
        try:
            notifications = self.api.list_notifications(self.last_notification_id)
        except Exception as exc:
            self._append_status(f"Offline ou erro de comunicação: {exc}")
            return

        if not notifications:
            return

        for item in sorted(notifications, key=lambda row: row["id"]):
            self.last_notification_id = max(self.last_notification_id, int(item["id"]))
            self.state["since_id"] = self.last_notification_id
            save_state(self.state)
            self._append_status(f"[{item['source_app']}] {item['title']}\n{item['body_short']}")
            self.pending_popup_id = item["id"]
            self.pending_popup_url = item["target_url"]
            self.tray.showMessage(item["title"], item["body_short"], QSystemTrayIcon.Information, 10000)
            try:
                self.api.mark_displayed(item["id"])
            except Exception:
                self._append_status(f"Falha ao marcar notificação {item['id']} como exibida.")

    def _on_tray_message_clicked(self):
        if not self.pending_popup_id:
            return
        try:
            webbrowser.open(self.pending_popup_url)
            self.api.mark_read(self.pending_popup_id)
            self._append_status(f"Notificação {self.pending_popup_id} aberta no navegador.")
        except Exception as exc:
            self._append_status(f"Falha ao abrir notificação: {exc}")
        finally:
            self.pending_popup_id = None
            self.pending_popup_url = ""

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("Client SGI", "O aplicativo continua em execução na bandeja.", QSystemTrayIcon.Information, 3000)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.setWindowFlag(Qt.WindowStaysOnTopHint, False)
    window.hide()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
