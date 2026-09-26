import xml.etree.ElementTree as ET
import numpy as np
import re
from pyproj import Transformer
from pyclothoids import Clothoid

# Longest step [m] between two samples of a curved element. A fixed 50 samples left a 650 m arc
# with a sample only every 13 m, and the map interpolates positions linearly between samples.
DENSE_SAMPLE_SPACING_M = 2.0


# Samples needed so no step along an element of this length exceeds the dense spacing
def sampleCountForLength(lengthM, minSamples):
    if not np.isfinite(lengthM) or lengthM <= 0:
        return minSamples
    return max(minSamples, int(np.ceil(lengthM / DENSE_SAMPLE_SPACING_M)) + 1)


# An element whose own chainage misses its station span by no more than this is fitted onto the
# span. A larger miss is a span an overlap merge cut short, and the geometry past it is clipped.
SPAN_SNAP_TOLERANCE_M = 0.05


# Latitude and longitude of original file coordinates. S-JTSK files list X (south) then Y (west),
# while EPSG:5514 expects easting then northing, both negated.
def transformToLatLon(x, y, epsgInput, transformer=None):
    if transformer is None:
        transformer = Transformer.from_crs(epsgInput, "EPSG:4326", always_xy=True)
    if epsgInput == "EPSG:5514":
        easting = -np.asarray(y, dtype=float)
        northing = -np.asarray(x, dtype=float)
    else:
        easting = np.asarray(x, dtype=float)
        northing = np.asarray(y, dtype=float)
    lon, lat = transformer.transform(easting, northing)
    return np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)

# Open file dialog

class ReadFile:
    def Read(self, filepath):
        try:
                        
            if filepath:
                try:
                    with open(filepath, "r", encoding='utf-8-sig') as file:
                        return file.read()
                    
                except UnicodeDecodeError:
                    with open(filepath, "r", encoding='cp1250') as file:
                        return file.read()
                    
                except Exception as e:
                    return f"Error reading file: {e}"
                            
        except:
            return "Error while opening file"
        

    def XMLType(self, xml_data):
        try:
            root = ET.fromstring(xml_data)
            
            if "LandXML" in root.tag:
                return 1
            elif "ArrayOfTab6b" in root.tag:
                return 2
            else:
                return 0
        except:
            return 0

    def GetAlignments(self, xml_data):
        try:
            root = ET.fromstring(xml_data)
            alignments = []
            count = 1
            for alig in root.iter():
                if alig.tag.endswith('Alignment'):
                    name = alig.get('name')
                    if not name:
                        name = alig.get('desc', f'Alignment {count}')
                    alignments.append(name)
                    count += 1
            return alignments
        except:
            return []

    def ParseLandXML(self, xml_data, epsgInput, alignmentIndex=0) -> dict:

        # Check if xml_data is provided
        if not xml_data:
            return {"error": "No data could be parsed / Keine Daten konnten geparst werden / Žádná data nelze zpracovat."}

        # Use the provided XML data string instead of opening a file            
        root = ET.fromstring(xml_data)

        alignments = []
        for alig in root.iter():
            if alig.tag.endswith('Alignment'):
                alignments.append(alig)

        if not alignments:
            return {"error": "No alignment found / Keine Achse gefunden / Nebyla nalezena žádná osa."}

        target_alignment = alignments[alignmentIndex] if alignmentIndex < len(alignments) else alignments[0]

        # Alignment length
        length = []
        length.append(target_alignment.get('length', "0"))
        length.append(target_alignment.get('staStart', "0"))
        length = np.array(length, dtype=float)

        # Extract cant stations and values in a single pass.
        # If no CantStation elements exist (e.g. straight track, test file) default to D=0.
        stationCant = []
        cant = []
        for km in target_alignment.iter():
            if km.tag.endswith('CantStation'):
                stationCant.append(km.get('station', '0'))
                cant.append(km.get('appliedCant', '0'))

        if cant:
            stationCant.append(length[0] + length[1])
            cant.append(cant[-1])
        else:
            # No cant data found — synthesise D=0 spanning the whole alignment
            stationCant = [length[1], length[0] + length[1]]
            cant = [0.0, 0.0]

        # Vertical alignment data
        stationVertical = []
        elevation = []

        for vl in target_alignment.iter():
            if vl.tag.endswith('PVI') or vl.tag.endswith('CircCurve'):

                verticalData = vl.text

                if verticalData:
                    parts = verticalData.strip().split()

                    if len(parts) >= 2:
                        try:
                            stationVertical.append((parts[0]))
                            elevation.append((parts[1]))
                        
                        # Error handling, if conversion to float fails or entry is invalid, skip the entry
                        except ValueError:
                            continue

        # Calculate vertical and horizontal difference and slope in per mille.
        # Guard: at least two points are required; fall back to level track otherwise.
        if len(stationVertical) >= 2:
            deltaZ = np.diff(np.array(elevation, dtype=float))
            deltaX = np.diff(np.array(stationVertical, dtype=float))
            slope = (deltaZ / deltaX) * 1000
        else:
            slope = np.array([0.0])
            if not stationVertical:
                stationVertical = [str(length[1]), str(length[0] + length[1])]
                elevation = ['0', '0']

        # Extract start and end of elements coordinates
        lineStartX = []
        lineStartY = []
        lineEndX = []
        lineEndY = []

        for lineCoordinates in target_alignment.iter():
            if lineCoordinates.tag.endswith('Line'):
                for coordinate in lineCoordinates:
                    if coordinate.tag.endswith('Start'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            lineStartX.append(coordinatesTemp[0])
                            lineStartY.append(coordinatesTemp[1])
                    elif coordinate.tag.endswith('End'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            lineEndX.append(coordinatesTemp[0])
                            lineEndY.append(coordinatesTemp[1])

        spiralStartX = []
        spiralStartY = []
        spiralEndX = []
        spiralEndY = []
        spiralPIX = []
        spiralPIY = []

        for spiralCoordinates in target_alignment.iter():
            if spiralCoordinates.tag.endswith('Spiral'):
                for coordinate in spiralCoordinates:
                    if coordinate.tag.endswith('Start'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            spiralStartX.append(coordinatesTemp[0])
                            spiralStartY.append(coordinatesTemp[1])    
                    elif coordinate.tag.endswith('End'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            spiralEndX.append(coordinatesTemp[0])
                            spiralEndY.append(coordinatesTemp[1])
                    elif coordinate.tag.endswith('PI'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            spiralPIX.append(coordinatesTemp[0])
                            spiralPIY.append(coordinatesTemp[1])

        curveStartX = []
        curveStartY = []
        curveEndX = []
        curveEndY = []
        curveCenterX = []
        curveCenterY = []

        for curveCoordinates in target_alignment.iter():
            base_cTag = curveCoordinates.tag.split('}')[-1] if '}' in curveCoordinates.tag else curveCoordinates.tag
            if base_cTag == 'Curve':
                for coordinate in curveCoordinates:
                    if coordinate.tag.endswith('Start'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            curveStartX.append(coordinatesTemp[0])
                            curveStartY.append(coordinatesTemp[1])
                    elif coordinate.tag.endswith('End'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            curveEndX.append(coordinatesTemp[0])
                            curveEndY.append(coordinatesTemp[1])
                    elif coordinate.tag.endswith('Center'):
                        coordinatesTemp = coordinate.text.strip().split()
                        if len(coordinatesTemp) >= 2:
                            curveCenterX.append(coordinatesTemp[0])
                            curveCenterY.append(coordinatesTemp[1])

        # Extract station, where horizontal alignment is being changed.
        # Elements without a staStart attribute (e.g. simple test files) receive an
        # inferred station from the running position; their length is estimated from
        # geometry if the next element also lacks staStart.

        def _infer_elem_length(el):
            """Estimate element length [m] from 'length' attribute or Start→End chord."""
            try:
                return float(el.get('length'))
            except (TypeError, ValueError):
                pass
            sx = sy = ex = ey = None
            for child in el:
                text = (child.text or '').strip().split()
                if child.tag.endswith('Start') and len(text) >= 2:
                    try: sx, sy = float(text[0]), float(text[1])
                    except ValueError: pass
                elif child.tag.endswith('End') and len(text) >= 2:
                    try: ex, ey = float(text[0]), float(text[1])
                    except ValueError: pass
            if None not in (sx, sy, ex, ey):
                return np.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
            return 0.0

        stationHorizontal = []
        elements = []
        elem_sta_starts = []   # inferred staStart [m], parallel to elements
        running_sta = length[1]

        for el in target_alignment.iter():
            base_tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if base_tag in ('Line', 'Spiral', 'Curve'):
                sta_str = el.get('staStart')
                try:
                    sta = float(sta_str) if sta_str is not None else running_sta
                except ValueError:
                    sta = running_sta
                elements.append(el)
                elem_sta_starts.append(sta)
                running_sta = sta

        # Map element object identity → inferred staStart [m] for use in attribute loops
        elem_sta_map = {id(el): sta for el, sta in zip(elements, elem_sta_starts)}

        for i, km in enumerate(elements):
            staStart = elem_sta_starts[i]
            if i + 1 < len(elements):
                staEnd = elem_sta_starts[i + 1]
                if staEnd <= staStart:
                    # Next element shares the same station — estimate from geometry
                    staEnd = staStart + _infer_elem_length(km)
            else:
                staEnd = length[0] + length[1]
            stationHorizontal.append(staStart)
            stationHorizontal.append(staEnd)

        keyStations = []
        keyTypes = []
        keyX = []
        keyY = []

        for i, el in enumerate(elements):
            sta = elem_sta_starts[i] / 1000.0
            ctype = "Změna"
            if i == 0:
                ctype = "ZÚ"
            else:
                prev_tag = elements[i-1].tag
                curr_tag = el.tag
                if curr_tag.endswith('Spiral'): ctype = "ZP" if prev_tag.endswith('Line') else "KP"
                elif curr_tag.endswith('Curve'): ctype = "ZO"
                elif curr_tag.endswith('Line'): ctype = "KO" if prev_tag.endswith('Curve') else "KP"
            
            for child in el:
                if child.tag.endswith('Start'):
                    coords = child.text.strip().split()
                    if len(coords) >= 2:
                        keyStations.append(sta); keyTypes.append(ctype)
                        keyX.append(float(coords[0])); keyY.append(float(coords[1]))
                    break

        if elements:
            end_sta = (length[0]+length[1])/1000.0
            for child in elements[-1]:
                if child.tag.endswith('End'):
                    coords = child.text.strip().split()
                    if len(coords) >= 2:
                        keyStations.append(end_sta); keyTypes.append("KÚ")
                        keyX.append(float(coords[0])); keyY.append(float(coords[1]))
                    break

        # Extract radius values
        radius = []
        curvature = []
        curvatureSign = []
        geometryType = []
        
        for r in elements:
            sign = 1.0
            if r.tag.endswith('Curve') or r.tag.endswith('Spiral'):
                if r.get('rot') == "ccw":
                    sign = -1.0

            if r.tag.endswith('Line'):
                radius.append('INF')    # Infinite radius for straight lines
                radius.append('INF')    # Once again for station end
                geometryType.append('Line')
                geometryType.append('Line')
                curvature.append(0)
                curvature.append(0)
                curvatureSign.append(sign)
                curvatureSign.append(sign)

            elif r.tag.endswith('Spiral'):
                radius.append(r.get('radiusStart'))
                radius.append(r.get('radiusEnd'))
                geometryType.append('Spiral')
                geometryType.append('Spiral')
                try:
                    curvature.append(1/float(r.get('radiusStart')))
                except:
                    curvature.append(0)
                try:
                    curvature.append(1/float(r.get('radiusEnd')))
                except:
                    curvature.append(0)
                curvatureSign.append(sign)
                curvatureSign.append(sign)

            elif r.tag.endswith('Curve'):
                radius.append(r.get('radius'))
                radius.append(r.get('radius'))
                geometryType.append('Curve')
                geometryType.append('Curve')
                try:
                    curvature.append(1/float(r.get('radius')))
                except:
                    curvature.append(0)
                try:
                    curvature.append(1/float(r.get('radius')))
                except:
                    curvature.append(0)
                curvatureSign.append(sign)
                curvatureSign.append(sign)

        # Parse line station (use inferred station from elem_sta_map)
        lineStationStart = []
        for km in target_alignment.iter():
            if km.tag.endswith('Line') and id(km) in elem_sta_map:
                lineStationStart.append(elem_sta_map[id(km)])

        # Parse spiral attributes
        spiralStationStart = []
        spiralLength = []
        spiralRadiusStart = []
        spiralRadiusEnd = []
        spiralRot = []
        spiralType = []
        spiralConst = []

        for spiral in target_alignment.iter():
            if spiral.tag.endswith('Spiral') and id(spiral) in elem_sta_map:

                spiralStationStart.append(elem_sta_map[id(spiral)])
                
                spiralLength.append(spiral.get('length'))
                
                spiralRadiusStart.append(spiral.get('radiusStart'))

                spiralRadiusEnd.append(spiral.get('radiusEnd'))

                spiralRot.append(spiral.get('rot'))

                spiralType.append(spiral.get('spiType'))

                spiralConst.append(spiral.get('consant'))

        # Parse curve attributes
        curveStationStart = []
        curveRot = []
        curveType = []
        curveRadius = []

        for curve in target_alignment.iter():
            if curve.tag.endswith('Curve') and id(curve) in elem_sta_map:

                curveStationStart.append(elem_sta_map[id(curve)])

                curveRot.append(curve.get('rot'))

                curveType.append(curve.get('crvType'))

                curveRadius.append(curve.get('radius'))
        
        # Convert to numpy arrays (float only)
        stationCant = np.array(stationCant, dtype=float)/1000  # Convert from m to km
        cant = np.array(cant, dtype=float)

        # np.interp reads its samples in order, so a cant table listed out of order would be
        # interpolated through whatever sequence the file happened to use. A stable sort keeps
        # two samples that share a chainage in their listed order.
        if len(stationCant) > 1:
            order = np.argsort(stationCant, kind="stable")
            stationCant, cant = stationCant[order], cant[order]
            # Only an exact repeat is redundant, and the parser creates one itself whenever the
            # last CantStation already sits at the alignment end. Two samples sharing a chainage
            # but carrying different cant are a genuine step, at a turnout or a merge seam, and
            # np.interp renders that step correctly, so they have to survive.
            isRedundant = np.zeros(len(stationCant), dtype=bool)
            isRedundant[1:] = (stationCant[1:] == stationCant[:-1]) & (cant[1:] == cant[:-1])
            stationCant, cant = stationCant[~isRedundant], cant[~isRedundant]
        stationHorizontal = np.array(stationHorizontal, dtype=float)/1000  # Convert from m to km
        geometryType = np.array(geometryType)
        radius = np.array(radius, dtype=float)
        curvatureSign = np.array(curvatureSign, dtype=float)
        curvature = np.array(curvature, dtype=float) * curvatureSign

        # Aplikace znaménka na výchozí hodnoty převýšení podle směru oblouku
        if len(stationHorizontal) > 0 and len(curvatureSign) > 0:
            starts = stationHorizontal[::2]
            signs = curvatureSign[::2]
            indices = np.searchsorted(starts, stationCant, side='right') - 1
            indices = np.clip(indices, 0, len(signs) - 1)
            cant_signs = np.where(signs[indices] < 0, -1.0, 1.0)
            cant = np.abs(cant) * cant_signs

        stationVertical = np.array(stationVertical, dtype=float)/1000  # Convert from m to km
        elevation = np.array(elevation, dtype=float)
        lineStartX = np.array(lineStartX, dtype=float)
        lineStartY = np.array(lineStartY, dtype=float)
        lineEndX = np.array(lineEndX, dtype=float)
        lineEndY = np.array(lineEndY, dtype=float)
        spiralStartX = np.array(spiralStartX, dtype=float)
        spiralStartY = np.array(spiralStartY, dtype=float)
        spiralEndX = np.array(spiralEndX, dtype=float)
        spiralEndY = np.array(spiralEndY, dtype=float)
        spiralPIX = np.array(spiralPIX, dtype=float)
        spiralPIY = np.array(spiralPIY, dtype=float)
        curveStartX = np.array(curveStartX, dtype=float)
        curveStartY = np.array(curveStartY, dtype=float)
        curveEndX = np.array(curveEndX, dtype=float)
        curveEndY = np.array(curveEndY, dtype=float)
        curveCenterX = np.array(curveCenterX, dtype=float)
        curveCenterY = np.array(curveCenterY, dtype=float)
        lineStationStart = np.array(lineStationStart, dtype=float)/1000  # Convert from m to km
        spiralStationStart = np.array(spiralStationStart, dtype=float)/1000  # Convert from m to km
        spiralLength = np.array(spiralLength, dtype=float)
        spiralRadiusStart = np.array(spiralRadiusStart, dtype=float)
        spiralRadiusEnd = np.array(spiralRadiusEnd, dtype=float)
        spiralConst = np.array(spiralConst, dtype=float)
        spiralRot = np.array(spiralRot)
        spiralType = np.array(spiralType)
        curveStationStart = np.array(curveStationStart, dtype=float)/1000  # Convert from m to km
        curveRadius = np.array(curveRadius, dtype=float)
        curveRot = np.array(curveRot)
        curveType = np.array(curveType)
        slope = np.array(slope, dtype=float)


        # Combine extracted data into a structured dictionary
        parsedXML = {
            "stationCant": stationCant,
            "cant": cant,
            "stationHorizontal": stationHorizontal,
            "geometryType": geometryType,
            "radius": radius,
            "curvature": curvature,
            "curvatureSign": curvatureSign,
            "stationVertical": stationVertical,
            "elevation": elevation,
            "lineStartX": lineStartX,
            "lineStartY": lineStartY,
            "lineEndX": lineEndX,
            "lineEndY": lineEndY,
            "spiralStartX": spiralStartX,
            "spiralStartY": spiralStartY,
            "spiralEndX": spiralEndX,
            "spiralEndY": spiralEndY,
            "spiralPIX": spiralPIX,
            "spiralPIY": spiralPIY,
            "curveStartX": curveStartX,
            "curveStartY": curveStartY,
            "curveEndX": curveEndX,
            "curveEndY": curveEndY,
            "curveCenterX": curveCenterX,
            "curveCenterY": curveCenterY,
            "lineStationStart": lineStationStart,
            "spiralStationStart": spiralStationStart,
            "spiralLength": spiralLength,
            "spiralRadiusStart": spiralRadiusStart,
            "spiralRadiusEnd": spiralRadiusEnd,
            "spiralRot": spiralRot,
            "spiralType": spiralType,
            "spiralConst": spiralConst,
            "curveStationStart": curveStationStart,
            "curveRot": curveRot,
            "curveType": curveType,
            "curveRadius": curveRadius,
            "slope": slope,
            "keyStations": np.array(keyStations),
            "keyTypes": np.array(keyTypes),
            "keyX": np.array(keyX),
            "keyY": np.array(keyY)
        }

        # Add transformed coordinates and more points for transition curves
        self.alignmentCoordinates(parsedXML, epsgInput, "EPSG:4326")

        return parsedXML
    
    def ParseXMLTTP(self, xml_data) -> dict:
        
        # Check if xml_data is provided
        if not xml_data:
            return {"error": "No data could be parsed / Keine Daten konnten geparst werden / Žádná data nelze zpracovat."}

        # Use the provided XML data string instead of opening a file            
        root = ET.fromstring(xml_data)

        # Extract stations of speed limit signals
        stations = []

        for umisteni in root.iter('umisteni'):
            stations.append(umisteni.text)

        # Extract speed limits of speed limit signals
        speedLimits = []

        for rychlostnikN in root.iter('rychlostnikN'):
            speedLimits.append(rychlostnikN.text)

        # Combine stations and speed limits into a structured array
        
        # Clean non-numeric characters and convert to float
        for i in reversed(range(len(speedLimits))):
            
            try:
                station = stations[i].replace(',', '.')
                stations[i] = float(re.sub(r'[^\d.]', '', station))
                speedLimits[i] = float(re.sub(r'[^\d.]', '', speedLimits[i])) 
            except:
                stations.pop(i)
                speedLimits.pop(i)

        # Convert to numpy arrays

        stationSpeedLimits = np.array(stations, dtype=float)
        speedLimits = np.array(speedLimits, dtype=float)
        
        # Combine extracted data into a structured dictionary

        parsedTTP = {
            "stationSpeedLimits": stationSpeedLimits,
            "speedLimits": speedLimits
        }
                
        return parsedTTP
    
    # Own geometry of one element as original x, y samples and their chainage in km. The chainage
    # runs from the element's own station start over its own length, never over a neighbour's.
    def sampleElement(self, parsedXML, elementType, typeIndex, epsgInput, fallbackStartKm=None):
        typeStations = parsedXML.get(f"{elementType.lower()}StationStart")
        if typeStations is not None and typeIndex < len(typeStations):
            staStart = float(typeStations[typeIndex])
        else:
            staStart = fallbackStartKm

        if elementType == "Line":
            x = [parsedXML["lineStartX"][typeIndex], parsedXML["lineEndX"][typeIndex]]
            y = [parsedXML["lineStartY"][typeIndex], parsedXML["lineEndY"][typeIndex]]
            lengthM = float(np.hypot(x[1] - x[0], y[1] - y[0]))
        elif elementType == "Spiral":
            x, y = self.discretizeSpiral(
                parsedXML["spiralStartX"][typeIndex],
                parsedXML["spiralStartY"][typeIndex],
                parsedXML["spiralPIX"][typeIndex],
                parsedXML["spiralPIY"][typeIndex],
                parsedXML["spiralLength"][typeIndex],
                parsedXML["spiralRadiusStart"][typeIndex],
                parsedXML["spiralRadiusEnd"][typeIndex],
                parsedXML["spiralRot"][typeIndex],
                smoothness = 50,
                epsgInput = epsgInput
                )
            lengthM = float(parsedXML["spiralLength"][typeIndex])
        else:
            curveArgs = (parsedXML["curveStartX"][typeIndex], parsedXML["curveStartY"][typeIndex],
                         parsedXML["curveEndX"][typeIndex], parsedXML["curveEndY"][typeIndex],
                         parsedXML["curveCenterX"][typeIndex], parsedXML["curveCenterY"][typeIndex],
                         parsedXML["curveRot"][typeIndex])
            radius = parsedXML["curveRadius"][typeIndex]
            x, y = self.discretizeCurve(*curveArgs, radius, smoothness = 50, epsgInput = epsgInput)
            angleStart, angleEnd = self.curveAngles(*curveArgs, epsgInput)
            lengthM = float(abs(radius * (angleEnd - angleStart)))

        s = np.linspace(staStart, staStart + lengthM / 1000.0, len(x))
        return np.asarray(x, dtype=float), np.asarray(y, dtype=float), s

    # Samples of one element fitted to its station span. A start or end within the snap tolerance
    # is moved onto the span, which keeps rounding in the file from opening chainage gaps. A span
    # a merge cropped is shorter than the geometry, and the samples outside it are cut away, the
    # cut point interpolated between its neighbours so the element still reaches the seam.
    def clipToSpan(self, x, y, s, spanStartKm, spanEndKm):
        if not (np.isfinite(spanStartKm) and np.isfinite(spanEndKm)) or spanEndKm <= spanStartKm or len(s) < 2:
            return x, y, s

        snapKm = SPAN_SNAP_TOLERANCE_M / 1000.0
        ownStart, ownEnd = float(s[0]), float(s[-1])
        newStart = spanStartKm if abs(ownStart - spanStartKm) <= snapKm else ownStart
        newEnd = spanEndKm if abs(ownEnd - spanEndKm) <= snapKm else ownEnd
        if ownEnd > ownStart:
            s = newStart + (s - ownStart) * (newEnd - newStart) / (ownEnd - ownStart)

        lowerKm = max(spanStartKm, float(s[0]))
        upperKm = min(spanEndKm, float(s[-1]))
        if upperKm <= lowerKm:
            # Nothing of the geometry lies on the span, drawing it whole beats dropping it
            return x, y, s

        clippedS = np.concatenate(([lowerKm], s[(s > lowerKm) & (s < upperKm)], [upperKm]))
        return np.interp(clippedS, s, x), np.interp(clippedS, s, y), clippedS

    # Every element in stream order as (elementType, typeIndex, spanStartKm, spanEndKm), or None
    # when the stream does not address the per type arrays one to one
    def elementStream(self, parsedXML):
        geometryType = parsedXML.get("geometryType")
        stationHorizontal = parsedXML.get("stationHorizontal")
        if geometryType is None or stationHorizontal is None:
            return None
        geometryType = np.asarray(geometryType)
        stationHorizontal = np.asarray(stationHorizontal, dtype=float)
        if len(geometryType) == 0 or len(geometryType) != len(stationHorizontal) or len(geometryType) % 2:
            return None

        typeCounts = {"Line": 0, "Spiral": 0, "Curve": 0}
        stream = []
        for elementIndex, elementType in enumerate(geometryType[::2]):
            elementType = str(elementType)
            if elementType not in typeCounts:
                return None
            stream.append((elementType, typeCounts[elementType],
                           float(stationHorizontal[2 * elementIndex]),
                           float(stationHorizontal[2 * elementIndex + 1])))
            typeCounts[elementType] += 1

        for elementType, count in typeCounts.items():
            if count != len(parsedXML.get(f"{elementType.lower()}StartX", [])):
                return None
        return stream

    def alignmentCoordinates(self, parsedXML, epsgInput, epsgOutput):

        alignmentCoords = []
        alignmentCoordsOriginal = []
        dense_points = []

        transformer = Transformer.from_crs(epsgInput, epsgOutput, always_xy=True)

        # Universal add segment method

        def addSegment(x, y, geom_type, s):

            originalCoords = np.column_stack((x, y)).tolist()
            alignmentCoordsOriginal.append((originalCoords, geom_type))

            lat, lon = transformToLatLon(x, y, epsgInput, transformer)

            transformedCoords = np.column_stack((lat, lon)).tolist()
            alignmentCoords.append((transformedCoords, geom_type))

            for sta, la, lo in zip(s, lat, lon):
                dense_points.append((float(sta), float(la), float(lo)))

        # One polyline per element in stream order, because a merge crops these lists with the same
        # per element keep decision as the element stream. Emitting them grouped by type made that
        # crop drop the wrong polylines, so the map drew removed elements and lost kept ones.
        stream = self.elementStream(parsedXML)
        if stream is not None:
            for elementType, typeIndex, spanStartKm, spanEndKm in stream:
                x, y, s = self.sampleElement(parsedXML, elementType, typeIndex, epsgInput, spanStartKm)
                x, y, s = self.clipToSpan(x, y, s, spanStartKm, spanEndKm)
                addSegment(x, y, elementType, s)
        else:
            # Without a usable element stream there is no span to fit to, the types go in turn
            for elementType in ("Line", "Spiral", "Curve"):
                for typeIndex in range(len(parsedXML.get(f"{elementType.lower()}StartX", []))):
                    x, y, s = self.sampleElement(parsedXML, elementType, typeIndex, epsgInput)
                    addSegment(x, y, elementType, s)

        dense_points.sort(key=lambda p: p[0])
        parsedXML["denseAlignment"] = dense_points

        if "keyX" in parsedXML and len(parsedXML["keyX"]) > 0:
            lat, lon = transformToLatLon(parsedXML["keyX"], parsedXML["keyY"], epsgInput, transformer)
            parsedXML["keyLat"] = lat.tolist()
            parsedXML["keyLon"] = lon.tolist()

        parsedXML["alignmentCoordinates"] = alignmentCoords
        parsedXML["alignmentCoordsOriginal"] = alignmentCoordsOriginal

        return parsedXML

    # Start and end angle of an arc about its centre, the end unwrapped in the direction of travel
    def curveAngles(self, startX, startY, endX, endY, centerX, centerY, rotDir, epsgInput):
        angleStart = np.arctan2(startY-centerY, startX-centerX)
        angleEnd = np.arctan2(endY-centerY, endX-centerX)

        if epsgInput == "EPSG:5514":
            if rotDir == "cw":
                if angleEnd < angleStart:
                    angleEnd += 2*np.pi
            else:
                if angleEnd > angleStart:
                    angleEnd -= 2*np.pi
        else:
            if rotDir == "cw":
                if angleEnd > angleStart:
                    angleEnd -= 2*np.pi
            else:
                if angleEnd < angleStart:
                    angleEnd += 2*np.pi

        return angleStart, angleEnd

    def discretizeCurve(self, startX, startY, endX, endY, centerX, centerY, rotDir, radius, smoothness, epsgInput):
        angleStart, angleEnd = self.curveAngles(startX, startY, endX, endY, centerX, centerY, rotDir, epsgInput)

        # smoothness is the minimum sample count, a long arc gets enough to honour the dense spacing
        sampleCount = sampleCountForLength(abs(radius * (angleEnd - angleStart)), smoothness)
        anglesLinspace = np.linspace(angleStart, angleEnd, sampleCount)

        x = centerX + radius * np.cos(anglesLinspace)
        y = centerY + radius * np.sin(anglesLinspace)

        return x, y

    # The clothoid a Spiral element describes, leaving its Start point towards its PI
    def spiralClothoid(self, startX, startY, piX, piY, length, radiusStart, radiusEnd, rot, epsgInput):
        # Calculate azimuth for clothoids library
        azimuth = np.arctan2(piY-startY, piX-startX)

        # Calculate curvature
        kappaStart = 1/radiusStart if (radiusStart != 0 and radiusStart != float('inf')) else 0.0
        kappaEnd = 1/radiusEnd if (radiusEnd != 0 and radiusEnd != float('inf')) else 0.0

        # Clockwise / Counterclockwise
        if epsgInput == "EPSG:5514":
            if rot == "cw":
                kappaStart, kappaEnd = abs(kappaStart), abs(kappaEnd)
            else:
                kappaStart, kappaEnd = -abs(kappaStart), -abs(kappaEnd)
        else:
            if rot == "cw":
                kappaStart, kappaEnd = -abs(kappaStart), -abs(kappaEnd)
            else:
                kappaStart, kappaEnd = abs(kappaStart), abs(kappaEnd)

        dKappa = (kappaEnd - kappaStart) / length
        return Clothoid.StandardParams(startX, startY, azimuth, kappaStart, dKappa, length)

    def discretizeSpiral(self, startX, startY, piX, piY, length, radiusStart, radiusEnd, rot, smoothness, epsgInput):
        spiral = self.spiralClothoid(startX, startY, piX, piY, length, radiusStart, radiusEnd, rot, epsgInput)

        # smoothness is the minimum sample count, as for arcs
        spiralLinspace = np.linspace(0, length, sampleCountForLength(length, smoothness))
        x = [spiral.X(t) for t in spiralLinspace]
        y = [spiral.Y(t) for t in spiralLinspace]

        return x, y