# -*- coding: utf-8 -*-

__author__ = "Markus Guenther (markus.guenther@gmail.com)"

"""This module implements monitoring logic for peers in an overlay as well as supporter servers that
join the overlay as seeders and are able to supply missing chunks to peers that suffer from chunk starvation.
The monitoring logic also assigns peers that are eligible for support to supporter servers.

Peer assignments are communicated to the resp. supporters via XMLRPC. Since supporters behave the same way
as a regular seeding peer in the overlay, they will use those lists to exclusively distribute chunks to
starving peers unless a supported peers goes back from supported state to default state.

The SupporterMonitor class handles all monitored subjects and peer-to-supporter assignments. From a
client-side perspective, it is the entry-point to the supporter strategy as a component and best integrated
with a central system component, like a torrent tracker.
"""

import logging
import threading
import time

from supporter.monitored_subjects import MonitoredPeer, MonitoredSupporter
from supporter.supporter_adapter import SupporteeListDispatcher
from supporter.state_machine import DefaultState, StarvingState, SupportedState, WatchedState
from supporter.shared import *


class SupporterMonitor(object):
    """This class keeps track of all registered peers and supporters and handles incoming messages.
    State transitions for peers are triggered synchronously in the resp. MonitoredPeer instances
    upon the receipt of a peer message. SupporterMonitor also triggers state changes for peers
    as well as supporters asynchronously by calling its update method in regular intervals of
    1 second.
    """

    def __init__(self, is_alive_timeout=None, peer_timeout=None):
        self._logger = logging.getLogger("Tracker.SupporterMonitor")
        self._dispatcher = SupporteeListDispatcher(self)
        self._monitored_peers = []
        self._monitored_supporters = []
        self._active_supporters = []
        self._lock = threading.RLock()
        self.schedule_next_asynchronous_update()
        self.number_of_assignments = {}
        self.statistics = MonitorState()
        self._is_alive_timeout = is_alive_timeout or IS_ALIVE_TIMEOUT_BOUND
        self._peer_timeout = peer_timeout or PEER_TIMEOUT_BOUND
        # contains supporter servers that were marked as dead (last communication was not
        # successful) and should be removed in the next update cycle (we cant do this
        # directly because of concurrency issues)
        self._dead_supporters = []

    def schedule_next_asynchronous_update(self):
        """Schedules the next asynchronous state update for peers and supporters.

        @return:
            NoneType
        """
        for th in threading.enumerate():
            if th.getName() == "MainThread" and not th.isAlive():
                return

        t = threading.Timer(1.0, self.update_states)
        t.start()

    def get_monitored_peers(self):
        """@return:
            List containing MonitoredPeer instances
        """
        return self._monitored_peers

    def get_monitored_supporters(self):
        """@return:
            List containing all MonitoredSupporter instances, independent of their state
            (active, not active)
        """
        return self._monitored_supporters

    def get_active_supporters(self):
        """@return:
            List containing all MonitoredSupporter instances that reside in the ACTIVE state
        """
        return self._active_supporters

    def register_monitored_peer(self, id, ip, port, peer_type):
        """Registers a peer at the monitor.

        @param id:
            ID of the peer to be registered
        @param ip:
            IP address of the peer
        @param port:
            port address of the peer
        @param peer_type:
            status of the peer (leecher or seeder)

        @return:
            The newly created MonitoredPeer instance. NoneType, if a MonitoredPeer instance
            with the given attributes already exists.
        """
        self._lock.acquire()
        mp = None
        try:
            mp = MonitoredPeer(id, ip, port, peer_type, self._is_alive_timeout, self._peer_timeout)
            if mp not in self._monitored_peers:
                self._monitored_peers.append(mp)
            else:
                mp = None
            self.received_peer_message(MSG_PEER_REGISTERED, id)
        finally:
            self._lock.release()
        return mp

    def unregister_monitored_peer(self, monitored_peer):
        """Unregisters a previously registered peer from the monitor.

        @param monitored_peer:
            Instance of MonitoredPeer that shall be unregistered from the monitor

        @return:
            NoneType
        """
        assert monitored_peer is not None
        assert isinstance(monitored_peer, MonitoredPeer)

        if monitored_peer in self._monitored_peers:
            self._monitored_peers.remove(monitored_peer)

    def register_monitored_supporter(self, id, addr, min_peer, max_peer):
        """Registers a supporter server at the monitor.

        @param id:
            ID of the supporter to be registered
        @param addr:
            2-tuple of the form (IP address, port address)
        @param min_peer:
            Minimum number of supportees that have to be assigned to this supporter
            in order to activate it
        @param max_peer:
            Maximum number of supportees that can be assigned to this supporter

        @return:
            The newly created MonitoredSupporter instance. NoneType, if a MonitoredSupporter
            with the given attributes already exists.
        """
        self._lock.acquire()
        ms = None
        try:
            ms = MonitoredSupporter(id, addr, min_peer, max_peer)
            if ms not in self._monitored_supporters:
                self._monitored_supporters.append(ms)
                self._dispatcher.register_proxy(ms)
            else:
                ms = None
        finally:
            self._lock.release()
        return ms

    def unregister_monitored_supporter(self, monitored_supporter):
        """Unregisters a previously registered supporter from the monitor.

        @param monitored_supporter:
            Instance of MonitoredSupporter that shall be unregistered from the monitor

        @return:
            NoneType
        """
        assert monitored_supporter is not None
        assert isinstance(monitored_supporter, MonitoredSupporter)

        if monitored_supporter in self._monitored_supporters:
            monitored_supporter.cancel_support_for_all_peers()
            self._monitored_supporters.remove(monitored_supporter)
            self._dispatcher.unregister_proxy(monitored_supporter)

    def order_active_supporters(self):
        """Orders all active supporters by decreasing value of their available slots.

        @return:
            NoneType
        """
        tmp = [(s, s.available_slots()) for s in self._active_supporters]
        tmp.sort(lambda x, y: cmp(y[1], x[1]))
        self._active_supporters = [s[0] for s in tmp]

    def filter_peers_by_state(self, state_class):
        """Extracts peers with the given state from the list of all registered peers.

        @param state_class:
            Subclass of SupporterMonitor.State which represents the state
            for which we want to filter.

        @return:
            List of registered monitored peers that currently reside in the given state
        """
        return [mp for mp in self._monitored_peers if isinstance(mp.get_state(), state_class)]

    def remaining_active_supporters_with_capacity(self):
        """@return:
            Boolean value, indicating whether we have at least one active supporter that still
            has available slots
        """
        return len(self._active_supporters) != 0 and self._active_supporters[0].available_slots() > 0

    def update_states(self):
        """Performs an asynchronous state update of all registered monitored peers and supporters.
        The method looks for starving peers and tries to assign them to active supporters. If
        starving peers remain afterwards, it tries to activate new supporters in order to support
        those starving peers. Dispatches supportee lists to all active supporters at the end
        of the state update.

        @return:
            NoneType
        """
        self._lock.acquire()
        try:
            self._remove_timedout_peers()
            self._mark_dead_supporters()
            self._remove_dead_supporters()

            self._enforce_update_of_monitored_peers()
            self._enforce_update_of_monitored_supporters()

            self.statistics.snapshot(self)

            self._assign_starving_peers_to_active_supporters()
            # at this point, we still might have some starving peers left, but no active
            # servers with free capacities. but we can see if we are able to activate more
            # supporters.
            self._check_for_activation_of_new_supporters()
            # now send new peer_lists to supporters
            self._dispatcher.dispatch_peer_lists()
        finally:
            self._lock.release()
        self.schedule_next_asynchronous_update()

    def _remove_timedout_peers(self):
        """Removes peers for which the last activity was reported more than PEER_REMOVAL_TIME
        seconds ago.

        @return:
            NoneType
        """
        peers_to_be_removed = []
        ts = time.time()
        for mp in self.get_monitored_peers():
            if (ts - mp.get_ts_last_message()) >= PEER_REMOVAL_TIME:
                peers_to_be_removed.append(mp)
        for mp in peers_to_be_removed:
            self.unregister_monitored_peer(mp)

    def _mark_dead_supporters(self):
        """Tries to contact every registered supporters and marks those that do not respond
        as being dead.

        @return:
            NoneType
        """
        self._dispatcher.query_all_supporters()

    def _remove_dead_supporters(self):
        """Removes supporters that were marked as being dead.

        @return:
            NoneType
        """
        for supporter in self._dead_supporters:
            self.unregister_monitored_supporter(supporter)

    def _enforce_update_of_monitored_peers(self):
        """Triggers an update on all registered monitored peers. This has to be done since
        peer status transitions might happen asynchronously (after a timer runs out).

        @return:
            NoneType
        """
        for mp in self.get_monitored_peers():
            if mp.get_ts_last_request() and (time.time() - mp.get_ts_last_request() > 10):
                mp.set_state(DefaultState(mp))
            else:
                mp.get_state().transition()

    def _enforce_update_of_monitored_supporters(self):
        """Triggers an update on all registered supporters. This includes the potential transition
        from ACTIVE to INACTIVE for a specific supporter. Updates the active supporter list.

        @return:
            NoneType
        """
        # check for all supporters if they have peers in their supported list
        # that no longer need support (state == DEFAULT)
        supporters_to_be_inactivated = []
        for supporter in self._active_supporters:
            supporter.update_supported_peer_list()
            if supporter.assigned_slots() == 0:
                supporters_to_be_inactivated.append(supporter)
        self._active_supporters = [s for s in self._active_supporters if s not in supporters_to_be_inactivated]

    def sort_starving_peers(self, starving_peers):
        nl = []
        for p in starving_peers:
            if self.number_of_assignments.has_key(p.get_id()):
                nl.append((self.number_of_assignments[p.get_id()], p))
            else:
                nl.append((0, p))
        nl.sort(lambda x, y: cmp(y[0], x[0]))  # cause we sort in descending order
        return [p[1] for p in nl]

    def _assign_starving_peers_to_active_supporters(self):
        """Tries to assign starving peers to already active supporters. This method relies on the
        available slots of all currently active supporters, which means that it can fail to
        allocate slots for all starving peers.

        @return:
            NoneType
        """
        starving_peers = self.filter_peers_by_state(StarvingState)
        starving_peers = self.sort_starving_peers(starving_peers)

        while len(starving_peers) > 0:
            peer = starving_peers[0]  # always take out the peer from the front, otherwise this loop wont work
            # 2. do we have active servers with free slots? it suffices to look
            # at the first supporter of the active list, since we keep this list
            # ordered
            active_supporters = self.get_active_supporters()

            if self.remaining_active_supporters_with_capacity():
                # assign peer to supporter and re-order the active list 
                self.assign_peer_to_supporter(peer, active_supporters[0])
                starving_peers.remove(peer)
                self.order_active_supporters()
            else:

                # this is the case if we have no longer any active supporters that
                # can provide slots to suffering peers. we break in this case and
                # handle the set of remaining peers (starving_peers) next
                break

    def _check_for_activation_of_new_supporters(self):
        """Checks if we can activate new supporters in order to support remaining starving peers
        (that could not be assigned to a supporter during the current update phase).

        @return:
            NoneType
        """

        def sorted_list_of_inactive_supporters():
            # create a list with supporters that are inactive and sort this list
            # in ascending order of min_peers, since we want to help suffering
            # peers as fast as possible (but please consider the fact this will
            # not result in an optimal distribution of starving peers in combination
            # with the used assignment algorithm underneath
            inactive_supporters = [(s, s.get_min_peer()) for s in self._monitored_supporters if
                                   s not in self._active_supporters]
            if len(inactive_supporters) == 0:
                return []
            inactive_supporters.sort(lambda x, y: cmp(x[1], y[1]))
            return inactive_supporters

        def retrieve_activation_index(starving_peers, inactive_supporters):
            # checks how many supporters (up to some index i) should be activated in order
            # to supply data to starving peers. this algorithm is quite simple. actually, we have a 
            # bin packing problem here at hand which we dont solve optimally using this algorithm.
            # the method used here is a very simple greedy approach, which might not assign peers 
            # optimally, meaning that some peers might remain in the STARVING state, although we 
            # could obtain a better result if our algorithm was better.
            starving_number = len(starving_peers)
            activate_up_to_index = -1
            for i in xrange(len(inactive_supporters)):
                if starving_number >= inactive_supporters[i][1]:
                    starving_number -= inactive_supporters[i][0].available_slots()
                    activate_up_to_index = i
                else:
                    break
            return activate_up_to_index

        def activate_supporters_and_assign_peers(index, starving_peers):
            # activates new supporters from the sorted inactivate supporters list starting from
            # index 0 up to the given max. index. the method assigns starving peers on-the-fly
            # to freshly activated supporters.
            if activate_up_to_index >= 0:
                for i in xrange(0, activate_up_to_index + 1):  # bound for xrange has to be +1
                    self.activate_supporter(inactive_supporters[i][0])
                    assigned_peers = []
                    for peer in starving_peers:
                        self.assign_peer_to_supporter(peer, inactive_supporters[0][0])
                        assigned_peers.append(peer)
                        if inactive_supporters[0][0].available_slots() == 0:
                            break
                    starving_peers = [p for p in starving_peers if p not in assigned_peers]
                # we activated some new supporters and have to maintain their sorting order now
                self.order_active_supporters()

        starving_peers = self.filter_peers_by_state(StarvingState)
        inactive_supporters = sorted_list_of_inactive_supporters()
        activate_up_to_index = retrieve_activation_index(starving_peers, inactive_supporters)
        activate_supporters_and_assign_peers(activate_up_to_index, starving_peers)

    def activate_supporter(self, monitored_supporter):
        """Activates the given MonitoredSupporter.

        @param monitored_supporter:
            Instance of MonitoredSupporter which represents the
            supporter that shall transition from INACTIVE to ACTIVE

        @return:
            NoneType
        """
        assert monitored_supporter is not None
        assert isinstance(monitored_supporter, MonitoredSupporter)

        if monitored_supporter.assigned_slots() != 0:
            # already activated
            return

        self._active_supporters.append(monitored_supporter)

    def inactivate_supporter(self, monitored_supporter):
        """Inactivates the given MonitoredSupporter if no peer is currently assigned to it.

        @param monitored_supporter:
            Instance of MonitoredSupporter which represents the
            supporter that shall transition from ACTIVE to INACTIVE

        @return:
            NoneType
        """
        assert monitored_supporter is not None
        assert isinstance(monitored_supporter, MonitoredSupporter)

        if monitored_supporter.assigned_slots() == 0:
            self._active_supporters.remove(monitored_supporter)

    def assign_peer_to_supporter(self, monitored_peer, monitored_supporter):
        """Assigns a peer to an active supporter and triggers the update of the peer's state.

        @param monitored_peer:
            Instance of MonitoredPeer which represents the peer that
            will be supported by the given MonitoredSupporter
        @param monitored_supporter:
            Instance of MonitoredSupporter which represents the supporter
            to which the given MonitoredPeer shall be assigned

        @return:
            NoneType
        """
        assert monitored_peer is not None
        assert monitored_supporter is not None

        if monitored_supporter not in self._active_supporters:
            return

        monitored_supporter.add_supported_peer(monitored_peer)
        self.order_active_supporters()
        monitored_peer.receive_msg(MSG_PEER_SUPPORTED)

        # update the number of assignments
        self.number_of_assignments.setdefault(monitored_peer.get_id(), 1)
        self.number_of_assignments[monitored_peer.get_id()] += 1

    def received_peer_message(self, msg_type, peer_id):
        """Handler method for incoming peer messages. Dispatches the message to the resp.
        monitored peer.

        @param msg_type:
            Represents the type of the message
        @param peer_id:
            The ID of the peer that sent the original message

        @return:
            NoneType
        """
        self._lock.acquire()
        found = False
        try:
            for peer in self.get_monitored_peers():
                if peer_id == peer.get_id():
                    self._logger.debug("Dispatching %s message to %s" % (msg_type, peer_id))
                    peer.receive_msg(msg_type)
                    found = True
                    break
            if not found:
                self._logger.warning("Got an unregistered peer ID: %s" % peer_id)
        finally:
            self._lock.release()


class MonitorState(object):
    """The MonitorState class provides static methods for summarizing the current state of
    a SupporterMonitor object. The generated output follows the HTML format and gives information
    on monitored peers (current state, address, ...) as well as monitored supporters (assigned
    supportees, ...).
    """

    def __init__(self):
        self.statistics = open('supporter_statistics.log', 'w')

    def __del__(self):
        if self.statistics is not None:
            self.statistics.close()

    def snapshot(self, monitor):
        monitored_peers = monitor.get_monitored_peers()

        nr_default, nr_watched, nr_starving, nr_supported = 0, 0, 0, 0

        for mp in monitored_peers:
            state = mp.get_state()
            if isinstance(state, DefaultState):
                nr_default += 1
            elif isinstance(state, WatchedState):
                nr_watched += 1
            elif isinstance(state, StarvingState):
                nr_starving += 1
            elif isinstance(state, SupportedState):
                nr_supported += 1

        dispatch = "%1.2f\t%i\t%i\t%i\t%i" % (time.time(), nr_default, nr_watched, nr_starving, nr_supported)
        dispatch = dispatch.encode("utf-8")

        self.statistics.write(dispatch)
        self.statistics.write('\n')
        self.statistics.flush()

    def _monitored_peers_to_html(monitor):
        """Static method which generates HTML-formatted information on the state of all
        peers a SupporterMonitor currently watches.

        @param monitor:
            Represents the instance of SupporterMonitor for which the state summary shall be
            generated

        @return:
            HTML representation containing state information on all peers that are currently
            watched by the given SupporterMonitor instance
        """
        monitored_peers = monitor.get_monitored_peers()

        html_string = '<h3>Monitored Peers</h3>\n'

        if len(monitored_peers) == 0:
            html_string += 'Nothing to report yet.\n'
        else:

            html_string += '<table border=1 cellspacing=1>\n'
            html_string += '<tr><th>ID</th><th>Address</th><th>Current State</th><th>Last received message</th><th># Support Requests</th></tr>\n'
            for peer in monitor.get_monitored_peers():
                html_string += '<tr>\n'
                html_string += '<td>%s</td>' % peer.get_id()
                html_string += '<td>%s:%i</td>' % (peer.get_ip(), peer.get_port())
                html_string += '<td>%s</td>' % str(peer.get_state())
                html_string += '<td>%s</td>' % peer.get_last_received_msg()
                html_string += '<td>%i</td>' % peer.get_number_of_support_requests()
                html_string += '</tr>\n'
            html_string += '<table>\n'

        return html_string

    _monitored_peers_to_html = staticmethod(_monitored_peers_to_html)

    def _monitored_supporters_to_html(monitor):
        """Static method which generates HTML-formatted output on the state of all supporter
        servers a SupporterMonitor currently watches.

        @param monitor:
            Represents the instance of SupporterMonitor for which the state summary shall be
            generated

        @return:
            HTML representation containing state information on all supporter servers that the
            given SupporterMonitor instance currently watches
        """
        monitored_supporters = monitor.get_monitored_supporters()

        html_string = '<h3>Monitored Supporters</h3>\n'

        if len(monitored_supporters) == 0:
            html_string += 'Nothing to report yet.\n'
        else:

            html_string += '<table border=1 cellspacing=1>\n'
            html_string += '<tr><th>ID</th><th>Address</th><th># Supportees</th><th># Slots Available</th></tr>\n'
            for supporter in monitor.get_monitored_supporters():
                html_string += '<tr>\n'
                html_string += '<td>%s</td>' % str(supporter.get_id())
                html_string += '<td>%s</td>' % str(supporter.get_addr())
                html_string += '<td>%i</td>' % supporter.assigned_slots()
                html_string += '<td>%i</td>' % supporter.available_slots()
                html_string += '</tr>\n'
            html_string += '</table>\n'

        return html_string

    _monitored_supporters_to_html = staticmethod(_monitored_supporters_to_html)

    def retrieve_monitor_state_as_html(monitor):
        """Static method which generates HTML-formatted output on the current state of all
        watched peers and supporters of the given SupporterMonitor instance. This method
        synchronizes against the SupporterMonitor instance and can thus be called by
        client code in a thread-safe manner.

        @param monitor:
            Represents the instance of SupporterMonitor for which the
            state summary shall be generated

        @return:
            HTML representation of the above mentioned state information
        """
        assert isinstance(monitor, SupporterMonitor)

        monitor._lock.acquire()
        html_string = ''
        try:
            html_string += '<h2>Supporter Monitor State</h2>\n'
            html_string += MonitorState._monitored_peers_to_html(monitor)
            html_string += MonitorState._monitored_supporters_to_html(monitor)
        finally:
            monitor._lock.release()
        return html_string

    retrieve_monitor_state_as_html = staticmethod(retrieve_monitor_state_as_html)