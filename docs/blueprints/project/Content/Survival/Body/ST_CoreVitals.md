# ST_CoreVitals — snapshot

Package: /Game/Survival/Body/ST_CoreVitals
AssetType: Blueprint Structure
DependsOn: none. Consumers: BPC_SurvivalBody, WBP_VitalsHUD, WBP_SurvivalDebug.
Status: stencil drafted / NEEDS REVIEW, 21.11.2026. Actual UE 5.8.4 pins/MCP/PIE not verified. [Research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).

Create User Defined Struct. Exact field names and types (type is NOT part of field name):
| Field | UE type | Default | Unit |
|---|---|---:|---|
| Warmth01 | Float (double precision) | 1 | game 0..1 |
| Rest01 | Float (double precision) | 1 | game 0..1 |
| Hydration01 | Float (double precision) | 1 | game 0..1 |
| Hunger01 | Float (double precision) | 1 | game 0..1 |
| Condition01 | Float (double precision) | 1 | game 0..1 |
| FeelsLikeC | Float (double precision) | -10 | synthetic °C fixture |
| WarmthDelta | Float (double precision) | 0 | signed last substep delta |
| RestDelta | Float (double precision) | 0 | signed last substep delta |
| HydrationDelta | Float (double precision) | 0 | signed last substep delta |
| HungerDelta | Float (double precision) | 0 | signed last substep delta |
| ConditionDelta | Float (double precision) | 0 | signed last substep delta |
| LastStepHours | Float (double precision) | 0 | last substep game hours (NOT last AdvanceGameTime call) |
| LastCause | String | Initial | diagnostics |
| ExposureSource | String | Uninitialized | Zone inside / Zone outside / DEBUG override / Invalid zone fallback |

BPC_SurvivalBody is only writer of its authoritative instance; getters and dispatchers pass snapshots by value. Persistent subset: five satisfaction/condition fields; diagnostics/input reconstructed later, no SG yet. Save/inspect actual struct fields and Make/Break pins.
