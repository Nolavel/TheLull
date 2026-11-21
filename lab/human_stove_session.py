"""Small human-in-the-loop text greybox for the *stove decision only*.

Run: python3 -m lab.human_stove_session --variant A_safe --seed 1 --json session.json

This is NOT a full human survival playtest: travel, searching and night furniture
work still use the scripted lab actor. A separate field interview is necessary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .heat_choice import LIGHT, SAVE
from .survival_loop import run


def human_provider(decision, *, ask=input, show=print) -> str:
    """Give a human only present observable cues; do not prime with agent scores."""
    show(f"\n[{decision.time}] {decision.point}")
    for cue in decision.cues:
        show("  " + cue)
    show("  1 — разжечь печь сейчас")
    show("  2 — сохранить топливо")
    while True:
        reply = ask("Твой выбор [1/2]: ").strip().lower()
        if reply in ("1", "light", "л"):
            selection = "light"
            break
        if reply in ("2", "save", "с"):
            selection = "save"
            break
        show("Ответь 1 или 2.")
    reason = ask("Почему сейчас так? (одна короткая фраза, можно пусто): ").strip()
    # Captured before the player sees the result, so this is not rationalized
    # hindsight; the model can log its own estimates without showing them.
    decision.reason = ("объяснение участника: " + (reason or "(без пояснения)"))
    return selection


def session(seed: int, variant: str, profile: str = "local",
            *, ask=input, show=print) -> dict:
    show("TheLull lab: один день и одна ночь, только решения у печи.")
    show("Движение/поиск и вечерняя работа пока контролируются симуляцией.")
    show("Погода и запасы мира скрыты. Результаты не показываются до окончания.")
    intention = ask("Как собираешься обращаться с дровами сегодня? ").strip()
    human = run(seed, days=1, variant=variant, profile=profile,
                heating_policy="agent",
                decision_provider=lambda d: human_provider(d, ask=ask, show=show))
    show("\nИтог: " + (human["end_reason"] or "дожил до следующего рассвета"))
    show(f"Прошло {human['elapsed_minutes']/60:.2f} игровых часов.")
    if human["history"]:
        final = human["history"][-1]
        show(f"Тело {final['core_next_dawn']}°; дров {final['fuel_next_dawn']}.")
    # Open questions are human observations, not fields guessed from the agent.
    interview = {
        "initial_intention": intention,
        "expected_outcome": ask("Какого исхода ожидал от своих решений? ").strip(),
        "surprise": ask("Что оказалось неожиданным или непонятным? ").strip(),
        "next_intention": ask("Что хотел бы сделать на следующий день? ").strip(),
    }
    reference = run(seed, days=1, variant=variant, profile=profile,
                    heating_policy="agent")
    baseline = run(seed, days=1, variant=variant, profile=profile,
                   heating_policy="dusk")
    return {
        "method": "human-in-loop text stove micro-greybox",
        "participant_count": 1,
        "scope": "only stove ignition, not movement/search/rest or a full greybox game",
        "seed": seed, "variant": variant, "profile": profile,
        "interview": interview,
        "human_run": human, "agent_same_seed": reference,
        "scripted_dusk_same_seed": baseline,
        "limits": [
            "Same deterministic weather and initial world; action sequence can change loot RNG draws.",
            "One participant yields anecdotes and observed decisions, NOT design validation.",
            "No account, identifying information or video/audio is collected by this script.",
            "The model's expected costs are logged but not shown before participant choices.",
            "For a real game-user-research session, build an interactive route/search greybox later.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--variant", choices=("A_safe","B_readable","C_unreadable"),
                        default="A_safe")
    parser.add_argument("--profile", choices=("local","novice"), default="local")
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    result = session(args.seed, args.variant, args.profile)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print("Записано:", args.json)
    print("Сравни decision/choice/outcome/next_intention с агентом при том же seed.")
    print("Личный отчёт содержит ответы участника; не загружай его в публичный репозиторий.")


if __name__ == "__main__":
    main()
