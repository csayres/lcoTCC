from __future__ import division, absolute_import
"""The TCC (telescope control code) interface shim for the Las Campanas Observatory du Pont telescope
"""
import sys
import traceback

from RO.StringUtil import strFromException
from RO.Comm.TwistedTimer import Timer

import numpy

from twistedActor import CommandError, BaseActor, DeviceCollection, expandUserCmd

from .tccLCOCmdParser import TCCLCOCmdParser
from ..version import __version__

from ..cmd.collimate import CollimationModel

# tcsHost = "localhost"
# tcsPort = 0
# scaleHost = "localhost"
# scalePort = 1

__all__ = ["TCCLCOActor"]

"""
From Paul's email regarding scaling solution:

focal plane focal plane      focal      ratio           Scale
location        location        length                          Change
BFDr        BFDp                                                1 parts in
(inches)        (mm)        (mm)
10           993            18868.78
10.04        994                 18870.37       1.0000843    8.43e-5
9.96                 992            18867.18        0.9999152       -8.48e-5

So lets say that a scale change +8.45e05 as reported by the guider requires a plate motion of up by 1mm (towards the primary)
                 and  a scale change -8.45e05 as reported by the guider requires a plate motion of down by 1mm (away from the primary)
"""

class TCCLCOActor(BaseActor):
    """!TCC actor for the LCO telescope
    """
    # SCALE_PER_MM = 8.45e-05 * -1# Scaling ring convention (higher abs values )
    SCALE_PER_MM = 8.45e-05 / 5. # more MM per scale
    SCALE_RATIO = 1/7. #Sec dist = SCALE_RATIO * scaling ring dist
    MAX_SF = 1.0008 # max scale factor from tcc25m/inst/default.dat
    MIN_SF = 1./MAX_SF  # min scale factor
    def __init__(self,
        userPort,
        tcsDev,
        scaleDev,
        m2Dev,
        name = "tcc",
    ):
        """Construct a TCCActor

        @param[in] userPort  port on which to listen for users
        @param[in] tcsDev a TCSDevice instance
        @param[in] scaleDev  a ScaleDevice instance
        @param[in] m2Dev a M2Device instance
        @param[in] name  actor name; used for logging
        """
        self.tcsDev = tcsDev
        self.tcsDev.writeToUsers = self.writeToUsers
        self.scaleDev = scaleDev
        self.scaleDev.writeToUsers = self.writeToUsers
        self.secDev = m2Dev
        self.secDev.writeToUsers = self.writeToUsers
        # auto connection looks for self.dev
        self.dev = DeviceCollection([self.tcsDev, self.scaleDev, self.secDev])
        # connect devices
        self.tcsDev.connect()
        self.scaleDev.connect()
        self.secDev.connect()
        self.cmdParser = TCCLCOCmdParser()
        self.collimationModel = CollimationModel()
        self.collimateTimer = Timer(0, self.updateCollimation)
        BaseActor.__init__(self, userPort=userPort, maxUsers=1, name=name, version=__version__)
        # Actor.__init__(self, userPort=userPort, maxUsers=1, name=name, devs=(tcsDev, scaleDev), version=__version__)

    @property
    def currentScaleFactor(self):
        return self.mm2scale(self.scaleDev.status.position)

    def scale2mm(self, scaleValue):
        # scale=1 device is at zero point
        return (scaleValue - 1.0) / self.SCALE_PER_MM + self.scaleDev.status.scaleZero

    def mm2scale(self, mm):
        return (mm - self.scaleDev.status.scaleZero) * self.SCALE_PER_MM + 1.0

    def scaleMult2mm(self, multiplier):
        return self.scale2mm(self.currentScaleFactor*multiplier)

    def scaleMult2mmStable(self, multiplier):
        # this may be more numerically stable,
        # according to unittests self.scaleMult2mm
        # works just fine, and it is simpler
        m = multiplier
        z = self.scaleDev.status.scaleZero
        p = self.scaleDev.status.position
        alpha = self.SCALE_PER_MM
        return m*(p-z)+(1.0/alpha)*(m-1.0)+z

    def parseAndDispatchCmd(self, cmd):
        """Dispatch the user command

        @param[in] cmd  user command (a twistedActor.UserCmd)
        """
        if not cmd.cmdBody:
            # echo to show alive
            self.writeToOneUser(":", "", cmd=cmd)
            return
        try:
            cmd.parsedCmd = self.cmdParser.parseLine(cmd.cmdBody)
        except Exception as e:
            cmd.setState(cmd.Failed, "Could not parse %r: %s" % (cmd.cmdBody, strFromException(e)))
            return

        #cmd.parsedCmd.printData()
        if cmd.parsedCmd.callFunc:
            cmd.setState(cmd.Running)
            try:
                cmd.parsedCmd.callFunc(self, cmd)
            except CommandError as e:
                cmd.setState("failed", textMsg=strFromException(e))
                return
            except Exception as e:
                sys.stderr.write("command %r failed\n" % (cmd.cmdStr,))
                sys.stderr.write("function %s raised %s\n" % (cmd.parsedCmd.callFunc, strFromException(e)))
                traceback.print_exc(file=sys.stderr)
                textMsg = strFromException(e)
                hubMsg = "Exception=%s" % (e.__class__.__name__,)
                cmd.setState("failed", textMsg=textMsg, hubMsg=hubMsg)
        else:
            raise RuntimeError("Command %r not yet implemented" % (cmd.parsedCmd.cmdVerb,))

    def updateCollimation(self, cmd=None, force=False, target=False, doFocus=False, setFocus=False):
        """Update collimation based on info in obj, inst, weath blocks, for all mirrors present

        @param[in] cmd  command (twistedActor.BaseCmd) associated with this request;
            state will be updated upon completion; None if no command is associated

        LCO HACK!!! clean this stuff up!!!!
        """
        cmd = expandUserCmd(cmd)
        if not self.collimationModel.doCollimate and not force and not setFocus:
            cmd.setState(cmd.Failed, "collimation is disabled")
            return
        self.collimateTimer.cancel() # incase one is pending
        # query for current telescope coords
        statusCmd = self.tcsDev.getStatus()
        # when status returns determine current coords

        # HACK!!!!
        statusCmd.doFocus = doFocus
        def moveMirrorCallback(statusCmd):
            doFocus = statusCmd.doFocus
            if statusCmd.didFail:
                cmd.setState(cmd.Failed, "status command failed")
            if statusCmd.isDone:
                # ha = self.tcsDev.status.statusFieldDict["ha"].value
                # dec = self.tcsDev.status.statusFieldDict["dec"].value
                if target:
                    # get target coords
                    # st and ra in degrees
                    st = self.tcsDev.status.statusFieldDict["st"].value
                    ra = self.tcsDev.status.statusFieldDict["inpra"].value
                    ha = st - ra
                    dec = self.tcsDev.status.statusFieldDict["inpdc"].value
                    self.writeToUsers("i", "collimate for target ha=%.2f, dec=%.2f"%(ha, dec))
                else:
                    # get current coords
                    ha, dec = self.tcsDev.status.statusFieldDict["pos"].value
                    self.writeToUsers("i", "collimate for current ha=%.2f, dec=%.2f"%(ha, dec))
                # self.writeToUsers("i", "pos collimate for ha=%.2f, dec=%.2f"%(pos[0], pos[1]))
                temp = None
                if doFocus:
                    if None in [self.collimationModel.baseFocus, self.collimationModel.baseTrussTemp]:
                        cmd.setState(cmd.Failed, "Must specify focus baseline first: collimate setFocus")
                        return
                    temp = self.tcsDev.status.trussTemp
                newOrient = self.collimationModel.getOrientation(ha, dec, temp=temp)
                orient = self.secDev.status.orientation[:]
                # check if mirror move is wanted based on tolerances
                dFocus = None if newOrient[0] is None else newOrient[0]-orient[0]
                dtiltX = newOrient[1]-orient[1]
                dtiltY = newOrient[2]-orient[2]
                dtransX = newOrient[3]-orient[3]
                dtransY = newOrient[4]-orient[4]
                doFlex = numpy.max(numpy.abs([dtiltX, dtiltY])) > self.collimationModel.minTilt or numpy.max(numpy.abs([dtransX, dtransY])) > self.collimationModel.minTrans
                if doFocus:
                    # check focus bounds
                    doFocus = numpy.abs(dFocus) > self.collimationModel.minFocus
                    if doFocus:
                        # do new focus value
                        self.writeToUsers("i", "collimation focus update: %.1f  (delta focus: %.2f)"%(newOrient[0], dFocus))
                        orient[0] = newOrient[0]
                    else:
                        self.writeToUsers("i", "collimation deltaFocus too small : %.1f"%dFocus)
                if not doFlex:
                    self.writeToUsers("i", "collimation flex update too small: dTiltX=%.2f, dTiltY=%.2f, dTransX=%.2f, dTransY=%.2f"%(dtiltX, dtiltY, dtransX, dtransY))
                else:
                    # update flex values
                    orient[1:] = newOrient[1:]
                if doFlex or doFocus:
                    self.writeToUsers("i", "collimation update: Focus=%.2f, TiltX=%.2f, TiltY=%.2f, TransX=%.2f, TransY=%.2f"%tuple(orient), cmd=cmd)
                    self.secDev.move(orient, userCmd=cmd)
                else:
                    # collimation not wanted
                    self.writeToUsers("i", "collimation update too small")
                    cmd.setState(cmd.Done)

        def setFocusCallback(statusCmd):
            if statusCmd.didFail:
                cmd.setState(cmd.Failed, "status command failed")
                return
            if statusCmd.isDone:
                baseTemp = self.tcsDev.status.trussTemp
                baseFocus = self.secDev.status.secFocus
                self.collimationModel.setFocus(baseFocus, baseTemp)
                cmd.setState(cmd.Done)

        if setFocus:
            statusCmd.addCallback(setFocusCallback)
        else:
            statusCmd.addCallback(moveMirrorCallback)

        # remove timer for now
        # if self.collimationModel.doCollimate:
        #     self.collimateTimer.start(self.collimationModel.collimateInterval, self.updateCollimation)
        # else:
        #     self.collimateTimer.cancel()