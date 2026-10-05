"""표기 해석만 수행한다. 농도 검증, 임상 판단, 추천 가중치 산출은 하지 않는다."""
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
import re

PARSER_VERSION = "cosmetic-amounts-v1"
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
TOKEN = rf"({NUMBER})\s*(IU/g|ppm|ppb|mg|%)"
SINGLE = re.compile(TOKEN, re.IGNORECASE)
DUAL = re.compile(rf"{TOKEN}\s*/\s*{TOKEN}", re.IGNORECASE)
SCALES = {"%": 0, "ppm": -4, "ppb": -7}
LIMITS = {"%": Decimal(100), "ppm": Decimal(1000000), "ppb": Decimal(1000000000)}


@dataclass(frozen=True)
class DeclaredAmount:
    value: str
    unit: str
    # 같은 비율 기준을 가정한 산술 환산. 완제품 농도가 아니다.
    conditional_percent: str | None


@dataclass(frozen=True)
class AmountInterpretation:
    raw_text: str | None
    status: str
    declarations: tuple[DeclaredAmount, ...] = ()
    issue: str | None = None
    dual_consistent_if_same_basis: bool | None = None
    basis: str = "unknown"
    concentration_verified: bool = False
    parser_version: str = PARSER_VERSION

    def to_dict(self):
        return asdict(self)


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _declaration(number: str, unit: str) -> DeclaredAmount:
    if len(number) > 50:
        raise ValueError("number_too_long")
    value = Decimal(number.replace(",", ""))
    unit = "IU/g" if unit.lower() == "iu/g" else unit.lower()
    if unit in LIMITS and value > LIMITS[unit]:
        raise ValueError("fraction_out_of_range")
    percent = None
    if unit in SCALES:
        with localcontext() as ctx:
            ctx.prec = 80
            percent = _plain(value.scaleb(SCALES[unit]))
    return DeclaredAmount(_plain(value), unit, percent)


def parse_amount(raw: str | None) -> AmountInterpretation:
    """허용 형식만 전체 일치로 해석. 누락을 0으로 바꾸거나 추측 보정하지 않는다."""
    if raw is not None and not isinstance(raw, str):
        raise TypeError("amount_text must be a string or None")
    if raw is None or not raw.strip():
        return AmountInterpretation(raw, "missing")
    if len(raw) > 256:
        return AmountInterpretation(raw, "unparsed", issue="text_too_long")
    text = raw.strip()
    single = SINGLE.fullmatch(text)
    dual = None if single else DUAL.fullmatch(text)
    if not single and not dual:
        return AmountInterpretation(raw, "unparsed", issue="unsupported_or_malformed")
    try:
        groups = (single or dual).groups()
        values = tuple(_declaration(groups[i], groups[i + 1]) for i in range(0, len(groups), 2))
    except ValueError as error:
        return AmountInterpretation(raw, "unparsed", issue=str(error))
    if single:
        issue = "denominator_missing" if values[0].unit == "mg" else (
            "activity_unit_not_converted" if values[0].unit == "IU/g" else None)
        return AmountInterpretation(raw, "single", values, issue)
    a, b = values
    if a.unit not in SCALES or b.unit not in SCALES or a.unit == b.unit:
        return AmountInterpretation(raw, "unparsed", values, "unsupported_dual_units")
    consistent = Decimal(a.conditional_percent) == Decimal(b.conditional_percent)
    return AmountInterpretation(raw, "dual", values,
                                None if consistent else "inconsistent_dual",
                                consistent)
