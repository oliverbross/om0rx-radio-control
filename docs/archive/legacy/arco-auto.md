Oliver Bross, 29m ago
we have our project on one page split to a 3 distinctive areas - radio control - first 3 rows, log/qrz/dxcc -3 columns for logging and last area is spots area with filters. I wan you to make one significant change, I want to split those 3 areas to 3 different pages/tabs, so they can be positioned anywhere on the screen, of course, they are still part of a single project, so clicking on the spot in one window still send spot to log and radio etc ... can you do this split from having everything in one window to 3, so radio control, logging and spots? cleanly, we are not modifying any functionality ... maybe if this is difficult, do a landing page with 3 buttons to open spots, radio and logging ... separately ... not sure what is easier... you decide, do a clean job pls

New task / improvement: look at ARCO.md and let's try to implement the rotator control! any questions, just ask.



ok, now we have a rotor implemented, and it's actually turning and working, we need to add AUTO button, next to "GO" button in the rotor area we show in ui. 
When user has the AUTO button active, rotor should turn automatically to the direction of the spot / callsign typed in the log qso area.

How are we going to achieve this? Firstly, we need to add Rotor bands to config, as for example most people might have beam antenna only for 20m and up to 10, 
so we need to add area in config to configure rotor bands, with tickboxes from 160m to 2m. so 160, 80, 60 etc ... 

When ticked, we know which band is the rotor 
used for and then the auto functionaltiy can work, also, when the band is not ticked, we know the rotor does not need to turn or function on that band. 

So let's say we have bands configured, we know rotor is working on those bands, how do we determine which way to turn? We need to add "Gridsquare" locator 
option to rotor bands area, so we know exactly where the user is located for example in JN88TQ. 

We can then calculate, based on the Gridsqure user supplied and it's saved in our config and the lat/lon provided shown in the /data/cty.dat, where to turn the rotor. cty.dat contains all
latitude / longtitude details for all prefixes. Also, if it helps, maybe we can have 2-tier system, when we first get spots/stations Gridsquare from qrz.com - we already doing this, then calculate 
the bearing betwen 2 gridsquares easily. If a gridsquare is not available, we will use lat/lon details from cty.dat to calculate it


So if on auto, it will turn , if not, user has to manually turn it . can you implement this functionality cleanly? don't forget a single thing I mentioned here, any questions, ask

So do this:

1. in the configuration area (ui as well) add bands from 160m to 2m, with tickboxes, so person can choose on which band the rotor works
2. add user's home qridsquare field, like in my case we will use JN88TQ and auto convert it next to it to lat'lon, let user to ammend lat/long if they know the details, so 3 fields will be shown - grid, lat and lon
3. once we know the band is selected by user, we can calculate the bearing between two points, which is the current position of the rotor and the spot location.
4. once we know users lat/lon we can calculate the beaming degress using user's and spots/dxstations lat/lon, which we get from cty.dat

Convert each grid to the center latitude/longitude

Compute the initial great-circle bearing from QTH → DX

Send that 0–360° value to your rotator (usually true bearing; apply magnetic declination only if your system expects it)

Formula (spherical Earth, plenty accurate for rotators)

Given QTH (φ₁, λ₁) and DX (φ₂, λ₂) in radians:

Δλ = λ₂ − λ₁

𝑥
=
sin
⁡
(
Δ
𝜆
)
cos
⁡
(
𝜑
2
)
x=sin(Δλ)cos(φ
2
	​

)

𝑦
=
cos
⁡
(
𝜑
1
)
cos
⁡
(
𝜑
2
)
cos
⁡
(
Δ
𝜆
)
−
sin
⁡
(
𝜑
1
)
sin
⁡
(
𝜑
2
)
y=cos(φ
1
	​

)cos(φ
2
	​

)cos(Δλ)−sin(φ
1
	​

)sin(φ
2
	​

)

bearing = 
m
o
d
(
\atan
2
(
𝑥
,
𝑦
)
×
180
/
𝜋
+
360
,
 
360
)
mod(\atan2(x,y)×180/π+360,360)

Grid → lat/lon (center of the square)

For 2/4/6/8-char grids (AA00aa00 pattern):

Start at lon = −180, lat = −90

Field (A–R): lon += 20·(c₀−‘A’), lat += 10·(c₁−‘A’)

Square (0–9): lon += 2·(c₂), lat += 1·(c₃)

Subsquare (a–x or A–X): lon += (2/24)·(c₄−‘A’), lat += (1/24)·(c₅−‘A’)

Extended (0–9): lon += (2/240)·(c₆), lat += (1/240)·(c₇)

Finally add half the cell size at the given precision so you land at the center.

example of python code:
import math

def grid_to_latlon(grid: str):
    g = grid.strip().upper()
    if len(g) not in (2,4,6,8) or len(g)%2:
        raise ValueError("Grid must be 2, 4, 6, or 8 chars")

    lon, lat = -180.0, -90.0
    lon += (ord(g[0]) - 65) * 20
    lat += (ord(g[1]) - 65) * 10
    if len(g) >= 4:
        lon += int(g[2]) * 2
        lat += int(g[3]) * 1
    if len(g) >= 6:
        lon += (ord(g[4]) - 65) * (2/24)
        lat += (ord(g[5]) - 65) * (1/24)
    if len(g) >= 8:
        lon += (ord(g[6]) - 48) * (2/240)
        lat += (ord(g[7]) - 48) * (1/240)

    # add half cell size for the given precision
    sizes = [(20,10), (2,1), (2/24,1/24), (2/240,1/240)]
    level = len(g)//2 - 1
    cw, ch = sizes[level]
    return (lat + ch/2.0, lon + cw/2.0)

def initial_bearing(lat1, lon1, lat2, lon2):
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1)*math.cos(φ2)*math.cos(Δλ) - math.sin(φ1)*math.sin(φ2)
    θ = math.degrees(math.atan2(x, y))
    return (θ + 360) % 360

def bearing_from_grids(grid_from: str, grid_to: str) -> float:
    lat1, lon1 = grid_to_latlon(grid_from)
    lat2, lon2 = grid_to_latlon(grid_to)
    return initial_bearing(lat1, lon1, lat2, lon2)

# Example:
# JN88TQ (your QTH) -> CN87 (Seattle area)
# print(round(bearing_from_grids("JN88TQ","CN87"), 1))  # ≈ 205.5°


example 1: from jn88 to north japan
From: JN88TQ (≈ 48.17 N, 17.08 E)
To: QN03 (≈ 43.0 N, 141.3 E)

Step-by-step bearing:

Δ
𝜆
=
141.3
−
17.08
=
124.22
°
Δλ=141.3−17.08=124.22°
𝜑
1
=
48.17
°
,
𝜑
2
=
43.0
°
φ
1
	​

=48.17°,φ
2
	​

=43.0°
𝑥
=
sin
⁡
(
124.22
°
)
cos
⁡
(
43.0
°
)
x=sin(124.22°)cos(43.0°)
𝑦
=
cos
⁡
(
48.17
°
)
cos
⁡
(
43.0
°
)
cos
⁡
(
124.22
°
)
−
sin
⁡
(
48.17
°
)
sin
⁡
(
43.0
°
)
y=cos(48.17°)cos(43.0°)cos(124.22°)−sin(48.17°)sin(43.0°)

→ bearing ≈ 54.8°

✅ Result:
JN88TQ → North Japan (QN03, Sapporo): ≈ 55° true bearing



