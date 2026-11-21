# BP_DayNightLighting — Hoarbound lighting rhythm in UE-native scene

Package: /Game/Survival/Environment/BP_DayNightLighting
AssetType: Blueprint Class
ParentClass: Actor
DependsOn: BP_SurvivalWorld and **native** UE DirectionalLight / DirectionalLightComponent, SkyAtmosphere, SkyLight / SkyLightComponent, Timer Manager. Do not duplicate stock level actors as authored MD assets.
PlacedIn: /Game/Maps/L_SurvivalCore (one actor).
Status: NEEDS REVIEW / UNBUILT / PIE NOT RUN, 21.11.2026.

## Exact source inheritance and purposeful UE differences

Hoarbound main `scripts/systems/world/DayNightManager.gd` + `DayNightSettings.gd`, instantiated in `scenes/game/systems/world/WorldEnvironmentSystem.tscn`:
- Sunrise **06:00**, sunset **18:00**.
- Sky/ambient start brightening **02:00**, reach full by **10:00**, evening dimming **18:00→22:00**.
- Warm dawn tint **05:00→07:00**, warm dusk tint **17:00→19:00**.
- Directional-light rotation every **4 game minutes**, blend across **2 real seconds**, snap on jump.
- Sun colors and night sky/fog are stylized; values such as Godot `light_energy=1.5` CANNOT be copied as UE lux.
- Day/night schedule is **art direction**, not claimed precise Key West solar ephemerides. No seasonal sunrise until climate/setting system.

UE implementation: reuse/place a **single native movable Directional Light** (Atmosphere Sun Light=true, index 0), native **Sky Atmosphere**, one native **movable Sky Light**. No new sky shader, no unverified day-night plugin, no C++/GAS. Sky Light Real Time Capture **OFF as LOW performance baseline**; avoid per-step `RecaptureSky` (Epic warns it can cost >=120ms). No second moon directional shadow actor yet: moon contribution approximated by dark cool SkyLight tint at night. Moon pass later only after GPU evidence. SkyAtmosphere should follow UE light rotation automatically. Existing third-person renderer and camera untouched.

## Ownership and construction in Level
Level must call `InitializeLighting(Clock)` **after clock initialization**; BP never writes clock, implements no simulation participant interface and has no own gameplay timer. Link existing native `SunLightActor:DirectionalLight Object Reference` and `SkyLightActor:SkyLight Object Reference` via Instance Editable fields; inspect names in *actual* Third Person UE map, do not invent package paths. Verify the Directional Light and Sky Light are Movable; avoid two Atmosphere Sun Lights of index 0. Add a native Sky Atmosphere actor if absent and record in Level .umap stanza; do not create a new MD for an unchanged built-in class.

## Variables / Types
| Name | UE type | Default | Owner/setting |
|---|---|---|---|
| Clock | BP_SurvivalWorld Object Reference | None | private; assigned from init |
| SunLightActor | DirectionalLight Object Reference | None | Instance Editable; selected Level actor |
| SkyLightActor | SkyLight Object Reference | None | Instance Editable |
| SunComponent | DirectionalLightComponent Object Reference | None | private cached component |
| SkyComponent | SkyLightComponent Object Reference | None | private cached component |
| bInitialized | Boolean | false | private |
| LastSunStepIndex | Integer (int32) | -1 | private, absolute index (not hour/day) |
| BlendTimerHandle | Timer Handle | invalid | private presentation timer |
| bBlending | Boolean | false | private |
| BlendStartRotation, BlendTargetRotation | Rotator | zero | private |
| BlendElapsedRealSeconds, BlendLastSampleRealSeconds | Float (double precision) | 0 | private presentation only |
| SunStepSeconds | Float (double precision) | 240.0 | 4 game minutes, class constant |
| BlendDurationRealSeconds | Float (double precision) | 2.0 | Hoarbound baseline, editable visual setting |
| BlendSampleRealSeconds | Float (double precision) | 0.2 | 5Hz only while blending |
| bSmoothSun | Boolean | true | editable; LOW perf comparison false |
| SunAzimuthOffsetDeg | Float (double precision) | 0.0 | editable provisional orientation |
| NoonSunIntensity | Float (double precision) | 0.0 | private cached native midday intensity; not hardcoded UE lux |
| NoonSkyIntensity | Float (double precision) | 0.0 | private cached native SkyLight intensity |
| NightSkyScale | Float (double precision) | 0.08 | synthetic visual fixture, 0..1 |
| SunDawnTint | Linear Color | (1,0.60,0.40,1) | private color default |
| SunNoonTint | Linear Color | (1,0.97,0.92,1) | private color default |
| SunDuskTint | Linear Color | (1,0.50,0.30,1) | private color default |
| NightSkyTint | Linear Color | (0.28,0.38,0.62,1) | private color default |
| DaySkyTint | Linear Color | (1,1,1,1) | private color default |

Read original native light Intensity **before first mutation** and treat as midday reference. Validate positive finite values. If native Blueprint getter not available via MCP, Local must first inspect Details and feed explicit validated values; do not guess a physical light-unit magnitude from Godot.

## Public functions
```text
InitializeLighting(InClock:BP_SurvivalWorld Object Reference) -> bOK:Boolean
RefreshForClockTime(bForceSnap:Boolean) -> bOK:Boolean
GetVisualHour() -> Hour:Float(double precision) [pure; valid when Clock ready]
GetVisualPeriod(WorldTimeSeconds:Float(double precision)) -> Label:String [pure]
OnVisualPeriodChanged(Label:String, DayNumber:Integer) [Event Dispatcher]
```

### Pure calculation helpers (no second time)
```text
HourOfDay(T) = FMod(T,86400.0)/3600.0
DayNumber(T) = Floor(T/86400.0)+1
SunStepIndex(T) = Floor(T/240.0 + 0.00000001)
StepSampleHour = FMod(SunStepIndex*240.0,86400.0)/3600.0

// Hoarbound ambient timing, normalized 0..1
RawFill(H):
  if 2<=H<10: (H-2)/8
  else if 10<=H<18: 1
  else if 18<=H<22: 1-(H-18)/4
  else: 0
Fill01 = Smooth01(Clamp01(RawFill))
Smooth01(X) = X*X*(3-2*X)

// UE candidate sun-ray direction, verified in 5.8.4 editor NOT assumed from Godot:
SunAltitudeDeg = 60.0 * Sin((StepSampleHour-6.0)*PI/12.0)
SunAzimuthDeg = (StepSampleHour/24.0)*360.0 - 90.0 + SunAzimuthOffsetDeg
SunRot = MakeRotator(Pitch=-SunAltitudeDeg,Yaw=SunAzimuthDeg,Roll=0)
// 06:00 solar altitude=0, noon +60, 18:00 0, midnight negative.
// This is a stylized candidate path, NOT accurate winter Key West sun track.

SunAboveHorizon = Max(0,Sin((StepSampleHour-6)*PI/12))
SunIntensityFactor = Fill01 * SunAboveHorizon
SkyIntensityFactor = NightSkyScale+(1-NightSkyScale)*Fill01
SunColor(H):
  [5..7) Lerp(SunDawnTint,SunNoonTint,Smooth01((H-5)/2))
  [7..17) SunNoonTint
  [17..19) Lerp(SunNoonTint,SunDuskTint,Smooth01((H-17)/2))
  else SunNoonTint // intensity is 0 in dark hours
SkyColor = Lerp(NightSkyTint,DaySkyTint,Fill01)
VisualPeriod(H):
  [2..6) Dawn; [6..10) Morning; [10..17) Day;
  [17..18) Evening; [18..22) Dusk; otherwise Night.
```

### Blueprint execution contracts
```text
BeginPlay:
  do nothing; Tick disabled; await explicit Level initialize.

InitializeLighting(InClock):
  reject if bInitialized / invalid InClock / !InClock.IsClockReady()
       / invalid SunLightActor or SkyLightActor
  Cache typed native components via GetLightComponent / Cast where supported;
       validate Sun=DirectionalLightComponent and Sky=SkyLightComponent.
  Read & verify native intensities (<=0 / missing accessor -> blocked).
  Set Clock=InClock, bInitialized=true
  Bind once to Clock.OnTimeAdvanceFinished -> OnClockAdvanceFinished
  RefreshForClockTime(true)  // snap first 08:00 presentation
  return true

OnClockAdvanceFinished(NewTimeSeconds, Reason:GameplayTag):
  // Clock's dispatch guard remains set; only read and mutate rendering!
  if bInitialized && Clock.IsClockReady() && !Clock.IsSimulationFaulted():
     ComputeApply(NewTimeSeconds, bForceSnap=false)
  // NO AdvanceGameTime, RegisterParticipant, RestoreWorldTime.

RefreshForClockTime(bForceSnap):
  if !bInitialized / !Clock.IsClockReady / Clock.IsSimulationFaulted: return false
  ComputeApply(Clock.GetWorldTimeSeconds(), bForceSnap); return true

ComputeApply(T,bForceSnap) [private impure]:
  compute StepIndex=Floor(T/240), DayNumber and VisualPeriod from T
  if StepIndex==LastSunStepIndex && !bForceSnap: return
  compute rotation from StepSampleHour
  cache previous index; compute Abs(StepIndex-LastSunStepIndex)
  SunComponent.SetIntensity(NoonSunIntensity * SunIntensityFactor)
  SunComponent.SetLightColor(SunColor, bSRGB=false if pin exists)
  SkyComponent.SetIntensity(NoonSkyIntensity * SkyIntensityFactor)
  SkyComponent.SetLightColor(SkyColor)
  // NO RecaptureSky, SetMobility, sky material writes or per-frame UMG update
  if bForceSnap || LastSunStepIndex<0 || IndexDelta>1 || !bSmoothSun:
       StopBlend(); SunLightActor.SetActorRotation(SunRot)
  else BeginBlend(SunRot)
  LastSunStepIndex=StepIndex
  if period actually changed: Broadcast OnVisualPeriodChanged(Period,DayNumber)

BeginBlend(Target):
  StopBlend()
  BlendStartRotation=SunLightActor.GetActorRotation
  BlendTargetRotation=Target
  BlendElapsedRealSeconds=0
  BlendLastSampleRealSeconds=Get Audio Time Seconds
  bBlending=true
  Set Timer by Event (AdvanceBlend; 0.2s looping) -> BlendTimerHandle

AdvanceBlend:
  if !bInitialized || !IsValid(SunLightActor): StopBlend(); return
  Now=Get Audio Time Seconds
  Dt=Max(0,Now-BlendLastSampleRealSeconds)
  BlendLastSampleRealSeconds=Now
  BlendElapsedRealSeconds+=Dt
  Alpha=Smooth01(Clamp01(BlendElapsedRealSeconds/2))
  SunLightActor.SetActorRotation(RLerp(BlendStartRotation,BlendTargetRotation,Alpha,ShortestPath=true))
  if Alpha>=1:
      SunLightActor.SetActorRotation(BlendTargetRotation)
      StopBlend()

StopBlend:
  Clear and Invalidate Timer by Handle(BlendTimerHandle); bBlending=false

EndPlay:
  StopBlend(); unbind own Clock.OnTimeAdvanceFinished listener.
```

### Visual + performance safeguards
- Lighting refresh only when 240 GAME seconds have crossed, **not on every 0.25s realtime clock request**. With 24 game s per real s, new SunStepIndex every **10 real seconds**. During normal transitions, 2s smooth uses only ten 0.2s visual rotation writes. LOW quality may disable smoothing if GPU cost/unstable shadow boundaries demonstrated; do not automatically change engine scalability.
- No SkyLight Real Time Capture in initial low-GPU setup. [Epic 5.8 Skylight docs](https://dev.epicgames.com/documentation/unreal-engine/sky-lights-in-unreal-engine) warn `RecaptureSky` may stall >=120ms; do not invoke on each 4 game min sample.
- Snapshot at 06:00/12:00/18:00/00:00 and compare native exposure. If auto-exposure makes midnight bright, inspect PostProcessVolume settings locally and write an explicit change before applying; do not invent auto-exposure pins.
- Sun rotation axes must be checked in editor: Unreal native light ray orientation differs from Godot. If Pitch sign or north alignment wrong, correct actual UE target with screenshots. No new UE astronomy plugin needed.
- Native sky is not an implementation of Hoarbound's custom clouds, fog/snow scattering or moon arc. Initial darkness + sky color is the scope; weather coupling remains a separate stencil.

## PIE acceptance (none run)
1. Initial BP_SurvivalWorld at 08:00 -> morning lighting, day number 1; manual jump to noon -> midday; 18:00 warm dusk and darkening sky; +6h -> next day 00:00 dark; midnight wrap day number correct.
2. Hoarbound-like dawn 05–07, evening 17–19, smooth ambient 02–10 & 18–22; not a hard switch.
3. 60 GAME seconds when no step crossed -> no unnecessary light writes. Crossing 240 GAME seconds -> one sun target update. Normal 10 real s interval has one 4min step. Paid +900s Rest or debug large jump -> snap immediately, never replay visuals for all intermediary minutes.
4. Pause game, disable BP_RealtimeClockDriver: clock and lighting frozen except already-in-progress **presentation-only** 2s blend. Clock failure: do not infer successful lights; session fault diagnostic.
5. Compare shadow shimmer and `stat unit` / `stat gpu` screenshots with bSmoothSun true/false. Record LOW performance; no promise Intel HD620 fps until tested.
6. Ensure no actor duplicates and no sky RecaptureSky per tick. UE editor/MCP actual component setter pin names and actor references: LOCAL VERIFICATION REQUIRED.

## Epic UE5.8 references
- [Native sky and atmospheric light](https://dev.epicgames.com/documentation/unreal-engine/environmental-light-with-fog-clouds-sky-and-atmosphere-in-unreal-engine)
- [DirectionalLightComponent Sun Light](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UDirectionalLightComponent?application_version=5.8)
- [Sky Light behavior / recapture performance](https://dev.epicgames.com/documentation/unreal-engine/sky-lights-in-unreal-engine)
- [LightComponent Set Intensity](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Rendering/Components/Light/SetIntensity)
- [SkyLightComponent Set Intensity](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Rendering/Components/SkyLight/SetIntensity)
- [SkyLightComponent Set Light Color](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Rendering/Components/SkyLight/SetLightColor)
