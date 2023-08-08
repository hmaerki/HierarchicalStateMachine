import collections
import dataclasses
import enum
import inspect
import io
import itertools
import pathlib
import types
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

__version__ = "1.0.2"


class _Verb(enum.Enum):
    STATE = "state_"
    INIT = "init_"
    ENTRY = "entry_"
    EXIT = "exit_"

    def __str__(self) -> str:
        return self.value


_MERMAID_INDENT = "    "

LogFunction = Callable[[str], None]
StateChangeFunction = Callable[["HsmState", "HsmState"], None]

SignalType = Any
"""
We only require the __str__ method of the signal.
Therefore, the signal may be of any type.
"""
StateType = Callable[[SignalType], None]
EntryType = StateType
ExitType = StateType

_HSM_INIT_INITSTATE = "hsm_init"


class StateChangeException(Exception):
    def __init__(self, fn_new_state: Callable, why: str = None):
        assert isinstance(fn_new_state, types.MethodType)
        assert isinstance(why, (type(None), str))
        Exception.__init__(self, f"New state is: {fn_new_state.__name__}")
        self.fn_new_state = fn_new_state
        self.why = why


class IgnoreEventException(Exception):
    def __init__(self, why: str = None):
        assert isinstance(why, (type(None), str))
        self.why = why


class DontChangeStateException(Exception):
    pass


class BadStatemachineException(Exception):
    def __init__(self, msg: str):
        Exception.__init__(self, msg)


class BadStateException(Exception):
    pass


def _assert_is_func_or_method(f: Callable, expected_python_type=types.FunctionType):
    assert_python = isinstance(f, expected_python_type)
    assert_cython = f.__class__.__name__ == "cython_function_or_method"
    assert assert_python or assert_cython


def init_state(f: Callable[[Any, SignalType], Any]) -> Callable[[Any, SignalType], Any]:
    """
    Decorator for the init state
    """
    _assert_is_func_or_method(f)

    err = f"'{f.__name__}()' does NOT start with '{_Verb.STATE.value}'. It may not be a init_state!"
    if not f.__name__.startswith(_Verb.STATE.value):
        raise BadStatemachineException(err)
    setattr(f, _HSM_INIT_INITSTATE, True)
    return f


@dataclasses.dataclass(frozen=True, repr=True)
class _Transition:
    when: str
    state_from: "HsmState" = dataclasses.field(repr=False)
    state_to: "HsmState" = dataclasses.field(repr=False)

    def link(self) -> None:
        self.state_from.transitions_from.append(self)
        self.state_to.transitions_to.append(self)

    @staticmethod
    def parse_docstring(state: "HsmState", doc: Optional[str]) -> None:
        """
        Parse the docstring.
        Lines line 'TRANSITION state_0_2_2 time > 0' will create
        a '_Transition()' object which will be attached to both states.
        """
        if doc is None:
            return
        tag_transition = "TRANSITION "
        tag_exit = "EXIT "
        for line in doc.split("\n"):
            line = line.strip()
            # Example line: 'TRANSITION state_0_2_2 time > 0'
            if line.startswith(tag_transition):
                line = line[len(tag_transition) :]
                fn_name, _, when = line.partition(" ")
                state_to = state.hsm.find_state_by_name(fn_name=fn_name)
                transition = _Transition(state_to=state_to, state_from=state, when=when)
                transition.link()
                continue

            if line.startswith(tag_exit):
                when = line[len(tag_exit) :]
                state.exit_when = when
                continue


@dataclasses.dataclass(repr=True)
class HsmState:
    hsm: "HsmMixin"
    name: str = None
    outer_state: "HsmState" = None
    fn_state: StateType = None
    fn_entry: EntryType = None
    fn_exit: ExitType = None
    init_state: "HsmState" = None
    substates: Dict[str, "HsmState"] = dataclasses.field(
        default_factory=collections.OrderedDict
    )
    transitions_from: List[_Transition] = dataclasses.field(default_factory=list)
    transitions_to: List[_Transition] = dataclasses.field(default_factory=list)
    exit_when: str = None

    def assert_consistency(self) -> None:
        assert isinstance(self.name, (type(None), str))
        assert isinstance(self.outer_state, (type(None), HsmState))
        assert isinstance(self.fn_state, (type(None), types.MethodType))
        assert isinstance(self.fn_entry, (type(None), types.MethodType))
        assert isinstance(self.fn_exit, (type(None), types.MethodType))
        assert isinstance(self.init_state, (type(None), HsmState))
        for substate_name, substate in self.substates.items():
            assert isinstance(substate_name, str)
            assert isinstance(substate, HsmState)
        for transition in self.transitions_from:
            assert isinstance(transition, _Transition)
        for transition in self.transitions_to:
            assert isinstance(transition, _Transition)

    def assert_loose_state(self) -> None:
        if self.outer_state is None:
            # This is the top state
            return
        if self.fn_state is None:
            raise BadStatemachineException(
                f"Missing '{_Verb.STATE.value}{self.full_name}()'!"
            )

    def resolve_init_state(self) -> "HsmState":
        if self.init_state is None:
            return self
        return self.init_state.resolve_init_state()

    @property
    def full_name(self) -> str:
        return "_".join(self.path)

    @property
    def mermaid_visible_name(self) -> str:
        "The name including spaces"
        if self.hsm._mermaid_detailed:
            return f"State {self.name} ({self.full_name})"
        return self.name

    @property
    def mermaid_tag(self) -> str:
        "The tag referencing a state"
        return self.full_name

    def define_init_state(self) -> None:
        if len(self.substates) == 0:
            assert self.init_state is None
            return

        if len(self.substates) == 1:
            # If the is exactly one substate: This is the init-state!
            for substate in self.substates.values():
                self.init_state = substate
                return
            assert False, "Never gets here!"

        # More than one substate. Exactly one must be decorated with "@hsm.init_state"
        for substate in self.substates.values():
            if hasattr(substate.fn_state, _HSM_INIT_INITSTATE):
                if self.init_state is not None:
                    raise BadStatemachineException("Only one init_state allowed!")
                self.init_state = substate

        assert self.init_state is not None

    def find_state(self, name: str, error_if_not_exists: str = None) -> "HsmState":
        """
        Find state.
        Create state if it does not exist.
        """
        try:
            return self.substates[name]
        except KeyError:
            if error_if_not_exists is not None:
                raise BadStatemachineException(  # pylint: disable=raise-missing-from,broad-exception-raised
                    error_if_not_exists
                )
            sub_state = HsmState(
                hsm=self.hsm,
                name=name,
                outer_state=self,
            )
            self.substates[name] = sub_state
            return sub_state

    @staticmethod
    def fn_name_to_path(verb: _Verb, fn_name: str) -> List[str]:
        """
        Return None: if not starting with verb
        Return [List]
        """
        assert isinstance(verb, _Verb)
        if not fn_name.startswith(verb.value):
            return None
        return fn_name[len(verb.value) :].split("_")

    @property
    def path(self) -> List[str]:
        if self.outer_state is None:
            return []
        return self.outer_state.path + [self.name]

    @property
    def is_init_state(self) -> bool:
        return self.outer_state.init_state is self

    def iter_states(self) -> Iterable["HsmState"]:
        yield self
        for substate in self.substates.values():
            yield from substate.iter_states()

    def list_states(self) -> List["HsmState"]:
        """
        This method is tolerant to changes in the list while processing it
        """
        return list(self.iter_states())

    def parse_transitions_from_docstring(self) -> None:
        doc = self.fn_state.__doc__
        _Transition.parse_docstring(state=self, doc=doc)

    def render_mermaid(self, f) -> None:
        def add_note(text: str) -> None:
            f.write(f"{indent}note right of {self.mermaid_tag}\n")
            for line in text.split("\n"):
                f.write(f"{indent}   {line}\n")
            f.write(f"{indent}end note\n")

        def add_note_for_entry_exit(fn: StateType, tag: str):
            if fn is None:
                return
            doc = fn.__doc__
            if doc is None:
                doc = "..."
            add_note(f"on {tag}:\n{doc}")

        def render_entry_exit() -> None:
            if self.exit_when is not None:
                f.write(f"{indent}{self.mermaid_tag} --> [*]: {self.exit_when}\n")

            if self.hsm._mermaid_entryexit:
                add_note_for_entry_exit(fn=self.fn_entry, tag="entry")
                add_note_for_entry_exit(fn=self.fn_exit, tag="exit")

        path = self.path
        indent = _MERMAID_INDENT * len(path)
        if len(self.substates) > 0:
            if self.name is not None:
                f.write(f"{indent}{self.mermaid_tag}: {self.mermaid_visible_name}\n")
                f.write(f"{indent}state {self.mermaid_tag} {{\n")
            for i, substate in zip(itertools.count(), self.substates.values()):
                if i > 0:
                    f.write("\n")
                substate.render_mermaid(f=f)
            assert (
                self.init_state is not None
            ), f"No init_state for substate of {self.full_name}"
            f.write(f"{_MERMAID_INDENT}{indent}[*] --> {self.init_state.mermaid_tag}\n")
            if self.name is not None:
                f.write(f"{indent}}}\n")
            render_entry_exit()
            return

        f.write(f"{indent}{self.mermaid_tag}: {self.mermaid_visible_name}\n")
        f.write(f"{indent}state {self.mermaid_tag}\n")

        if not self.is_init_state:
            # Bugfix mermaid: Add at least one transistion - if not, mermaid will swallow the state
            if len(self.transitions_from) + len(self.transitions_to) == 0:
                f.write(f"{indent}{self.mermaid_tag} --> {self.mermaid_tag}: Dummy\n")
        render_entry_exit()

    def render_mermaid_transitions(self, f) -> None:
        f.write(f"\n{_MERMAID_INDENT}%% Transitions\n")
        for state in self.iter_states():
            for transition_from in state.transitions_from:
                f.write(
                    f"{_MERMAID_INDENT}{state.mermaid_tag} --> {transition_from.state_to.mermaid_tag}: {transition_from.when}\n"
                )


@runtime_checkable
class HsmLogger(Protocol):
    def fn_log_info(self, msg: str) -> None:
        ...

    def fn_log_debug(self, msg: str) -> None:
        ...

    def fn_state_change(self, before: HsmState, after: HsmState, why: str) -> None:
        ...


class _StringIoLogger(HsmLogger):
    def __init__(self):
        self._f = io.StringIO()

    def fn_log_info(self, msg: str) -> None:
        self._f.write(f"{msg}\n")

    def fn_log_debug(self, msg: str) -> None:
        self._f.write(f"> {msg}\n")

    def fn_state_change(self, before: HsmState, after: HsmState, why: str) -> None:
        why_text = ""
        if why is not None:
            why_text = f" ({why})"
        self._f.write(f">>> {before.full_name} ==> {after.full_name}{why_text}\n")

    @staticmethod
    def strip_string(multiline_text: str) -> str:
        lines = [line.strip() for line in multiline_text.split("\n")]
        lines = [line for line in lines if len(line) > 0]
        return "\n".join(lines)

    def assert_equal(self, expected: str) -> None:
        expected_stripped = _StringIoLogger.strip_string(expected)
        stripped = self.get_log(reset=True)
        assert (
            stripped == expected_stripped
        ), f"\n--------\n{stripped}\n-- != --\n{expected_stripped}\n--------\n"

    def get_log(self, reset=False) -> str:
        multiline_text = self._f.getvalue()
        if reset:
            self._f = io.StringIO()
        return _StringIoLogger.strip_string(multiline_text)


class HsmMixin:
    def __init__(self, mermaid_detailed=True, mermaid_entryexit=True):
        self._mermaid_detailed = mermaid_detailed
        self._mermaid_entryexit = mermaid_entryexit
        self._logger: HsmLogger = _StringIoLogger()
        self._top_state = HsmState(hsm=self)
        self._dict_fn_state: Dict[StateType, HsmState] = {}
        self._state_actual: HsmState = None

    def get_state(self) -> HsmState:
        return self._state_actual

    def assert_valid_state(self, *fns: StateType) -> None:
        for fn in fns:
            if fn in self._dict_fn_state:
                continue
            try:
                name = fn.__name__
            except AttributeError:
                name = str(fn)
            if not isinstance(fn, types.MethodType):
                raise BadStateException(
                    f"State '{name}' is expected to be a method of the statemachine but got type '{type(fn)}'!"
                )
            raise BadStateException(
                f"State '{name}' is NOT a state of this statemachine!"
            )

    def is_state(self, *fns: StateType) -> bool:
        """
        If a outer state is given, all substates are implied too!
        """
        self.assert_valid_state(*fns)
        state_actual = self._state_actual
        while state_actual.fn_state is not None:
            for fn in fns:
                assert isinstance(fn, types.MethodType)
                # Why does 'is' return always False?
                if state_actual.fn_state == fn:
                    return True
            # Test also the outer states
            state_actual = state_actual.outer_state
        return False

    def force_state(self, fn: StateType) -> bool:
        assert isinstance(fn, types.MethodType)
        self._state_actual = self._dict_fn_state[fn]
        self._logger.fn_log_info(f"force_state({self._state_actual.full_name})")

    def set_logger(self, logger: HsmLogger):
        """
        Tell the statemachine where to log
        """
        assert isinstance(logger, HsmLogger)
        self._logger = logger

    def dispatch(self, signal: SignalType):
        state_before = self._state_actual
        why = None

        try:
            self._logger.fn_log_info(
                f"{signal!r}: will be handled by {self._state_actual.full_name}"
            )
            self._logger.fn_log_debug(
                f'  calling state "state_{state_before.full_name}({signal})"'
            )
            handling_state = self._state_actual
            while True:
                handling_state.fn_state(signal)
                err = f"Signal {signal} was not handled by state_{handling_state.full_name}!"
                handling_state = handling_state.outer_state
                if (handling_state is None) or (handling_state.fn_state is None):
                    raise Exception(err)  # pylint: disable=broad-exception-raised

        except DontChangeStateException:
            self._logger.fn_log_debug("  No state change!")
            return
        except IgnoreEventException as e:
            why = e.why
            why_text = ""
            if why is not None:
                why_text = f" ({why})"
            self._logger.fn_log_debug(f"  Empty Transition!{why_text}")
            return
        except StateChangeException as e:
            why = e.why
            self._logger.fn_log_debug(
                f"{signal}: was handled by state_{handling_state.full_name}"
            )
            # Evaluate init-state
            new_state = self._dict_fn_state[e.fn_new_state]
            state_after = new_state.resolve_init_state()
            if state_after is not new_state:
                self._logger.fn_log_debug(
                    f"  Init-State for {new_state.full_name} is {state_after.full_name}."
                )
            self._state_actual = state_after

        # Call the exit/entry-actions
        self.call_exit_entry_actions(
            signal=signal,
            state_before=state_before,
            state_after=state_after,
        )

        self._logger.fn_state_change(state_before, state_after, why)

    def call_exit_entry_actions(
        self,
        signal: SignalType,
        state_before: HsmState,
        state_after,
    ):
        assert isinstance(state_before, HsmState)
        assert isinstance(state_after, HsmState)

        def find_common_path() -> List[str]:
            path_before = state_before.path
            path_after = state_after.path
            path_common: List[str] = []
            for i in range(min(len(path_before), len(path_after))):
                if path_before[i] != path_after[i]:
                    return path_common
                path_common.append(path_before[i])
            return path_common

        path_common = find_common_path()

        toppest_state = self.find_state(path=path_common)

        # Call Exit-Actions
        while state_before is not toppest_state:
            if state_before.fn_exit is not None:
                self._logger.fn_log_debug(f"  Calling {state_before.fn_exit.__name__}")
                state_before.fn_exit(signal)
            state_before = state_before.outer_state

        # Call all Entry-Actions
        def recurse_entry_actions(state: HsmState) -> None:
            if state is toppest_state:
                return
            recurse_entry_actions(state=state.outer_state)
            if state.fn_entry is not None:
                self._logger.fn_log_debug(f"  Calling {state.fn_entry.__name__}")
                state.fn_entry(signal)

        recurse_entry_actions(state_after)

    def find_state(self, path: List[str], error_if_not_exists: str = None) -> HsmState:
        actual_state = self._top_state
        for name in path:
            actual_state = actual_state.find_state(
                name=name, error_if_not_exists=error_if_not_exists
            )
        return actual_state

    def find_state_by_name(self, fn_name: str) -> HsmState:
        path = HsmState.fn_name_to_path(verb=_Verb.STATE, fn_name=fn_name)
        return self.find_state(path=path)

    def init(self):
        def iter_member(verb: _Verb):
            assert isinstance(verb, _Verb)
            for fn_name, method in inspect.getmembers(self, predicate=inspect.ismethod):
                path = HsmState.fn_name_to_path(verb=verb, fn_name=fn_name)
                if path is None:
                    continue
                yield fn_name, path, method

        # Initialize all states
        for fn_name, path, fn_state in iter_member(_Verb.STATE):
            state = self.find_state(path=path)
            state.fn_state = fn_state

        # Find loose states
        for state in self._top_state.iter_states():
            state.assert_loose_state()

        # Attach entry-actions
        for fn_name, path, fn_state in iter_member(_Verb.ENTRY):
            state = self.find_state(
                path=path,
                error_if_not_exists=f"No corresponding state_Xyz() for {fn_name}()!",
            )
            state.fn_entry = fn_state

        # Attach exit-actions
        for fn_name, path, fn_state in iter_member(_Verb.EXIT):
            state = self.find_state(
                path=path,
                error_if_not_exists=f"No corresponding state_Xyz() for {fn_name}()!",
            )
            state.fn_exit = fn_state

        # Define init state if no substates
        for state in self._top_state.list_states():
            state.define_init_state()

        # Read transitions from docstrings
        for state in self._top_state.list_states():
            state.parse_transitions_from_docstring()

        for state in self._top_state.list_states():
            self._dict_fn_state[state.fn_state] = state

        for state in self._top_state.list_states():
            state.assert_consistency()

        self._state_actual = self._top_state.resolve_init_state()
        assert self._state_actual is not None

        # TODO
        # self.start()

    def start(self):
        # Call the entry-actions
        # self.call_exit_entry_actions(self.strTopState, self._state_actual)
        self.call_exit_entry_actions(
            signal=None, state_before=self._top_state, state_after=self._state_actual
        )

    def write_mermaid_md(self, filename: pathlib.Path) -> None:
        assert isinstance(filename, pathlib.Path)
        with filename.open("w") as f:
            f.write("```mermaid\n")
            f.write("stateDiagram-v2\n")
            self._top_state.render_mermaid(f=f)
            self._top_state.render_mermaid_transitions(f=f)
            f.write("```\n")
