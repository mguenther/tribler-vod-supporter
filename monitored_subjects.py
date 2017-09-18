# -*- coding: utf-8 -*-

__author__ = 'Markus Guenther (markus.guenther@gmail.com)'

"""This module provides abstractions for all types of monitorable participants (subjects) in an overlay."""

import time

from supporter.state_machine import DefaultState, State, StarvingState
from supporter.shared import *


class MonitoredPeer(object):
    """The MonitoredPeer class represents the local state of a peer as seen by the SupporterMonitor.
    It handles incoming messages and triggers state transitions as appropriate.

    MonitoredPeer keeps track of the last PEER_REQUIRED_MSGS that were forwarded from a
    SupporterMonitor instance to it (sliding window over all received messages)."""

    def __init__(self, peer_id, ip, port, peer_type, is_alive_timeout=None, peer_timeout=None):
        self._last_received_msg = None
        self._ts_last_received_msg = None  # there is a difference between the request message window
        self._is_alive_timeout = is_alive_timeout or IS_ALIVE_TIMEOUT_BOUND
        self._peer_timeout = peer_timeout or PEER_TIMEOUT_BOUND
        # and this one here! (this is set for ALL message types)
        self._state = DefaultState(self)
        self._timeout_timer = None
        self.reset_support_cycle()
        # assign given parameters using class methods (they perform further checks on validity)
        self._set_id(peer_id)
        self._set_ip(ip)
        self._set_port(port)
        self.set_peer_type(peer_type)
        self.msg_handler = {
            MSG_PEER_SUPPORTED:     self.received_peer_supported_message,
            MSG_SUPPORT_NOT_NEEDED: self.received_support_not_needed_message,
            MSG_SUPPORT_REQUIRED:   self.received_support_required_message,
            MSG_PEER_REGISTERED:    self.received_peer_registered_message}

    def __hash__(self):
        """The hash of a MonitoredPeer is based on the peer's ID and its address. The implementation
        utilizes the hash function on Python's tuple data type to generate the hash value for
        a MonitoredPeer object.

        @return:
            Hash value based on the 3-tuple (ID, IP, Port)
        """
        return hash((self._id, self._ip, self._port))

    def __eq__(self, other):
        """Equality test on two MonitoredPeer instances. The test is based on the comparison of
        the objects hash values and therefore solely relies on the 3-tuple (ID, IP, Port).

        @param other:
            Another instance of MonitoredPeer to which this instance shall be compared to

        @return:
            Boolean value indicating whether two instances represent the same state of information.
        """
        assert isinstance(other, MonitoredPeer)
        return self.__hash__() == other.__hash__()

    def get_ts_last_message(self):
        """@return:
            The timestamp of the last message (over all message types, not just the request
            messages, as in the sliding window over all requests!) that was received.
        """
        return self._ts_last_received_msg

    def get_ts_first_request(self):
        """@return:
            The timestamp of the first message in the sliding window over the last
            PEER_REQUIRED_MSGS. NoneTyp if no messages were received prior to the call
            of this method. Please be aware that the returned value of get_ts_last_request
            equals the return value of get_ts_first_request if there was only one message
            receive prior the resp. method call.
        """
        if len(self._ts_list) == 0:
            return None
        return self._ts_list[0]

    def get_ts_last_request(self):
        """@return:
            The timestamp of the last message in the sliding window over the last
            PEER_REQUIRED_MSGS. NoneType if no messages were received prior to the call
            of this method. Please be aware that the returned value of get_ts_last_request
            equals the return value of get_ts_first_request if there was only one message
            receive prior the resp. method call.
        """
        if len(self._ts_list) == 0:
            return None
        return self._ts_list[len(self._ts_list) - 1]

    def get_number_of_support_requests(self):
        """@return:
            The number of support requests by this peer during the current admission cycle
        """
        return self._support_requests

    def increment_support_requests(self):
        """Increments the number of support requests. Triggered upon the receipt of a support
        message.

        @return:
            NoneType
        """
        self._support_requests += 1

    def reset_support_cycle(self):
        """Resets the support cycle, which results in the deletion of the last PEER_REQUIRED_MSGS
        (the sliding window over the last received messages is empty afterwards) and the reset of
        the number of support requests to its initial value of 0.

        @return:
            NoneType
        """
        self._ts_list = []
        self._support_requests = 0

    def _set_id(self, peer_id):
        """Sets the ID for this MonitoredPeer instance.

        @param peer_id:
            The ID of the associated peer

        @return:
            NoneType
        """
        self._id = peer_id

    def get_id(self):
        """@return:
            The ID of the associated MonitoredPeer instance.
        """
        return self._id

    def _set_ip(self, ip):
        """Sets the IP address for this MonitoredPeer instance.

        @param ip:
            The IP address of the associated peer

        @return:
            NoneType
        """
        self._ip = ip

    def get_ip(self):
        """@return:
            The IP address of the associated MonitoredPeer instance.
        """
        return self._ip

    def _set_port(self, port):
        """Sets the port address of the associated MonitoredPeer instance. Asserts that the
        given port is >= 1024 (given port must be out of the range of reserved ports).

        @param port:
            The port address of the associated peer

        @return:
            NoneType
        """
        assert port >= 1024
        self._port = port

    def get_port(self):
        """@return:
            The port address of the associated MonitoredPeer instance.
        """
        return self._port

    def set_peer_type(self, peer_type):
        """Sets the peer type.

        @param peer_type:
            Parameter that describes the behaviour of the associated peer.
            The given value must be in [PEER_TYPE_LEECHER, PEER_TYPE_SEEDER].

        @return:
            NoneType
        """
        assert peer_type in PEER_TYPES
        self._peer_type = peer_type

    def get_peer_type(self):
        """Returns:
            The peer type of the associated MonitoredPeer instance
        """
        return self._peer_type

    def set_state(self, state):
        """Sets the current state of the MonitoredPeer instance. The given state must be
        a subclass of SupporterMonitor.State.

        @param state:
            Instance of a subclass of SupporterMonitor.State, representing
            the state that the associated peer resides in

        @return:
            NoneType
        """
        assert isinstance(state, State)
        self._state = state

    def get_state(self):
        """@return:
            The current state of the MonitoredPeer instance.
        """
        return self._state

    def get_last_received_msg(self):
        """@return:
            The type of the last received message. Return values are in [MSG_PEER_SUPPORTED,
            MSG_SUPPORT_NOT_NEEDED, MSG_SUPPORT_REQUIRED].
        """
        return self._last_received_msg

    def peer_timed_out(self):
        """Checks if the associated MonitoredPeer suffers from a timeout.

        The difference between peer_timed_out and peer_is_alive is simply the fact, that a peer
        has to remain in the SUPPORTED state for a short period of time, even if it does not
        need support any longer. peer_timed_out checks for this timeout. peer_is_alive on the
        other hand, checks, if the peer should transition back from any state to DEFAULT
        state after a while.

        @return:
            Boolean value, indicating whether the peer timed out
        """
        if self.timeout_timer_stopped():
            return False
        return (time.time() - self._timeout_timer) >= self._peer_timeout

    def peer_is_alive(self):
        """Checks if the associated MonitoredPeer is considered as being alive or not.

        The difference between peer_timed_out and peer_is_alive is simply the fact, that a peer
        has to remain in the SUPPORTED state for a short period of time, even if it does not
        need support any longer. peer_timed_out checks for this timeout. peer_is_alive on the
        other hand, checks, if the peer should transition back from any state to DEFAULT
        state after a while.
        """

        if self.get_ts_last_request() is not None:
            return (time.time() - self.get_ts_last_request()) < self._is_alive_timeout
        else:
            # if last_request_ts is NoneType, then the peer was just added to the monitor
            # and we have to wait a bit until it actually has send its first message
            return True

    def receive_msg(self, msg_type):
        """Handler method which gets called whenever a message from a monitored peer was received.
        The method sets the internal state accordingly, calls the appropriate specific message
        handler method as defined in MonitoredPeer.msg_handler and triggers the synchronous
        transition of the current state.

        @param msg_type:
            Represents the message type of the received message. The given
            value must be in [MSG_PEER_SUPPORTED, MSG_SUPPORT_NOT_NEEDED,
            MSG_SUPPORT_REQUIRED].

        @return:
            NoneType
        """
        assert msg_type in [MSG_PEER_SUPPORTED, MSG_SUPPORT_NOT_NEEDED, MSG_SUPPORT_REQUIRED,
                            MSG_PEER_REGISTERED]
        self._last_received_msg = msg_type
        self._ts_last_received_msg = time.time()
        self.msg_handler[msg_type]()
        self.get_state().transition()

    def support_aborted(self):
        """Resets the peers state. This may occur the supporter the peer is assigned to
        is no longer reachable. The peers state will be set to STARVING STATE.

        @return:
            NoneType
        """
        self._state = StarvingState(self)

    def received_support_required_message(self):
        """Handler method for the event that the associated monitored peer sent MSG_SUPPORT_REQUIRED.
        The method updates the internal state as appropriate (timeout handling, sliding window
        update, support requests made update).

        @return:
            NoneType
        """
        self.increment_support_requests()
        self.stop_timeout_timer()

        self._ts_list.append(time.time())

        if len(self._ts_list) > PEER_REQUIRED_MSGS:
            # slide one step further
            self._ts_list = self._ts_list[1:]

    def received_support_not_needed_message(self):
        """Handler method for the event that the associated monitored peer sent
        MSG_SUPPORT_NOT_NEEDED. The method triggers the reset of the current admission cycle
        and starts a timeout timer which is needed for asynchronous state transitions.

        @return:
            NoneType
        """
        self.reset_support_cycle()
        self.start_timeout_timer()

    def received_peer_supported_message(self):
        """Handler method for the event that SupporterMonitor assigned the MonitoredPeer to
        a supporter server. The implementation does nothing at the moment.

        @return:
            NoneType
        """
        pass

    def received_peer_registered_message(self):
        """Handler method for the event that SupporterMonitor has just registered the
        associated peer. The implementation does nothing at the moment.

        @return:
            NoneType
        """
        pass

    def start_timeout_timer(self):
        """Starts a timeout timer (if it wasn't started before).

        @return:
            NoneType
        """
        if self._timeout_timer is None:
            self._timeout_timer = time.time()

    def stop_timeout_timer(self):
        """Stops the timeout timer.

        @return:
            NoneType
        """
        self._timeout_timer = None

    def timeout_timer_stopped(self):
        """@return:
            Boolean value, indicating whether the timeout timer is stopped.
        """
        return self._timeout_timer is None


class MonitoredSupporter(object):
    """The MonitoredSupporter class represents the local state of a monitored supporter as seen
    by the SupporterMonitor. It basically is a wrapper for some attributes, implements logic
    to maintain an internal supportee list (starving peers get assigned to a supporter) and is
    able to differentiate between active and inactive supporter states.
    """

    def __init__(self, supporter_id, addr, min_peer, max_peer):
        self._supporterId = supporter_id
        assert isinstance(addr, tuple)
        assert len(addr) == 2
        assert addr[1] >= 1024
        self._addr = addr
        assert min_peer <= max_peer
        self._min_peer = min_peer
        self._max_peer = max_peer
        self._supported_peers = []  # holds MonitoredPeer instances
        global supported_peers
        supported_peers = self._supported_peers
        # self._is_active = False
        self._updated = True

    def __hash__(self):
        """The hash of a MonitoredSupporter is based on the supporter's static attributes: its
        internal ID (we use the swarm-related peer ID, but any ID will do), its address in terms
        of IP address and port number, and the minimum and maximum amount of peers it can supply.
        The implementation utilizes Python's hash function on a newly constructed tuple that
        covers all static attributes.

        @return:
            Hash value based on the 4-tuple (ID, address, min_peer, max_peer)
        """
        return hash((self._supporterId, self._addr, self._min_peer, self._max_peer))

    def __eq__(self, other):
        """Equality test on two MonitoredSupporter instances. The test is based on the comparison
        of the objects hash values as returned by __hash__ and therefore solely relies on the
        4-tuple (ID, address, min_peer, max_peer).

        @param other:
            Another instance of MonitoredSupporter that shall be compared to this instance

        @return:
            Boolean value indicating whether two instances represent the same state of information.
        """
        assert isinstance(other, MonitoredSupporter)
        return self.__hash__() == other.__hash__()

    def get_id(self):
        """@return:
            The ID of the associated monitored supporter
        """
        return self._supporterId

    def get_addr(self):
        """@return:
            2-tuple of the form (IP, Port), which represents the address of the associated supporter
        """
        return self._addr

    def get_min_peer(self):
        """@return:
            The amount of peers that are needed at minimum to activate the associated supporter
        """
        return self._min_peer

    def get_max_peer(self):
        """@return:
            The amount of peers that the supporter is able to supply at maximum
        """
        return self._max_peer

    def add_supported_peer(self, monitored_peer):
        """Adds a given MonitoredPeer to the internal list of supported peers. Please be aware
        that this method does not check if the addition of the given peer results in an amount
        of peers larger than the supporter can supply. Such checks have to be performed at the
        caller.

        @param monitored_peer:
            Instance of MonitoredPeer that shall be added to the list of currently supported peers

        @return:
            NoneType
        """
        assert monitored_peer is not None
        if monitored_peer not in self._supported_peers:
            self._updated = True
            self._supported_peers.append(monitored_peer)

    def cancel_support_for_all_peers(self):
        """Removes all supported peers from the supporter and resets them to STARVING state.

        @return:
            NoneType
        """
        collected_peers = []
        for mp in self._supported_peers:
            collected_peers.append(mp)
        for mp in collected_peers:
            self.remove_supported_peer(mp)
            mp.support_aborted()

    def remove_supported_peer(self, monitored_peer):
        """Removes a MonitoredPeer from the list of supported ones.

        @param monitored_peer:
            Instance of MonitoredPeer that shall be removed from the list of currently supported
            peers

        @return:
            NoneType
        """
        assert monitored_peer is not None
        if monitored_peer in self._supported_peers:
            self._supported_peers.remove(monitored_peer)
            self._updated = True

    def available_slots(self):
        """@return:
            The amount of currently available slots at the associated supporter.
        """
        return self.get_max_peer() - len(self._supported_peers)

    def assigned_slots(self):
        """@return:
            The amount of currently assigned slots at the associated supporter.
        """
        return len(self._supported_peers)

    def minimum_starving_peers_reached(self):
        """@return:
            Boolean value, indicating whether the supporter has reached its minimum amount
        """
        return len(self._supported_peers) - self.get_min_peer() >= 0

    def reset_update_counter(self):
        value = self._updated
        self._updated = False
        return value

    def get_supported_peers(self):
        """@return:
            List of MonitoredPeers instances that are currently assigned to the associated
            supporter.
        """
        return self._supported_peers

    def update_supported_peer_list(self):
        """Performs an update of the supportee list. Removes every peer that is in default state.
        Please note that the default state is the only state reachable from the supported state.
        Thus, it is not necessary to check for other states.

        @return:
            NoneType
        """
        to_be_removed = []
        for peer in self.get_supported_peers():
            if isinstance(peer.get_state(), DefaultState):
                to_be_removed.append(peer)
        for peer in to_be_removed:
            self.remove_supported_peer(peer)
            self._updated = True