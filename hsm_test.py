import pathlib

import pytest

from hsm import hsm
from hsm.hsm import (
    BadStateException,
    BadStatemachineException,
    DontChangeStateException,
    HsmMixin,
    IgnoreEventException,
    StateChangeException,
)

SignalType = str

DIRECTORY_THIS_FILE = pathlib.Path(__file__).parent
DIRECTORY_RESULTS = DIRECTORY_THIS_FILE / "hsm_test_results"
DIRECTORY_RESULTS.mkdir(parents=True, exist_ok=True)


def test_practical_statecharts():
    class UnderTest(hsm.HsmMixin):
        """
        This is a sample StatemachineMixin as in figure 6.2 on page 170
        in 'Practical Statecharts in C/C++', ISBN 1-57820-110-1.
        """

        @hsm.init_state
        def state_0(self, signal: SignalType):
            'This is State "0"!'
            if signal == "E":
                raise hsm.StateChangeException(self.state_0_2_1_1)
            if signal == "I":
                raise hsm.StateChangeException(self.state_0)
            if signal == "J":
                raise hsm.IgnoreEventException()

        @hsm.init_state
        def state_0_1(self, signal: SignalType):
            if signal == "A":
                raise hsm.StateChangeException(self.state_0_1)
            if signal == "C":
                raise hsm.StateChangeException(self.state_0_2)
            if signal == "D":
                raise hsm.StateChangeException(self.state_0)
            if signal == "E":
                raise hsm.StateChangeException(self.state_0_2_1_1)

        @hsm.init_state
        def state_0_1_1(self, signal: SignalType):
            """
            TRANSITION state_0_2_2 time > 0
            TRANSITION state_0_2_1_1 time < 0, Switch light off
            TRANSITION state_unexistent money is nothing
            """
            if signal == "G":
                raise hsm.StateChangeException(self.state_0_2_1_1)
            if signal == "H":
                pass

        def state_0_2(self, signal: SignalType):
            if signal == "K":
                raise hsm.StateChangeException(self.state_0_1)
            if signal == "F":
                raise hsm.StateChangeException(self.state_0_1_1)

        def state_0_2_1(self, signal: SignalType):
            if signal == "B":
                raise hsm.StateChangeException(self.state_0_2_1_1)
            if signal == "H":
                raise hsm.StateChangeException(self.state_0_2_1)

        @hsm.init_state
        def state_0_2_1_1(self, signal: SignalType):
            if signal == "C":
                raise hsm.StateChangeException(self.state_0_2_2)
            if signal == "D":
                raise hsm.StateChangeException(self.state_0_2_1)
            if signal == "G":
                raise hsm.StateChangeException(self.state_0)

        @hsm.init_state
        def state_0_2_2(self, signal: SignalType):
            """
            EXIT something happened
            """
            if signal == "B":
                raise hsm.IgnoreEventException()
            if signal == "G":
                raise hsm.StateChangeException(self.state_0_2_1)

        def entry_0(self, signal: SignalType):
            pass

        def exit_0(self, signal: SignalType):
            pass

        def entry_0_1(self, signal: SignalType):
            pass

        def exit_0_1(self, signal: SignalType):
            "Reset XY"

        def entry_0_1_1(self, signal: SignalType):
            "Start RS"

    sm = UnderTest()
    sm.init()
    sm.write_mermaid_md(DIRECTORY_RESULTS / f"{test_practical_statecharts.__name__}.md")

    # TRIPTEST_ASSERT(hsm_Statemachine.state == sm.state_011)
    # test_entry_exit(sm, 1, 0, 1, 0, 1)
    sm._logger.assert_equal(
        """
        """
    )

    sm.dispatch("G")
    # test_entry_exit(sm, 0, 0, 0, 1, 0)
    sm._logger.assert_equal(
        """
            'G': will be handled by 0_1_1
            >   calling state "state_0_1_1(G)"
            > G: was handled by state_0_1_1
            >   Calling exit_0_1
            >>> 0_1_1 ==>exit_0_1==> 0_2_1_1
        """
    )

    with pytest.raises(BadStateException) as excinfo:
        sm.is_state(UnderTest.state_0_1)
    assert (
        "State 'state_0_1' is expected to be a method of the statemachine but got type '<class 'function'>'!"
        == excinfo.value.args[0]
    )

    with pytest.raises(BadStateException) as excinfo:
        assert sm.is_state(sm.entry_0)
    assert (
        "State 'entry_0' is NOT a state of this statemachine!" == excinfo.value.args[0]
    )
    assert sm.is_state(sm.state_0_2_1_1)
    assert sm.is_state(sm.state_0_2_1)
    assert sm.is_state(sm.state_0_2)
    assert sm.is_state(sm.state_0)

    sm.dispatch("F")
    # test_entry_exit(sm, 0, 0, 1, 0, 1)
    sm._logger.assert_equal(
        """
            'F': will be handled by 0_2_1_1
            >   calling state "state_0_2_1_1(F)"
            > F: was handled by state_0_2
            >   Calling entry_0_1
            >   Calling entry_0_1_1
            >>> 0_2_1_1 ==>entry_0_1==>entry_0_1_1==> 0_1_1
        """
    )

    sm.dispatch("E")
    # test_entry_exit(sm, 0, 0, 0, 1, 0)
    sm._logger.assert_equal(
        """
            'E': will be handled by 0_1_1
            >   calling state "state_0_1_1(E)"
            > E: was handled by state_0_1
            >   Calling exit_0_1
            >>> 0_1_1 ==>exit_0_1==> 0_2_1_1

        """
    )

    sm.dispatch("C")
    # test_entry_exit(sm, 0, 0, 0, 0, 0)
    sm._logger.assert_equal(
        """
            'C': will be handled by 0_2_1_1
            >   calling state "state_0_2_1_1(C)"
            > C: was handled by state_0_2_1_1
            >>> 0_2_1_1 ==> 0_2_2
        """
    )

    sm.dispatch("B")
    # test_entry_exit(sm, 0, 0, 0, 0, 0)
    sm._logger.assert_equal(
        """
            'B': will be handled by 0_2_2
            >   calling state "state_0_2_2(B)"
            >   Empty Transition!
        """
    )

    sm.dispatch("E")
    # test_entry_exit(sm, 1, 1, 0, 0, 0)
    sm._logger.assert_equal(
        """
            'E': will be handled by 0_2_2
            >   calling state "state_0_2_2(E)"
            > E: was handled by state_0
            >>> 0_2_2 ==> 0_2_1_1
        """
    )

    sm.dispatch("D")
    # test_entry_exit(sm, 0, 0, 0, 0, 0)
    sm._logger.assert_equal(
        """
            'D': will be handled by 0_2_1_1
            >   calling state "state_0_2_1_1(D)"
            > D: was handled by state_0_2_1_1
            >   Init-State for 0_2_1 is 0_2_1_1.
            >>> 0_2_1_1 ==> 0_2_1_1
        """
    )

    sm.dispatch("K")
    # test_entry_exit(sm, 0, 0, 1, 0, 1)
    sm._logger.assert_equal(
        """
            'K': will be handled by 0_2_1_1
            >   calling state "state_0_2_1_1(K)"
            > K: was handled by state_0_2
            >   Init-State for 0_1 is 0_1_1.
            >   Calling entry_0_1
            >   Calling entry_0_1_1
            >>> 0_2_1_1 ==>entry_0_1==>entry_0_1_1==> 0_1_1
        """
    )

    sm.dispatch("A")
    # test_entry_exit(sm, 0, 0, 1, 1, 1)
    sm._logger.assert_equal(
        """
            'A': will be handled by 0_1_1
            >   calling state "state_0_1_1(A)"
            > A: was handled by state_0_1
            >   Init-State for 0_1 is 0_1_1.
            >>> 0_1_1 ==> 0_1_1
        """
    )

    sm.dispatch("I")
    # test_entry_exit(sm, 1, 1, 1, 1, 1)
    sm._logger.assert_equal(
        """
            'I': will be handled by 0_1_1
            >   calling state "state_0_1_1(I)"
            > I: was handled by state_0
            >   Init-State for 0 is 0_1_1.
            >>> 0_1_1 ==> 0_1_1
        """
    )

    sm.dispatch("G")
    # test_entry_exit(sm, 0, 0, 0, 1, 0)
    sm._logger.assert_equal(
        """
            'G': will be handled by 0_1_1
            >   calling state "state_0_1_1(G)"
            > G: was handled by state_0_1_1
            >   Calling exit_0_1
            >>> 0_1_1 ==>exit_0_1==> 0_2_1_1
        """
    )

    sm.dispatch("I")
    # test_entry_exit(sm, 1, 1, 1, 0, 1)
    sm._logger.assert_equal(
        """
            'I': will be handled by 0_2_1_1
            >   calling state "state_0_2_1_1(I)"
            > I: was handled by state_0
            >   Init-State for 0 is 0_1_1.
            >   Calling entry_0_1
            >   Calling entry_0_1_1
            >>> 0_2_1_1 ==>entry_0_1==>entry_0_1_1==> 0_1_1
        """
    )

    sm.dispatch("J")
    # test_entry_exit(sm, 0, 0, 0, 0, 0)
    sm._logger.assert_equal(
        """
            'J': will be handled by 0_1_1
            >   calling state "state_0_1_1(J)"
            >   Empty Transition!
        """
    )


def test_loose_state():
    """
    Top state hangs in the air.
    """

    class UnderTest(HsmMixin):
        def state_TopA_SubB(self, signal: SignalType):
            pass

    sm = UnderTest()
    with pytest.raises(BadStatemachineException) as excinfo:
        sm.init()

    assert "Missing 'state_TopA()'!" == excinfo.value.args[0]


def test_unmatched_entry_action():
    class UnderTest(HsmMixin):
        def state_TopA(self, signal: SignalType):
            pass

        def entry_TopA_SubB(self, signal: SignalType):
            pass

    sm = UnderTest()

    with pytest.raises(BadStatemachineException) as excinfo:
        sm.init()

    assert (
        "No corresponding state_Xyz() for entry_TopA_SubB()!" == excinfo.value.args[0]
    )


def test_init_state_on_wrong_method():
    with pytest.raises(BadStatemachineException) as excinfo:

        class UnderTest(HsmMixin):
            def state_TopA(self, signal: SignalType):
                pass

            @hsm.init_state  # type: ignore
            def exit_TopA_SubB(self, signal: SignalType):
                pass

    assert (
        "'exit_TopA_SubB()' does NOT start with 'state_'. It may not be a init_state!"
        == excinfo.value.args[0]
    )


def test_two_init_states():
    class UnderTest(HsmMixin):
        @hsm.init_state
        def state_TopA(self, signal: SignalType):
            pass

        def state_TopB(self, signal: SignalType):
            pass

        @hsm.init_state
        def state_TopC(self, signal: SignalType):
            pass

    sm = UnderTest()
    with pytest.raises(BadStatemachineException) as excinfo:
        sm.init()
    assert "Only one init_state allowed!" == excinfo.value.args[0]


def test_unmatched_exit_action():
    class UnderTest(HsmMixin):
        def state_TopA(self, signal: SignalType):
            pass

        def exit_TopA_SubB(self, signal: SignalType):
            pass

    sm = UnderTest()
    with pytest.raises(BadStatemachineException) as excinfo:
        sm.init()
    assert "No corresponding state_Xyz() for exit_TopA_SubB()!" == excinfo.value.args[0]


def test_init_not_called():
    class UnderTest(HsmMixin):
        @hsm.init_state
        def state_TopA(self, signal: SignalType):
            pass

    sm = UnderTest()
    with pytest.raises(AssertionError) as excinfo:
        sm.dispatch("Peng")
    assert "You have to call 'init()' first!" == excinfo.value.args[0]


def test_simple_statemachine_top_state_handles_signal():
    class UnderTest(HsmMixin):
        def state_TopA(self, signal: SignalType):
            if signal == "a":
                raise DontChangeStateException

        def state_TopA_SubA(self, signal: SignalType):
            if signal == "b":
                raise StateChangeException(self.state_TopA_SubA, why="Got b")

    sm = UnderTest()
    sm.init()
    sm.write_mermaid_md(
        DIRECTORY_RESULTS
        / f"{test_simple_statemachine_top_state_handles_signal.__name__}.md"
    )
    sm.dispatch("a")
    sm._logger.assert_equal(
        """
            'a': will be handled by TopA_SubA
            >   calling state "state_TopA_SubA(a)"
            >   No state change!
        """
    )
    sm.dispatch("b")
    sm._logger.assert_equal(
        """
            'b': will be handled by TopA_SubA
            >   calling state "state_TopA_SubA(b)"
            > b: was handled by state_TopA_SubA
            >>> TopA_SubA ==> TopA_SubA (Got b)
        """
    )


def test_simple_statemachine():
    class UnderTest(HsmMixin):
        def state_TopA(self, signal: SignalType):
            if signal == "a":
                raise StateChangeException(self.state_TopA_SubA)
            raise IgnoreEventException("Weekend, do not bother me!")

        def state_TopA_SubA(self, signal: SignalType):
            if signal == "b":
                raise StateChangeException(self.state_TopA_SubB)

        @hsm.init_state
        def state_TopA_SubB(self, signal: SignalType):
            pass

        def exit_TopA_SubB(self, signal: SignalType):
            pass

        def entry_TopA_SubB(self, signal: SignalType):
            pass

    sm = UnderTest()
    sm.init()
    sm.write_mermaid_md(DIRECTORY_RESULTS / f"{test_simple_statemachine.__name__}.md")
    sm.dispatch("a")
    sm._logger.assert_equal(
        """
            'a': will be handled by TopA_SubB
            >   calling state "state_TopA_SubB(a)"
            > a: was handled by state_TopA
            >   Calling exit_TopA_SubB
            >>> TopA_SubB ==>exit_TopA_SubB==> TopA_SubA
        """
    )
    sm.dispatch("b")
    sm._logger.assert_equal(
        """
            'b': will be handled by TopA_SubA
            >   calling state "state_TopA_SubA(b)"
            > b: was handled by state_TopA_SubA
            >   Calling entry_TopA_SubB
            >>> TopA_SubA ==>entry_TopA_SubB==> TopA_SubB
        """
    )
    sm.dispatch("b")
    sm._logger.assert_equal(
        """
            'b': will be handled by TopA_SubB
            >   calling state "state_TopA_SubB(b)"
            >   Empty Transition! (Weekend, do not bother me!)
        """
    )
    sm.dispatch("a")
    sm._logger.assert_equal(
        """
            'a': will be handled by TopA_SubB
            >   calling state "state_TopA_SubB(a)"
            > a: was handled by state_TopA
            >   Calling exit_TopA_SubB
            >>> TopA_SubB ==>exit_TopA_SubB==> TopA_SubA
        """
    )


def test_statemachine_with_entry_exit_actions():
    class UnderTest(HsmMixin):
        @hsm.init_state
        def state_TopA(self, signal: SignalType):
            raise StateChangeException(self.state_TopC)

        def exit_TopA(self, signal: SignalType):
            pass

        def state_TopB(self, signal: SignalType):
            pass

        def entry_TopB(self, signal: SignalType):
            pass

        def exit_TopB(self, signal: SignalType):
            pass

        def state_TopB_SubA(self, signal: SignalType):
            pass

        def entry_TopB_SubA(self, signal: SignalType):
            pass

        def exit_TopB_SubA(self, signal: SignalType):
            pass

        def state_TopB_SubA_SubsubA(self, signal: SignalType):
            raise StateChangeException(self.state_TopC)

        def entry_TopB_SubA_SubsubA(self, signal: SignalType):
            pass

        def exit_TopB_SubA_SubsubA(self, signal: SignalType):
            pass

        def state_TopC(self, signal: SignalType):
            raise StateChangeException(self.state_TopB_SubA_SubsubA)

        def entry_TopC(self, signal: SignalType):
            pass

        def exit_TopC(self, signal: SignalType):
            pass

    sm = UnderTest()
    sm.init()
    sm.write_mermaid_md(
        DIRECTORY_RESULTS / f"{test_statemachine_with_entry_exit_actions.__name__}.md"
    )
    sm.dispatch("r")
    sm._logger.assert_equal(
        """
            'r': will be handled by TopA
            >   calling state "state_TopA(r)"
            > r: was handled by state_TopA
            >   Calling exit_TopA
            >   Calling entry_TopC
            >>> TopA ==>exit_TopA==>entry_TopC==> TopC
        """
    )
    sm.dispatch("s")
    sm._logger.assert_equal(
        """
            's': will be handled by TopC
            >   calling state "state_TopC(s)"
            > s: was handled by state_TopC
            >   Calling exit_TopC
            >   Calling entry_TopB
            >   Calling entry_TopB_SubA
            >   Calling entry_TopB_SubA_SubsubA
            >>> TopC ==>exit_TopC==>entry_TopB==>entry_TopB_SubA==>entry_TopB_SubA_SubsubA==> TopB_SubA_SubsubA
        """
    )
    sm.dispatch("t")
    sm._logger.assert_equal(
        """
            't': will be handled by TopB_SubA_SubsubA
            >   calling state "state_TopB_SubA_SubsubA(t)"
            > t: was handled by state_TopB_SubA_SubsubA
            >   Calling exit_TopB_SubA_SubsubA
            >   Calling exit_TopB_SubA
            >   Calling exit_TopB
            >   Calling entry_TopC
            >>> TopB_SubA_SubsubA ==>exit_TopB_SubA_SubsubA==>exit_TopB_SubA==>exit_TopB==>entry_TopC==> TopC
        """
    )


if __name__ == "__main__":
    test_practical_statecharts()
    # test_two_init_states()
    # test_loose_state()
    # test_unmatched_exit_action()
    # test_unmatched_entry_action()
    # test_simple_statemachine()
    # test_statemachine_with_entry_exit_actions()
