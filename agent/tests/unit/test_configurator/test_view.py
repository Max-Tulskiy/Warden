"""The window itself, driven the way a person drives it, on Qt's offscreen platform.

The controller's behaviour is tested without a window; this checks that the
widgets show what it holds, that clicks reach it, that the dialogs offer the
right buttons, and that nothing a person reads is in another language.
"""

import asyncio
import json
import re

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
)

from warden_agent.configurator import messages, view
from warden_agent.configurator.__main__ import main
from warden_agent.configurator.backend import LocalBackend, ServiceState
from warden_agent.configurator.controller import WindowController
from warden_agent.configurator.paths import AgentPaths
from warden_agent.configurator.view import (
    ConfigWindow,
    QtExecutor,
    ReplaceDialog,
    TrustDialog,
)
from warden_agent.core.transport import FailureKind
from warden_agent.state import AgentState
from warden_agent.status import StatusStore

CODE = "s3cret-enrollment-token"
CYRILLIC = re.compile("[А-Яа-яЁё]")


class _SyncExecutor:
    def run(self, factory, on_done) -> None:
        try:
            result = asyncio.run(factory())
        except BaseException as exc:
            on_done(exc)
        else:
            on_done(result)


class _Backend(LocalBackend):
    def __init__(self, paths, *, elevated=True):
        super().__init__(paths)
        self.elevated = elevated
        self.restarts = 0

    def is_elevated(self) -> bool:
        return self.elevated

    def service_state(self) -> ServiceState:
        return ServiceState.RUNNING

    def restart_service(self) -> None:
        self.restarts += 1


@pytest.fixture
def paths(tmp_path) -> AgentPaths:
    return AgentPaths.for_directory(tmp_path)


@pytest.fixture
def server(tls_server):
    tls_server.on(
        "POST",
        "/api/v1/enroll",
        lambda request: (
            (201, {"agent_id": "a1", "agent_key": "k1"})
            if json.loads(request.body)["token"] == CODE
            else (400, {"detail": "bad"})
        ),
    )
    tls_server.on(
        "GET",
        "/api/v1/tls/ca",
        lambda _request: (200, {"pem": tls_server.authority_pem}),
    )
    return tls_server


def _window(qtbot, paths, *, elevated=True):
    controller = WindowController(_Backend(paths, elevated=elevated), _SyncExecutor())
    window = ConfigWindow(controller)
    qtbot.addWidget(window)
    window.show()
    return window, controller


def _visible_words(widget) -> list[str]:
    """Every text a person reads that is not a value the program fills in."""
    texts = [widget.windowTitle()]
    for group in widget.findChildren(QGroupBox):
        texts.append(group.title())
    for button in widget.findChildren(QPushButton):
        texts.append(button.text())
    for edit in widget.findChildren(QLineEdit):
        texts.append(edit.placeholderText())
    for label in widget.findChildren(QLabel):
        if not label.property("value") and label.isVisibleTo(widget):
            texts.append(label.text())
    return [text for text in texts if text.strip()]


def _click(qtbot, button) -> None:
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)


def test_the_window_opens_with_the_titles_and_the_configured_address(qtbot, paths):
    paths.config.write_text('server_url = "https://a.example"\n')

    window, _ = _window(qtbot, paths)

    assert window.windowTitle() == messages.WINDOW_TITLE
    assert window.address_field.text() == "https://a.example"
    assert window.token_field.echoMode() == QLineEdit.EchoMode.Password


def test_typing_and_pressing_connect_reaches_the_controller(qtbot, paths, server):
    window, controller = _window(qtbot, paths)

    window.address_field.setText(server.url)
    window.token_field.setText(CODE)

    assert controller.state.address == server.url
    assert controller.state.token == CODE
    assert window.connect_button.isEnabled()


def test_the_connect_button_waits_for_an_address(qtbot, paths):
    window, _ = _window(qtbot, paths)

    assert not window.connect_button.isEnabled()
    window.address_field.setText("https://a.example")
    assert window.connect_button.isEnabled()


def test_an_untrusted_server_opens_the_trust_dialog_with_the_fingerprint(
    qtbot, paths, server
):
    window, controller = _window(qtbot, paths)
    window.address_field.setText(server.url)
    window.token_field.setText(CODE)

    _click(qtbot, window.connect_button)

    qtbot.waitUntil(lambda: window.trust_dialog is not None)
    dialog = window.trust_dialog
    assert isinstance(dialog, TrustDialog)
    assert controller.state.pending_trust is not None
    shown = dialog.fingerprint_label.text().replace("\n", ":")
    assert shown == controller.state.pending_trust.fingerprint
    assert dialog.accept_button.text() == messages.BUTTON_TRUST_AND_CONNECT
    assert dialog.cancel_button.text() == messages.BUTTON_CANCEL


def test_accepting_in_the_dialog_connects_the_station(qtbot, paths, server):
    window, _ = _window(qtbot, paths)
    window.address_field.setText(server.url)
    window.token_field.setText(CODE)
    _click(qtbot, window.connect_button)
    qtbot.waitUntil(lambda: window.trust_dialog is not None)

    _click(qtbot, window.trust_dialog.accept_button)

    qtbot.waitUntil(lambda: AgentState.load(paths.state).is_enrolled)
    assert window.message_label.text() == messages.CONNECTED.format(server=server.url)
    assert window.token_field.text() == ""


def test_cancelling_the_dialog_stores_nothing_and_says_so(qtbot, paths, server):
    window, _ = _window(qtbot, paths)
    window.address_field.setText(server.url)
    window.token_field.setText(CODE)
    _click(qtbot, window.connect_button)
    qtbot.waitUntil(lambda: window.trust_dialog is not None)

    _click(qtbot, window.trust_dialog.cancel_button)

    assert window.message_label.text() == messages.TRUST_NOT_GIVEN
    assert not AgentState.load(paths.state).is_enrolled
    assert not paths.authority.exists()


def test_moving_an_enrolled_station_asks_for_confirmation_first(qtbot, paths, server):
    AgentState(
        agent_id="old", agent_key="oldkey", server_url="https://old.example"
    ).save(paths.state)
    window, _ = _window(qtbot, paths)
    window.address_field.setText(server.url)
    window.token_field.setText(CODE)

    _click(qtbot, window.connect_button)

    qtbot.waitUntil(lambda: window.replace_dialog is not None)
    dialog = window.replace_dialog
    assert isinstance(dialog, ReplaceDialog)
    assert "https://old.example" in dialog.text_label.text()
    assert dialog.accept_button.text() == messages.BUTTON_REPLACE
    _click(qtbot, dialog.cancel_button)
    assert AgentState.load(paths.state).agent_id == "old"


def test_without_administrator_rights_the_fields_are_disabled_and_a_banner_shows(
    qtbot, paths
):
    window, _ = _window(qtbot, paths, elevated=False)

    assert window.banner_label.isVisibleTo(window)
    assert window.banner_label.text() == messages.BANNER_NOT_ADMIN
    assert not window.address_field.isEnabled()
    assert not window.token_field.isEnabled()
    assert not window.connect_button.isEnabled()
    assert not window.check_button.isEnabled()


def test_the_state_block_shows_what_the_controller_read(qtbot, paths):
    AgentState(agent_id="a1", agent_key="k1", server_url="https://a.example").save(
        paths.state
    )
    StatusStore(paths.status).record_failure(FailureKind.UNREACHABLE)

    window, _ = _window(qtbot, paths)

    shown = {label.text() for label in window.findChildren(QLabel)}
    assert messages.STATION_ENROLLED.format(server="https://a.example") in shown
    assert messages.ERROR_UNREACHABLE in shown
    assert messages.LAST_CONTACT_NEVER in shown


def test_the_retrust_button_shows_only_when_the_server_cannot_be_verified(qtbot, paths):
    AgentState(agent_id="a1", agent_key="k1", server_url="https://a.example").save(
        paths.state
    )
    window, controller = _window(qtbot, paths)
    assert not window.retrust_button.isVisibleTo(window)

    StatusStore(paths.status).record_failure(FailureKind.CERTIFICATE_NOT_TRUSTED)
    controller.refresh()

    assert window.retrust_button.isVisibleTo(window)
    assert window.retrust_button.text() == messages.BUTTON_RETRUST


def test_everything_a_person_reads_is_in_russian(qtbot, paths, server):
    AgentState(agent_id="a1", agent_key="k1", server_url=server.url).save(paths.state)
    StatusStore(paths.status).record_failure(FailureKind.CERTIFICATE_NOT_TRUSTED)
    window, controller = _window(qtbot, paths)
    window.address_field.setText(server.url)

    latin_only = [w for w in _visible_words(window) if not CYRILLIC.search(w)]
    assert latin_only == []

    controller.begin_retrust()
    qtbot.waitUntil(lambda: window.trust_dialog is not None)
    dialog_latin = [
        w for w in _visible_words(window.trust_dialog) if not CYRILLIC.search(w)
    ]
    assert dialog_latin == []


def test_each_state_can_be_photographed(qtbot, paths, server, tmp_path):
    window, _ = _window(qtbot, paths)
    window.address_field.setText(server.url)
    window.token_field.setText(CODE)
    _click(qtbot, window.connect_button)
    qtbot.waitUntil(lambda: window.trust_dialog is not None)

    for name, widget in (("window", window), ("dialog", window.trust_dialog)):
        target = tmp_path / f"{name}.png"
        assert widget.grab().save(str(target))
        assert target.stat().st_size > 1000


def test_the_qt_executor_runs_work_off_the_interface_thread_and_reports_back(qtbot):
    executor = QtExecutor()
    results = []

    async def work():
        await asyncio.sleep(0)
        return 42

    executor.run(work, results.append)

    qtbot.waitUntil(lambda: results == [42])


def test_the_qt_executor_hands_over_a_failure_instead_of_losing_it(qtbot):
    executor = QtExecutor()
    results = []

    async def work():
        raise RuntimeError("boom")

    executor.run(work, results.append)

    qtbot.waitUntil(lambda: len(results) == 1)
    assert isinstance(results[0], RuntimeError)


def test_the_application_object_exists_for_every_test(qtbot):
    assert QApplication.instance() is not None


def test_gui_opens_the_window_over_the_folder_of_the_given_configuration(
    tmp_path, monkeypatch
):
    opened = []
    monkeypatch.setattr(view, "run_window", lambda backend: opened.append(backend) or 0)

    with pytest.raises(SystemExit) as finished:
        main(["--gui", "--config", str(tmp_path / "config.toml")])

    assert finished.value.code == 0
    assert opened[0].paths == AgentPaths.for_directory(tmp_path)


def test_the_selftest_builds_the_window_off_screen_and_leaves(tmp_path):
    assert view.run_selftest(LocalBackend(AgentPaths.for_directory(tmp_path))) == 0
