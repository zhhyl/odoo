# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestPlmFeasibility(TransactionCase):
    """測試可行性評估主檔：總分計算、決策門檻、state machine。"""

    _test_user_groups = (
        "base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Feasibility = cls.env["plm_custom.feasibility"]
        cls.Score = cls.env["plm_custom.feasibility.score"]
        cls.Partner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"]

        cls.partner = cls.Partner.create({"name": "Test Customer"})
        cls.product = cls.Product.create({"name": "Test Product"})
        # 業務 / 工程 / 產線 / 品保 / 採購 五位評分者
        cls.user_sales = new_test_user(
            cls.env, login="feas_sales", groups="base.group_user"
        )
        cls.user_engineering = new_test_user(
            cls.env, login="feas_eng", groups="base.group_user"
        )
        cls.user_production = new_test_user(
            cls.env, login="feas_prod", groups="base.group_user"
        )
        cls.user_qa = new_test_user(
            cls.env, login="feas_qa", groups="base.group_user"
        )
        cls.user_procurement = new_test_user(
            cls.env, login="feas_proc", groups="base.group_user"
        )
        # 簽核關卡的核准者（需有 mfg_custom_base.group_user 才能讀寫評估單）
        cls.approver = new_test_user(
            cls.env,
            login="feas_approver",
            groups="base.group_user,mfg_custom_base.group_user",
        )
        # 測試規則 sequence=1 → 優先於種子規則「可行性評估簽核」
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.rule = cls.Rule.create({
            "name": "可行性評估測試簽核規則",
            "model_id": cls.env["ir.model"]._get("plm_custom.feasibility").id,
            "sequence": 1,
            "step_ids": [
                Command.create({
                    "name": "測試核准",
                    "approver_mode": "user",
                    "user_ids": [Command.set([cls.approver.id])],
                }),
            ],
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_feasibility(self, **extra):
        vals = {
            "partner_id": self.partner.id,
            "product_id": self.product.id,
            "user_id": self.env.user.id,
        }
        vals.update(extra)
        return self.Feasibility.create(vals)

    def _add_full_scores(self, feasibility, base=8):
        """為 feasibility 加上五部門評分（皆為 base 分）。"""
        scores = [
            ("sales", self.user_sales, base),
            ("engineering", self.user_engineering, base),
            ("production", self.user_production, base),
            ("qa", self.user_qa, base),
            ("procurement", self.user_procurement, base),
        ]
        for dept, user, sc in scores:
            self.Score.create({
                "feasibility_id": feasibility.id,
                "department": dept,
                "reviewer_id": user.id,
                "score": sc,
            })
        return scores

    # ------------------------------------------------------------------
    # Score total & decision thresholds
    # ------------------------------------------------------------------

    def test_01_compute_score_total(self):
        """五項分數 → score_total = sum × 2。"""
        rec = self._make_feasibility()
        self.assertEqual(rec.score_total, 0)
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "production",
            "reviewer_id": self.user_production.id,
            "score": 8,
        })
        self.assertEqual(rec.score_capacity, 8)
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "engineering",
            "reviewer_id": self.user_engineering.id,
            "score": 7,
        })
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "procurement",
            "reviewer_id": self.user_procurement.id,
            "score": 6,
        })
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "qa",
            "reviewer_id": self.user_qa.id,
            "score": 9,
        })
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "sales",
            "reviewer_id": self.user_sales.id,
            "score": 5,
        })
        # 8+7+6+9+5 = 35，score_total = 70
        self.assertEqual(rec.score_total, 70)
        self.assertEqual(rec.decision, "feasible_with_risk")

    def test_02_decision_thresholds(self):
        """決策門檻：80+ feasible、60-79 feasible_with_risk、<60 infeasible。"""
        # 79 分 → feasible_with_risk
        rec_low = self._make_feasibility()
        # 採用 5 個分數組合：合計 = 39.5 → 無法直接整數，改寫為 8,8,8,8,7.5
        # 但 score 是 Integer 0-10，所以用 8,8,8,8,7 → total = 39 → 78 → feasible_with_risk
        # 為精準達成 79：使用 8,8,8,8,8-1 = 40-1 = 39 → 78，差 1 分
        # 改用直接寫入 score_capacity/technical/... 模擬 79.5
        rec_low.write({
            "score_capacity": 8,
            "score_technical": 8,
            "score_material": 8,
            "score_regulatory": 8,
            "score_risk": 7,  # sum=39 → total=78
        })
        self.assertEqual(rec_low.score_total, 78)
        self.assertEqual(rec_low.decision, "feasible_with_risk")

        # 80 分 → feasible
        rec_hi = self._make_feasibility()
        rec_hi.write({
            "score_capacity": 8,
            "score_technical": 8,
            "score_material": 8,
            "score_regulatory": 8,
            "score_risk": 8,  # sum=40 → total=80
        })
        self.assertEqual(rec_hi.score_total, 80)
        self.assertEqual(rec_hi.decision, "feasible")

        # 59 分 → infeasible
        rec_lo = self._make_feasibility()
        rec_lo.write({
            "score_capacity": 6,
            "score_technical": 6,
            "score_material": 6,
            "score_regulatory": 6,
            "score_risk": 5,  # sum=29 → total=58
        })
        self.assertEqual(rec_lo.score_total, 58)
        self.assertEqual(rec_lo.decision, "infeasible")

    # ------------------------------------------------------------------
    # Action methods
    # ------------------------------------------------------------------

    def test_03_action_submit_requires_scores(self):
        """草稿狀態下，若無評分直接 submit 應拋 UserError。"""
        rec = self._make_feasibility()
        with self.assertRaises(UserError):
            rec.action_submit()

        # 加 1 筆評分後可送出
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "sales",
            "reviewer_id": self.user_sales.id,
            "score": 5,
        })
        rec.action_submit()
        self.assertEqual(rec.state, "in_review")

    def test_04_action_approve_requires_all_dept(self):
        """所有關卡核准時若缺一部門評分，應拋 UserError。"""
        rec = self._make_feasibility()
        # 只給 4 個部門評分（各 8 分）
        for dept, user in (
            ("sales", self.user_sales),
            ("engineering", self.user_engineering),
            ("production", self.user_production),
            ("qa", self.user_qa),
        ):
            self.Score.create({
                "feasibility_id": rec.id,
                "department": dept,
                "reviewer_id": user.id,
                "score": 8,
            })
        rec.action_submit()
        rec.action_submit_for_approval()
        with self.assertRaises(UserError):
            rec.with_user(self.approver).action_approve()

    def test_04b_action_approve_all_dept_scored(self):
        """五個部門都評分後，簽核核准 → 評估通過。"""
        rec = self._make_feasibility()
        # 5 部門 × 8 分 = 40 → 總分 80 → feasible
        self._add_full_scores(rec, base=8)
        rec.action_submit()
        rec.action_submit_for_approval()
        rec.with_user(self.approver).action_approve()
        rec.invalidate_recordset()
        self.assertEqual(rec.state, "approved")
        self.assertEqual(rec.decision, "feasible")
        self.assertEqual(rec.approval_state, "approved")

    def test_05_action_reject_from_in_review(self):
        """簽核引擎駁回後，評估單改為不通過。"""
        rec = self._make_feasibility()
        self._add_full_scores(rec, base=3)
        rec.action_submit()
        rec.action_submit_for_approval()
        rec.with_user(self.approver).action_reject()
        rec.invalidate_recordset()
        self.assertEqual(rec.state, "rejected")
        self.assertEqual(rec.decision, "infeasible")
        self.assertEqual(rec.approval_state, "rejected")

    def test_06_action_cancel(self):
        """草稿狀態可取消。"""
        rec = self._make_feasibility()
        rec.action_cancel()
        self.assertEqual(rec.state, "cancelled")

    def test_07_action_submit_wrong_state(self):
        """非 draft 狀態不可 submit。"""
        rec = self._make_feasibility()
        self._add_full_scores(rec)
        rec.action_submit()
        with self.assertRaises(UserError):
            rec.action_submit()

    # ------------------------------------------------------------------
    # Sequence
    # ------------------------------------------------------------------

    def test_08_sequence_assigned(self):
        """create 時自動帶入序號。"""
        rec = self._make_feasibility()
        self.assertNotEqual(rec.name, "New")
        self.assertTrue(rec.name.startswith("FEA/"))

    # ------------------------------------------------------------------
    # Constraint: 0-10
    # ------------------------------------------------------------------

    def test_09_score_out_of_range_raises(self):
        """score 超出 0-10 應拋 ValidationError。"""
        rec = self._make_feasibility()
        with self.assertRaises(ValidationError):
            self.Score.create({
                "feasibility_id": rec.id,
                "department": "sales",
                "reviewer_id": self.user_sales.id,
                "score": 11,
            })


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestPlmFeasibilityApproval(TransactionCase):
    """測試可行性評估的簽核引擎回寫（送出檢查 / 核准 / 取消）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Feasibility = cls.env["plm_custom.feasibility"]
        cls.Score = cls.env["plm_custom.feasibility.score"]
        cls.Partner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"]
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.partner = cls.Partner.create({"name": "Approval Customer"})
        cls.product = cls.Product.create({"name": "Approval Product"})
        cls.approver = new_test_user(
            cls.env,
            login="feas_approval_approver",
            groups="base.group_user,mfg_custom_base.group_user",
        )
        # 評分者必須是「啟用」的帳號：Odoo 20 的測試預設使用者（OdooBot）
        # 已是停用狀態，評分模型會拒絕停用帳號當評分者。
        cls.user_sales = new_test_user(
            cls.env, login="feas_appr_sales", groups="base.group_user"
        )
        cls.user_engineering = new_test_user(
            cls.env, login="feas_appr_eng", groups="base.group_user"
        )
        cls.user_production = new_test_user(
            cls.env, login="feas_appr_prod", groups="base.group_user"
        )
        cls.user_qa = new_test_user(
            cls.env, login="feas_appr_qa", groups="base.group_user"
        )
        cls.user_procurement = new_test_user(
            cls.env, login="feas_appr_proc", groups="base.group_user"
        )
        # 測試規則 sequence=1 → 優先於種子規則「可行性評估簽核」
        cls.rule = cls.Rule.create({
            "name": "可行性評估審核測試規則",
            "model_id": cls.env["ir.model"]._get("plm_custom.feasibility").id,
            "sequence": 1,
            "step_ids": [
                Command.create({
                    "name": "測試核准",
                    "approver_mode": "user",
                    "user_ids": [Command.set([cls.approver.id])],
                }),
            ],
        })

    def _make_feasibility(self, **extra):
        vals = {
            "partner_id": self.partner.id,
            "product_id": self.product.id,
            "user_id": self.user_sales.id,
        }
        vals.update(extra)
        return self.Feasibility.create(vals)

    def _add_score(self, feasibility, department="sales", reviewer=None):
        """新增一筆評分明細（評分者預設為啟用中的業務評分者）。"""
        return self.Score.create({
            "feasibility_id": feasibility.id,
            "department": department,
            "reviewer_id": (reviewer or self.user_sales).id,
            "score": 8,
        })

    def _add_full_scores(self, feasibility, base=8):
        """五個必要部門（業務/工程/產線/品保/採購）都評分。

        核准時 ``_approval_on_approved()`` 會呼叫 ``_check_all_scores_filled()``，
        缺任何一個部門都會拋 UserError。
        """
        scores = [
            ("sales", self.user_sales),
            ("engineering", self.user_engineering),
            ("production", self.user_production),
            ("qa", self.user_qa),
            ("procurement", self.user_procurement),
        ]
        for dept, user in scores:
            self.Score.create({
                "feasibility_id": feasibility.id,
                "department": dept,
                "reviewer_id": user.id,
                "score": base,
            })
        return scores

    def test_01_before_submit_requires_in_review(self):
        """draft 狀態不可送出簽核（須先送出評估）。"""
        rec = self._make_feasibility()
        self._add_score(rec)
        with self.assertRaises(UserError):
            rec.action_submit_for_approval()

    def test_02_before_submit_requires_scores(self):
        """送出簽核時若已無評分明細，應拋 UserError。"""
        rec = self._make_feasibility()
        score = self._add_score(rec)
        rec.action_submit()
        score.unlink()
        with self.assertRaises(UserError):
            rec.action_submit_for_approval()

    def test_03_approved_sets_state_approved(self):
        """所有關卡核准後，評估單改為「通過」。"""
        rec = self._make_feasibility()
        # 核准前必須五個必要部門都已評分
        self._add_full_scores(rec)
        rec.action_submit()
        rec.action_submit_for_approval()
        rec.with_user(self.approver).action_approve()
        rec.invalidate_recordset()
        self.assertEqual(rec.state, "approved")
        self.assertEqual(rec.approval_state, "approved")

    def test_04_cancelled_back_to_draft(self):
        """簽核取消後，評估單退回草稿。"""
        rec = self._make_feasibility()
        self._add_score(rec)
        rec.action_submit()
        rec.action_submit_for_approval()
        rec.action_cancel_approval()
        rec.invalidate_recordset()
        self.assertEqual(rec.state, "draft")
        self.assertEqual(rec.approval_state, "not_required")
