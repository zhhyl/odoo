# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.mrp.tests.common import TestMrpCommon


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgMoYieldReport(TestMrpCommon):
    """測試 MO 含良率總覽 PDF report 的資料收集。"""

    # Odoo 20 的測試框架會以受限使用者執行測試（_test_user_groups），
    # 此處需補齊本模組測試會用到的權限（讀寫 MO / BOM / 品檢單）。
    _test_user_groups = (
        'mrp.group_mrp_user',
        'mrp.group_mrp_manager',
        'mfg_custom_base.group_user',
        'mfg_custom_base.group_manager',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report_model = cls.env[
            "report.mfg_custom_production_stage.mfg_mo_yield_report_document"
        ]

    # ---- 01 _get_report_values 字典完整性 ------------------

    def test_01_report_values_contains_required_keys(self):
        """`_get_report_values` 應回傳樣板所需的所有 key。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 3.0,
            },
        )
        values = self.report_model._get_report_values(mo.ids)
        self.assertEqual(values["doc_ids"], mo.ids)
        self.assertEqual(values["doc_model"], "mrp.production")
        self.assertEqual(set(values["docs"].ids), set(mo.ids))
        self.assertIn("scrap_data", values)
        self.assertIn(mo.id, values["scrap_data"])
        # scrap 字典對該 MO 的 recordset 應為空 recordset（此情境無報廢）
        self.assertFalse(values["scrap_data"][mo.id])

    # ---- 02 scrap_data 收集 -----------------------------------

    def test_02_scrap_data_collected(self):
        """`is_scrap=True` 且關聯此 MO 的 stock.move 應被收集進 scrap_data。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 5.0,
            },
        )
        scrap_move = self.env["stock.move"].create(
            {
                "product_id": self.product_5.id,
                "uom_id": self.product_5.uom_id.id,
                "raw_material_production_id": mo.id,
                "is_scrap": True,
                "state": "done",
                "product_uom_qty": 1.0,
            },
        )
        values = self.report_model._get_report_values(mo.ids)
        self.assertIn(scrap_move.id, values["scrap_data"][mo.id].ids)

    def test_03_scrap_data_excludes_other_mo(self):
        """其他 MO 的 scrap move 不應混入 scrap_data。"""
        mo_a = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 2.0,
            },
        )
        mo_b = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 2.0,
            },
        )
        scrap_b = self.env["stock.move"].create(
            {
                "product_id": self.product_5.id,
                "uom_id": self.product_5.uom_id.id,
                "raw_material_production_id": mo_b.id,
                "is_scrap": True,
                "state": "done",
                "product_uom_qty": 1.0,
            },
        )
        values = self.report_model._get_report_values([mo_a.id, mo_b.id])
        self.assertFalse(values["scrap_data"][mo_a.id])
        self.assertIn(scrap_b.id, values["scrap_data"][mo_b.id].ids)

    # ---- 03 format_qty -----------------------------------------

    def test_04_format_qty(self):
        """`_format_qty` 應回傳帶 UoM 名稱字串。"""
        formatted = self.report_model._format_qty(12.5, self.uom_unit)
        self.assertIn("12.50", formatted)
        self.assertIn(self.uom_unit.name, formatted)

    # ---- 04 _render_pass 結論 ---------------------------------

    def test_05_render_pass_above_expected(self):
        """done 且實際 >= 期望 → PASS / text-success。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
                "state": "done",
                # Odoo 20 的 uom_id 為必填且僅在 draft 狀態由 _compute_uom_id 帶入，
                # 直接以 done 狀態建立時必須自行指定，否則會產生 NOT NULL 違規。
                "uom_id": self.product_4.uom_id.id,
            },
        )
        # 直接寫欄位避免 full warehouse 流程
        mo.write(
            {
                "mfg_custom_yield_rate": 99.0,
                "mfg_custom_expected_yield_rate": 95.0,
            },
        )
        result = self.report_model._render_pass(mo)
        self.assertEqual(result["label"], "PASS")
        self.assertEqual(result["klass"], "text-success")

    def test_06_render_pass_below_expected(self):
        """done 且實際 < 期望 → FAIL / text-danger。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
                "state": "done",
                # 同 test_05：done 狀態建立時 uom_id 不會被自動計算，須自行指定。
                "uom_id": self.product_4.uom_id.id,
            },
        )
        mo.write(
            {
                "mfg_custom_yield_rate": 80.0,
                "mfg_custom_expected_yield_rate": 95.0,
            },
        )
        result = self.report_model._render_pass(mo)
        self.assertEqual(result["label"], "FAIL")
        self.assertEqual(result["klass"], "text-danger")

    def test_07_render_pass_when_not_done(self):
        """非 done 狀態 → N/A。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
            },
        )
        result = self.report_model._render_pass(mo)
        self.assertEqual(result["label"], "N/A")
