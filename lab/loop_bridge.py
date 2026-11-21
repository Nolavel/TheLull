"""Compatibility entrypoint for the historical day/evening integration probe.

There is now exactly ONE connected implementation, `lab.survival_loop`.
Do not restore the old compensating fuel arithmetic or second Body here.
"""
from .survival_loop import main, run as linked, study


if __name__ == "__main__":
    main()
