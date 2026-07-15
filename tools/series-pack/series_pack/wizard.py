from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .export import build_zip
from .image_proc import slug_guess_from_filename
from .models import (
    NAME_MAX,
    RARITIES,
    RARITY_COLORS,
    TELEGRAM_URL,
    TARGET_H,
    TARGET_W,
    BoosterDraft,
    CardDraft,
    DrawDraft,
    PackDraft,
    SeriesDraft,
)
from .validate import (
    validate_booster,
    validate_cards,
    validate_draw,
    validate_series,
    weights_percent_map,
)


def _show_errors(parent: QWidget, errs: list[str]) -> None:
    QMessageBox.warning(parent, "Проверьте поля", "\n".join(f"• {e}" for e in errs))


def _pil_to_pixmap(img: Image.Image, max_side: int = 120) -> QPixmap:
    rgb = img.convert("RGBA")
    rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    qimg = QImage.fromData(buf.getvalue(), "PNG")
    return QPixmap.fromImage(qimg)


class DropHint(QFrame):
    filesDropped = Signal(list)
    imagePasted = Signal(object)  # PIL Image

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 2px dashed #5a6a8a; border-radius: 10px; background: #12182a; }"
            "QLabel { color: #a8b4d0; }"
        )
        lay = QVBoxLayout(self)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        self.setMinimumHeight(100)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        md = event.mimeData()
        paths: list[Path] = []
        if md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    paths.append(Path(url.toLocalFile()))
        if paths:
            self.filesDropped.emit(paths)
        elif md.hasImage():
            qimg = md.imageData()
            if isinstance(qimg, QImage) and not qimg.isNull():
                self.imagePasted.emit(_qimage_to_pil(qimg))
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self._paste_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def _paste_clipboard(self):
        clip = QApplication.clipboard()
        md = clip.mimeData()
        if md.hasImage():
            qimg = clip.image()
            if not qimg.isNull():
                self.imagePasted.emit(_qimage_to_pil(qimg))
                return
        if md.hasUrls():
            paths = [Path(u.toLocalFile()) for u in md.urls() if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)


def _qimage_to_pil(qimg: QImage) -> Image.Image:
    qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.bits()
    arr = bytes(ptr)  # type: ignore[arg-type]
    return Image.frombuffer("RGBA", (w, h), arr, "raw", "RGBA", 0, 1).copy()


class StepSeries(QWidget):
    def __init__(self, draft: PackDraft):
        super().__init__()
        self.draft = draft
        form = QFormLayout(self)

        hint = QLabel(
            "series_id / card_back_id — латиница lower case, a-z 0-9 - _.\n"
            "Рубашка только .svg. Если исходник PNG/JPG — оберните в SVG "
            f"(viewBox / холст желательно {350}×{490}) и загрузите сюда."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a9ab8;")
        form.addRow(hint)

        self.series_id = QLineEdit()
        self.series_id.setPlaceholderText("classic")
        self.name = QLineEdit()
        self.name.setMaxLength(NAME_MAX)
        self.name.setPlaceholderText("Классический набор")
        self.card_back_id = QLineEdit()
        self.card_back_id.setPlaceholderText("card-back-classic")
        self.sort_order = QSpinBox()
        self.sort_order.setRange(0, 9999)
        self.sort_order.setValue(1)

        self.back_path_label = QLabel("файл не выбран")
        self.back_preview = QLabel()
        self.back_preview.setFixedSize(120, 168)
        self.back_preview.setStyleSheet("background:#0a0e18; border:1px solid #334;")
        self.back_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_back = QPushButton("Выбрать SVG…")
        btn_back.clicked.connect(self._pick_svg)

        form.addRow("series_id", self.series_id)
        form.addRow("Name", self.name)
        form.addRow("card_back_id", self.card_back_id)
        row = QHBoxLayout()
        row.addWidget(btn_back)
        row.addWidget(self.back_path_label, 1)
        form.addRow("card_back_image", row)
        form.addRow("Превью", self.back_preview)
        form.addRow("Порядок", self.sort_order)

    def _pick_svg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Рубашка SVG", "", "SVG (*.svg)"
        )
        if not path:
            return
        p = Path(path)
        self.draft.series.card_back_path = p
        self.back_path_label.setText(p.name)
        # SVG preview as text note (Qt doesn't render SVG without svg module easily)
        self.back_preview.setText("SVG\nOK")
        if not self.card_back_id.text().strip():
            stem = p.stem.lower()
            if stem.startswith("card-back"):
                self.card_back_id.setText(stem)

    def collect(self) -> SeriesDraft:
        s = self.draft.series
        s.series_id = self.series_id.text().strip().lower()
        s.name = self.name.text().strip()
        s.card_back_id = self.card_back_id.text().strip().lower()
        s.sort_order = int(self.sort_order.value())
        return s

    def validate(self) -> list[str]:
        self.collect()
        return validate_series(self.draft.series)


class CardRow(QFrame):
    removed = Signal(object)

    def __init__(self, card: CardDraft, parent=None):
        super().__init__(parent)
        self.card = card
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background:#151c2e; border-radius:8px; }")
        lay = QHBoxLayout(self)

        self.thumb = QLabel()
        self.thumb.setFixedSize(72, 72)
        self.thumb.setStyleSheet("background:#0a0e18;")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.thumb)

        form = QFormLayout()
        self.id_edit = QLineEdit(card.card_id)
        self.name_edit = QLineEdit(card.name)
        self.name_edit.setMaxLength(NAME_MAX)
        self.rarity = QComboBox()
        for r in RARITIES:
            self.rarity.addItem(r, r)
        idx = list(RARITIES).index(card.rarity) if card.rarity in RARITIES else 0
        self.rarity.setCurrentIndex(idx)
        self.rarity.currentIndexChanged.connect(self._paint_rarity)
        self.story = QTextEdit(card.story)
        self.story.setFixedHeight(70)
        form.addRow("id", self.id_edit)
        form.addRow("Имя", self.name_edit)
        form.addRow("Редкость", self.rarity)
        form.addRow("Описание", self.story)
        lay.addLayout(form, 1)

        btn_rm = QPushButton("✕")
        btn_rm.setFixedWidth(36)
        btn_rm.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(btn_rm)

        self._refresh_thumb()
        self._paint_rarity()

    def _paint_rarity(self):
        r = self.rarity.currentData()
        color = RARITY_COLORS.get(r, "#888")
        self.rarity.setStyleSheet(
            f"QComboBox {{ border: 2px solid {color}; color: {color}; font-weight: 600; padding: 4px; }}"
        )

    def _refresh_thumb(self):
        try:
            if self.card.paste_image is not None:
                img = self.card.paste_image
            elif self.card.source_path:
                img = Image.open(self.card.source_path)
            else:
                self.thumb.setText("?")
                return
            self.thumb.setPixmap(_pil_to_pixmap(img, 72))
        except Exception:
            self.thumb.setText("err")

    def sync_to_draft(self):
        self.card.card_id = self.id_edit.text().strip().lower()
        self.card.name = self.name_edit.text().strip()
        self.card.rarity = self.rarity.currentData()
        self.card.story = self.story.toPlainText().strip()


class StepCards(QWidget):
    def __init__(self, draft: PackDraft):
        super().__init__()
        self.draft = draft
        self.rows: list[CardRow] = []

        root = QVBoxLayout(self)
        instr = QLabel(
            f"Картинки будут преобразованы в WebP {TARGET_W}×{TARGET_H} "
            "(cover/crop по центру, без прозрачности). "
            "Добавляйте пачкой (DnD / Ctrl+V / файлы), затем заполните id, имя, редкость и описание. "
            "Все поля обязательны. Id должен быть уникален внутри пакета "
            "(занятый в уже существующих сериях id лучше не использовать — "
            "запись миграции потом может быть проигнорирована)."
        )
        instr.setWordWrap(True)
        instr.setStyleSheet("color:#8a9ab8;")
        root.addWidget(instr)

        self.drop = DropHint(
            "Перетащите изображения сюда\nили кликните и нажмите Ctrl+V\nили «Добавить файлы»"
        )
        self.drop.filesDropped.connect(self.add_files)
        self.drop.imagePasted.connect(self.add_paste)
        root.addWidget(self.drop)

        btns = QHBoxLayout()
        b_add = QPushButton("Добавить файлы…")
        b_add.clicked.connect(self._pick_files)
        b_clear = QPushButton("Очистить список")
        b_clear.clicked.connect(self.clear_all)
        btns.addWidget(b_add)
        btns.addWidget(b_clear)
        btns.addStretch()
        root.addLayout(btns)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.addStretch()
        scroll.setWidget(self.list_host)
        root.addWidget(scroll, 1)

        self.count_label = QLabel("Карт: 0")
        root.addWidget(self.count_label)

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Карты",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if paths:
            self.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]):
        for p in paths:
            if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                continue
            try:
                with Image.open(p) as im:
                    im.load()
            except Exception:
                QMessageBox.warning(self, "Битый файл", f"Не удалось прочитать:\n{p}")
                continue
            guess = slug_guess_from_filename(p)
            card = CardDraft(source_path=p, card_id=guess, name="", rarity="common", story="")
            self._append_row(card)

    def add_paste(self, img: Image.Image):
        card = CardDraft(
            source_path=None,
            paste_image=img.copy(),
            card_id="",
            name="",
            rarity="common",
            story="",
        )
        self._append_row(card)

    def _append_row(self, card: CardDraft):
        self.draft.cards.append(card)
        row = CardRow(card)
        row.removed.connect(self._remove_row)
        self.rows.append(row)
        self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self._update_count()

    def _remove_row(self, row: CardRow):
        if row in self.rows:
            self.rows.remove(row)
        if row.card in self.draft.cards:
            self.draft.cards.remove(row.card)
        row.setParent(None)
        row.deleteLater()
        self._update_count()

    def clear_all(self):
        for row in list(self.rows):
            self._remove_row(row)

    def _update_count(self):
        self.count_label.setText(f"Карт: {len(self.rows)}")

    def collect(self):
        for row in self.rows:
            row.sync_to_draft()

    def validate(self) -> list[str]:
        self.collect()
        return validate_cards(self.draft.cards)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.drop._paste_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)


class StepBooster(QWidget):
    def __init__(self, draft: PackDraft):
        super().__init__()
        self.draft = draft
        form = QFormLayout(self)
        hint = QLabel(
            "id бустера — латиница. Убедитесь, что такого бустера ещё нет в prod "
            "(этот UI в БД не пишет; конфликт поймает миграция на вашей стороне)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a9ab8;")
        form.addRow(hint)
        self.booster_id = QLineEdit()
        self.name = QLineEdit()
        self.name.setMaxLength(NAME_MAX)
        self.promo = QLineEdit()
        self.promo.setPlaceholderText("https://… или пусто")
        form.addRow("id", self.booster_id)
        form.addRow("Название", self.name)
        form.addRow("Promo URL", self.promo)

    def prefill_from_series(self):
        s = self.draft.series
        if not self.booster_id.text().strip():
            self.booster_id.setText(s.series_id)
        if not self.name.text().strip():
            self.name.setText(s.name)

    def collect(self) -> BoosterDraft:
        b = self.draft.booster
        b.booster_id = self.booster_id.text().strip().lower()
        b.name = self.name.text().strip()
        b.promo_image_url = self.promo.text().strip()
        return b

    def validate(self) -> list[str]:
        self.collect()
        return validate_booster(self.draft.booster)


class StepDraw(QWidget):
    def __init__(self, draft: PackDraft):
        super().__init__()
        self.draft = draft
        root = QVBoxLayout(self)
        hint = QLabel(
            "Шансы редкости: относительные веса (сумма не обязана быть 100). "
            "Проценты справа — для наглядности, как в cards-admin → Тиражи."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a9ab8;")
        root.addWidget(hint)

        form = QFormLayout()
        self.draw_id = QLineEdit()
        self.name = QLineEdit(self.draft.draw.name)
        self.cost = QSpinBox()
        self.cost.setRange(1, 10_000_000)
        self.cost.setValue(self.draft.draw.cost_points)
        self.cards_n = QSpinBox()
        self.cards_n.setRange(1, 50)
        self.cards_n.setValue(self.draft.draw.cards_per_open)
        self.limit = QSpinBox()
        self.limit.setRange(0, 10_000)
        self.limit.setValue(self.draft.draw.daily_limit)
        form.addRow("id", self.draw_id)
        form.addRow("Название", self.name)
        form.addRow("Цена (поинты)", self.cost)
        form.addRow("Карт за открытие", self.cards_n)
        form.addRow("Дневной лимит (0 = без)", self.limit)
        root.addLayout(form)

        root.addWidget(QLabel("Шансы редкости"))
        self.weight_spins: dict[str, QDoubleSpinBox] = {}
        self.pct_labels: dict[str, QLabel] = {}
        grid = QVBoxLayout()
        for r in RARITIES:
            row = QHBoxLayout()
            lab = QLabel(r)
            lab.setFixedWidth(100)
            color = RARITY_COLORS[r]
            lab.setStyleSheet(f"color:{color}; font-weight:600;")
            spin = QDoubleSpinBox()
            spin.setRange(0, 10_000)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setValue(float(self.draft.draw.rarity_weights.get(r, 0)))
            spin.valueChanged.connect(self._refresh_pct)
            pct = QLabel("0.0%")
            pct.setFixedWidth(64)
            self.weight_spins[r] = spin
            self.pct_labels[r] = pct
            row.addWidget(lab)
            row.addWidget(spin)
            row.addWidget(pct)
            row.addStretch()
            grid.addLayout(row)
        root.addLayout(grid)
        root.addStretch()
        self._refresh_pct()

    def prefill_from_series(self):
        s = self.draft.series
        if not self.draw_id.text().strip():
            self.draw_id.setText(f"draw-{s.series_id}-001")
        # zero weights for rarities not present in pack
        present = {c.rarity for c in self.draft.cards}
        for r, spin in self.weight_spins.items():
            if r not in present and spin.value() > 0:
                # keep defaults but user sees validation; optional soft zero:
                pass
        self._refresh_pct()

    def _refresh_pct(self):
        weights = {r: float(self.weight_spins[r].value()) for r in RARITIES}
        pct = weights_percent_map(weights)
        for r in RARITIES:
            self.pct_labels[r].setText(f"{pct[r]}%")

    def collect(self) -> DrawDraft:
        d = self.draft.draw
        d.draw_id = self.draw_id.text().strip().lower()
        d.name = self.name.text().strip()
        d.cost_points = int(self.cost.value())
        d.cards_per_open = int(self.cards_n.value())
        d.daily_limit = int(self.limit.value())
        d.rarity_weights = {r: float(self.weight_spins[r].value()) for r in RARITIES}
        d.status = "queued"
        return d

    def validate(self) -> list[str]:
        self.collect()
        rarities = {c.rarity for c in self.draft.cards}
        return validate_draw(self.draft.draw, rarities)


class StepDone(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.title = QLabel("Процесс упаковывания завершён!")
        self.title.setStyleSheet("font-size:18px; font-weight:700; color:#F0D060;")
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.tg = QLabel(
            f'Отправьте архив на <a href="{TELEGRAM_URL}">{TELEGRAM_URL}</a>'
        )
        self.tg.setOpenExternalLinks(True)
        self.tg.setTextFormat(Qt.TextFormat.RichText)
        btn_open = QPushButton("Открыть папку с архивом")
        btn_open.clicked.connect(self._open_folder)
        btn_tg = QPushButton("Открыть Telegram")
        btn_tg.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TELEGRAM_URL)))
        lay.addWidget(self.title)
        lay.addWidget(self.path_label)
        lay.addWidget(self.tg)
        lay.addWidget(btn_open)
        lay.addWidget(btn_tg)
        lay.addStretch()
        self._zip_path: Path | None = None

    def set_result(self, zip_path: Path):
        self._zip_path = zip_path
        self.path_label.setText(f"Архив:\n{zip_path}")

    def _open_folder(self):
        if self._zip_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._zip_path.parent)))


class Wizard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Series Pack — упаковка серии карт")
        self.resize(920, 720)
        self.draft = PackDraft()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self.step_label = QLabel("Шаг 1 / 4 — Серия")
        self.step_label.setStyleSheet("font-size:15px; font-weight:600;")
        root.addWidget(self.step_label)

        self.stack = QStackedWidget()
        self.step1 = StepSeries(self.draft)
        self.step2 = StepCards(self.draft)
        self.step3 = StepBooster(self.draft)
        self.step4 = StepDraw(self.draft)
        self.step_done = StepDone()
        for w in (self.step1, self.step2, self.step3, self.step4, self.step_done):
            self.stack.addWidget(w)
        root.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        self.btn_back = QPushButton("Назад")
        self.btn_next = QPushButton("Далее")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_next.clicked.connect(self.go_next)
        nav.addWidget(self.btn_back)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        root.addLayout(nav)
        self._sync_nav()

    def _sync_nav(self):
        i = self.stack.currentIndex()
        titles = [
            "Шаг 1 / 4 — Серия",
            "Шаг 2 / 4 — Карточки",
            "Шаг 3 / 4 — Бустер",
            "Шаг 4 / 4 — Тираж",
            "Готово",
        ]
        self.step_label.setText(titles[i])
        self.btn_back.setEnabled(i > 0 and i < 4)
        if i >= 4:
            self.btn_next.setText("Закрыть")
        elif i == 3:
            self.btn_next.setText("Упаковать ZIP")
        else:
            self.btn_next.setText("Далее")

    def go_back(self):
        i = self.stack.currentIndex()
        if i > 0 and i < 4:
            self.stack.setCurrentIndex(i - 1)
            self._sync_nav()

    def go_next(self):
        i = self.stack.currentIndex()
        if i >= 4:
            self.close()
            return

        validators = [
            self.step1.validate,
            self.step2.validate,
            self.step3.validate,
            self.step4.validate,
        ]
        errs = validators[i]()
        if errs:
            _show_errors(self, errs)
            return

        if i == 3:
            try:
                zip_path = build_zip(self.draft)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Ошибка упаковки", str(exc))
                return
            self.step_done.set_result(zip_path)
            self.stack.setCurrentIndex(4)
            self._sync_nav()
            return

        nxt = i + 1
        if nxt == 2:
            self.step3.prefill_from_series()
        if nxt == 3:
            self.step2.collect()
            self.step4.prefill_from_series()
        self.stack.setCurrentIndex(nxt)
        self._sync_nav()


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = Wizard()
    win.show()
    return app.exec()
