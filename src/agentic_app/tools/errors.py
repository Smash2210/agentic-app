"""Typed tool errors (spec 004 FR-403). A tool never raises these out of an agent run: the
resilience wrapper turns them into a result dict the model reads and can act on."""


class ToolError(Exception):
    retryable = False

    def __init__(self, tool: str, message: str):
        super().__init__(message)
        self.tool, self.message = tool, message

    def result(self, *, attempts: int, fallback: str) -> dict:
        return {
            "status": "error",
            "error": {"type": type(self).__name__, "tool": self.tool, "message": self.message,
                      "attempts": attempts, "retryable": self.retryable},
            "fallback": fallback,
        }


class ToolTimeout(ToolError):
    """The tool did not answer within its timeout."""
    retryable = True


class ToolUnavailable(ToolError):
    """The tool or a service behind it failed."""
    retryable = True


class ToolBadInput(ToolError):
    """The arguments are invalid (e.g. a claim that does not exist). Retrying will not help."""
