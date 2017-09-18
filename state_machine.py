# -*- coding: utf-8 -*-

__author__ = 'Markus Guenther (markus.guenther@gmail.com)'

"""This module contains a decentralized state engine. Every state knows its potential successor states, which
eliminates the need for a centralized state engine component, since states implementations are able to
handle state transitions locally.

The module implements all states of a peer within the context of the supporter strategy (default, watched,
starving, supported) that are admissible during its lifecycle inside the overlay. Peers start off in default
state, which basically means that they just joined the overlay and registered themselves at the monitoring
component. If the overlay is unable to sustain such a peer with missing chunks, it is likely that this peer
will suffer from starvation. In this case, the peers themselves send support requests to the monitoring component,
which will trigger state transitions if certain conditions are met.

A peer will go from default state to watched state if it has send at least one support request within a
certain time frame. If a peer frequently sends support requests within a given time frame, it will transition
from watched state to starving state, which indicates that the peer will be unable to sustain video playback
if no additional chunk provider will serve the necessary data.

A peer will go from starving state to supported state if a supporter was assigned to this peer. A peer will stop
sending requests and dispatch a supplied request to the monitoring component if the overlay is capable of providing
the missing chunks as required for an uninterruptible video playback."""

from supporter.shared import *


class State(object):
    """State is the abstract base class for all states that can be assigned to a monitored
    peer. There is a bidirectional dependency between State and MonitoredPeer, so each
    MonitoredPeer knows its state, and each State knows the MonitoredPeer it belongs to."""

    def __init__(self, monitored_peer):
        assert monitored_peer is not None
        self._monitored_peer = monitored_peer

    def get_monitored_peer(self):
        """
        @return: The associated MonitoredPeer object
        """
        return self._monitored_peer

    def transition(self):
        """Checks if a transition to successor states is possible from the current state
        and performs this transition. This method has to be overriden in implementing classes.

        @return:
            NoneType
        """
        pass

    def __str__(self):
        pass


class DefaultState(State):
    """Realizes the DEFAULT state of a MonitoredPeer as described in (Gerlach, 2010). Every newly
    registered peers starts out in this state and returns back to it, once it does not need any
    further support.
    """

    def __init__(self, monitored_peer):
        State.__init__(self, monitored_peer)

    def transition(self):
        """Checks if the MonitoredPeer can transition to the WATCHED state. See State.transition
        for further documentation.

        @return:
            NoneType
        """
        m = self.get_monitored_peer()
        if m.get_ts_first_request() is not None and m.get_number_of_support_requests() == 1:
            m.set_state(WatchedState(m))

    def __str__(self):
        return 'Default'


class WatchedState(State):
    """Realizes the WATCHED state of a MonitoredPeer as described in (Gerlach, 2010). The
    implementation deviates from the before mentioned work since it also allows to transition
    back to the DEFAULT state from WATCHED state.
    """

    def __init__(self, monitored_peer):
        State.__init__(self, monitored_peer)

    def transition(self):
        """Checks if the MonitoredPeer can transition back to the DEFAULT state or forward
        to the STARVING state. The transition to the DEFAULT state happens immediately and thus
        does not rely on the peer timeout (cf. constant PEER_TIMEOUT_BOUND). For the transition
        to the STARVING state, a certain number of support requests
        (cf. constant PEER_REQUIRED_MSGS) have to be arrived in a certain time
        window (cf. constant PEER_STATUS_APPROVAL_TIME).

        @return:
            NoneType
        """
        m = self.get_monitored_peer()

        if not m.peer_is_alive():
            m.set_state(DefaultState(m))
            m.reset_support_cycle()
        elif m.get_last_received_msg() == MSG_SUPPORT_NOT_NEEDED:
            # the transition from WATCHED -> DEFAULT is not dependent on the timeout
            m.set_state(DefaultState(m))
        elif m.get_last_received_msg() == MSG_SUPPORT_REQUIRED:
            # this is the regular case (WATCHED -> STARVING
            if self.support_requests_are_within_approval_interval() and self.minimum_support_requests_reached():
                m.set_state(StarvingState(m))

    def support_requests_are_within_approval_interval(self):
        m = self.get_monitored_peer()
        return (m.get_ts_last_request() - m.get_ts_first_request()) <= PEER_STATUS_APPROVAL_TIME

    def minimum_support_requests_reached(self):
        m = self.get_monitored_peer()
        return m.get_number_of_support_requests() >= PEER_REQUIRED_MSGS

    def __str__(self):
        return 'Watched'


class StarvingState(State):
    """Realizes the STARVING state of a MonitoredPeer as described in (Gerlach, 2010). The
    implementation deviates from the before mentioned work since it also allows to transition
    back to the DEFAULT state from STARVING state.
    """

    def __init__(self, monitored_peer):
        State.__init__(self, monitored_peer)

    def transition(self):
        """Checks if the associated MonitoredPeer can transition back to the DEFAULT state
        (in case the support is no longer required) or transition forward to the SUPPORTED
        state. The transition to the DEFAULT state happens immediately and thus does not
        rely on the peer timeout (cf. constant PEER_TIMEOUT_BOUND). For the transition to
        the SUPPORTED state, the peer has to receive the supported message from the
        SupporterMonitor beforehand.

        @return:
            NoneType
        """
        m = self.get_monitored_peer()
        msg_type = m.get_last_received_msg()

        if not m.peer_is_alive():
            m.set_state(DefaultState(m))
            m.reset_support_cycle()
        elif msg_type == MSG_SUPPORT_NOT_NEEDED:
            # the transition from STARVING -> DEFAULT is not dependent on the timeout
            m.set_state(DefaultState(m))

        if msg_type == MSG_PEER_SUPPORTED:
            m.set_state(SupportedState(m))

    def __str__(self):
        return 'Starving'


class SupportedState(State):
    """Realizes the SUPPORTED state of a MonitoredPeer as described in (Gerlach, 2010).
    """

    def __init__(self, monitored_peer):
        State.__init__(self, monitored_peer)

    def transition(self):
        """Checks if the associated MonitoredPeer can transition back to the DEFAULT state.
        This transition occurs, if the peer does not longer rely on the support of a
        server and waited some more time after the NO SUPPORT REQUIRED message was received by
        the SupporterMonitor in the current state.

        @return:
            NoneType
        """
        m = self.get_monitored_peer()
        msg_type = m.get_last_received_msg()

        if not m.peer_is_alive():
            m.set_state(DefaultState(m))
            m.reset_support_cycle()
        elif msg_type == MSG_SUPPORT_NOT_NEEDED and m.peer_timed_out() or not m.peer_is_alive():
            m.set_state(DefaultState(m))

    def __str__(self):
        return 'Supported'