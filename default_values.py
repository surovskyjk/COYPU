# Default values for settings

defVal = {
"I":    [
        [0,79,80,100,130],
        [79,230,80,100,150],
        [230,250,70,100,130],
        [250,300,70,80,100],
        [300,360,60,65,90]
        ],
"dI":   [
        [0,100,50,85,100],
        [100,120,40,85,85],
        [120,170,40,50,60],
        [170,230,25,30,40]
        ],
"nLin": [
        [0,80,10,500,6,500,6,400],
        [80,120,10,800,7,560,6,480],
        [120,160,10,1200,8,960,7,840],
        [160,200,10,1600,8,1280,7,1120],
        [200,360,7,2000,6,1200,5,1000]
        ],
"nILin":    [
            [0,160,10,4,4],
            [160,200,10,8,6],
            [200,360,10,9,6]
            ],
"vInit":    [120],
"iterationStep": 5.0,
"maxIterations": 50,
"profileDefault": ["I150"],
"maxD":     [150],
"designApproach": "standard",
"disableGeometryMaxD": False,
"balanceInflectionCants": False,
"alignmentOptimization": {
    "dMaxM": 0.5,
    "lMinM": 25.0,
    "lkMaxM": 250.0,
    "isRMaxEnabled": False,
    "rMaxM": 10000.0,
    "ratioCPercent": 50,
    "modeLcl": "shiftArc",
    "modeLscsl": "shiftAndExtend"
    },
# Matches vehicles/generic_bemu.csv so a fresh install's default already has correct physics
"trainRes": [["Generic BEMU", 1.6616, 0.00415, 0.00017]],
"trainTrac": [["Generic BEMU", 0, 53.724, 112.5, 0, 0],
              ["Generic BEMU", 53.724, 95.72, 264.1023212, -3.758085809, 0.017385477],
              ["Generic BEMU", 95.72, 160, 152.6900328, -1.247380411, 0.003296517]
              ],
"trainBrakeDecel": 0.45,
"trainParam": [["Generic BEMU", 1.08, 113.5, 52.9]],
"maxCantDeficiencyMm": 150.0
        
}