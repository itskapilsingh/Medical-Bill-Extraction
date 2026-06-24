import asyncio

from app.ai.retry import is_transient


# Stand-ins shaped like the OpenAI SDK's exceptions (matched by class name).
class RateLimitError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class _WithStatus(Exception):
    def __init__(self, status_code):
        super().__init__("boom")
        self.status_code = status_code


class _Named(Exception):
    """Lets us forge an exception with an arbitrary class name."""


def _named(cls_name: str) -> Exception:
    return type(cls_name, (_Named,), {})()


def test_named_transient_errors():
    assert is_transient(RateLimitError())
    assert is_transient(APITimeoutError())


def test_full_transient_name_set():
    # Every name the classifier treats as retryable (across SDK versions).
    for name in (
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "APIError",
    ):
        assert is_transient(_named(name)), name


def test_status_attribute_alias_is_honored():
    # Some SDK errors expose `status` rather than `status_code`.
    class _WithStatusAttr(Exception):
        status = 503

    assert is_transient(_WithStatusAttr())


def test_5xx_range_boundaries():
    assert is_transient(_WithStatus(500))
    assert is_transient(_WithStatus(599))
    assert not is_transient(_WithStatus(600))
    assert not is_transient(_WithStatus(499))


def test_builtin_transient_errors():
    assert is_transient(asyncio.TimeoutError())
    assert is_transient(TimeoutError())
    assert is_transient(ConnectionError())


def test_status_codes():
    assert is_transient(_WithStatus(429))      # rate limited
    assert is_transient(_WithStatus(503))      # service unavailable
    assert not is_transient(_WithStatus(400))  # bad request — fatal
    assert not is_transient(_WithStatus(404))


def test_fatal_errors_are_not_transient():
    assert not is_transient(ValueError("corrupt PDF"))
    assert not is_transient(FileNotFoundError("missing"))
    assert not is_transient(KeyError("bug"))
