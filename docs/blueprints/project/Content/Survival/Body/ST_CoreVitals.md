# ST_CoreVitals — snapshot

Package: /Game/Survival/Body/ST_CoreVitals
AssetType: Blueprint Structure
DependsOn: none. Consumers: BPC_SurvivalBody, WBP_VitalsHUD, WBP_SurvivalDebug.
Status: stencil drafted / NEEDS REVIEW, 21.11.2026. Actual UE 5.8.4 pins/MCP/PIE not verified. [Research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).

Create User Defined Struct. All numeric fields Float (double precision). String fields explicitly marked.
| Field | Default | Unit |
|---|---:|---|
| Warmth01 | 1 | game 0..1 |
| Rest01 | 1 | game 0..1 |
| Hydration01 | 1 | game 0..1 |
| Hunger01 | 1 | game 0..1 |
| Condition01 | 1 | game 0..1 |
| FeelsLikeC | -10 | test effective C |
| WarmthDelta | 0 | signed last change |
| RestDelta | 0 | signed last change |
| HydrationDelta | 0 | signed last change |
| HungerDelta | 0 | signed last change |
| ConditionDelta | 0 | signed last change |
| LastStepHours | 0 | game hours |
| LastCause (String) | Initial | diagnostics |
| ExposureSource (String) | Uninitialized | Zone outside / Zone inside / DEBUG override / Invalid zone |
 
BPC_SurvivalBody is only writer of its authoritative instance; getters and dispatchers pass snapshots by value. Persistent subset: five satisfaction/condition fields; diagnostics/input reconstructed later, no SG yet. Save/inspect actual struct fields and Make/Break pins.
