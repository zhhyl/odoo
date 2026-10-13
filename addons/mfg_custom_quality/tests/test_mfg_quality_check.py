# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgQualityCheck(TransactionCase):
    """測試 :class:`MfgQualityCheck` 之生命週期與檢項帶入邏輯。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Check = cls.env["mfg_custom.quality.check"]
        cls.CheckLine = cls.env["mfg_custom.quality.check.line"]
        cls.Point = cls.env["mfg_custom.quality.point"]
        cls.PointLine = cls.env["mfg_custom.quality.point.line"]
        cls.Product = cls.env["product.product"]
        cls.product = cls.Product.create(
            {"name": "QC-Test Product", "type": "product"},
        )
        cls.point = cls.Point.create(
            {
                "name": "QC 規格",
                "product_id": cls.product.id,
                "sample_qty": 2,
            },
        )
        cls.line_length = cls.PointLine.create(
            {
                "point_id": cls.point.id,
                "name": "長度",
                "min_value": 10.0,
                "max_value": 11.0,
            },
        )
        cls.line_width = cls.PointLine.create(
            {
                "point_id": cls.point.id,
                "name": "寬度",
                "min_value": 4.0,
                "max_value": 5.0,
            },
        )
        cls.line_visual = cls.PointLine.create(
            {
                "point_id": cls.point.id,
                "name": "外觀（關鍵項）",
                "is_critical": True,
            },
        )

    def _new_check(self, **extra):
        vals = {
            "point_id": self.point.id,
            "product_id": self.product.id,
            "qty_to_check": 2.0,
        }
        vals.update(extra)
        return self.Check.create(vals)

    def test_check_create_assigns_sequence(self):
        """建立品檢單會自動取號。"""
        check = self._new_check()
        self.assertNotEqual(check.name, "New")
        self.assertTrue(check.name)
        self.assertEqual(check.state, "draft")

    def test_action_start_pulls_point_lines(self):
        """action_start 應將 point 的檢項帶入為 check_line_ids。"""
        check = self._new_check()
        check.action_start()
        self.assertEqual(check.state, "in_progress")
        self.assertEqual(len(check.check_line_ids), 3)
        self.assertEqual(
            sorted(check.check_line_ids.mapped("name")),
            sorted(["長度", "寬度", "外觀（關鍵項）"]),
        )

    def test_action_start_requires_point_lines(self):
        """品檢點沒檢項時 action_start 應拋 UserError。"""
        empty_point = self.Point.create({"name": "空白規格", "product_id": self.product.id})
        check = self.Check.create(
            {
                "point_id": empty_point.id,
                "product_id": self.product.id,
                "qty_to_check": 1.0,
            },
        )
        with self.assertRaises(UserError):
            check.action_start()

    def test_action_start_only_once(self):
        """state 不在 draft 時 action_start 應拋錯。"""
        check = self._new_check()
        check.action_start()
        with self.assertRaises(UserError):
            check.action_start()

    def test_critical_failure_blocks_pass(self):
        """關鍵項 fail → action_pass 拋 UserError。"""
        check = self._new_check()
        check.action_start()
        # 填量測結果：長度 ok、寬度 ok、外觀 fail（關鍵項）
        for line in check.check_line_ids:
            if line.name == "外觀（關鍵項）":
                line.write({"measured_value": 0.0, "result": "fail"})
            else:
                line.write({"measured_value": 10.5, "result": "ok"})
        with self.assertRaises(UserError):
            check.action_pass()
        self.assertEqual(check.state, "in_progress")

    def test_pending_line_blocks_pass(self):
        """有檢項仍為 pending → action_pass 拋錯。"""
        check = self._new_check()
        check.action_start()
        # 全部填為 pending（不實際填 result）
        for line in check.check_line_ids:
            self.assertEqual(line.result, "pending")
        with self.assertRaises(UserError):
            check.action_pass()

    def test_action_pass_full_flow(self):
        """全部 ok → action_pass 將 state 改為 passed。"""
        check = self._new_check()
        check.action_start()
        for line in check.check_line_ids:
            line.write({"measured_value": 10.5, "result": "ok"})
        check.action_pass()
        self.assertEqual(check.state, "passed")
        self.assertFalse(check.failure_reason)

    def test_action_fail_requires_reason(self):
        """action_fail 必須有 failure_reason。"""
        check = self._new_check()
        check.action_start()
        for line in check.check_line_ids:
            line.write({"measured_value": 0.0, "result": "fail"})
        with self.assertRaises(UserError):
            check.action_fail()
        check.failure_reason = "<p>尺寸超差</p>"
        check.action_fail()
        self.assertEqual(check.state, "failed")

    def test_action_fail_passed_reason(self):
        """action_fail 接受 reason 參數並寫入欄位。"""
        check = self._new_check()
        check.action_start()
        for line in check.check_line_ids:
            line.write({"measured_value": 0.0, "result": "fail"})
        check.action_fail(reason="<p>自動判定</p>")
        self.assertEqual(check.state, "failed")
        self.assertIn("自動判定", check.failure_reason)

    def test_action_conditional(self):
        """draft / in_progress 均可改判為特採。"""
        check = self._new_check()
        check.action_start()
        check.action_conditional()
        self.assertEqual(check.state, "conditional")

    def test_action_cancel(self):
        """draft / in_progress 可取消；已結案不可取消。"""
        check = self._new_check()
        check.action_cancel()
        self.assertEqual(check.state, "cancelled")

        # 已結案：無法取消
        check2 = self._new_check()
        check2.action_start()
        for line in check2.check_line_ids:
            line.write({"measured_value": 10.5, "result": "ok"})
        check2.action_pass()
        with self.assertRaises(UserError):
            check2.action_cancel()

    def test_state_transitions(self):
        """完整狀態流：draft → in_progress → passed → 不可改 draft。"""
        check = self._new_check()
        self.assertEqual(check.state, "draft")
        check.action_start()
        self.assertEqual(check.state, "in_progress")
        for line in check.check_line_ids:
            line.write({"measured_value": 10.5, "result": "ok"})
        check.action_pass()
        self.assertEqual(check.state, "passed")
        # passed 後不可再 pass / fail / cancel
        with self.assertRaises(UserError):
            check.action_pass()
        with self.assertRaises(UserError):
            check.action_fail()

    def test_qty_to_check_validation(self):
        """qty_to_check <= 0 應拋 ValidationError。"""
        check = self._new_check(qty_to_check=1.0)
        with self.assertRaises(ValidationError):
            check.write({"qty_to_check": -1.0})
        with self.assertRaises(ValidationError):
            check.write({"qty_to_check": 0.0})

    def test_restart_after_start_repopulates(self):
        """action_reset_to_draft 回 draft，再次 start 應重帶入檢項。"""
        check = self._new_check()
        check.action_start()
        check.action_reset_to_draft()
        self.assertEqual(check.state, "draft")
        check.action_start()
        self.assertEqual(len(check.check_line_ids), 3)

    def test_failure_creates_issue_placeholder(self):
        """改善單欄位只是 ``mfg_custom.issue`` 的 Many2one，目前不自動建立。

        待 ``mfg_custom_issue`` 模組上線後，本測試可改為：
        1. 透過 ``self.env['mfg_custom.issue'].create(...)`` 建立 issue
        2. 在 ``action_fail()`` 內呼叫 ``_create_corrective_action`` 自動建立
        """
        check = self._new_check()
        check.action_start()
        for line in check.check_line_ids:
            line.write({"measured_value": 0.0, "result": "fail"})
        # 目前欄位為可選，留空即可作為 record
        self.assertFalse(check.corrective_action_id)
        check.failure_reason = "<p>留待改善</p>"
        check.action_fail()
        self.assertEqual(check.state, "failed")
        # 未來版本會自動建立，這裡只驗證不爆炸即可
        self.assertFalse(check.corrective_action_id)
