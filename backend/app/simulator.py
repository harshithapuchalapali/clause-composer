import math


def simulate(rent, deposit, lockin_months, notice_days, months_stayed,
             penalty_months=0, penalty_remaining=False, fixed_deductions=0):
    """Exact, AI-free cost of leaving after `months_stayed` months."""
    remaining = max(0, lockin_months - months_stayed)
    notice_rent = rent * notice_days / 30
    remaining_rent = rent * remaining if penalty_remaining else 0
    rent_owed = max(notice_rent, remaining_rent)
    penalty = rent * penalty_months if remaining > 0 else 0
    total = rent_owed + penalty + fixed_deductions
    return {
        "months_remaining_in_lockin": remaining,
        "rent_owed": round(rent_owed, 2),
        "penalty": round(penalty, 2),
        "deductions": round(fixed_deductions, 2),
        "total_cost": round(total, 2),
        "net_deposit_refund": round(max(0, deposit - total), 2),
        "out_of_pocket": round(max(0, total - deposit), 2),
    }


def cost_series(rent, deposit, lockin_months, notice_days, **kw):
    last = int(lockin_months) + math.ceil(notice_days / 30) + 1
    return [{"month": m, "total_cost": simulate(rent, deposit, lockin_months, notice_days, m, **kw)["total_cost"]}
            for m in range(0, last + 1)]
