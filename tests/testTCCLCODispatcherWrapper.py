#!/usr/bin/env python2
from __future__ import division, absolute_import

import RO.Comm.Generic
RO.Comm.Generic.setFramework("twisted")
from twisted.trial.unittest import TestCase
from twisted.internet import reactor

from tcc.actor import TCCLCODispatcherWrapper

from twistedActor import testUtils
testUtils.init(__file__)

class TestMirrorDispatcherWrapper(TestCase):
    """Test basics of MirrorDispatcherWrapper
    """
    def setUp(self):
        self.dw = TCCLCODispatcherWrapper()
        return self.dw.readyDeferred

    def tearDown(self):
        self.dw.actorWrapper.actor.collimateStatusTimer.cancel()
        delayedCalls = reactor.getDelayedCalls()
        for call in delayedCalls:
            call.cancel()
        return self.dw.close()

    def testSetUpTearDown(self):
        self.assertFalse(self.dw.didFail)
        self.assertFalse(self.dw.isDone)
        self.assertTrue(self.dw.isReady)


if __name__ == '__main__':
    from unittest import main
    main()
