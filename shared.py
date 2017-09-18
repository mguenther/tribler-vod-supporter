# -*- coding: utf-8 -*-

__author__ = 'Markus Guenther (markus.guenther@gmail.com'

"""This module holds constants and default values for the supporter monitor component."""

MSG_SUPPORT_REQUIRED = "support_required"
MSG_SUPPORT_NOT_NEEDED = "support_not_needed"
MSG_PEER_SUPPORTED = "peer_supported"
MSG_PEER_REGISTERED = "peer_registered"

PEER_TIMEOUT_BOUND = 5  # seconds (should not be set too high!)
IS_ALIVE_TIMEOUT_BOUND = 10  # every peer transitions back to default state if it has not send
# any messages for IS_ALIVE_TIMEOUT_BOUND seconds
PEER_REQUIRED_MSGS = 4
# the underneath parameters represents the time interval in which a peer has to send its
# requests, so it can transition to the STARVING state. the value is based on the total number
# of required requests (for every request, we assume 1 second), and a typical RTT value which
# is taken into account for every made request)
PEER_STATUS_APPROVAL_TIME = PEER_REQUIRED_MSGS * (1 + 0.150)
PEER_REMOVAL_TIME = 45  # removes a monitored peer if the last activity was reported more
# than PEER_REMOVAL_TIME seconds ago

PEER_TYPE_SEEDER = 0
PEER_TYPE_LEECHER = 1
PEER_TYPES = [PEER_TYPE_SEEDER, PEER_TYPE_LEECHER]