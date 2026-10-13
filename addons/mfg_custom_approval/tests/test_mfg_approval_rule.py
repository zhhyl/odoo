# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestMfgApprovalRule(BaseCommon):
    """測試簽核規則的 domain 匹配與基本 CRUD。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.TestModel = cls.env["mfg_custom.approval.test.model"]

    def _make_rule(self, name, sequence=10, domain="", steps=None):
        vals = {
            "name": name,
            "sequence": sequence,
            "res_model": "mfg_custom.approval.test.model",
            "domain": domain,
        }
        if steps:
            vals["step_ids"] = [
                Command.create(s) for s in steps
            ]
        return self.Rule.create(vals)

    def test_01_rule_match_by_domain_high_amount(self):
        """金額大於 100 萬的單據應命中「大額」規則。"""
        self._make_rule("小額", sequence=10, domain="[('amount_total', '<=', 1000000)]")
        big = self._make_rule(
            "大額",
            sequence=20,
            domain="[('amount_total', '>', 1000000)]",
        )
        rec_high = self.TestModel.create({"amount_total": 2000000.0})
        rec_low = self.TestModel.create({"amount_total": 500.0})
        self.assertEqual(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec_high),
            big,
        )
        self.assertNotEqual(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec_low),
            big,
        )

    def test_02_rule_match_no_domain_catches_all(self):
        """無 domain 的規則應匹配所有同 model 的單據。"""
        catch_all = self._make_rule("全部", sequence=10, domain="")
        rec = self.TestModel.create({"amount_total": 1.0})
        self.assertEqual(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec),
            catch_all,
        )

    def test_03_invalid_domain_raises(self):
        """語法錯誤的 domain 應在建檔時 raise。"""
        with self.assertRaises(ValidationError):
            self._make_rule("壞規則", domain="[('amount_total', =, 1)]")

    def test_04_rule_sequence_picks_first_match(self):
        """sequence 較小的規則優先匹配。"""
        r1 = self._make_rule("r1", sequence=5, domain="[('amount_total', '>=', 0)]")
        r2 = self._make_rule("r2", sequence=20, domain="[('amount_total', '>=', 0)]")
        rec = self.TestModel.create({"amount_total": 1.0})
        self.assertEqual(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec),
            r1,
        )
        self.assertNotEqual(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec),
            r2,
        )
