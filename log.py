"""Logging padrão: módulos logam via `logging`; a UI recebe via `UiHandler`."""

import logging

_ROOT_LEVEL = logging.INFO


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class UiHandler(logging.Handler):
    """Encaminha records de log para a UI (fila de eventos), como {"type": "log"}."""

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback({"type": "log", "message": record.getMessage()})
        except Exception:
            pass


def setup(callback) -> None:
    """Configura o root logger para encaminhar logs à UI via `callback`."""
    handler = UiHandler(callback)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.setLevel(_ROOT_LEVEL)
    root.addHandler(handler)
