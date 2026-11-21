# TheLull — cross-stencil self-audit before external review

**Status: SELF-REVIEWED / NEEDS CLOUD REVIEW.** 21 November 2026. Scope: 19 active project targets (17 Content assets/level + 2 config files), plus the DEFERRED Key West level. All reviewed as one graph at the parent commit of this document. None exists as a real Unreal asset yet. No compile, PIE, local Editor or MCP capabilities verified.

## Target / dependency / consumer matrix

| Target | Upstream prerequisites | Downstream consumer | Status |
|---|---|---|---|
| Config/DefaultGameplayTags.ini | real UE project | ST_SimStep, Clock, Probe, Level | NEEDS REVIEW |
| /Game/Survival/Time/E_SimPhase | project | BPI, Clock, Body, Probe | NEEDS RE-REVIEW |
| /Game/Survival/Time/E_AdvanceResult | project | Clock, Probe, Level | NEEDS REVIEW |
| /Game/Survival/Time/ST_SimStep | gameplay tags config | BPI, Clock, Body, Probe | NEEDS RE-REVIEW |
| /Game/Survival/Time/BPI_SimStepReceiver | E_SimPhase, ST_SimStep | Clock, Body, Probe | NEEDS RE-REVIEW |
| /Game/Survival/Time/BP_SurvivalWorld | E_AdvanceResult, E_SimPhase, BPI, ST_SimStep, tags | Body, Probe, Driver, DayNight, Level | NEEDS RE-REVIEW |
| /Game/Survival/Time/BP_RealtimeClockDriver | BP_SurvivalWorld + E_AdvanceResult + tags + native Timer / audio time | L_SurvivalCore only; requests Clock time, not a clock | NEEDS REVIEW |
| /Game/Survival/Environment/BP_DayNightLighting | BP_SurvivalWorld + native DirectionalLight/SkyAtmosphere/SkyLight | Level, Debug period label via Level | NEEDS REVIEW |
| /Game/Tests/Survival/BP_F00ClockProbe | Clock, BPI, two enums, ST_SimStep, tags | Level (opt-in only) | NEEDS RE-REVIEW |
| /Game/Survival/Environment/BP_CoreExposureZone | engine BoxCollision, stock Pawn collision | Body, Level | NEEDS REVIEW |
| /Game/Survival/Body/ST_CoreVitals | project | Body, HUD, Debug | NEEDS REVIEW |
| /Game/Survival/Body/BPC_SurvivalBody | ST_CoreVitals, ST_SimStep, BPI, E_SimPhase, Clock, Zone | Level, BPC_CoreActions, widgets via snapshot | NEEDS RE-REVIEW |
| /Game/Survival/Actions/ST_CoreSupplies | project | BPC_CoreActions, WBP_SurvivalDebug | NEEDS REVIEW |
| /Game/Survival/Environment/BP_CoreRestSpot | engine Box Collision and stock Pawn | BPC_CoreActions, Level | NEEDS REVIEW |
| /Game/Survival/Actions/BPC_CoreActions | Stock struct, RestSpot, Zone, Body, Clock, Advance enum, Gameplay Tags | Level and Debug via copies | NEEDS REVIEW |
| /Game/UI/Survival/WBP_VitalsHUD | ST_CoreVitals, native UMG | Level | NEEDS REVIEW |
| /Game/UI/Survival/WBP_SurvivalDebug | ST_CoreVitals + ST_CoreSupplies, native UMG | Level | NEEDS RE-REVIEW |
| /Game/Maps/L_SurvivalCore | stock template, Clock/Probe, Zone/Body, Widgets, RestSpot/Actions, then Driver/Lighting in stages | startup ini, PIE | NEEDS RE-REVIEW |
| Config/DefaultEngine.ini | L_SurvivalCore must exist first | project Maps & Modes startup | NEEDS REVIEW |
| /Game/Maps/L_KeyWestBlockout | future Core integration + geography sources | later, not part of present build | DEFERRED |

External Epic Third Person pawn/character, GameMode, camera, PlayerController, input assets/mapping contexts and template source map **are not to be recreated**. Their real package paths remain unknown until the local project exists. Level Blueprint is part of L_SurvivalCore.umap, not an independent blueprint asset. One new custom asset or edited config = one MD, including E_AdvanceResult and DefaultEngine.ini which were previously missing.

## Cross-file contract checks

1. **F00 request:** BP_SurvivalWorld.AdvanceGameTime takes game-seconds + GameplayTag and returns **E_AdvanceResult**, not Boolean. Level/Probe compare Completed explicitly. Rejected means no time change. PartialFailure means some clock/receiver mutation may already have happened; bFaulted locks further time requests. Never retry, rollback by imagination, or claim save validity.
2. **Receiver:** BPI_SimStepReceiver.GetSimPhase returns E_SimPhase; SimulateStep accepts ST_SimStep and **returns bApplied:Boolean**. That output makes it an interface **function**, not Event. Probe and Body must both implement exact output; Clock handles false. It is not atomic multi-receiver dispatch; stop/fault is only detection.
3. **Restore:** RestoreWorldTime is accepted before bReady only; no post-init restore while body and environment are active. No save/load coordinator exists. Future coordinated load must initialize all authoritative owners together, never only the clock.
4. **Time integration:** F00 3600 versus 4×900 has same four substeps, not proof of arbitrary call partition equivalence. 1000+2600 can shift boundaries. BPC needs an explicit F01 integration policy for real heat/weather, and may first compare constant-zone results for same total duration. No claim of determinism across movement during one step.
5. **Body/environment:** Body alone owns live ST_CoreVitals; source is a zone query based on Pawn overlap each paid step; debug fixture override is marked. Invalid zone returns bApplied=false **before body state mutation**; Clock reports PartialFailure. Fixture writers must refuse updates during clock dispatch and after fault. Five normalized needs/condition fields are not medical body temperatures.
6. **Time-of-day (new):** Hoarbound actual 1800s day + 1800s night is 60 REAL minutes per 24 game hours. BP_RealtimeClockDriver samples non-paused UE elapsed time, requests elapsed×24 game seconds through BP_SurvivalWorld; the old Level 1s→+60 timer is explicitly removed, avoiding two requesters/24min days. BP_DayNightLighting reads absolute Clock on OnTimeAdvanceFinished, uses UE native lights, steps sun every 240 GAME seconds and optionally eases over 2 REAL seconds. SkyLight Real Time Capture OFF for first LOW test; no per-step recapture. Lighting is not its own phase receiver and does not alter climate/body.
6. **UI:** HUD and Debug Widget Blueprints take a ST_CoreVitals **value copy**. They must never write body, clock, or weather, and must not maintain a second authoritative time. LastStepHours/Last*Delta describe the **last sim substep**, not necessarily the entire last Advance request.
7. **Level + config:** L_SurvivalCore is a copy of actual playable Third Person template level. Startup and opt-in probe are mutually exclusive. Level Blueprint test key input depends on actual runtime input routing alongside stock Enhanced Input; no fictitious IA/IMC asset is assumed. Config/DefaultEngine.ini is a **dependent output after the level exists**, not a prerequisite for creating that level. Preserve stock GameMode, camera and input configuration.
8. **Tags and types:** ST_SimStep.Reason is Gameplay Tag selected from DefaultGameplayTags.ini; time fields are UE Float with double-precision subtype, not a separate Double picker type. ST_CoreVitals has exact fields LastCause:String and ExposureSource:String; type annotations are not part of their variable names.

## Found and corrected during this self-review

- **BLOCKER** — initial receiver returned void; no signal when step failed. Added bApplied return, E_AdvanceResult and terminal PartialFailure. Full transactional rollback still **not implemented**.
- **BLOCKER** — clock could restore time after other owners had mutated. Rejected post-initialization restore; future SaveGame coordinator **not implemented**.
- **MAJOR** — one Probe Advance caller still expected a Boolean, but F00 result was changed to an enum. Corrected and checked other callers in Level/Probe.
- **MAJOR** — ST_CoreVitals declared names like "LastCause (String)" under Field heading, inconsistent with Body MakeStruct pins. Replaced with exact field/type/default/unit table.
- **MAJOR** — missing startup map config stencil, and Core map called its future config a prerequisite. Added Config/DefaultEngine.ini, applied direction of dependency.
- **MAJOR** — private body debug update methods only trusted Level to run them while idle; clock now exposes IsTimeDispatching and Body requires busy/fault/ready guards.
- **MAJOR** — fallback outside temperature if Zone invalid would conceal a missing provider; Body now refuses the step. This may leave earlier phase mutations; terminal clock fault is required.
- **DOC CONFLICT** — older exploratory foundation reference listed future core/body fields and outdated Advance signature; marked as historical, not current build contract.

## New review blockers — native UE lighting
- Native light package/actor paths in user's installed Third Person level are not known. Check DirectionalLight Mobility/Atmosphere Sun Light index, SkyAtmosphere existence, Movable Skylight color/intensity Blueprint pins. Sun rotation Pitch/Yaw is a **candidate** until observed PIE screenshots.
- Get Audio Time Seconds is documented as undilated and pause-stopped, but MCP node availability and timer callback scheduling on 5.8.4 are untested. Compare delayed ticks at low FPS and fix if rate drifts. No hidden fallback clock.
- Sun 2s smoothing may cause moving dynamic shadows; benchmark on low graphics. No claim of free GPU cost, no automatic SkyLight recapture, no fake moon/real weather.
- Debug RenderDebug now has PeriodName:String at the *final stage*; Level passes period label. Existing unreviewed RenderDebug pin signature must be reviewed after change.

## Not resolved — review requirements

- UE 5.8.4 BPI output types, enum pin names, actual Blueprint Map key support, ForLoopWithBreak/return propagation, event dispatcher reentrancy, UMG widget graph creation, Level Blueprint and input priority.
- MCP capability inventory: create/enumerate/edit Enum, Struct, Interface function outputs, Blueprint functions, UMG Designer+graph, Level/Level Blueprint; Compile, Save, re-open, inspect actual graph, PIE.
- SimStep partial failure is **not an atomic transaction**. Clock does not fire OnTimeAdvanceFinished; a session stops. Reviewer should assess whether preflight validation must be a separate interface before game actions, without inventing a rollback engine.
- Future scope not claimed: SaveGame coordinator, real weather/shelter/heat, food/water/rest inventory, action prices, bodily recovery, real Key West level. These are NOT missing files of current F00/Core stencils.
- Reviewer should issue per-asset verdict REVIEWED / NEEDS REVISION / LOCAL VERIFICATION REQUIRED. Review the **actual current SHA**, not only BP_SurvivalWorld. Full MD agreement alone is not UE feasibility.

## Epic sources checked

- Blueprint Interface: https://dev.epicgames.com/documentation/unreal-engine/blueprint-interface-in-unreal-engine (page served 5.9; editor 5.8.4 check pending).
- Blueprint Variables / Private: https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-variables-in-unreal-engine (page served 5.9).
- Set Timer by Event (5.8): https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UKismetSystemLibrary/K2_SetTimerDelegate?application_version=5.8.
- Actor input: https://dev.epicgames.com/documentation/unreal-engine/setting-up-input-on-an-actor-in-unreal-engine (may serve 5.9).
- Cross-check the exact 5.8.4 graph with Local Unreal MCP before labeling any asset assembled or PIE tested.
