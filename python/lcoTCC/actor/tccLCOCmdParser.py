from __future__ import division, absolute_import
"""!TCC command parser subclassed for LCO TCS
"""
from ..parse.cmdParse import CmdParser
from ..parse import parseDefs
from ..cmd import track, setFocus, setScaleFactor, offset, device, ping

__all__ = ["TCCLCOCmdParser"]

TimeLimit = parseDefs.Qualifier("TimeLimit", numValueRange=[1,1], valType=float,
    help = "Specify timeout time for communication with controllers.",
)

_CoordSysList = (
    parseDefs.Keyword(
        name = "icrs",
        help = "ICRS RA, Dec (deg); date is Julian date (years) of observation and defaults to 2000",
        numValueRange = [0,1],
        castVals=float,
    ),
    # parseDefs.Keyword(
    #     name = "fk5",
    #     help = "FK5 RA, Dec (deg); date is Julian date (years) of equinox and of observation and defaults to 2000",
    #     numValueRange = [0,1],
    #     castVals=float,
    #     defValueList=[2000.0],
    # ),
)

class CoordSet(parseDefs.ValueParam):
    def __init__(self, name, defValueList=(), help=""):
        parseDefs.ValueParam.__init__(self,
            name=name,
            castVals=float,
            numValueRange=(0, None),
            defValueList=defValueList,
            help=help,
        )

class CoordPair(CoordSet):
    def __init__(self, name, extraHelp=""):
        helpList = ["""equatPos, polarPos [, equatVel, polarVel [, tai]]
                Specifies equatorial position and, optionally, velocity and time, where:
                - position is in degrees
                - velocity is in degrees/sec; default is 0
                - tai is TAI (MJD, seconds); default is the current TAI"""]
        if extraHelp:
            helpList.append(extraHelp)
        CoordSet.__init__(self,
            name=name,
            help="\n".join(helpList),
        )

class CoordSys(parseDefs.KeywordParam):
    def __init__(self, name, help, omit=()):
        """Construct a CoordSys keyword parameter

        @param[in] name  name of parameter
        @param[in] help  help string for parameter
        @paramm[in] omit: list of coordinate systems to omit (case blind)
        """
        omitSet = frozenset(str.lower() for str in omit)
        parseDefs.KeywordParam.__init__(self,
            name = name,
            help = help,
            keywordDefList = [kwd for kwd in _CoordSysList if kwd.name.lower() not in omitSet],
        )

######################## Command Definitions ###########################

TCCLCOCmdList = (

    parseDefs.Command(
        name = "offset",
        minParAmt = 1,
        help = "Offsets the telescope in various ways in position and velocity.",
        callFunc = offset,
        paramList = [
            parseDefs.KeywordParam(
                name = 'type',
                keywordDefList = [
                    parseDefs.Keyword(name = "arc", help = "Offset along great circle on sky (coordSys axis 1, 2, e.g. RA, Dec)."),
                    parseDefs.Keyword(name = "rotator", help = "Rotator offset (1 axis)"),
                    parseDefs.Keyword(name = "calibration", help = "Local pointing correction (az, alt, rot)."),
                ],
            ),
            CoordSet(
                name='coordset',
                help="""position and optionally velocity and TAI date (optional);
                    the format depends on the offset (because of varying #s of axes):
                    arc and boresight (aka instPlane) offsets have 2 axes:
                        pos1, pos2 [, vel1, vel2, [, TAI]]]
                    rotator offsets have 1 axis:
                        rotPos [, rotVel [, TAI]]
                    calibration and gCorrection offsets have 3 axes, though rotator is optional:
                        azPos, altPos [, rotPos [, azVel, altVel, [rotVel [, TAI]]]]
                    where:
                    - position is in degrees; default is 0
                    - velocity is in degrees/sec; default is 0
                    - TAI is TAI date (MJD, seconds); default is the current date""",
            ),
        ],
    ),
    parseDefs.Command(
        name = "track",
        help = "Make the telescope to slew to and track an object.",
        callFunc = track,
        paramList = [
            CoordPair(
                name = 'coordPair',
                extraHelp =  "Nonzero velocity specifies dEquatAng/dt, dPolarAng/dt; " \
                    "to track along a great circle specify /ScanVelocity or, " \
                    "equivalently, specify an arc offset with nonzero velocity.",
                ),
            CoordSys(
                name = 'coordSys',
                help = "Coordinate system and date",
                omit = ("Instrument", "GProbe", "GImage", "PtCorr", "Rotator"),
            ),
        ],
        minParAmt = 0,
    ),
    parseDefs.CommandWrapper(
        name = "set",
        subCmdList = [
            parseDefs.SubCommand(
                parseDefs.Keyword(
                                name="focus",
                                castVals = float,
                                numValueRange = [0,1],
                            ),
                callFunc = setFocus,
                qualifierList = [
                    parseDefs.Qualifier(
                        name = "incremental",
                        help = "Add the new focus offset to the existing focus offset, rather than replacing it.",
                    ),
                ],
                help = "Changes the user-settable focus offset for the " \
                    "secondary mirror (microns), if a new value is specified. " \
                    "Then updates collimation (if tracking or slewing).",
            ),
            parseDefs.SubCommand(
                parseDefs.Keyword(
                    name="scaleFactor",
                    castVals = float,
                    numValueRange = [0,1],
                ),
                qualifierList = [
                    parseDefs.Qualifier(
                        "multiplicative",
                        help = "If specified then new scale factor = old scale factor * value.",
                    )
                ],
                callFunc = setScaleFactor,
                help = "Set the desired scale factor.",
            ),
        ],
    ),
    parseDefs.Command(
        name = "ping",
        callFunc = ping,
        help = "test if actor is alive",
    ),
    parseDefs.Command(
        name = "device",
        minParAmt = 1,
        help = "Command the tcs and/or scale controllers",
        callFunc = device,
        paramList = [
            parseDefs.KeywordParam(
                name = 'command',
                keywordDefList = (
                    parseDefs.Keyword(name = "initialize", help = "Reconnect (if disconnected) and initialize the controller. " + \
                        "Initializing an controller halts it and puts it into a state in which it can be moved, if possible."),
                    parseDefs.Keyword(name = "status", help = "Get controller status"),
                    parseDefs.Keyword(name = "connect", help = "Connect to the controller"),
                    parseDefs.Keyword(name = "disconnect", help = "Disconnect from the controller"),
                ),
                help = "What to do with the controller."
            ),
            parseDefs.KeywordParam(
                name = 'device',
                keywordDefList = [parseDefs.Keyword(name = item) for item in [
                    "tcs", "scale"]] + [parseDefs.Keyword(name = "all", passMeByDefault=True)],
                numParamRange = [0, None],
                help = "Which controller? If omitted then both tcs and scale.",
            ),
        ],
        qualifierList = [TimeLimit],
    )

)

class TCCLCOCmdParser(CmdParser):
    """!TCC command parser for LCO TCS
    """
    def __init__(self):
        """!Construct a TCCLCOCmdParser

        ONLY SUPPORTED COMMANDS ARE:
        set focus=focusVal
        set scaleFactor=scaleVale
        track ra, dec fk5=equinox
        offset arc ra, dec

        """

        CmdParser.__init__(self, TCCLCOCmdList)
