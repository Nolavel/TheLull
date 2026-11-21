# BP_CoreRestSpot — spatial rest prerequisite, not a sleeping system

Package: /Game/Survival/Environment/BP_CoreRestSpot
AssetType: Blueprint Class
ParentClass: Actor
DependsOn: engine Box Collision; stock Third Person Pawn collision (external unknown package)
Status: NEEDS REVIEW / NOT ASSEMBLED / NOT PIE TESTED. 21.11.2026.

## Scene
DefaultSceneRoot → Box Collision "RestArea" (Box Extent X=120,Y=120,Z=150 cm). Query Only. Object WorldDynamic; Pawn: Overlap, other channels Ignore; Generate Overlap Events=true. A visible Cube mesh is OPTIONAL test geometry; collision must not block movement. Place the actor inside the *warm* half of BP_CoreExposureZone in L_SurvivalCore; actor location and overlap with player capsule verified in editor, not invented coordinates. No Tick.

## Contract
- CanRest(Subject: Actor Object Reference) -> bAllowed:Boolean (pure): return false if Subject not valid; otherwise RestArea.IsOverlappingActor(Subject). One query; no register/clock/need mutation.
- A room does not automatically imply a bed. Core actions require **both** CanRest(Pawn)=true and BP_CoreExposureZone.QueryExposure(Pawn).bInside=true. This is a provisional safe-rest fixture, not a generalized indoor/bedroll system.
- Rest spot is not saved and cannot write time, warmth or fatigue; later rest affordance will replace this fixture through an interface after separate design.

## Negative PIE checks
Pawn outside: CanRest=false, no rest time cost; inside warm zone but *outside* RestArea: still false; inside both: true. Moving outside during a 900 s time advance is not simulated: fixed-position snapshot semantics. Verify native component IsOverlappingActor node and pins in UE 5.8.4; no claim of actual tests.
