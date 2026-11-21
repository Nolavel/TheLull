# WBP_SurvivalDebug — diagnostic UI

Package: /Game/UI/Survival/WBP_SurvivalDebug
AssetType: Widget Blueprint
DependsOn: ST_CoreVitals
Status: stencil drafted / NEEDS REVIEW, 21.11.2026. Actual UE 5.8.4 pins/MCP/PIE not verified. [Research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).

ParentClass: UserWidget
Designer: Canvas top-left; Border with TextBlock TB_Debug (Is Variable), root Not Hit-Testable (Self & All Children). No Tick or binding.
 
RenderDebug(Snapshot:ST_CoreVitals, WorldTimeSeconds:Float(double precision), bAutoAdvance:Boolean, LastCommand:String) -> no output.
Format Text → SetText on TB_Debug. Display time seconds, five raw 0..1 values, FeelsLikeC labeled FIXTURE, five deltas, LastStepHours and LastCause, autoadvance state, LastCommand. If step hours >0 display rates delta/h, else n/a. No independent clock, no calculations that modify state. Key legend: 1 auto/manual; 2 +15min; 3 cold; 4 warm; 5 water mock; 6 food mock; 7 rest mock; 8 toggle debug. Commands handled by core level; debug view never sets state. Refresh immediately on command and clock/body event; not present on geography. 
PIE: exposure change without time updates input, not meters; +15min changed clock exactly 900s, raw matches HUD; hide/show no impact on state. No actual asset yet.
