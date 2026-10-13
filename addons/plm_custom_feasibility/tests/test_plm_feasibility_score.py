# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestPlmFeasibilityScore(TransactionCase):
    """測試可行性評估評分明細：唯一性、範圍、同步主檔分數。"""

    _test_user_groups = (
        "base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Feasibility = cls.env["plm_custom.feasibility"]
        cls.Score = cls.env["plm_custom.feasibility.score"]
        cls.partner = cls.env["res.partner"].create({"name": "Score Customer"})
        cls.product = cls.env["product.product"].create({"name": "Score Product"})
        cls.user = new_test_user(
            cls.env, login="score_user", groups="base.group_user"
        )

    def _make_feasibility(self):
        return self.Feasibility.create({
            "partner_id": self.partner.id,
            "product_id": self.product.id,
        })

    def test_01_duplicate_dept_score_constrained(self):
        """同部門兩筆評分應被 UNIQUE(feasibility_id, department) 阻擋。"""
        rec = self._make_feasibility()
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "sales",
            "reviewer_id": self.user.id,
            "score": 7,
        })
        with self.assertRaises(ValidationError):
            self.Score.create({
                "feasibility_id": rec.id,
                "department": "sales",
                "reviewer_id": self.user.id,
                "score": 5,
            })

    def test_02_score_syncs_main_field(self):
        """新增 / 修改 score 應同步主檔對應欄位。"""
        rec = self._make_feasibility()
        # 業務 → 風險分數
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "sales",
            "reviewer_id": self.user.id,
            "score": 6,
        })
        self.assertEqual(rec.score_risk, 6)
        # 工程 → 技術分數
        self.Score.create({
            "feasibility_id": rec.id,
            "department": "engineering",
            "reviewer_id": self.user.id,
            "score": 9,
        })
        self.assertEqual(rec.score_technical, 9)
        # 修改分數：同步
        line = rec.score_ids.filtered(lambda s: s.department == "sales")
        line.write({"score": 3})
        self.assertEqual(rec.score_risk, 3)

    def test_03_score_unlink_resets_main_field(self):
        """刪除 score 後主檔對應欄位歸零。"""
        rec = self._make_feasibility()
        line = self.Score.create({
            "feasibility_id": rec.id,
            "department": "qa",
            "reviewer_id": self.user.id,
            "score": 8,
        })
        self.assertEqual(rec.score_regulatory, 8)
        line.unlink()
        self.assertEqual(rec.score_regulatory, 0)

    def test_04_score_out_of_range(self):
        """score=11 / score=-1 應拋 ValidationError。"""
        rec = self._make_feasibility()
        with self.assertRaises(ValidationError):
            self.Score.create({
                "feasibility_id": rec.id,
                "department": "production",
                "reviewer_id": self.user.id,
                "score": 11,
            })
        with self.assertRaises(ValidationError):
            self.Score.create({
                "feasibility_id": rec.id,
                "department": "production",
                "reviewer_id": self.user.id,
                "score": -1,
            })
