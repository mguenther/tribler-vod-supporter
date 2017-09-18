# -*- coding: utf-8 -*-

__author__ = 'Markus Guenther (markus.guenther@gmail.com)'

"""
This module implements an XMLRPC-based adapter for sending serializable data to supporter server.
"""

import logging
import sys
import xmlrpclib


class SupporteeListDispatcher(object):
    """This class implements a strategy to dispatch supportee lists to specific supporter
    servers. The communication runs over XML-RPC. The implementation requires the establishment
    of a proxy for every registered supporter.
    """

    def __init__(self, monitor):
        self._monitor = monitor
        self._logger = logging.getLogger("Tracker.SupporterMonitor.XMLRPC")
        # mapping: hash(MonitoredSupporter) => XML/RPC proxy for that supporter
        self._proxies = {}

    def register_proxy(self, supporter):
        """Creates a proxy for the given supporter.

        @param supporter:
            MonitoredSupporter instance representing the supporter to establish the connection to

        @return:
            NoneType
        """
        proxy_uri = "http://%s:%i" % (supporter.get_addr()[0], supporter.get_addr()[1] + 1)
        self._proxies[supporter] = xmlrpclib.ServerProxy(proxy_uri)

    def unregister_proxy(self, supporter):
        """Dereferences the proxy for the given supporter (if the proxy was created prior
        by calling SupporteeListDispatcher.register_proxy).

        @param supporter:
            MonitoredSupporter instance representing the supporter for which the proxy
            shall be terminated

        @return:
            NoneType
        """
        if self._proxies.has_key(supporter):
            self._proxies[supporter] = None
            del self._proxies[supporter]

    def query_all_supporters(self):
        """Queries all registered supporters in order to check if they are still alive. If a
        supporter is considered as being dead, it will be marked for removal from the
        supporter monitor.

        @return:
            NoneType
        """
        for supporter in self._monitor.get_monitored_supporters():
            proxy = self._proxies[supporter]
            try:
                proxy.is_alive()
            except:
                self._logger.info("Supporter at %s:%s is not responding. Marking it for unregistering.")
                self._monitor._dead_supporters.append(supporter)

    def dispatch_peer_lists(self):
        """Collects supportee data for every monitored supporter and dispatches the resulting
        supportee lists via the XML-RPC proxy interface to the resp. supporter.

        @return:
            NoneType
        """
        for supporter in self._monitor.get_monitored_supporters():
            if not supporter.reset_update_counter():
                continue  # NO CHANGES!
            # gather peers
            peers_to_be_unchoked = []
            for peer in supporter.get_supported_peers():
                peers_to_be_unchoked.append((peer.get_id(), peer.get_ip(), peer.get_port()))

            if supporter in self._proxies.keys():
                proxy = self._proxies[supporter]
                # send peer list to resp. supporter
                try:
                    proxy.receive_peer_list(peers_to_be_unchoked)
                    sys.stderr.write(
                        "Let supporter %s support peers %s\n" % (supporter.get_addr(), peers_to_be_unchoked))
                except:
                    sys.stderr.write(
                        "Failed to connect to supporter %s:%i\n" % (supporter.get_addr()[0], supporter.get_addr()[1]))