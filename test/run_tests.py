# -*- coding: utf-8 -*-

__author__ = 'Markus Guenther (markus.guenther@gmail.com)'

import unittest

from test_monitored_subjects import TestMonitoredPeer, TestMonitoredSupporter
from test_supporter_monitor import TestSupporterMonitor

def collect_testsuites():
    suites = [unittest.TestLoader().loadTestsFromTestCase(TestMonitoredPeer),
              unittest.TestLoader().loadTestsFromTestCase(TestMonitoredSupporter),
              unittest.TestLoader().loadTestsFromTestCase(TestSupporterMonitor)]
    return suites

if __name__ == "__main__":

    suite = unittest.TestSuite(collect_testsuites())
    unittest\
        .TextTestRunner(verbosity=2)\
        .run(suite)