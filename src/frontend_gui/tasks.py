"""One background operation at a time, with Qt-owned lifecycle and UI callbacks."""

from pathlib import Path
import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot

from frontend_common.jobs import Cancelled
from frontend_common.locking import workspace_lock


class TaskWorker(QThread):
    progress = Signal(str, int, bool)
    item = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function, log_directory: Path, parent: QObject):
        super().__init__(parent)
        self.function = function
        self.log_directory = log_directory

    def run(self):
        try:
            with workspace_lock(self.log_directory.parent):
                result = self.function(self)
        except Cancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            try:
                self.log_directory.mkdir(parents=True, exist_ok=True)
                with (self.log_directory / "desktop.log").open("a", encoding="utf-8") as handle:
                    handle.write(traceback.format_exc() + "\n")
            except OSError:
                pass
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)


class TaskHub(QObject):
    busy_changed = Signal(bool)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.worker = None
        self._result = None
        self._error = None
        self._on_item = None

    @property
    def busy(self):
        return self.worker is not None

    def start(self, function, feedback, on_result, on_item=None, on_error=None):
        if self.busy:
            feedback.finish("另一个操作正在进行，请等待完成后再试。")
            return False
        self._feedback, self._complete = feedback, on_result
        self._on_item, self._on_error = on_item, on_error
        self._result, self._error = None, None
        worker = TaskWorker(function, self.store.workspace / "logs", self)
        self.worker = worker
        worker.progress.connect(self._progress)
        worker.item.connect(self._item)
        worker.succeeded.connect(self._succeeded)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        self.busy_changed.emit(True)
        feedback.update_progress("准备操作…", 0)
        worker.start()
        return True

    @Slot(str, int, bool)
    def _progress(self, text, value, cancellable):
        self._feedback.update_progress(text, value, cancellable)

    @Slot(object)
    def _item(self, item):
        if self._on_item:
            self._on_item(item)

    @Slot(object)
    def _succeeded(self, result):
        self._result = result

    @Slot(str)
    def _failed(self, message):
        self._error = message

    @Slot()
    def _finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.busy_changed.emit(False)
        if self._error is not None:
            self._feedback.finish(self._error)
            if self._on_error:
                self._on_error(self._error)
        else:
            self._complete(self._result)

    def cancel(self):
        if self.worker is not None:
            self.worker.requestInterruption()

