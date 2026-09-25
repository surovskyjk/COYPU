# COYPU

**https://github.com/surovskyjk/COYPU**

A desktop application for railway track geometry analysis and train performance simulation, developed as part of a master's thesis. The tool follows the Czech railway standard CSN 73 6360-1.

Built with Python and PySide6.

---

## Main Features

- Parse and visualize LandXML horizontal alignment files (lines, spirals, curves; cant; vertical profile)
- Parse line speed limits from XML TTP files (Czech national infrastructure registry format)
- Append multiple LandXML or TTP files to build a longer corridor
- Optional alignment optimization: enlarge curve radii and lengthen transition curves inside a bounded lateral slew envelope, preview the new curvature against the imported baseline, and revert at any time
- Design cant (D) and calculate permissible speed profiles for four speed profiles (difference in global max cant deficiency): V100, V130, V150, VK
- Enforce norm limits: cant ramp gradient (n), rate of change of cant deficiency (nI), abrupt change of cant deficiency (deltaI)
- Simulate train kinematics using a forward-backward pass algorithm with traction, resistance, and braking
- Interactive map viewer showing the alignment coloured by selected speed profile (TTP, V100, V130, V150, VK) with a colour-scale legend, a basemap selector, an OpenRailwayMap overlay with adjustable transparency, and markers for every scheduled stop
- Ribbon command bar (Project, Geometry, Simulation, View, Data series, Settings) with generated vector icons, compact labels and full-text tooltips
- Dockable, floatable and tabbed panels: workflow guide, XML source viewers with code folding, parsed data tables, plots and help
- All plots rendered with pyqtgraph, each with its own context menu offering the native export (SVG / PNG / CSV) plus detach to a large window, interaction modes, grid and station marker toggles, and series highlighting
- Chainage crosshair synchronised between the geometry plot, the speed profile, the longitudinal profile and the map
- Light and dark themes following the operating system, with a manual override
- Dock layout, theme and language persisted between sessions
- Multi-language UI: Czech, English, German
- Export geometry report (Text, PDF, Markdown or LaTeX) and kinematics results (CSV)
- Batch processing: merge several LandXML files with rebased chainage, run a matrix of stopping patterns x design approaches x an optional sensitivity sweep as isolated background variants, compare them on a dedicated overlay dashboard, and export every report, protocol and comparison table as one ZIP archive
- Native `.coypu` project files: one compressed archive holding the project metadata, every merged alignment with its raw imported assets, stops and TTP data, vehicle configurations, the cached GPK and cant deficiency results, and the saved viewport state, so a reopened project restores its plots without recalculating
- Extended project metadata dialog: title, author, contract number, date, notes, target norm, optional track / definition section and TUDU codes, and the coordinate system descriptor reused by the LandXML export
- Export the designed alignment back to LandXML 1.2 including the application header, the coordinate system, the horizontal geometry, the newly calculated cant D with its design speeds, and a vertical profile whose curve tangents are guaranteed never to overlap
- Unsaved changes tracker in the window title, a recent projects list, and a background recovery snapshot written every five minutes and offered for restore after a crash

---

## Application Settings

The following parameters can be adjusted in the Settings dialog:

- `vInit` - initial trial speed for the iterative geometry solver [km/h]
- `maxD` - maximum permissible cant [mm]
- `iterationStep` - speed reduction step per solver iteration [km/h]
- `maxIterations` - maximum number of solver iterations
- `designApproach` - norm approach used for limit lookup (standard / alternative)
- EPSG code - coordinate reference system of the input LandXML file
- CARTO API key - set in Map Settings, needed only for the CARTO basemaps, see [Map Basemaps and API Key](#map-basemaps-and-api-key)

Alignment optimization parameters, set in the Alignment Optimization dialog:

- `dMaxM` - lateral slew envelope, the largest permitted displacement from the imported axis [m]
- `lMinM` - minimum element length [m]
- `lkMaxM` - maximum optimized transition curve length [m]
- `isRMaxEnabled` / `rMaxM` - optional ceiling on radius maximization [m], off by default
- `ratioCPercent` - mode 5 only, the share of the slew envelope given to the arc radius [%]
- `modeLcl` / `modeLscsl` - optimization mode per element pattern

---

## Map Basemaps and API Key

The map offers OpenStreetMap, the ČÚZK orthophoto and the two CARTO basemaps (Voyager and Dark). Since 23 September 2026 CARTO stamps every tile requested without an API key with an "API KEY REQUIRED" watermark, so the CARTO basemaps are only offered once a key is set. Without a key the map falls back to OpenStreetMap, which needs no key.

Getting a key:

- ask the author for one via GitHub (https://github.com/surovskyjk), the key is then sent privately, or
- register your own free key at https://carto.com/basemaps/apikey/ (only an e-mail address is needed)

Paste the key into Map Settings. It is kept in the operating system credential vault (Windows Credential Manager) for your user account, attached only to requests for CARTO tiles, and never written to project files, presets or logs. Projects saved by older versions that still carry a key have it removed on load. For development and scripted runs the key can also be supplied through the `COYPU_MAP_API_KEY` environment variable, which is read when the vault holds nothing.

A key must never be committed to this repository or bundled into a build: anything shipped with a desktop application can be extracted from it, and public repositories are scanned for keys. If a key leaks, regenerate it at CARTO and paste the new one into Map Settings.

Tile terms the map follows:

- **CARTO** ([Basemaps Terms](https://carto.com/legal/basemap-terms/)): free up to 5 million tile requests a month for non-commercial use (personal, educational, academic, research) and 1 million for commercial use, counted per account across all its keys. The key holder is responsible for all usage on it. The credit "© OpenStreetMap contributors, © CARTO" stays visible on the map, and no tiles are cached on disk or through a server.
- **OpenStreetMap** ([Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)): the application identifies itself with its own User-Agent, shows "© OpenStreetMap contributors", honours the tile cache headers, and requests only the tiles in view, never in bulk or for offline use.
- **OpenRailwayMap** overlay ([usage policy](https://wiki.openstreetmap.org/wiki/OpenRailwayMap/API)): credited as "Data © OpenStreetMap contributors, Style: CC-BY-SA 2.0 OpenRailwayMap"; commercial use requires your own tile server.

---

## Norm Limit Tables (Configurable, CSV Import/Export)

The geometry solver uses four speed-dependent norm limit tables. Each can be edited in the Settings dialog and imported or exported as CSV.

- `I` - maximum permissible cant deficiency by speed range and design approach [mm]
- `DI` - maximum permissible sudden cant deficiency change (deltaI) [mm]
- `nLin` - cant ramp slope limits (n), governing the rate of D change along a spiral
- `nILin` - cant deficiency change rate coefficient (nI), governing the rate of I change along a spiral

CSV format for geometry limits: one row per speed band, first column is the section identifier (`I`, `DI`, `nLin`, or `nILin`), followed by the numerical values. A header row is expected and skipped on import.

---

## Vehicle Catalog and CSV Format

The `vehicles/` folder in the repository root is a catalog of ready-made vehicle CSV files, scanned automatically on
startup and offered as presets in the Vehicle Settings dialog and the standalone Vehicle Catalog browser. Drop an
extra CSV into `vehicles/` (next to the executable when running a packaged build) to add it to the catalog on the
next launch.

Vehicle parameters can also be imported and exported per vehicle as a single CSV file. The file uses a section
identifier in the first column:

- `Meta` - single line key/value metadata: `vehicleName`, `maxSpeedKmh`, `massTonnes`, `lengthM`, `brakeDecelMs2`,
  `maxTractiveForceKN` (informational only, does not clip the curve). Optional - a file without `Meta` rows still
  imports using the `Param`/`Res` values below.
- `Res` - Davis resistance coefficients: name, A, B, C [N/kN]
- `Trac` - Traction curve segments: name, V_bottom, V_top, b0, b1, b2 (piecewise polynomial F = b0 + b1*v + b2*v^2 [kN], V [km/h])
- `Param` - Train parameters: name, rotational mass factor, total weight [t], train length [m]

Multiple vehicles can be defined per project (1 to 5); each is simulated independently.

---

## Train Stops (CSV Import/Export)

Scheduled stops can be imported and exported via CSV with columns: station [km], dwell time [s], name.

---

## Geometry Calculation

The geometry engine uses an iterative convergence loop that starts from `vInit` and reduces the trial speed by one `iterationStep` per pass until the computed permissible speed matches the trial speed.

The descent moves one grid step at a time on purpose. The permissible speed is *increasing* in the trial speed, because the cant D is designed for that trial speed, so the loop is looking for the largest self-consistent speed and jumping straight to the computed one would skip past it.

`maxIterations` is therefore a floor rather than a cap: the engine raises it to whatever the distance from `vInit` down to the answer actually needs, so the result no longer depends on the budget being generous. The descent is additionally bounded by a hard iteration ceiling and a wall clock budget; if either is reached the profile is marked as not converged (`converged_<profile>` in the LandXML dictionary) and the GUI says so, rather than publishing a trial speed as though it were a design.

Within each iteration:

- Stage 1 - designs cant D for each alignment element based on the equilibrium cant formula, constrained by the cant ramp slope (n limit) through a forward and backward sweep; the less aggressive sweep is applied
- Stage 2 - designs cant deficiency I for each element constrained by nI and deltaI limits; again a forward and backward sweep are performed and the stricter result is used
- Stage 3 - enforces D continuity at zero-length element boundaries (element pair junctions)
- cantDefSpeed - computes an additional speed limit for spirals from the physical I change across the spiral, using both the nI-based formula and the virtual deltaI approach; the more lenient of the two is applied
- Stage 4 - computes the permissible speed for each element pair from the D+I formula; if the computed speed is lower than the trial speed, the trial speed is reduced and the loop repeats

Two calculation modes are available:

- Design mode (`runCalculationLoop`) - calculates optimal D for the given speed, then derives I and the permissible speed; produces one output profile using the default speed profile
- As-built mode (`runCalculationLoopI`) - uses the measured cant from the LandXML file directly; derives I and permissible speed for all four speed profiles (V100, V130, V150, VK)

After convergence, D and I values are rounded and the final speed is verified against the D+I formula.

The cant deficiency keeps its sign. A negative value is cant *excess*, meaning D sits above the equilibrium cant for the permissible speed, which is the opposite of a deficiency: it is reported as negative, it is not credited as speed headroom, and it does not load the cant deficiency limit.

---

## Alignment Optimization (Lateral Slew)

An optional design phase that enlarges curve radii and lengthens transition curves within a bounded
lateral displacement envelope, so an existing corridor can carry a higher speed without being
realigned. It reshapes horizontal geometry only. Cant and speeds are **not** recalculated by it, and
must be re-run afterwards from the Geometry page.

### Workflow position

The application separates three explicit, user driven phases:

1. **Load** the LandXML alignment (and optionally the XML TTP speed limits).
2. **Optimize** the alignment (optional). Previews the new curvature against the imported baseline
   and the resulting lateral slew profile. Any cached cant, speed and kinematics results are cleared,
   because they describe geometry that no longer exists. A `Revert to Baseline` button in the
   optimization dialog, and the `Clear Optimization` ribbon command, restore the imported alignment.
   Every run starts from the imported alignment, rebuilt from the source files stored in the project
   when it is reopened, so running the optimizer again never stacks on a previous result.
3. **Design cant** (D + I) on whichever alignment is currently active, then run the simulation.

Only one alignment is ever *active*. The plots show a single set of cant, cant deficiency and speed
curves belonging to that active alignment. The curvature plot is the exception: it keeps the imported
baseline as a muted dashed curve underneath the vivid active one, and the map does the same with a
dashed grey baseline polyline under the styled active axis.

**As-built mode** (`Calculate I, D stays the same`) is disabled while an optimization is active. The
cant recorded in the LandXML file was installed for the imported geometry; on a displaced axis it no
longer describes anything physical.

### Sign convention

Lateral slew `Δy` is the signed perpendicular distance from the imported axis to the optimized one:

- **Positive `+Δy` (inward)** — displacement **towards the centre of curvature**, away from the
  intersection point (PI) of the bounding tangents. The radius **grows**.
- **Negative `−Δy` (outward)** — displacement **towards the PI apex**, away from the curve centre.
  The radius **shrinks**.

The sign is independent of whether the curve turns left or right: the fixed frame's normals are
multiplied by the turn sign, so the test is always "is the new axis on the centre side". The plot,
the slew report table, the CSV export and the map colour scale all follow this one definition.

### Closed-form geometry

For a clothoid of length `L` at radius `R`, with the deflection angle `Δ` between the bounding
tangents:

| Quantity | Formula |
|---|---|
| Spiral (clothoid) angle | `θs = L / (2R)` |
| Shift of the arc off the tangent | `ΔR = L² / (24R) − L⁴ / (2688R³)` |
| Tangent foot offset | `x_m = L / 2 − L³ / (240R²)` |
| Clothoid parameter | `A = sqrt(R · L)` |
| Circular arc length | `L_C = R · abs(Δ) − ½ (L_e + L_x)` |
| Apex offset against the baseline | `Δy_apex = (R − R₀)(sec(Δ/2) − 1) + (ΔR̄ − ΔR̄₀) · sec(Δ/2)` |

`ΔR̄` is the mean of the entry and exit clothoid shifts. The last identity is inverted by Newton
iteration (`solveRadiusForEnvelope`) to seed the search with the radius whose apex offset exactly
reaches the envelope `d_max`; the seed is then refined by a bracketed bisection against the true
sampled slew, so the analytic approximation never decides feasibility on its own.

Feasibility of a candidate is always measured as the maximum perpendicular distance between the
sampled candidate axis and the baseline polyline, not from the apex identity.

### Optimization modes

| Mode | Name | Radius | Transitions | Available for |
|---|---|---|---|---|
| — | No optimization | unchanged | unchanged | every pattern |
| 1 | Shift arc and extend transitions (C+S) | grows | grow with it | L-S-C-S-L |
| 2 | Extend transitions only (S) | unchanged | grow | L-S-C-S-L |
| 3 | Enlarge radius only (C) | grows | unchanged | L-C-L, L-S-C-S-L |
| 4 | Inverted shift (C+S) | shrinks | grow | L-S-C-S-L |
| 5 | Configured slew allocation ratio (C / S) | grows by its share | grow by their share | L-S-C-S-L |

**Mode 1** drives the radius and both clothoids from a single parameter, holding the spiral angle
`θs = L / (2R)` constant, so `L(R) = L₀ · R / R₀`. That is what "shift the arc **and** extend the
transitions" means: as the radius grows the transition lengthens proportionally, preserving the
cant ramp gradient the imported design used. Solving the radius first and the spirals afterwards
does not work — the radius search alone consumes the whole `d_max` envelope, and every longer
clothoid then increases `ΔR` and breaches it, which is why a sequential formulation collapses onto
mode 3. When the tangent budget or `L_k,max` caps either transition, both freeze at that common
scale and the remaining envelope goes to the radius alone.

**Mode 2** keeps `R₀` and spends the whole envelope on the clothoids, raising the permissible speed
through the cant deficiency change rate rather than through curvature. Both transitions grow off one
parameter, the length of the longer one, with the shorter following at the imported ratio.

**Mode 3** is the only mode offered for L-C-L, and the only one that changes nothing but `R`.

**Mode 4** reduces the radius while lengthening the transitions, both from one parameter
`s`: `R = R₀ − s` and `L = sqrt(24 R (ΔR₀ + 2s))` for the longer transition, the shorter one
following at the imported ratio. It trades curvature for a gentler cant ramp, which helps where the
ramp gradient rather than the radius is what limits the speed.

**Mode 5** lets the designer split the envelope instead of letting one mechanism take all of it.
A ratio `C : S` (default 50 : 50, set in the optimization dialog) partitions `d_max` into an arc
share `d_C = (C/100) · d_max` and a transition share `d_S = (S/100) · d_max`, and the two stages are
solved independently:

1. The radius is maximised against `d_C` alone, with the clothoids held at `L₀`.
2. At that new radius, the longer transition's tangent offset is raised to
   `m_new = ΔR(R_new, L₀) + d_S` and it is lengthened to `L = sqrt(24 · R_new · m_new)`; the shorter
   transition follows at the imported ratio.

The ratio only decides *where the search starts*: the accepted
candidate is still measured against the full `d_max` on the sampled geometry, and when the two
stages combined would overshoot it the transitions are backed off rather than the extension being
abandoned. Setting the ratio to 100 : 0 reproduces mode 3 exactly; 0 : 100 keeps `R₀` and spends
everything on the transitions.

**Symmetry.** Every mode keeps the imported `L_entry : L_exit`: the transitions are lengthened by one
common scale factor, and any cap that binds on one side stops both. A symmetric curve therefore stays
symmetric and an asymmetric one keeps its proportions. An L-C-L group is symmetric by construction,
its enlarged arc is centred on the bisector of the fixed PI.

### Element pattern handling

Groups are maximal runs of non-straight elements between two straights.

- **L-C-L** — a bare circular curve. It has no transitions, so only mode 3 is offered; a stale
  project or batch preset asking for a spiral mode is skipped with `optSkipNoSpirals`.
- **L-S-C-S-L** — clothoid, arc, clothoid. All four modes apply. Both spirals must be genuine
  clothoids (one end at infinite radius, length above 0.5 m) and share the arc's turn direction.
- **Reverse compound (S-curve)** — `S-C-S-S-C-S` with opposite turn directions. **Never optimized.**
  A reverse curve is a different geometry problem: its two halves share an inflection point that is
  not fixed by either bounding straight, so solving them independently moves each half's tangent
  point along the shared tangent on its own and leaves a gap of a metre or more at the inflection.
  The pattern is recognised only so the report can name it, and the group is skipped with
  `optSkipReverseCurve` and left exactly as imported.
- Anything else is reported as `optSkipCompound` or `optSkipNotClothoid` and left untouched.

Only `L-C-L` and `L-S-C-S-L` are ever reshaped. Every other pattern keeps the geometry it was
imported with; a skipped group's radius, centre and transition lengths are preserved exactly,
and only its chainage follows the corridor when an upstream group changes length.

A group also needs a real straight on both sides (`optSkipNoTangent`).

### Boundary constraints

- **`d_max`** — the lateral slew envelope in metres (0.05 to 1.50). No sampled point of the optimized
  axis may lie further than this from the imported one.
- **`L_min`** — the minimum element length in metres. Enforced on the circular arc and, through the
  shared tangent budget, on the straights.
- **`L_k,max`** — an upper bound on an optimized transition length, so a curve cannot be given a
  disproportionately long clothoid just because the envelope still allows one. It clamps the search
  ceiling and every candidate, and never shortens a transition that was already longer on import.
  It caps the pair: once either transition reaches it, neither grows further, so a transition
  already longer than `L_k,max` on import keeps both at their imported lengths.
- **`R_max`** — a ceiling on radius maximization (100 to 99000 m). When it is switched off the
  upper bound of that range still applies as a sanity bound: on a near straight kink `sec(Δ/2)` is
  barely above one, so the apex offset hardly moves with the radius and an unbounded search runs
  out to implausible values. A group stopped by the ceiling is flagged in the summary. It is for the
  modes that grow the radius: 1, 3 and 5. It is enforced as a feasibility gate rather than a
  post-hoc clamp — a candidate above the ceiling is simply infeasible — so the bisection converges
  onto `R_max` itself and the matching inward shift `d ≤ d_max` falls out of the same search. Mode 2
  leaves the radius alone and mode 4 shrinks it, so neither is affected. When the ceiling binds
  before the envelope does, the group still succeeds and its reported slew sits below `d_max`.
- **Shared tangent budget** — a straight between two curves is consumed by both, by a transition
  growing into it and by a tangent point migrating along it as the radius grows (roughly
  `ΔR·tan(Δ/2)` per end). Both are charged and both are gated: every candidate, in every mode, has
  to leave each bounding straight at least `L_min`, or at least what it already had when it was
  shorter than `L_min` to begin with. The remaining length is re-measured from the straight's own
  endpoints after each group, so two neighbouring curves cannot each spend the same metres, and a
  straight can never be consumed past its own start. Whichever straight runs out first limits both
  transitions, so the imported ratio survives a short tangent on one side.

#### Minimum length relaxation

A strict `L_C ≥ L_min` gate rejects exactly the curves that need help most: a short arc that the
optimization would *lengthen* is refused because it is still short afterwards. The gate is therefore
relaxed:

> An arc below `L_min` is accepted provided the optimization does not shorten it further, **and**
> both bounding straights keep at least `L_min` of their own.

A `500 – 15 – 500 m` L-C-L with `L_min = 30 m` becomes `495 – 25 – 495 m`: the arc is still under
`L_min`, but it is 10 m longer than it was and the straights keep 495 m each, so it is a net
geometric improvement and is accepted. If the straights cannot back the relaxation the group is
skipped with `optSkipShortTangent`, and where they can only partly back it the search stops exactly
at the point where a straight would fall to `L_min`. An arc that starts *above* `L_min` still faces
the hard gate and may never be driven below it.

### Chainage

Changing element lengths changes the chainage of everything downstream, so after all groups are
solved the whole corridor is **re-chained from the alignment start** out of the final element
lengths. This guarantees the station array is monotonic and that each element's end coincides with
the next element's start. A curve that expands into its bounding tangents therefore moves its start
chainage *backwards* and its end chainage *forwards* symmetrically, rather than pushing the whole
expansion downstream.

Note that enlarging a radius between fixed tangents makes the corridor slightly **shorter** overall:
the arc grows by `ΔR · Δ` while the two tangents each give up `ΔR · tan(Δ/2)`, and
`tan(Δ/2) > Δ/2`.

The optimizer also emits a monotone piecewise linear map from baseline chainage to active chainage
(`chainageMapBaselineKm` / `chainageMapActiveKm`). Its nodes sit on the part of every straight that
neither neighbouring curve consumed, where both axes run on the same ground, so anything entered
against the imported chainage keeps its physical position. Scheduled stops, the measured cant, the
vertical profile and the TTP speed signs are projected through this map, and the muted imported
curvature curve is drawn through it too, so both curvature curves line up on the same ground instead
of drifting apart by the length every reshaped curve gave up.

### Outputs

- **Lateral slew profile plot** — a third row under the geometry and speed plots, with the `±d_max`
  envelope drawn as threshold lines.
- **Slew report** — per curve group: pattern, mode, `R` before and after, both transition lengths
  before and after, peak local slew and where it occurs, a per-element breakdown of that peak across
  the entry transition, the arc and the exit transition, and the resulting speed change.

  The slew columns are **local peaks, not a parallel offset**. With the intersection points held
  fixed, an enlarged curve is not shifted in parallel: displacement is largest on the apex bisector
  and tapers to zero at the transition tangent points, which is exactly what the three per-element
  columns show. Where the envelope is the binding constraint the peak sits on `d_max` by
  construction; where `R_max`, `L_k,max` or the tangent budget binds first, it sits below it.

  The two speed columns come from running the native D+I design loop twice on the fly, once on the
  imported alignment and once on the active one, and mapping the result by element index. Element
  order and count are preserved by the optimizer, so no chainage window is involved and the columns
  fill in even when the optimization was run before any cant design.
- **Map** — the dashed grey baseline, the styled active axis, and a heat line over every stretch
  whose displacement clears 5 mm. Hovering any segment reports its element number, type, radius
  (`R_orig → R_new` where it changed), length, full stationing range and local slew.
- **Skip reasons** — every group that was not modified reports why, and the reasons are aggregated in
  the dialog shown at the end of a run.

---

## Vehicle Kinematics Simulation

Train motion is simulated by numerical integration of the equation of motion at 1 m intervals along the alignment.

- Forward pass - accelerates the train from initial speed using tractive effort, subtracting vehicle resistance, gradient resistance, and curve resistance; speed is capped at the permissible speed profile at each step
- Backward pass - applies braking from the end of the section or from each speed reduction point, using a constant deceleration value
- Final speed profile - element-wise minimum of the forward and backward passes
- Train length look-ahead - the speed limit applied at each point is the minimum over a sliding window equal to the train length, so the full train must fit within each speed restriction

Track resistance components:

- Gradient resistance - proportional to slope [N/t per per-mille]
- Curve resistance - Rockl formula based on curve radius

Vehicle resistance uses the Davis equation: F_res = A + B*v + C*v^2

Traction is defined as a piecewise polynomial over speed bands: F_trac = b0 + b1*v + b2*v^2

Train stops are enforced by setting the speed limit to zero at the stop station. A configurable dwell time is added to the travel time.

---

## Batch Processing and Variant Comparison

The Batch page runs many track variants unattended and compares them side by side.

- Multi-LandXML merger - select several LandXML files in one picker; they are concatenated end to end with chainage rebased so file N+1 continues where file N ends (or kept as imported for genuinely contiguous surveys), with a warning if a junction gap exceeds 100 m
- Variant matrix - cross a set of station CSV stopping patterns (e.g. Regional vs Express) with a set of design-approach combinations (standard / limit / minmax per I, deltaI, n, nI), optionally stepping one further parameter (D_max, cant gradient, braking deceleration, ...) across a `[min, max, step]` range
- Isolated execution - every variant runs the unmodified `GeometryCalculator` and `VehicleCalculator` engines against its own deep-copied data on a background thread, so the ribbon stays responsive and a failed or cancelled variant never aborts the rest of the batch
- Variant Comparison Dashboard - a third central view overlaying every variant's speed profile v(s) and cant deficiency I(s) on synchronised pyqtgraph plots, plus side-by-side summary and inter-station travel-time tables
- Presets - a batch configuration (files, stopping patterns, approaches, sweep, output formats) can be saved to and reloaded from a JSON preset
- ZIP export - packages every variant's report, calculation protocol, raw CSV data and comparison matrices, plus the overlay plot images, into one structured archive; reports can be written as Text, PDF, Markdown or LaTeX

---

## Project Structure

- `main.py` - application entry point
- `gui.py` - main window, ribbon, docks and data flow
- `gui_overlay.py` - settings and vehicle dialogs, detached plot window
- `geometry_engine.py` - cant design, permissible speed calculation and the alignment optimizer
- `optimization_runner.py` - isolated background execution of the alignment optimization
- `slew_report.py` - lateral slew summary table and its window
- `vehicle_engine.py` - train kinematics simulation
- `readfile.py` - LandXML and XML TTP parsers, coordinate transformations
- `map_viewer.py` - interactive Folium map widget with floating map controls
- `basemap_key.py` - CARTO basemap key storage in the operating system credential vault
- `plot_widgets.py` - shared pyqtgraph base widget, context menus and navigation toolbar
- `graphs_dock.py` - linked track geometry and speed profile plots
- `profile_dock.py` - longitudinal profile plot with gradient annotations
- `kinematics_dock.py` - four linked kinematics plots
- `workflow_dock.py` - seven step workflow guide
- `help_dock.py` - in-application documentation panel rendering this file
- `xml_editor.py` - XML source viewer with folding and syntax highlighting
- `ribbon.py` - ribbon command bar widgets
- `lazy_dock.py` - dock widget with deferred rendering and a title bar menu
- `theme_manager.py` - operating system theme detection, colour tokens and application styling
- `track_stats_dock.py` - track statistics dock with design and achieved speed sections
- `ui_kit.py` - small shared widgets, the KPI cards and the collapsible sections
- `presets_manager.py` - export and import of the interface presets
- `source_stack.py` - provenance of the imported source files
- `icons.py` - programmatically generated vector icons and text badges
- `default_values.py` - built-in default norm limits and vehicle parameters
- `translations/` - external JSON translation files (cz.json, en.json, de.json)
- `translation_manager.py` - discovers and loads translation JSON files at runtime
- `resource_paths.py` - shared helper for locating bundled and writable resources
- `shortcut_manager.py` - loads `config/shortcuts.json`, applies shortcuts, resolves typed commands
- `settings_dialog.py` - dialog for editing command aliases and keyboard shortcuts
- `config/shortcuts.json` - external command name, alias, and keyboard shortcut mappings
- `landxml_merger.py` - chainage-rebasing concatenation of several parsed LandXML alignments
- `project_metadata.py` - project metadata model and the Project Properties dialog
- `project_file.py` - native `.coypu` archive format, recent projects list and recovery snapshot paths
- `landxml_exporter.py` - LandXML 1.2 writer for the horizontal geometry, calculated cant and vertical profile
- `batch_config.py` - batch configuration schema, JSON preset persistence, variant cross-product expansion
- `batch_metrics.py` - headless travel-time, track-length and variant metric helpers shared by the track stats dock
- `batch_runner.py` - isolated per-variant execution and the QThread worker/controller running a batch
- `batch_results.py` - holds the most recently run batch's results, outside the live project data
- `batch_dialog.py` - batch configuration modal (track sources, stopping patterns, approaches, sensitivity, output)
- `batch_progress.py` - progress dialog shown while a batch runs and while the archive is packaged
- `variant_dashboard.py` - overlay plots and comparison tables for the Variant Comparison Dashboard
- `report_formats.py` - renders a report's lines to Text, Markdown, LaTeX, CSV or PDF
- `batch_export.py` - assembles a batch's reports, protocols and comparison data into one ZIP archive
- `tests/` - unit tests for the geometry engine, vehicle catalog, and batch processing modules

---

## Repository

Source code: https://github.com/surovskyjk/COYPU
