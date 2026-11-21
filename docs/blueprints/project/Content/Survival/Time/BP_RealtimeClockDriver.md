# BP_RealtimeClockDriver — 60-минутные сутки Hoarbound

Package: /Game/Survival/Time/BP_RealtimeClockDriver
AssetType: Blueprint Class
ParentClass: Actor
DependsOn: BP_SurvivalWorld, E_AdvanceResult, Config/DefaultGameplayTags.ini; native UE Timer Manager, GameplayStatics Get Audio Time Seconds.
PlacedIn: /Game/Maps/L_SurvivalCore (one persistent instance).
Status: NEEDS REVIEW / UNBUILT / PIE NOT RUN, 21.11.2026.

## Source / design contract

Hoarbound main `scenes/game/systems/world/WorldEnvironmentSystem.tscn`: DayNightSettings.day_duration=1800.0 real seconds and night_duration=1800.0, hence a **24 game hour day lasts 3600 real seconds (60 min)**. `scripts/systems/world/DayNightManager.gd` derives game hours per real second and calls SimulationClock. TheLull mirrors this pacing, not the old F00 artificial 60 game seconds per 1 real second.

**Rate:** 86400 game s / 3600 real s = **24 game seconds per 1 unpaused real second**. One real minute = 24 game minutes. F00 BP_SurvivalWorld remains the *only authoritative writer*; this actor merely requests `AdvanceGameTime`. Does not implement BPI_SimStepReceiver, does not Tick, does not write time in BeginPlay, has no save data or independent game-day counter.

## Variables
All runtime vars Private=true; no Instance Editable/ExposeOnSpawn. `SampleIntervalRealSeconds` (Float, double precision) class constant 0.25; `GameSecondsPerRealSecond` (Float double) constant 24.0. `Clock:BP_SurvivalWorld Object Reference=None`; `bInitialized:Boolean=false`; `bEnabled:Boolean=false`; `bFaulted:Boolean=false`; `LastSampleRealSeconds:Float(double)=0`; `TimerHandle:TimerHandle=invalid`; `LastResult:E_AdvanceResult=NotAttempted`; `LastError:String=""`. LastSampleRealSeconds is **only UE elapsed-time sampling**; it is NOT a second world clock.

## Public methods / events
```text
InitializeDriver(InClock:BP_SurvivalWorld Object Reference) -> bOK:Boolean
SetRealtimeEnabled(bNewEnabled:Boolean) -> bOK:Boolean
IsRealtimeEnabled() -> bEnabled:Boolean [pure]
IsDriverFaulted() -> bFaulted:Boolean [pure]
GetRate() -> GameSecondsPerRealSecond:Float (double precision) [pure]
GetLastError() -> Message:String [pure]
OnRealtimeDriverFault(Result:E_AdvanceResult, Message:String) [Event Dispatcher]
```

## Graph construction, executable order
```text
BeginPlay:
  // no automatic clock initialization or timer

InitializeDriver(InClock):
  if bInitialized || !IsValid(InClock) || !InClock.IsClockReady()
     || InClock.IsTimeDispatching() || InClock.IsSimulationFaulted(): return false
  Clock=InClock; LastSampleRealSeconds=Get Audio Time Seconds;
  bInitialized=true; bEnabled=false; return true

SetRealtimeEnabled(NewEnabled):
  if !bInitialized || !IsValid(Clock) || bFaulted || Clock.IsSimulationFaulted(): return false
  if NewEnabled==bEnabled: return true   // never duplicate Timer
  if NewEnabled:
     if Clock.IsTimeDispatching(): return false
     LastSampleRealSeconds=Get Audio Time Seconds
     Set Timer by Event (Event=OnRealtimeSample, Time=0.25, Looping=true)
        -> TimerHandle
     if TimerHandle invalid: return false (print error)
     bEnabled=true; return true
  else:
     Clear and Invalidate Timer by Handle(TimerHandle)
     bEnabled=false
     LastSampleRealSeconds=Get Audio Time Seconds // discard inactive elapsed, no catch-up
     return true

OnRealtimeSample [Custom Event]:
  if !bEnabled: return
  if !IsValid(Clock) || !Clock.IsClockReady() || Clock.IsSimulationFaulted():
      Fault(Rejected,"clock unavailable"); return
  Now=Get Audio Time Seconds
  Elapsed=Now-LastSampleRealSeconds
  if !(Elapsed>0.0 && Elapsed<=3600.0): Fault(Rejected,"invalid elapsed"); return
  PaidDelta=Elapsed*24.0
  if !(PaidDelta>0.0 && PaidDelta<=86400.0): Fault(Rejected,"invalid delta"); return
  Result=Clock.AdvanceGameTime(PaidDelta, Time.Advance.Realtime)
  LastResult=Result
  if Result!=Completed: Fault(Result,"realtime advance incomplete"); return
  LastSampleRealSeconds=Now
  // neither Body nor Lighting receives direct commands; Clock alone dispatches

Fault(Result,Message) [private impure]:
  Clear and Invalidate Timer by Handle(TimerHandle)
  bEnabled=false; bFaulted=true; LastResult=Result; LastError=Message
  PrintString("REALTIME DRIVER FAULT "+Message)
  Broadcast OnRealtimeDriverFault(Result,Message)
  // Never retry a PartialFailure.

EndPlay:
  Clear and Invalidate Timer by Handle(TimerHandle)
```

**Timer sampling:** UE 5.8 [Get Audio Time Seconds](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/Utilities/Time/GetAudioTimeSeconds) returns world elapsed real seconds **stopped during pause, unaffected by time dilation**; it measures elapsed, not gameplay time. The 0.25s timer is only an interval to sample elapsed; if frame drops, next successful sample catches up (within 1-h maximum per Clock call). UE [Get Game Time in Seconds](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/Utilities/Time/GetGameTimeinSeconds) is time-dilated, so cannot preserve 60 real-minute days when slomo changes. Check availability/behavior in installed UE 5.8.4/MCP, do not guess alternate nodes. Pausing/disabled driver discards inactive elapsed, avoids double billing.

**One requester:** the current Level's old `Set Timer by Event → Clock.AdvanceGameTime(60)` MUST BE REMOVED. Level key 1 now calls Driver.SetRealtimeEnabled; `bAutoAdvance` UI is derived from Driver.IsRealtimeEnabled, not a second authoritative timer. Paid J/K/L and manual key 2 remain disabled during realtime mode in this harness. `OnTimeAdvanceFinished` must not call a second Advance because Clock still holds its guard during this dispatcher.

## PIE acceptance — all NOT RUN
- Fresh clock 08:00, Driver initialized/off: elapsed 10 real s does not advance game time.
- Enable: 10 unpaused real s -> +240 game s (4 min); 60 real s -> +1440 game s (24 min); 3600 real s -> +86400 game s (24h). Compare clock and UE elapsed sample with timer jitter; math is contract, long runtime test remains pending.
- Pause game 10s → no accrual; disable realtime 10s → re-enable and no backlog. Low FPS delayed sample must bill elapsed correctly (not frame count).
- Manual AdvanceGameTime(900,Debug) while driver disabled → exactly 900s. Re-enable, no reset of clock. Duplicate Drivers/Timers rejected at Level startup.
- Clock PartialFailure -> driver latches fault; no future time request. Engine/world dilation should not alter 24/real-s ratio if timer callbacks execute.
- Verify TimerHandle validity and UE Set Timer by Event pins via MCP, Compile/PIE before REVIEWED.

UE docs: [Set Timer by Event 5.8](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UKismetSystemLibrary/K2_SetTimerDelegate?application_version=5.8); [Clear by Handle](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/Utilities/Time/ClearandInvalidateTimerbyHandle).
