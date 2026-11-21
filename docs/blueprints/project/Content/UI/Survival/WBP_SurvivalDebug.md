# WBP_SurvivalDebug — diagnostic UI

Package: /Game/UI/Survival/WBP_SurvivalDebug
AssetType: Widget Blueprint
DependsOn: ST_CoreVitals and ST_CoreSupplies (custom); engine native UMG. Consumer: L_SurvivalCore; commands belong to level.
Status: stencil drafted / NEEDS REVIEW, 21.11.2026. Actual UE 5.8.4 pins/MCP/PIE not verified. [Research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).

ParentClass: UserWidget
Designer: Canvas top-left; Border with TextBlock TB_Debug (Is Variable), root Not Hit-Testable (Self & All Children). No Tick or binding.
 
RenderDebug(Snapshot:ST_CoreVitals, WorldTimeSeconds:Float(double precision), bAutoAdvance:Boolean, LastCommand:String, Supplies:ST_CoreSupplies, LastActionError:String) -> no output. FINAL function signature after Core Actions addition. Level supplies zero-value stock before actions init; never calls missing class in earlier build stage.
Format Text → SetText on TB_Debug. Display time seconds, five raw 0..1 values, FeelsLikeC labeled FIXTURE with ExposureSource (Zone inside / Zone outside / DEBUG override / Invalid zone fallback), five deltas, LastStepHours and LastCause, autoadvance state, LastCommand, WaterServings, FoodServings, LastStockChange and LastActionError. If step hours >0 display rates delta/h, else n/a. No independent clock, no calculations that modify state. Key legend: 1 auto/manual; 2 +15min; 3 cold; 4 warm; 5 water mock; 6 food mock; 7 rest mock; 8 toggle debug; 9 clear exposure override. J/K/L are PAID actions (Drink/Eat/Rest at spatial rest spot), separate from 5/6/7 MOCK free replenishment. Commands handled by core level; debug view never sets state. Refresh immediately on command and clock/body event; not present on geography. 
PIE: exposure change without time updates input, not meters; +15min changed clock exactly 900s, raw matches HUD; hide/show no impact on state. Walking across zone boundary then advancing must display actual source and signed warmth delta; override on/off visible. After J/K/L the Debug stock display must reflect a real paid commit, and never change for a rejected action. No actual asset yet.
