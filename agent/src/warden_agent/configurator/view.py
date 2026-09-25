"""The connection window, in PySide6.

Thin over `WindowController`: it draws what the controller holds, forwards
clicks to it, and asks its questions in dialogs. Every text comes from
`messages`, and Qt's own standard buttons are never used, so nothing depends on
Qt's translation files. This is the only module that imports Qt.
"""

import asyncio
import itertools
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from warden_agent.configurator import messages
from warden_agent.configurator.backend import Backend
from warden_agent.configurator.controller import WindowController
from warden_agent.configurator.logic import TrustOffer

_ERROR_STYLE = "color: #b00020"
_BANNER_STYLE = "background: #fff4ce; color: #5c4300; padding: 6px"


class _Job(QThread):
    """One coroutine on its own thread and event loop."""

    done = Signal(int, object)

    def __init__(
        self,
        job_id: int,
        factory: Callable[[], Awaitable[Any]],
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self._factory = factory

    def run(self) -> None:
        try:
            result: Any = asyncio.run(self._factory())  # type: ignore[arg-type]
        except BaseException as exc:  # handed to the controller, never lost
            result = exc
        self.done.emit(self._job_id, result)


class QtExecutor(QObject):
    """Runs the controller's slow work off the interface thread.

    The result comes back through a signal, which Qt queues onto the thread this
    object lives in, so `on_done` always runs on the interface's own thread.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._jobs: dict[int, tuple[_Job, Callable[[Any], None]]] = {}
        self._ids = itertools.count()

    def run(
        self, factory: Callable[[], Awaitable[Any]], on_done: Callable[[Any], None]
    ) -> None:
        job_id = next(self._ids)
        job = _Job(job_id, factory, self)
        self._jobs[job_id] = (job, on_done)
        job.done.connect(self._deliver)
        job.start()

    @Slot(int, object)
    def _deliver(self, job_id: int, result: Any) -> None:
        job, on_done = self._jobs.pop(job_id)
        job.wait()
        job.deleteLater()
        on_done(result)


def _two_lines(fingerprint: str) -> str:
    """A 95-character fingerprint does not fit a dialog; halve it at a colon."""
    pairs = fingerprint.split(":")
    middle = len(pairs) // 2
    return ":".join(pairs[:middle]) + "\n" + ":".join(pairs[middle:])


def _value_label(text: str = "") -> QLabel:
    """A label showing something the program fills in, not text to be translated."""
    label = QLabel(text)
    label.setProperty("value", True)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class _QuestionDialog(QDialog):
    """A dialog with a heading, a body, and two buttons of the caller's wording."""

    def __init__(self, title: str, accept_text: str, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(messages.WINDOW_TITLE)
        self.setMinimumWidth(480)
        self.layout_ = QVBoxLayout(self)
        heading = QLabel(title)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setWordWrap(True)
        self.layout_.addWidget(heading)
        self.accept_button = QPushButton(accept_text)
        self.cancel_button = QPushButton(messages.BUTTON_CANCEL)
        self.accept_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def _add_buttons(self) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.accept_button)
        row.addWidget(self.cancel_button)
        self.layout_.addLayout(row)
        self.cancel_button.setDefault(True)


class TrustDialog(_QuestionDialog):
    """Shows an authority on offer, and asks whether to trust it."""

    def __init__(
        self, offer: TrustOffer, *, retrust: bool, parent: QWidget | None = None
    ) -> None:
        accept_text = (
            messages.BUTTON_TRUST if retrust else messages.BUTTON_TRUST_AND_CONNECT
        )
        super().__init__(messages.TRUST_TITLE, accept_text, parent)
        intro = QLabel(messages.TRUST_INTRO)
        intro.setWordWrap(True)
        self.layout_.addWidget(intro)

        form = QFormLayout()
        self.fingerprint_label = _value_label(_two_lines(offer.fingerprint))
        self.fingerprint_label.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        form.addRow(messages.TRUST_ISSUER, _value_label(offer.subject))
        form.addRow(
            messages.TRUST_VALID_UNTIL,
            _value_label(offer.not_after.astimezone().strftime("%d.%m.%Y")),
        )
        form.addRow(messages.TRUST_FINGERPRINT, self.fingerprint_label)
        self.layout_.addLayout(form)
        self._add_buttons()


class ReplaceDialog(_QuestionDialog):
    """Asks whether to move an enrolled station to another server."""

    def __init__(self, current_server: str, parent: QWidget | None = None) -> None:
        super().__init__(messages.REPLACE_TITLE, messages.BUTTON_REPLACE, parent)
        self.text_label = QLabel(messages.REPLACE_TEXT.format(current=current_server))
        self.text_label.setWordWrap(True)
        self.layout_.addWidget(self.text_label)
        self._add_buttons()


class ConfigWindow(QMainWindow):
    """Draws the controller's state and forwards what the person does."""

    def __init__(self, controller: WindowController) -> None:
        super().__init__()
        self._controller = controller
        self.trust_dialog: TrustDialog | None = None
        self.replace_dialog: ReplaceDialog | None = None
        self.setWindowTitle(messages.WINDOW_TITLE)
        self.setMinimumWidth(560)

        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        self.banner_label.setStyleSheet(_BANNER_STYLE)

        self.address_field = QLineEdit()
        self.address_field.setPlaceholderText(messages.PLACEHOLDER_ADDRESS)
        self.token_field = QLineEdit()
        self.token_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.check_button = QPushButton(messages.BUTTON_CHECK)
        self.connect_button = QPushButton(messages.BUTTON_CONNECT)
        self.connect_button.setDefault(True)

        connection = QGroupBox(messages.GROUP_CONNECTION)
        form = QFormLayout(connection)
        form.addRow(messages.LABEL_SERVER, self.address_field)
        form.addRow(messages.LABEL_ENROLLMENT, self.token_field)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.connect_button)
        form.addRow(buttons)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        state = QGroupBox(messages.GROUP_STATE)
        state_layout = QVBoxLayout(state)
        self._state_form = QFormLayout()
        state_layout.addLayout(self._state_form)
        self.retrust_button = QPushButton(messages.BUTTON_RETRUST)
        state_layout.addWidget(self.retrust_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.banner_label)
        layout.addWidget(connection)
        layout.addWidget(self.message_label)
        layout.addWidget(state)
        layout.addStretch(1)
        self.setCentralWidget(central)

        self.address_field.textChanged.connect(controller.set_address)
        self.token_field.textChanged.connect(controller.set_token)
        self.check_button.clicked.connect(controller.check)
        self.connect_button.clicked.connect(controller.connect)
        self.retrust_button.clicked.connect(controller.begin_retrust)
        controller.subscribe(self._render)
        self._render()

    def _render(self) -> None:
        state = self._controller.state
        self._show(self.address_field, state.address)
        self._show(self.token_field, state.token)
        self.banner_label.setText(state.banner or "")
        self.banner_label.setVisible(state.banner is not None)
        self.address_field.setEnabled(state.fields_enabled)
        self.token_field.setEnabled(state.fields_enabled)
        self.check_button.setEnabled(state.can_connect)
        self.connect_button.setEnabled(state.can_connect)
        self.message_label.setText(state.message)
        self.message_label.setVisible(bool(state.message))
        self.message_label.setStyleSheet(_ERROR_STYLE if state.message_is_error else "")
        self.retrust_button.setVisible(state.offers_retrust)
        self.retrust_button.setEnabled(state.fields_enabled)
        self._draw_state_rows(state.status_lines)
        self.setCursor(
            Qt.CursorShape.WaitCursor if state.busy else Qt.CursorShape.ArrowCursor
        )
        if state.pending_trust is not None and self.trust_dialog is None:
            self._ask_trust(state.pending_trust, retrust=state.trust_for == "retrust")
        if state.pending_replace is not None and self.replace_dialog is None:
            self._ask_replace(state.pending_replace)

    @staticmethod
    def _show(field: QLineEdit, text: str) -> None:
        if field.text() != text:
            field.blockSignals(True)
            field.setText(text)
            field.blockSignals(False)

    def _draw_state_rows(self, lines: list[tuple[str, str]]) -> None:
        while self._state_form.rowCount():
            self._state_form.removeRow(0)
        for label, value in lines:
            self._state_form.addRow(label, _value_label(value))

    def _ask_trust(self, offer: TrustOffer, *, retrust: bool) -> None:
        dialog = TrustDialog(offer, retrust=retrust, parent=self)
        self.trust_dialog = dialog
        dialog.accepted.connect(lambda: self._trust_answered(True))
        dialog.rejected.connect(lambda: self._trust_answered(False))
        dialog.open()

    def _trust_answered(self, accepted: bool) -> None:
        dialog = self.trust_dialog
        self._controller.answer_trust(accepted)
        self.trust_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _ask_replace(self, current_server: str) -> None:
        dialog = ReplaceDialog(current_server, parent=self)
        self.replace_dialog = dialog
        dialog.accepted.connect(lambda: self._replace_answered(True))
        dialog.rejected.connect(lambda: self._replace_answered(False))
        dialog.open()

    def _replace_answered(self, accepted: bool) -> None:
        dialog = self.replace_dialog
        self._controller.answer_replace(accepted)
        self.replace_dialog = None
        if dialog is not None:
            dialog.deleteLater()


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    if not isinstance(app, QApplication):
        raise RuntimeError("a Qt application without widgets is already running")
    return app


def run_window(backend: Backend) -> int:
    """Open the window and run until it is closed."""
    app = _application()
    controller = WindowController(backend, QtExecutor())
    window = ConfigWindow(controller)
    window.show()
    return app.exec()


def run_selftest(backend: Backend) -> int:
    """Build the window off screen and leave: proves a frozen build can start."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = _application()
    window = ConfigWindow(WindowController(backend, QtExecutor()))
    window.show()
    app.processEvents()
    window.close()
    return 0
