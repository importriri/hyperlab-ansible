"""Failures that a provider is allowed to have without taking the document down."""


class HyperlabError(Exception):
    """Base class. Carries an id so renderers can group problems."""

    problem_id = "hyperlab.error"
    severity = "error"

    def __init__(self, message, problem_id=None, severity=None):
        super().__init__(message)
        if problem_id is not None:
            self.problem_id = problem_id
        if severity is not None:
            self.severity = severity


class Unavailable(HyperlabError):
    """A source this provider needs is absent. The section degrades to null."""

    problem_id = "hyperlab.unavailable"
    severity = "warn"


class Missing(Unavailable):
    """The source genuinely does not exist, as opposed to could not be read.

    Only this subclass carries "absence" as information. A permission or I/O
    failure stays a plain Unavailable, so a provider that gives absence a
    meaning (trust: no claim this boot) can never mistake a read failure for
    it.
    """

    problem_id = "hyperlab.missing"


class ContractError(HyperlabError):
    """The repository contract says something this code cannot honour."""

    problem_id = "hyperlab.contract"
    severity = "error"
