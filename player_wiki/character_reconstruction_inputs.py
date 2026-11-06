"""Detached immutable inputs for one reconstruction preparation only.

Authorities, proofs, live stores and filesystem custody verdicts never enter
this scope. Each retained input is compared with freshly observed full inputs.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy


class ReconstructionInputDrift(ValueError):
    """A retained input changed while a reconstruction was being prepared."""


class ReconstructionInputScope:
    def __init__(self, owner):
        self.owner = owner
        self._entries = {}
        self._active = True

    def resolve(self, key, observe, load):
        """Observe on every call; detach both insertion and returned values.

        ``observe`` returns an equality-comparable complete input witness.
        ``load`` consumes that witness, and is followed by a second observation.
        No-context callers use their normal fresh loader instead.
        """
        if not self._active:
            raise ReconstructionInputDrift("The reconstruction input scope has closed.")
        try:
            witness = deepcopy(observe())
            retained = self._entries.get(key)
            if retained is not None:
                if witness != retained[0]:
                    raise ReconstructionInputDrift("Reconstruction inputs changed; review again.")
                return deepcopy(retained[1])
            value = load(witness)
            if observe() != witness:
                raise ReconstructionInputDrift("Reconstruction inputs changed during resolution; review again.")
            self._entries[key] = (witness, deepcopy(value))
            return deepcopy(value)
        except BaseException:
            self.close()
            raise

    def close(self):
        self._active = False
        self._entries.clear()


_scope = ContextVar("character_reconstruction_inputs", default=None)


@contextmanager
def reconstruction_input_scope(owner):
    """Always start a fresh epoch, including nested/reservation preparations."""
    scope = ReconstructionInputScope(owner)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        scope.close()
        _scope.reset(token)


def current_input_scope():
    return _scope.get()


def audit_input_witness(connection, campaign, character):
    """The manual loader consumes only these historical audit fields.

    Numeric witnesses also inspect transition/history/current source inputs;
    their loader deliberately remains fresh rather than sharing this witness.
    """
    return (id(connection), connection.in_transaction, connection.total_changes,
        tuple(tuple(row) for row in connection.execute(
            "SELECT actor_user_id,metadata_json FROM auth_audit_log WHERE event_type='character_update_applied' AND campaign_slug=? AND character_slug=? ORDER BY id",
            (campaign, character)).fetchall()))
