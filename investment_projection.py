"""Deterministic monthly cash-flow projections, independent of account state."""
import math
from collections import defaultdict


def _amount(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: יש להזין מספר תקין") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label}: יש להזין מספר סופי שאינו שלילי")
    return result


def _month(value, label, maximum):
    result = _amount(value, label)
    if not result.is_integer() or result > maximum:
        raise ValueError(f"{label}: יש להזין חודש שלם בין 0 ל־{maximum}")
    return int(result)


def annual_to_monthly(annual_return_pct):
    """Convert an effective annual return, not a nominal APR, to a monthly rate."""
    try:
        rate = float(annual_return_pct)
    except (TypeError, ValueError):
        raise ValueError("התשואה השנתית אינה תקינה") from None
    if not math.isfinite(rate) or not -100 < rate <= 1000:
        raise ValueError("התשואה השנתית חייבת להיות גדולה מ־‎-100% ועד 1,000%")
    return math.expm1(math.log1p(rate / 100) / 12)


def project_investment(initial_value, monthly_contribution, months, annual_return_pct,
                       changed_monthly=None, change_after_months=0, lump_sums=None,
                       annual_inflation_pct=0):
    """Return month-end balances; month 0 lumps are invested immediately.

    Months 1..N: grow the previous balance, then add the recurring contribution
    and any lump sums. A change after 12 months begins with contribution 13.
    The initial value is today's market value, not the historical purchase cost.
    """
    initial = _amount(initial_value, "סכום התחלתי")
    recurring = _amount(monthly_contribution, "הפקדה חודשית")
    horizon = _month(months, "אופק התחזית", 1200)
    changed = recurring if changed_monthly is None else _amount(changed_monthly, "הפקדה חודשית חדשה")
    change_after = _month(change_after_months, "מועד שינוי ההפקדה", horizon)
    monthly_rate = annual_to_monthly(annual_return_pct)
    inflation = _amount(annual_inflation_pct, "אינפלציה") / 100
    lumps = defaultdict(float)
    for row in lump_sums or []:
        month = _month(row.get("month"), "מועד הפקדה חד־פעמית", horizon)
        lumps[month] += _amount(row.get("amount"), "סכום הפקדה חד־פעמית")

    balance = initial + lumps[0]
    future_deposits = lumps[0]
    result = []
    for month in range(horizon + 1):
        if month:
            contribution = changed if month > change_after else recurring
            addition = contribution + lumps[month]
            balance = balance * (1 + monthly_rate) + addition
            future_deposits += addition
        capital = initial + future_deposits
        real_value = balance / math.exp(math.log1p(inflation) * month / 12)
        if not all(math.isfinite(v) for v in (balance, capital, real_value)):
            raise ValueError("הסכומים חורגים מטווח החישוב; קצר את התקופה או הקטן את הערכים")
        result.append({"month": month, "years": month / 12, "balance": balance,
                       "initial_value": initial, "future_deposits": future_deposits,
                       "capital": capital, "growth": balance - capital, "real_value": real_value})
    return result


def compare_funding(initial_value, monthly_contribution, months, annual_return_pct,
                    changed_monthly, change_after_months=0, lump_sums=None,
                    annual_inflation_pct=0):
    common = dict(initial_value=initial_value, monthly_contribution=monthly_contribution,
                  months=months, annual_return_pct=annual_return_pct,
                  annual_inflation_pct=annual_inflation_pct)
    baseline = project_investment(**common)
    monthly_only = project_investment(**common, changed_monthly=changed_monthly,
                                      change_after_months=change_after_months)
    lumps_only = project_investment(**common, lump_sums=lump_sums)
    combined = project_investment(**common, changed_monthly=changed_monthly,
                                  change_after_months=change_after_months, lump_sums=lump_sums)
    return {"baseline": baseline, "monthly_only": monthly_only,
            "lumps_only": lumps_only, "combined": combined}
