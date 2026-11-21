# L_SurvivalCore — playable core, no geography
Package: /Game/Maps/L_SurvivalCore
AssetType: Level (umap)
Status: draft / NEEDS REVIEW. [Manifest](../../../../gameplay/SURVIVAL_MANIFEST.md).
 
## A: Third Person + F00
Duplicate default Third Person Blueprint None level under /Game/Maps/L_SurvivalCore. Preserve GameMode, PlayerStart, pawn/camera/input. Add one BP_SurvivalWorld and optional BP_F00ClockProbe. Level BeginPlay count public bRunProbe flags; >1 active abort error, 1 active skip startup (probe owns init), 0 active find exactly one clock, InitializeNewGame true or abort. F00 PIE first; do not reference not-yet-created core assets.
 
## B: Body and HUD
After successful clock init, get Player Pawn 0 valid, check Get Components By Class BPC_SurvivalBody count zero; Add Component by Class on pawn, cast returned component, call InitializeFixture(Clock), require true. If pawn not ready, log actual order, request possession hook fix (no arbitrary Delay). Store Clock/Body refs in Level Blueprint. Create Widget WBP_VitalsHUD with PlayerController 0, validate, Add to Viewport z0. Render initial Body.GetVitals; bind to OnVitalsChanged. C: add WBP_SurvivalDebug z1 similarly. Bind clock completion to debug refresh from latest snapshot (body dispatcher during step and final callback; no UMG Tick). 
## C: Fixture controls
Level vars bCoreReady=false, bAutoAdvance=false, bDebugVisible=true, LastCommand="Initial", AutoTimerHandle; ready only after required assets valid. Level keyboard events 1..8, verify no template binding collision. 1 toggles automatic fixture time: Set Timer by Event looping 1 real s → if ready+auto Clock.AdvanceGameTime(60, Time.Advance.Realtime), on rejection clear timer and log. Off Clear and Invalidate Timer by Handle. Use one handle. Fixture ratio only. 2..7 require ready and !auto; 2 Clock.AdvanceGameTime(900, Time.Advance.Debug), 3/4 Body.SetFixtureExposure(-10/+5), 5 Body.ApplyFixtureReplenish(0,.25,0), 6 (0,0,.25), 7 (.25,0,0). 8 toggles visibility (Collapsed / Not Hit-Testable). Each command logs accepted/rejected and refreshes both views. No direct Set time/body. EndPlay clear timer, remove widgets, unbind own receivers. Debug overrides are not actual resources or heat yet. No fixture commands during F00 probe run.
 
## Acceptance
Default pawn moves/camera works. F00 probe separate. Normal fresh PIE: 4 presses key2=1h, 8 additional=3h; W/C results per body stencil. Warm override then 4 steps: warmth rises, other needs decrease. Mock water changes hydration only, time unchanged. Auto/manual cannot double bill; hide/show debug no state mutation. Reopen PIE no duplicate clock/body/widgets. Full climate, real zone, real finite items/actions before geographic production; no UE result yet.
