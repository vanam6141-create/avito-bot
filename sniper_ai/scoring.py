from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DealScore:
    score: int
    discount_percent: float | None
    risk_level: str
    reasons: tuple[str, ...]


def score_listing(
    asking_price: int | None,
    comparable_market_price: int | None,
    *,
    condition: str = "unknown",
    seller_verified: bool = False,
    has_delivery: bool = False,
    suspicious_text: bool = False,
) -> DealScore:
    """Transparent heuristic score; not an AI appraisal or authenticity guarantee."""
    score = 45
    reasons: list[str] = []
    discount: float | None = None
    if asking_price is not None and asking_price > 0 and comparable_market_price is not None and comparable_market_price > 0:
        discount = (comparable_market_price - asking_price) / comparable_market_price * 100
        score += max(-25, min(30, round(discount * 0.8)))
        reasons.append(f"Отклонение от указанной рыночной цены: {discount:.1f}%")
    else:
        score -= 10
        reasons.append("Недостаточно данных для сравнения цены")
    condition_key = condition.strip().lower()
    if condition_key in {"new", "новое", "новый"}:
        score += 8
        reasons.append("Указано новое состояние")
    elif condition_key in {"used", "б/у", "бу", "used_good"}:
        score += 2
        reasons.append("Указано состояние б/у; нужна проверка")
    else:
        score -= 5
        reasons.append("Состояние не подтверждено")
    if seller_verified:
        score += 7
        reasons.append("Есть признак подтверждённого продавца")
    if has_delivery:
        score += 3
        reasons.append("Доставка заявлена")
    if suspicious_text:
        score -= 30
        reasons.append("Обнаружены подозрительные формулировки")
    score = max(0, min(100, score))
    risk = "high" if suspicious_text or score < 35 else "medium" if score < 65 else "low"
    return DealScore(score, round(discount, 1) if discount is not None else None, risk, tuple(reasons))
