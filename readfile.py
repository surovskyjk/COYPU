import xml.etree.ElementTree as ET
import numpy as np
import re
from pyproj import Transformer
from pyclothoids import Clothoid

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
    
    # Element index of the n-th element of one type, taken from the flat geometryType array.
    # stationHorizontal is a [start, end] pair per element, so index 2*k+1 is element k's end.
    def elementIndicesOfType(self, parsedXML, elementType):
        geometryType = parsedXML.get("geometryType")
        if geometryType is None or len(geometryType) == 0:
            return []
        elementTypes = list(np.asarray(geometryType)[::2])
        return [index for index, name in enumerate(elementTypes) if name == elementType]

    # End chainage of the i-th Curve, addressed by element index where the element stream is
    # available and by a positive length chainage match otherwise. None when neither resolves.
    def curveEndStation(self, parsedXML, curveIndex, staStart):
        stationHorizontal = parsedXML.get("stationHorizontal")
        if stationHorizontal is None or len(stationHorizontal) == 0:
            return None

        curveElements = self.elementIndicesOfType(parsedXML, "Curve")
        if curveIndex < len(curveElements):
            endIndex = 2 * curveElements[curveIndex] + 1
            if endIndex < len(stationHorizontal):
                return float(stationHorizontal[endIndex])

        # No element stream to address: take the first element start matching this chainage
        # that actually spans a positive length, which is never the preceding element's end.
        elementStarts = np.asarray(stationHorizontal[::2], dtype=float)
        for elementIndex in np.where(np.isclose(elementStarts, staStart))[0]:
            endIndex = 2 * int(elementIndex) + 1
            if endIndex < len(stationHorizontal) and float(stationHorizontal[endIndex]) > staStart:
                return float(stationHorizontal[endIndex])
        return None

    def alignmentCoordinates(self, parsedXML, epsgInput, epsgOutput):
        
        alignmentCoords = []
        alignmentCoordsOriginal = []
        dense_points = []
        
        transformer = Transformer.from_crs(epsgInput, epsgOutput, always_xy=True)

        # Universal add segment method

        def addSegment(x, y, geom_type, s=None):

            originalCoords = np.column_stack((x, y)).tolist()
            alignmentCoordsOriginal.append((originalCoords, geom_type))

            if epsgInput == "EPSG:5514":
                easting = -np.array(y)
                northing = -np.array(x)
            else:
                easting = np.array(x)
                northing = np.array(y)

            lon, lat = transformer.transform(easting, northing)

            transformedCoords = np.column_stack((lat, lon)).tolist()
            alignmentCoords.append((transformedCoords, geom_type))

            if s is not None:
                for sta, la, lo in zip(s, lat, lon):
                    dense_points.append((sta, la, lo))

        # Line
        if "lineStartX" in parsedXML:
            for i in range(len(parsedXML["lineStartX"])):
                staStart = parsedXML["lineStationStart"][i]
                dx = parsedXML["lineEndX"][i] - parsedXML["lineStartX"][i]
                dy = parsedXML["lineEndY"][i] - parsedXML["lineStartY"][i]
                length = np.sqrt(dx**2 + dy**2) / 1000.0
                staEnd = staStart + length
                addSegment([parsedXML["lineStartX"][i], parsedXML["lineEndX"][i]],
                           [parsedXML["lineStartY"][i], parsedXML["lineEndY"][i]], "Line", [staStart, staEnd])

        # Spiral
        if "spiralStartX" in parsedXML:
            for i in range(len(parsedXML["spiralStartX"])):
                x, y = self.discretizeSpiral(
                    parsedXML["spiralStartX"][i],
                    parsedXML["spiralStartY"][i],
                    parsedXML["spiralPIX"][i],
                    parsedXML["spiralPIY"][i],
                    parsedXML["spiralLength"][i],
                    parsedXML["spiralRadiusStart"][i],
                    parsedXML["spiralRadiusEnd"][i],
                    parsedXML["spiralRot"][i],
                    smoothness = 50,
                    epsgInput = epsgInput
                    )
                
                staStart = parsedXML["spiralStationStart"][i]
                length = parsedXML["spiralLength"][i] / 1000.0
                staEnd = staStart + length
                s = np.linspace(staStart, staEnd, len(x)).tolist()
                addSegment(x, y, "Spiral", s)

        # Curve
        if "curveStartX" in parsedXML:
            for i in range(len(parsedXML["curveStartX"])):
                x, y = self.discretizeCurve(
                    parsedXML["curveStartX"][i],
                    parsedXML["curveStartY"][i],
                    parsedXML["curveEndX"][i],
                    parsedXML["curveEndY"][i],
                    parsedXML["curveCenterX"][i],
                    parsedXML["curveCenterY"][i],
                    parsedXML["curveRot"][i],
                    parsedXML["curveRadius"][i],
                    smoothness = 50,
                    epsgInput = epsgInput
                    )
                
                staStart = parsedXML["curveStationStart"][i]
                # An arc's start chainage also appears as the previous element's end, so
                # searching the flat station array found that earlier index and read the arc's
                # own start back as its end. Every dense point of the arc then carried a single
                # chainage, which snapped the map cursor and station flags to the arc end.
                staEnd = self.curveEndStation(parsedXML, i, staStart)
                if staEnd is None:
                    length = sum(np.sqrt((x[k]-x[k-1])**2 + (y[k]-y[k-1])**2) for k in range(1, len(x))) / 1000.0
                    staEnd = staStart + length
                
                s = np.linspace(staStart, staEnd, len(x)).tolist()
                addSegment(x, y, "Curve", s)

        dense_points.sort(key=lambda p: p[0])
        parsedXML["denseAlignment"] = dense_points

        if "keyX" in parsedXML and len(parsedXML["keyX"]) > 0:
            if epsgInput == "EPSG:5514":
                easting = -np.array(parsedXML["keyY"])
                northing = -np.array(parsedXML["keyX"])
            else:
                easting = np.array(parsedXML["keyX"])
                northing = np.array(parsedXML["keyY"])
            lon, lat = transformer.transform(easting, northing)
            parsedXML["keyLat"] = lat.tolist()
            parsedXML["keyLon"] = lon.tolist()

        parsedXML["alignmentCoordinates"] = alignmentCoords
        parsedXML["alignmentCoordsOriginal"] = alignmentCoordsOriginal

        return parsedXML
    
    def discretizeCurve(self, startX, startY, endX, endY, centerX, centerY, rotDir, radius, smoothness, epsgInput):
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
        
        anglesLinspace = np.linspace(angleStart, angleEnd, smoothness)

        x = centerX + radius * np.cos(anglesLinspace)
        y = centerY + radius * np.sin(anglesLinspace)

        return x, y
    
    def discretizeSpiral(self, startX, startY, piX, piY, length, radiusStart, radiusEnd, rot, smoothness, epsgInput):
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
        spiral = Clothoid.StandardParams(startX, startY, azimuth, kappaStart, dKappa, length)

        spiralLinspace = np.linspace(0, length, smoothness)
        x = [spiral.X(t) for t in spiralLinspace]
        y = [spiral.Y(t) for t in spiralLinspace]

        return x, y