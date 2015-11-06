#!/usr/bin/env python2
from __future__ import division, absolute_import
"""Run the TCC LCO actor
"""
import sys
import traceback
import os

from twisted.internet import reactor
# from twistedActor import startSystemLogging
from twistedActor import startFileLogging

from tcc.actor.tccLCOActor import TCCLCOActor
from tcc.lco import TCSDevice, ScaleDevice, FakeScaleCtrl, FakeTCS

# log to directory $HOME/tcclogs/
homeDir = os.path.expanduser("~")
logPath = os.path.join(homeDir, "tcclogs")
if not os.path.exists(logPath):
    os.makedirs(logPath)

startFileLogging(os.path.join(logPath, "tcc"))
# startSystemLogging(TCC25mActor.Facility)

UserPort = 25000
UDPPort = 25010

ScaleDevicePort = 26000
TCSDevicePort = 27000
# TCSDevicePort = 4242
# TCSDevicePort = 50016


print "Start fake LCO controllers"
fakeScaleController  = FakeScaleCtrl("fakeScale",  ScaleDevicePort)
fakeTCS = FakeTCS("mockTCSDevice", TCSDevicePort)

def startTCCLCO(*args):
    try:
        tccActor = TCCLCOActor(
            name = "tccLCOActor",
            userPort = UserPort,
            udpPort = UDPPort,
            tcsDev = TCSDevice("tcsDev", "localhost", TCSDevicePort),
            scaleDev = ScaleDevice("mockScale", "localhost", ScaleDevicePort),
            )
    except Exception:
        print >>sys.stderr, "Error starting fake TCC"
        traceback.print_exc(file=sys.stderr)

def checkFakesRunning(ignored):
    if fakeScaleController.isReady and fakeTCS.isReady:
        startTCCLCO()

fakeScaleController.addStateCallback(checkFakesRunning)
fakeTCS.addStateCallback(checkFakesRunning)


reactor.run()
