"""Devil's advocate agent: the strongest evidence-backed opposing case.

``DevilsAdvocateAgent`` implements ``Agent`` and ``Debater``. See
``agent.py`` for the flow and ``prompts.py`` for the prompt tags
(``devils_advocate.plan``, ``.assess``, ``.rebut``, ``.debate``).
"""

from secondread.agents.devils_advocate.agent import DevilsAdvocateAgent, rebuttal_severity
from secondread.agents.devils_advocate.prompts import TAG_ASSESS, TAG_DEBATE, TAG_PLAN, TAG_REBUT

__all__ = [
    "TAG_ASSESS",
    "TAG_DEBATE",
    "TAG_PLAN",
    "TAG_REBUT",
    "DevilsAdvocateAgent",
    "rebuttal_severity",
]
