"""Reply builder and output gate.

Replies are assembled from fixed templates. The gate is the last check before
anything reaches a tenant: it also protects model-phrased text later on, so the
model can never promise a repair or claim a filing (docs/security-layer.md).

Spanish support (issue #16): every fixed string a tenant sees has an `_ES`
counterpart below. This is a first, grammatically-considered translation, not a
native speaker's review -- the issue's own done-when line says it needs one
before real use, and that still applies.
"""
import re
from datetime import datetime

from .engine import Assessment

# Warm first, then the policy: acknowledge how frustrating this is before explaining the limit.
DISCLAIMER = ("I know how frustrating it is to wait on a repair, so I want to be upfront: HeatWatch does not "
              "file complaints with the city. If you have not already done so, please also report this to "
              "311 (call 311 or visit nyc.gov/311) so there is an official record.")
DISCLAIMER_ES = ("Sé lo frustrante que es esperar una reparación, así que quiero ser clara desde el principio: "
                  "HeatWatch no presenta quejas ante la ciudad. Si aún no lo ha hecho, por favor reporte esto "
                  "también al 311 (llame al 311 o visite nyc.gov/311) para que quede un registro oficial.")
EMERGENCY = ("Your safety comes first. If you smell gas, feel unsafe, or anyone is unwell, leave the area "
             "if needed and call 911 now. Do not wait for a reply here.")
EMERGENCY_ES = ("Su seguridad es lo primero. Si huele a gas, se siente inseguro/a, o alguien no se encuentra "
                 "bien, salga del área si es necesario y llame al 911 ahora mismo. No espere una respuesta aquí.")

PRIORITY_LINE = {
    "critical": "We have marked this as urgent, and a person has been asked to review it.",
    "high": "We have marked this as high priority.",
    "normal": "We have recorded this as a standard priority.",
    "low": "We have recorded this as a lower priority.",
}
PRIORITY_LINE_ES = {
    "critical": "Hemos marcado esto como urgente, y hemos pedido que una persona lo revise.",
    "high": "Hemos marcado esto como de alta prioridad.",
    "normal": "Hemos registrado esto con prioridad estándar.",
    "low": "Hemos registrado esto con una prioridad más baja.",
}

_FORBIDDEN = [
    (re.compile(r"\b(we|i)\s*(have|'ve|’ve)?\s*(already\s*)?(filed|submitted|reported|sent)\b", re.I),
     "claims to have filed or reported with the city"),
    (re.compile(r"\b(guarantee[ds]?|promise[ds]?)\b", re.I), "makes a guarantee or promise"),
    (re.compile(r"\bwill\s+(definitely\s+)?be\s+(fixed|repaired|resolved|restored)\b", re.I),
     "promises a repair"),
    # The intake prompt already says not to ask for these; this is the code-level backstop
    # in case the model asks anyway. Matches "your name/phone/email", not any other use of
    # those words (the real reply says "give them a phone number", never "your phone number").
    (re.compile(r"\byour\s+(full\s+|last\s+|first\s+)?name\b|"
                r"\byour\s+(phone|cell|mobile)(\s+number)?\b|"
                r"\byour\s+e-?mail(\s+address)?\b|"
                r"\b(social\s+security|\bssn\b)", re.I),
     "asks for personal information beyond what intake is allowed to collect"),
    # Spanish equivalents -- checked regardless of the ticket's recorded language, since
    # lang is tenant/model-reported and not itself fully trusted (same reasoning as #15).
    (re.compile(r"\b(ya\s+)?(hemos|he)\s*(presentado|enviado|reportado|mandado)\b", re.I),
     "claims to have filed or reported with the city (Spanish)"),
    (re.compile(r"\b(garantiz(amos|o)|promet(emos|o))\b", re.I), "makes a guarantee or promise (Spanish)"),
    (re.compile(r"\bse\s+(lo\s+|la\s+|les\s+|le\s+)?(arreglará|reparará|resolverá|restaurará)\b", re.I),
     "promises a repair (Spanish)"),
    (re.compile(r"\b(su|tu)\s+nombre\b|"
                r"\b(su|tu)\s+(número\s+de\s+)?(tel[ée]fono|celular)\b|"
                r"\b(su|tu)\s+(correo(\s+electr[oó]nico)?|email)\b|"
                r"\bn[uú]mero\s+de\s+seguro\s+social\b", re.I),
     "asks for personal information beyond what intake is allowed to collect (Spanish)"),
]

# A model-authored message should never carry a link -- that's a known way a tricked
# model ends up phishing someone. The one link HeatWatch's own fixed wording uses
# (nyc.gov/311, in DISCLAIMER) is explicitly allowed; anything else is not.
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:gov|com|org|net|io|co|info|biz)\b(?:/\S*)?", re.I)
_APPROVED_LINKS = {"nyc.gov/311"}


def _disallowed_link(text: str) -> bool:
    for m in _URL.finditer(text):
        url = m.group(0).strip(".,;:!?)")
        normalized = re.sub(r"^https?://", "", url, flags=re.I)
        normalized = re.sub(r"^www\.", "", normalized, flags=re.I).rstrip("/").lower()
        if normalized not in _APPROVED_LINKS:
            return True
    return False


class ReplyViolation(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


_DISCLAIMER_MARK = {
    "en": "does not file complaints with the city",
    "es": "HeatWatch no presenta quejas ante la ciudad",
}


def check_reply(text: str, ticket_id: str | None = None, needs_emergency: bool = False,
                needs_disclaimer: bool = True, lang: str = "en") -> list[str]:
    problems = [why for pat, why in _FORBIDDEN if pat.search(text)]
    if _disallowed_link(text):
        problems.append("contains a link other than the approved nyc.gov/311")
    if ticket_id and ticket_id not in text:
        problems.append("missing ticket number")
    if needs_disclaimer and _DISCLAIMER_MARK.get(lang, _DISCLAIMER_MARK["en"]) not in text:
        problems.append("missing 'we do not file with the city' notice")
    if needs_emergency and "911" not in text:
        problems.append("missing emergency instruction")
    return problems


def gate(text: str, ticket_id: str | None = None, needs_emergency: bool = False,
         needs_disclaimer: bool = True, lang: str = "en") -> str:
    problems = check_reply(text, ticket_id, needs_emergency, needs_disclaimer, lang)
    if problems:
        raise ReplyViolation(problems)
    return text


def _duplicate_line(a: Assessment, lang: str = "en") -> str | None:
    d = a.duplicate
    if not d:
        return None
    if lang == "es":
        if d.source == "ticket":
            return (f"Ya existe un ticket abierto de HeatWatch para esta dirección ({d.ref}). "
                    "Hemos vinculado el suyo a ese ticket.")
        when = d.created[:10] if d.created else "recientemente"
        return (f"Ya existe una queja abierta de la ciudad para esta dirección, presentada el {when}. "
                "Hemos vinculado la suya, lo cual ayuda a mostrar cuántos hogares están afectados.")
    if d.source == "ticket":
        return f"There is already an open HeatWatch ticket for this address ({d.ref}). We have linked yours to it."
    when = d.created[:10] if d.created else "recently"
    return (f"There is already an open city complaint for this address, filed {when}. "
            "We have linked yours to it, which helps show how many households are affected.")


def _eta_line(eta, lang: str) -> str:
    if lang == "es":
        p50, p90 = round(eta.p50_h), round(eta.p90_h)
        return (f"Quejas similares normalmente se resuelven en aproximadamente {p50} horas, "
                f"y 9 de cada 10 se resuelven dentro de {p90} horas. Esto es un estimado basado "
                "en quejas anteriores.")
    return eta.text + " This is an estimate based on past complaints."


def build_reply(assessment: Assessment, ticket_id: str, safety_flag: bool = False,
                scope: str | None = None, when: datetime | None = None, lang: str = "en") -> str:
    """Compose the full reply for a newly created ticket."""
    if not assessment.in_scope or assessment.priority is None:
        raise ValueError("use build_out_of_area_reply for out-of-area complaints")
    emergency = safety_flag or assessment.override == "safety_risk"
    es = lang == "es"
    parts = [(f"Lamento mucho que esté pasando por esto, y gracias por reportarlo. Su número de ticket "
              f"es {ticket_id}. Guárdelo para consultar el progreso más adelante.") if es else
             (f"I'm really sorry you're dealing with this, and thank you for reporting it. "
              f"Your ticket number is {ticket_id}. Keep it to check progress later.")]
    if emergency:
        parts.append(EMERGENCY_ES if es else EMERGENCY)
    parts.append((PRIORITY_LINE_ES if es else PRIORITY_LINE)[assessment.priority])
    if assessment.override == "vulnerable_no_heat_in_season":
        parts.append(
            "Debido a que una persona vulnerable está sin calefacción, hemos marcado esto para una "
            "revisión urgente. Si alguien se siente mal, llame al 911." if es else
            "Because someone vulnerable is without heat, we have flagged this for urgent review. "
            "If anyone feels unwell, call 911.")
    dup = _duplicate_line(assessment, "es" if es else "en")
    if dup:
        parts.append(dup)
    if assessment.eta:
        parts.append(_eta_line(assessment.eta, "es" if es else "en"))
    parts.append(
        "Qué hacer a continuación: si reporta esto al 311, déles un número de teléfono donde puedan "
        "localizarlo/a, y permita la entrada al inspector o al personal del edificio si la ciudad viene "
        "a revisar. Muchas quejas se estancan cuando no se puede contactar a nadie. Puede volver a "
        "consultar con su número de ticket para ver cómo va su caso." if es else
        "What to do next: if you report this to 311, give them a phone number where you can be "
        "reached, and let the inspector or building staff in if the city comes to check. "
        "Many complaints stall when no one can be reached. You can come back with your ticket "
        "number to see how your ticket is progressing.")
    if scope == "apartment":
        parts.append(
            "Si los vecinos también están sin calefacción, pídales que reporten también. Los problemas "
            "en todo el edificio se tratan con mayor prioridad." if es else
            "If neighbors also have no heat, ask them to report too. "
            "Whole-building problems are treated with higher priority.")
    if assessment.escalate:
        parts.append(
            "Una persona de HeatWatch lo revisará. Por favor guarde su número de ticket para consultar "
            "su estado." if es else
            "A person at HeatWatch will review it. Please keep your ticket number to check its status.")
    parts.append(DISCLAIMER_ES if es else DISCLAIMER)
    return gate(" ".join(parts), ticket_id, needs_emergency=emergency, lang="es" if es else "en")


def build_out_of_area_reply(lang: str = "en") -> str:
    es = lang == "es"
    text = (
        "Lo siento, sé que esto es importante para usted, y desearía poder hacer más desde aquí. "
        "HeatWatch actualmente cubre solo Washington Heights e Inwood, así que no podemos crear un "
        "ticket para esta dirección. " + DISCLAIMER_ES if es else
        "I'm sorry, I can tell this matters to you, and I wish I could do more from here. HeatWatch "
        "currently covers Washington Heights and Inwood only, so we cannot create a ticket for this "
        "address. " + DISCLAIMER)
    return gate(text, None, lang="es" if es else "en")
