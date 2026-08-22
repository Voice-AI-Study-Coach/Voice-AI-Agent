import sys
from types import ModuleType
from src.logger import logging

def error_message_detail(error, error_detail: ModuleType):
    _, _, exc_tb = error_detail.exc_info()
    # exc_info() only returns a real traceback from inside an `except` block.
    # CustomException is sometimes raised directly (no active exception to
    # wrap, e.g. "all keys are rate-limited"), in which case exc_tb is None -
    # fall back to just the message rather than crashing on tb_frame.
    if exc_tb is None:
        return f"Error: [{str(error)}]"
    file_name = exc_tb.tb_frame.f_code.co_filename
    error_message = "Error occured in filename [{0}] line number [{1}] and error is [{2}]".format(
        file_name, exc_tb.tb_lineno, str(error)
    )
    return error_message

class CustomException(Exception):
    def __init__(self, error, error_detail: ModuleType):
        super().__init__(error)
        self.error = error_message_detail(error, error_detail)
    def __str__(self):
        return self.error


class GradingException(CustomException):
    """Exception type for grading-related failures."""
    def __init__(self, error, error_detail: ModuleType = sys):
        super().__init__(error, error_detail)