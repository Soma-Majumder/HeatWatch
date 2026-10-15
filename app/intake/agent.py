"""The intake conversation. See INTERFACES.md for the Intake and Assessment shapes."""
import json
from dataclasses import dataclass, field
from datetime import datetime

from ..engine import Assessment, Intake, IntakeError, assess
from ..replies import EMERGENCY, build_out_of_area_reply, build_reply, check_reply
from ..tickets import create_ticket
from ..engine import IN_SCOPE_ZIPS
from .guard import detect_safety, has_explicit_duration, is_unsure, sanitize_text, validate_fields
from .llm import LLMError
from .prompt import build_system_prompt

REQUIRED = ("address", "scope", "problem")
SOFT_TURN_CAP = 6        # after this many turns, stop asking optional questions
HARD_TURN_CAP = 12       # after this many, hand the tenant to 311
GREETING = ("Hi, I'm the HeatWatch assistant, and I'm here to help. Tell me what's happening and "
            "the address where the heat or hot water is out.")
FALLBACK_QUESTION = {
    "address": "Thanks for bearing with me. Could you tell me the building number and street where the problem is?",
    "scope": "Thank you. Is the whole building affected, or only your apartment?",
    "problem": "Thank you. Is it heat, hot water, or both?",
}
DURATION_QUESTION = ("Thanks, that helps. About how many hours has the heat or hot water been out? "
                     "A rough number is fine, and it's okay to say you're not sure.")
DURATION_FOLLOWUP = "Can you tell me specifically how many hours has the heat or hot water been out?"
MAX_DURATION_ASKS = 2
GIVE_UP = ("I'm so sorry, I wasn't able to finish taking your report, and I know that's frustrating. "
           "Please call 311 so the city has your complaint, and call 911 right away if there is any danger.")


@dataclass
class TurnResult:
    message: str
    done: bool = False
    ticket_id: str | None = None
    assessment: Assessment | None = None
    gave_up: bool = False


@dataclass
class IntakeSession:
    llm: object
    conn: object
    now_fn: object = datetime.now
    fields: dict = field(default_factory=dict)
    turns: int = 0
    history: list = field(default_factory=list)
    description: str = ""
    bad_replies: int = 0
    emergency_shown: bool = False
    duration_asks: int = 0
    last_text: str = ""
    last_error: str | None = None       # why the last model turn was unusable; for debugging only

    def start(self) -> str:
        return GREETING

    def _missing(self) -> list[str]:
        return [k for k in REQUIRED if k not in self.fields]

    def _ask(self, model_message: str | None) -> str:
        if model_message and not check_reply(model_message, None, False, False):
            return model_message
        missing = self._missing()
        return FALLBACK_QUESTION[missing[0]] if missing else "Is there anything else you want to add?"

    def step(self, user_text: str) -> TurnResult:
        self.turns += 1
        text = sanitize_text(user_text)
        if not text:
            return TurnResult("I didn't catch that. Could you tell me what is happening?")
        if self.turns > HARD_TURN_CAP:
            return TurnResult(GIVE_UP, done=True, gave_up=True)

        self.last_text = text
        self.description = (self.description + " " + text).strip()[:1000]
        newly_unsafe = detect_safety(text) and not self.fields.get("safety_flag")
        if newly_unsafe:
            self.fields["safety_flag"] = True

        self.history.append({"role": "user", "content": text})
        try:
            raw = self.llm.complete(build_system_prompt(self.now_fn()), self.history)
            data = self._parse(raw)
        except (LLMError, ValueError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.history.pop()
            self.bad_replies += 1
            if self.bad_replies >= 3:
                return TurnResult(GIVE_UP, done=True, gave_up=True)
            return TurnResult(self._prefix(newly_unsafe, self._ask(None)))
        self.bad_replies = 0
        self.last_error = None
        self.history.append({"role": "assistant", "content": raw})
        new = validate_fields(data.get("fields"))
        if "duration_hours" in new and not has_explicit_duration(self.description):
            del new["duration_hours"]          # the tenant did not say it; do not accept a guess
        self._merge(new)

        if self._missing():
            return TurnResult(self._prefix(newly_unsafe, self._ask(data.get("message"))))
        if data.get("ready") is True or self.turns >= SOFT_TURN_CAP:
            if self._needs_duration():
                question = DURATION_QUESTION if self.duration_asks == 0 else DURATION_FOLLOWUP
                self.duration_asks += 1
                return TurnResult(self._prefix(newly_unsafe, question))
            return self._finalize()
        return TurnResult(self._prefix(newly_unsafe, self._ask(data.get("message"))))

    def _needs_duration(self) -> bool:
        """Ask for hours, and once more if the answer was still vague, unless it is an emergency,
        an out-of-area address, or the tenant says they are not sure."""
        if "duration_hours" in self.fields or self.duration_asks >= MAX_DURATION_ASKS:
            return False
        if self.duration_asks >= 1 and is_unsure(self.last_text):
            return False
        if self.fields.get("safety_flag"):
            return False
        z = self.fields.get("zip")
        return not (z and z not in IN_SCOPE_ZIPS)

    @staticmethod
    def _parse(raw: str) -> dict:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object")
        data = json.loads(raw[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return data

    def _merge(self, new: dict) -> None:
        for key, value in new.items():
            if key in ("safety_flag", "vulnerable") and self.fields.get(key) is True:
                continue                      # once raised, only a person lowers it
            self.fields[key] = value

    def _prefix(self, unsafe: bool, message: str) -> str:
        if unsafe and not self.emergency_shown:
            self.emergency_shown = True
            return EMERGENCY + " " + message
        return message

    def _finalize(self) -> TurnResult:
        f = self.fields
        try:
            intake = Intake(
                address=f["address"], scope=f["scope"], problem=f["problem"], zip=f.get("zip"),
                duration_hours=f.get("duration_hours"), vulnerable=bool(f.get("vulnerable")),
                safety_flag=bool(f.get("safety_flag")), description=self.description or None,
                lang=f.get("lang", "en"),
            )
            now = self.now_fn()
            a = assess(self.conn, intake, now)
        except IntakeError:
            return TurnResult(self._ask(None))
        if not a.in_scope:
            return TurnResult(build_out_of_area_reply(), done=True, assessment=a)
        ticket = create_ticket(self.conn, intake, a, now)
        reply = build_reply(a, ticket.id, safety_flag=intake.safety_flag, scope=intake.scope)
        return TurnResult(reply, done=True, ticket_id=ticket.id, assessment=a)
