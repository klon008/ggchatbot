from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .apply_bot import apply_bot
from .apply_frontend import apply_frontend
from .unpack import cleanup_tmp, unpack_zip
from .validate_pack import validate_pack, validate_roots

DEFAULT_BOT = r"E:\programs\OBS\botmsc"
DEFAULT_FE = r"E:\Work\dartvalkkiprincess\princtascdwk"


class ImporterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Series Pack Importer")
        self.resize(820, 640)
        self._zip: Path | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        form = QFormLayout()
        self.bot_edit = QLineEdit(DEFAULT_BOT)
        self.fe_edit = QLineEdit(DEFAULT_FE)
        form.addRow("Bot root (botmsc)", self.bot_edit)
        form.addRow("Frontend root (princtascdwk)", self.fe_edit)
        root.addLayout(form)

        row = QHBoxLayout()
        self.zip_label = QLabel("ZIP не выбран")
        self.zip_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        btn_zip = QPushButton("Выбрать ZIP…")
        btn_zip.clicked.connect(self._pick_zip)
        row.addWidget(btn_zip)
        row.addWidget(self.zip_label, 1)
        root.addLayout(row)

        self.chk_migrate = QCheckBox(
            "Применить migrate_db.py (остановить бота перед импортом)"
        )
        self.chk_migrate.setChecked(True)
        root.addWidget(self.chk_migrate)

        self.btn_import = QPushButton("Импортировать")
        self.btn_import.clicked.connect(self._run_import)
        root.addWidget(self.btn_import)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

        hint = QLabel(
            "После успеха: push фронта на GH Pages; в admin активируйте тираж (queued)."
        )
        hint.setStyleSheet("color:#8a9ab8;")
        hint.setWordWrap(True)
        root.addWidget(hint)

    def _append(self, msg: str) -> None:
        self.log.append(msg)

    def _pick_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Series pack ZIP", "", "ZIP (*.zip)"
        )
        if path:
            self._zip = Path(path)
            self.zip_label.setText(str(self._zip))

    def _run_import(self) -> None:
        try:
            self._import_safe()
        except Exception as exc:  # noqa: BLE001
            self._append(f"ERROR: {exc}")
            self._append(traceback.format_exc())
            QMessageBox.critical(self, "Ошибка импорта", str(exc))

    def _import_safe(self) -> None:
        if not self._zip or not self._zip.is_file():
            QMessageBox.warning(self, "ZIP", "Сначала выберите .zip")
            return

        bot_root = Path(self.bot_edit.text().strip())
        fe_root = Path(self.fe_edit.text().strip())
        errs = validate_roots(bot_root, fe_root)
        if errs:
            QMessageBox.warning(self, "Пути", "\n".join(errs))
            return

        tool_root = Path(__file__).resolve().parent.parent
        tmp_root = tool_root / "tmp"
        tmp_root.mkdir(exist_ok=True)

        self._append(f"Распаковка {self._zip.name} …")
        pack = unpack_zip(self._zip, tmp_root)
        self._append(f"tmp → {pack.root}")

        errs = validate_pack(pack, bot_root, fe_root)
        if errs:
            self._append("Preflight FAILED:")
            for e in errs:
                self._append(f"  • {e}")
            QMessageBox.warning(self, "Валидация пака", "\n".join(errs[:30]))
            return

        self._append("Preflight OK")
        apply_frontend(pack, fe_root, self._append)
        apply_bot(pack, bot_root, self.chk_migrate.isChecked(), self._append)
        cleanup_tmp(pack.root)
        self._append("Готово. Не забудьте git push фронта → GH Pages.")
        QMessageBox.information(
            self,
            "Импорт завершён",
            "Серия добавлена.\n\n"
            "1) Commit + push фронтенда (Pages)\n"
            "2) В cards-admin активируйте тираж",
        )


def main() -> int:
    import sys

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ImporterWindow()
    win.show()
    return app.exec()
