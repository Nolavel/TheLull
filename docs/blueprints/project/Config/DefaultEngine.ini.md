# DefaultEngine.ini — Core startup map config
Mirror: docs/blueprints/project/Config/DefaultEngine.ini.md → <ProjectRoot>/Config/DefaultEngine.ini
AssetType: Config, not UE asset. Status: NEEDS REVIEW / no project or editor verification.
DependsOn: actual L_SurvivalCore.umap, stock Third Person GameMode (external, unknown actual path).
 
## Scope
Once L_SurvivalCore exists, use Project Settings → Maps & Modes to set Editor Startup Map and Game Default Map to /Game/Maps/L_SurvivalCore. Check generated [ /Script/EngineSettings.GameMapsSettings ] (without spaces around brackets in real INI) keys EditorStartupMap and GameDefaultMap, rather than inventing a literal value. Preserve all other template settings, including DefaultGameMode, controller, input contexts, rendering and plugins. Inspect initial file first and diff only intended keys.
 
If MCP/editor cannot do so, open the level manually and mark BLOCKED config capability; never claim an unmodified ini was updated. Close/reopen: map + stock pawn/movement/camera still work in PIE.
Official Epic Maps & Modes: https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-your-game-in-unreal-engine (verify 5.8.4 editor labels).
