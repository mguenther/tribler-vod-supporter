# -*- coding: utf-8 -*-

__author__ = "Markus Guenther (markus.guenther@gmail.com)"

import unittest
import time

import supporter.shared as shared

from supporter.supporter_monitor import SupporterMonitor
from supporter.monitored_subjects import MonitoredSupporter
from supporter.state_machine import DefaultState, SupportedState, StarvingState

TEST_IS_ALIVE_TIMEOUT_BOUND = 2
TEST_PEER_TIMEOUT_BOUND = 1

        
class TestSupporterMonitor(unittest.TestCase):
    def setUp(self):
        pass
    
    def tearDown(self):
        pass
    
    def testUnregisterMonitoredPeers(self):
        """Tests if peers can be properly unregistered from a SupporterMonitor instance."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        mp1 = monitor.register_monitored_peer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER)
        mp2 = monitor.register_monitored_peer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER)
        self.assertTrue(len(monitor.get_monitored_peers()) == 2)
        monitor.unregister_monitored_peer(mp1)
        self.assertTrue(len(monitor.get_monitored_peers()) == 1)
        monitor.unregister_monitored_peer(mp2)
        self.assertTrue(len(monitor.get_monitored_peers()) == 0)
    
    def testPeersRemainInStarvingState(self):
        """Peers remain in STARVING state if no supporter can be activated."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        monitor.register_monitored_peer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_peer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_supporter(1, ('192.168.2.10', 1024), 3, 5)

        monitor.update_states()
        
        self.assertTrue(len(monitor.get_monitored_peers()) == 2)
        self.assertTrue(len(monitor.get_monitored_supporters()) == 1)
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(DefaultState)) == 2)
        
        for _ in xrange(5):
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920F')
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920G')
        monitor.update_states()
            
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 2)
    
    def testSimpleProtocol(self):
        """Simple test for correct supporter assignments, state transitions and supporter activations."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        monitor.register_monitored_peer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_supporter(1, ('192.168.2.1', 1024), 2, 5)
        
        self.assertTrue(len(monitor.get_monitored_peers()) == 1)
        self.assertTrue(len(monitor.get_monitored_supporters()) == 1)
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(DefaultState)) == 1)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 0)
        
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920F')
            
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 1)
        
        monitor.update_states()
                
        monitor.register_monitored_peer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER)
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920G')
            
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 2)
        
        monitor.update_states()
        
        self.assertTrue(len(monitor.get_active_supporters()) == 1)
        self.assertTrue(len(monitor.filter_peers_by_state(SupportedState)) == 2)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 0)
        
        monitor.received_peer_message(shared.MSG_SUPPORT_NOT_NEEDED, 'XXX---34920F')
        monitor.received_peer_message(shared.MSG_SUPPORT_NOT_NEEDED, 'XXX---34920G')
        time.sleep(shared.PEER_TIMEOUT_BOUND)
        
        monitor.update_states()
        
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(DefaultState)) == 2)
        self.assertTrue(len(monitor.filter_peers_by_state(SupportedState)) == 0)
        
    def testActivatingMoreThanOneSupporterAtOnce(self):
        """Checks if we can activate more than one supporter during one monitor state update."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        monitor.register_monitored_supporter(1, ('192.168.2.10', 5000), 2, 2)
        monitor.register_monitored_supporter(2, ('192.168.2.11', 5001), 1, 1)
        monitor.register_monitored_peer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_peer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_peer('XXX---34920H', '192.168.2.52', 10002, shared.PEER_TYPE_LEECHER)
        
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920F')
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920G')
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920H')
        
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 3)
        self.assertTrue(len(monitor.filter_peers_by_state(SupportedState)) == 0)
        
        monitor.update_states()
        
        self.assertTrue(len(monitor.get_active_supporters()) == 2)
        self.assertTrue(len(monitor.filter_peers_by_state(SupportedState)) == 3)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 0)
        
    def testActivateOneSupporterFromMultipleInactiveSupporters(self):
        """Checks if the activation algorithm considers min_peers/max_peers together.

        The outcome of the test should be, that only one of the two available supporters
        is activated. If the activation algorithm just focuses on min_peers, it will
        activate both supporters, which should not happen."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        monitor.register_monitored_supporter(1, ('192.168.2.10', 5000), 2, 3)
        monitor.register_monitored_supporter(2, ('192.168.2.11', 5001), 1, 3)
        monitor.register_monitored_peer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_peer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_peer('XXX---34920H', '192.168.2.52', 10002, shared.PEER_TYPE_LEECHER)

        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920F')
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920G')
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920H')
        
        self.assertTrue(len(monitor.get_active_supporters()) == 0)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 3)
        self.assertTrue(len(monitor.filter_peers_by_state(SupportedState)) == 0)
        
        monitor.update_states()
        
        self.assertTrue(len(monitor.get_active_supporters()) == 1)
        self.assertTrue(len(monitor.filter_peers_by_state(SupportedState)) == 3)
        self.assertTrue(len(monitor.filter_peers_by_state(StarvingState)) == 0)
    
    def testCorrectOrderOfActiveSupporters(self):
        """Checks if the ordering of active supporters is correct."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        s1 = monitor.register_monitored_supporter(1, ('192.168.2.50', 5000), 1, 1)
        s2 = monitor.register_monitored_supporter(2, ('192.168.2.51', 5001), 1, 6)
        monitor.register_monitored_peer('XXX---34920F', '192.168.2.50', 10000, shared.PEER_TYPE_LEECHER)
        monitor.register_monitored_peer('XXX---34920G', '192.168.2.51', 10001, shared.PEER_TYPE_LEECHER)
        
        for _ in xrange(shared.PEER_REQUIRED_MSGS):
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920F')
            monitor.received_peer_message(shared.MSG_SUPPORT_REQUIRED, 'XXX---34920G')
        monitor.update_states()
        
        self.assertTrue(len(monitor.get_active_supporters()) == 2)
        self.assertEquals(monitor.get_active_supporters()[0], s2)
        self.assertEquals(monitor.get_active_supporters()[1], s1)
        
    def testUpdateCallWithoutHavingPeersOrSupportersSucceeds(self):
        """Tests if the update call succeeds if no peers/supporters are registered.

        Actually, there was a bug that was seen during writing the tracker integration code that
        was caused when update_states() was called when no peers/supporters were registered
        at the monitor. This test remains in the testsuite, so that this bug will not get
        introduced again."""
        monitor = SupporterMonitor(TEST_IS_ALIVE_TIMEOUT_BOUND, TEST_PEER_TIMEOUT_BOUND)
        monitor._dispatcher = MockSupporteeListDispatcher(monitor)
        monitor.update_states()


class MockSupporteeListDispatcher():
    def __init__(self, monitor):
        assert isinstance(monitor, SupporterMonitor)
        
        self._monitor = monitor
        
    def register_proxy(self, supporter):
        assert isinstance(supporter, MonitoredSupporter)

        
    def unregister_proxy(self, supporter):
        assert isinstance(supporter, MonitoredSupporter)
    
    def dispatch_peer_lists(self):
        pass
    
    def query_all_supporters(self):
        pass