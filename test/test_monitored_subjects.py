# -*- coding: utf-8 -*-

__author__ = 'Markus Guenther (markus.guenther@gmail.com)'

import time
import unittest

import supporter.shared as shared

from supporter.monitored_subjects import MonitoredPeer, MonitoredSupporter
from supporter.state_machine import DefaultState, WatchedState, StarvingState, SupportedState

TEST_IS_ALIVE_TIMEOUT_BOUND = 2
TEST_PEER_TIMEOUT_BOUND = 1


class TestMonitoredPeer(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def testMonitoredPeerDefaults(self):
        """Tests proper setup of a new MonitoredPeer instance (including defaults).
        """
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10333, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        self.assertEquals('XXX---34920F', peer.get_id())
        self.assertEquals('192.168.2.1', peer.get_ip())
        self.assertEquals(10333, peer.get_port())
        self.assertEquals(shared.PEER_TYPE_LEECHER, peer.get_peer_type())
        # check default values
        self.assertTrue(isinstance(peer.get_state(), DefaultState))
        self.assertEquals(None, peer.get_ts_first_request())
        self.assertEquals(None, peer.get_ts_last_request())
        self.assertEquals(0, peer.get_number_of_support_requests())
        self.assertEquals(None, peer.get_last_received_msg())

    def testMonitoredPeerWithInvalidArguments(self):
        """Tests instantiation of a MonitoredPeer with invalid arguments.
        """
        try:
            _ = MonitoredPeer('XXX---34920F', '192.168.2.1', 500, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
            self.fail("The instantiation should have raised an AssertionError")
        except AssertionError:
            pass

    def testMonitoredPeerStateCorrectNextCycle(self):
        """Tests if a peer can walk through two cycles.

        This test shows that the extended tracker monitors peer states correctly as they
        progress the state diagram. A peer transitions along the following path of states
        during this test:

        DEFAULT -> WATCHED -> DEFAULT -> WATCHED -> STARVING -> SUPPORTED -> DEFAULT

        The test also ensures that the internal attributes are set to the correct values
        after each state transition.
        """
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)

        self.assertTrue(isinstance(peer.get_state(), WatchedState))

        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)

        self.assertTrue(isinstance(peer.get_state(), DefaultState))
        self.assertEquals(None, peer.get_ts_first_request())
        self.assertEquals(None, peer.get_ts_last_request())
        self.assertEquals(0, peer.get_number_of_support_requests())

        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), WatchedState))
        self.assertNotEquals(None, peer.get_ts_first_request())
        self.assertNotEquals(None, peer.get_ts_last_request())
        self.assertEquals(peer.get_ts_first_request(), peer.get_ts_last_request())
        self.assertEquals(1, peer.get_number_of_support_requests())
        # new cycle has started
        for _ in xrange(5):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), StarvingState))

        peer.receive_msg(shared.MSG_PEER_SUPPORTED)
        self.assertTrue(isinstance(peer.get_state(), SupportedState))
        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)
        time.sleep(1)
        # this transition call would normally have to happen asynchronously through the
        # SupporterMonitor's cyclic transition check
        peer.get_state().transition()
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

    def testMonitoredPeerStateTransitionsEarlyCancel(self):
        """Tests if a peer can cancel its request while being in WATCHED state.

        This test shows that the extended tracker monitors peer states correctly as they
        progress a part of the state diagram. A peer transitions along the following path of
        states during this test:

        DEFAULT -> WATCHED -> DEFAULT (early cancel due to sending of buffer full msg)

        The test also ensures that the internal attributes are set to the correct values
        after each state transition.
        """
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        self.assertTrue(isinstance(peer.get_state(), DefaultState))
        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), WatchedState))
        self.assertEquals(1, peer.get_number_of_support_requests())
        self.assertEquals(shared.MSG_SUPPORT_REQUIRED, peer.get_last_received_msg())
        self.assertNotEquals(None, peer.get_ts_first_request())
        self.assertNotEquals(None, peer.get_ts_last_request())
        self.assertEquals(peer.get_ts_first_request(), peer.get_ts_last_request())
        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)
        self.assertTrue(isinstance(peer.get_state(), DefaultState))
        self.assertEquals(0, peer.get_number_of_support_requests())
        self.assertEquals(None, peer.get_ts_first_request())
        self.assertEquals(None, peer.get_ts_last_request())

    def testMonitoredPeerStateTransitionsFull(self):
        """Tests if a peer can transition through all states correctly.

        This test shows that the extended tracker monitors peer states correctly as they
        progress the state diagram completely. A peer transitions along the following path
        of states during this test:

        DEFAULT -> WATCHED -> STARVING -> SUPPORTED -> DEFAULT (on buffer full msg)

        The test also ensures that the internal attributes are set to the correct values
        after each state transition.
        """
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        self.assertTrue(isinstance(peer.get_state(), DefaultState))
        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertEquals(shared.MSG_SUPPORT_REQUIRED, peer.get_last_received_msg())
        self.assertEquals(1, peer.get_number_of_support_requests())
        self.assertNotEquals(None, peer.get_ts_first_request())
        self.assertTrue(isinstance(peer.get_state(), WatchedState))

        for _ in xrange(5):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)

        self.assertEquals(shared.MSG_SUPPORT_REQUIRED, peer.get_last_received_msg())
        self.assertTrue(isinstance(peer.get_state(), StarvingState))
        peer.receive_msg(shared.MSG_PEER_SUPPORTED)
        self.assertEquals(shared.MSG_PEER_SUPPORTED, peer.get_last_received_msg())
        self.assertTrue(isinstance(peer.get_state(), SupportedState))
        # TODO: also check with server side message (timeout)
        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)
        self.assertEquals(shared.MSG_SUPPORT_NOT_NEEDED, peer.get_last_received_msg())
        time.sleep(1)
        peer.get_state().transition()
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

    def testMonitoredPeerStateRequiredMsgsInIntervalNotMet(self):
        """Tests if the time interval requirements for the transition from WATCHED to STARVING are met.

        This test simulates PEER_REQUIRED_MSGS support required message arrivals over a time period
        greater than the time window in which they should arrive, so that the transition from
        WATCHED to STARVING can be carried out. To pass this test, the peer should remain in
        the WATCHED state after the last message was received.
        """
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)

        for _ in xrange(shared.PEER_REQUIRED_MSGS-1):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), WatchedState))
        time.sleep(shared.PEER_STATUS_APPROVAL_TIME+1)
        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        # although we have now received PEER_REQUIRED_MSGS support messages, the peer has not
        # transitioned to the starving state, since those messages arrived over a time which
        # is greater than the calculated time bound in which they should have arrived
        self.assertTrue(isinstance(peer.get_state(), WatchedState))

    def testSlidingWindowOnRequestTime(self):
        """Checks if the sliding window for arrived support requests works correctly."""
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)

        for _ in xrange(shared.PEER_REQUIRED_MSGS-1):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), WatchedState))
        time.sleep(shared.PEER_STATUS_APPROVAL_TIME+1)
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), StarvingState))

    def testPeerTimesOut(self):
        """Test transitions from {WATCHED,STARVING,SUPPORTED} to DEFAULT.

        In the implementation, the timeout is only relevant if we want to transition
        from SUPPORTED to DEFAULT. Transitions from {WATCHED,STARVING} to DEFAULT
        should happen instantaneously if the peer informs the SupporterMonitor that
        his buffer is full.
        """
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)

        # test the transition on buffer full + timeout from WATCHED -> DEFAULT
        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), WatchedState))
        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

        # test the transition on buffer full + timeout from STARVING -> DEFAULT
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), StarvingState))
        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

        # test the transition on buffer full + timeout from SUPPORTED -> DEFAULT
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), StarvingState))
        peer.receive_msg(shared.MSG_PEER_SUPPORTED)
        self.assertTrue(isinstance(peer.get_state(), SupportedState))
        peer.receive_msg(shared.MSG_SUPPORT_NOT_NEEDED)
        time.sleep(shared.PEER_TIMEOUT_BOUND)
        peer.get_state().transition()
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

    def testEqualityTest(self):
        """Tests if two monitored peers with same static attributes are considered equal."""
        p1 = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        p2 = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        self.assertEquals(p1, p2)

    def testPeerIsAliveTriggersStateTransitionsCorrectly(self):
        """Tests if peer states transition back to DEFAULT state if peer is considered as not being alive."""
        peer = MonitoredPeer('XXX---34920F', '192.168.2.1', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        peer.receive_msg(shared.MSG_PEER_REGISTERED)

        # transition from WATCHED -> DEFAULT on is-alive timeout
        peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), WatchedState))
        time.sleep(shared.IS_ALIVE_TIMEOUT_BOUND)
        self.assertFalse(peer.peer_is_alive())
        peer.get_state().transition()
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

        # transition from STARVING -> DEFAULT on is-alive timeout
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        self.assertTrue(isinstance(peer.get_state(), StarvingState))
        time.sleep(shared.IS_ALIVE_TIMEOUT_BOUND)
        self.assertFalse(peer.peer_is_alive())
        peer.get_state().transition()
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

        # transition from SUPPORTED -> DEFAULT on is-alive timeout
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            peer.receive_msg(shared.MSG_SUPPORT_REQUIRED)
        peer.receive_msg(shared.MSG_PEER_SUPPORTED)
        self.assertTrue(isinstance(peer.get_state(), SupportedState))
        time.sleep(shared.IS_ALIVE_TIMEOUT_BOUND)
        peer.get_state().transition()
        self.assertTrue(isinstance(peer.get_state(), DefaultState))

class TestMonitoredSupporter(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def testInstantiationWithCorrectParameters(self):
        """Tests if the instantiation of MonitoredSupporter works, given correct parameters."""
        supporter = MonitoredSupporter(1, ('192.168.2.1', 1024), 3, 5)
        self.assertEquals(('192.168.2.1', 1024), supporter.get_addr())
        self.assertEquals(1, supporter.get_id())
        self.assertEquals(3, supporter.get_min_peer())
        self.assertEquals(5, supporter.get_max_peer())
        self.assertEquals(5, supporter.available_slots())
        self.assertEquals(0, supporter.assigned_slots())

    def testInstantiationWithIncorrectParameters(self):
        """Tests if the instantiation of MonitoredSupporter fails correctly, given wrong parameters."""
        try:
            _ = MonitoredSupporter(1, None, 3, 5)
            self.fail("Supporter address incorrect. Expected: (ip,port) tuple, given: None")
        except AssertionError:
            pass

        try:
            _ = MonitoredSupporter(1, ('192.168.2.1', 1000), 3, 5)
            self.fail("Port number incorrect. Expected: port >= 1024, given: 1000")
        except AssertionError:
            pass

        try:
            _ = MonitoredSupporter(1, ('192.168.2.1', 1024), 5, 4)
            self.fail("min-/max_peers wrong. Expected: min_peers <= max_peers, given: 5 > 4")
        except AssertionError:
            pass

    def testMaintainSupporteeList(self):
        """Tests if the maintenance of the supportee list works correctly."""
        supporter = MonitoredSupporter(1, ('192.168.2.1', 1024), 2, 5)
        p1 = MonitoredPeer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        p2 = MonitoredPeer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        p3 = MonitoredPeer('XXX---34920H', '192.168.2.52', 10002, shared.PEER_TYPE_LEECHER, TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        supporter.add_supported_peer(p1)
        self.assertFalse(supporter.minimum_starving_peers_reached())
        supporter.add_supported_peer(p2)
        self.assertEquals(2, supporter.assigned_slots())
        self.assertEquals(3, supporter.available_slots())
        self.assertTrue(supporter.minimum_starving_peers_reached())
        supporter.add_supported_peer(p3)
        self.assertEquals(3, supporter.assigned_slots())
        self.assertEquals(2, supporter.available_slots())
        supporter.remove_supported_peer(p1)
        self.assertEquals(2, supporter.assigned_slots())
        self.assertEquals(3, supporter.available_slots())
        supporter.remove_supported_peer(p2)
        self.assertEquals(1, supporter.assigned_slots())
        self.assertEquals(4, supporter.available_slots())
        # TODO: see remark in MonitoredSupporter.inactivate
        self.assertFalse(supporter.minimum_starving_peers_reached())

    def testEqualityTest(self):
        """Tests if two monitored supporters with same static attributes are considered equal."""
        s1 = MonitoredSupporter(1, ('192.168.2.1', 1024), 2, 5)
        s2 = MonitoredSupporter(1, ('192.168.2.1', 1024), 2, 5)
        self.assertEquals(s1, s2)