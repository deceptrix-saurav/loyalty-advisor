import unittest

from app import engine as e


def prof(**kw):
    base = dict(business_type="cafe_restaurant", monthly_transactions=3000, avg_bill=250, tech="phone_number")
    p, _ = e.complete_profile({**base, **kw})
    return p


class Maths(unittest.TestCase):
    def test_net_is_zero_at_break_even_lift(self):
        for design in ("punch_card", "points", "tiers", "cashback"):
            p = prof()
            plan = e.design_plan(p, design)
            be = e.economics(p, plan)["break_even_lift_pct"]
            row = e._econ_spend(p, plan, {"uplift_pct": be, "enroll_mult": 1.0})
            self.assertLess(abs(row["net_month"]), 5, design)  # rounding only

    def test_no_break_even_when_rewards_exceed_margin(self):
        p = prof(gross_margin_pct=2)
        plan = e.design_plan(p, "punch_card", max_giveaway_pct=10)
        self.assertIsNone(e.economics(p, plan)["break_even_lift_pct"])

    def test_rewards_never_exceed_the_owners_cap(self):
        for bt in e.BUSINESS:
            p = prof(business_type=bt)
            for key in ("punch_card", "points", "tiers", "cashback"):
                rate = e.design_plan(p, key)["reward_rate"]
                self.assertLessEqual(rate, max(p["max_giveaway_pct"] / 100, e.MIN_REWARD) + 1e-9, (bt, key))

    def test_sized_rewards_pay_off_in_expected_case_for_healthy_margins(self):
        p = prof(business_type="bakery_sweets", tech="pos_app")
        for key in ("punch_card", "points", "tiers", "cashback"):
            ec = e.economics(p, e.design_plan(p, key))
            self.assertTrue(ec["scenarios"]["expected"]["pays_off"], key)

    def test_rounding_never_overshoots(self):
        for x in (0.7, 3.3, 47, 96, 1234):
            self.assertLessEqual(e.nice_down(x), x * 1.0001)
            self.assertGreaterEqual(e.nice(x), x * 0.9999)

    def test_bigger_extra_spend_never_hurts(self):
        p = prof()
        plan = e.design_plan(p, "points")
        nets = [e._econ_spend(p, plan, {"uplift_pct": u, "enroll_mult": 1.0})["net_month"] for u in (0, 2, 6, 12)]
        self.assertEqual(nets, sorted(nets))

    def test_unaffordable_reward_is_flagged_not_hidden(self):
        p = prof(business_type="grocery", gross_margin_pct=6)
        ids = {g["id"]: g["status"] for g in e.check_gates(p)}
        self.assertEqual(ids["margin"], "fail")


class Verdicts(unittest.TestCase):
    def test_few_returning_customers_blocks(self):
        a = e.full_analysis(prof(business_type="electronics", monthly_transactions=120, avg_bill=15000))
        self.assertEqual(a["verdict"]["code"], "not_yet")
        self.assertIn("returning_customers", a["verdict"]["blocked_by"])

    def test_too_few_regulars_blocks(self):
        a = e.full_analysis(prof(monthly_transactions=60, avg_bill=150))
        self.assertIn("enough_regulars", a["verdict"]["blocked_by"])

    def test_referral_goal_ranks_referral_first_for_a_salon(self):
        p = prof(business_type="salon_spa", monthly_transactions=250, avg_bill=900, goal="referral")
        self.assertEqual(e.score_designs(p)[0]["key"], "referral")

    def test_tiers_not_recommended_without_software(self):
        p = prof(tech="none")
        ranking = {r["key"]: r for r in e.score_designs(p)}
        self.assertTrue(any("needs" in n for n in ranking["tiers"]["needs"]))
        self.assertNotEqual(e.score_designs(p)[0]["key"], "tiers")

    def test_ranking_is_sorted_and_complete(self):
        r = e.score_designs(prof())
        self.assertEqual(len(r), 6)
        self.assertEqual([x["score"] for x in r], sorted((x["score"] for x in r), reverse=True))
        self.assertTrue(all(0 <= x["score"] <= 100 for x in r))


class Profiles(unittest.TestCase):
    def test_defaults_are_listed_as_assumptions_with_a_basis(self):
        p, assumed = e.complete_profile(dict(business_type="grocery", monthly_transactions=900, avg_bill=300, gross_margin_pct=18))
        fields = {a["field"] for a in assumed}
        self.assertNotIn("gross_margin_pct", fields)
        self.assertIn("regular_share_pct", fields)
        self.assertTrue(all(a["basis"] for a in assumed))

    def test_missing_or_invalid_input(self):
        with self.assertRaises(e.ProfileError):
            e.complete_profile(dict(business_type="cafe_restaurant", avg_bill=100))
        with self.assertRaises(e.ProfileError):
            e.complete_profile(dict(business_type="rocket", monthly_transactions=100, avg_bill=100))
        with self.assertRaises(e.ProfileError):
            e.complete_profile(dict(business_type="grocery", monthly_transactions=100, avg_bill=100, gross_margin_pct=400))

    def test_money_format(self):
        self.assertEqual(e.fmt(1234567, "₹"), "₹12,34,567")
        self.assertEqual(e.fmt(1234567, "$"), "$1,234,567")
        self.assertEqual(e.fmt(-9876, "₹"), "-₹9,876")


if __name__ == "__main__":
    unittest.main()
