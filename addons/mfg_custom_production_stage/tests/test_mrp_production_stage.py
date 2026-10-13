# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import Form, tagged

from odoo.addons.mrp.tests.common import TestMrpCommon


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMrpProductionStage(TestMrpCommon):
    """測試 mfg_custom_production_stage 模組的階段變更與預設邏輯。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.StageLog = cls.env["mrp.production.stage.log"]

    # ---- 01 預設值 ---------------------------------------------------------

    def test_01_default_stage_is_mass(self):
        """新建 MO 不指定 stage 時，預設為 'mass'。"""
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.product_4
        mo_form.bom_id = self.bom_1
        mo = mo_form.save()
        self.assertEqual(mo.mfg_custom_production_stage, "mass")

    def test_02_bom_default_stage_propagates(self):
        """BOM 預設階段為 pilot 時，新建 MO 自動帶入 pilot。"""
        self.bom_1.write({"mfg_custom_default_production_stage": "pilot"})
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.product_4
        mo_form.bom_id = self.bom_1
        mo = mo_form.save()
        self.assertEqual(mo.mfg_custom_production_stage, "pilot")

    def test_03_explicit_stage_overrides_bom(self):
        """vals 明確指定 stage 時，不被 BOM 預設覆寫。"""
        self.bom_1.write({"mfg_custom_default_production_stage": "pilot"})
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
                "mfg_custom_production_stage": "sample",
            },
        )
        self.assertEqual(mo.mfg_custom_production_stage, "sample")

    # ---- 02 階段變更寫日誌 -----------------------------------------------

    def test_10_stage_change_logged(self):
        """變更 stage 應新增一筆 stage.log。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
            },
        )
        self.assertEqual(mo.mfg_custom_stage_log_count, 0)
        mo.action_change_stage("pilot", reason="PP 試量產")
        self.assertEqual(mo.mfg_custom_stage_log_count, 1)
        log = mo.mfg_custom_stage_log_ids[0]
        self.assertEqual(log.from_stage, "mass")
        self.assertEqual(log.to_stage, "pilot")
        self.assertEqual(log.reason, "PP 試量產")
        self.assertEqual(log.user_id, self.env.user)

    def test_11_stage_change_same_value_no_log(self):
        """設定為相同 stage 不應寫日誌。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
                "mfg_custom_production_stage": "mass",
            },
        )
        mo.action_change_stage("mass")
        self.assertEqual(mo.mfg_custom_stage_log_count, 0)

    def test_12_stage_change_invalid_value_raises(self):
        """無效 stage 字串應丟 UserError。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
            },
        )
        with self.assertRaises(Exception):
            mo.action_change_stage("invalid_stage")

    def test_13_stage_change_full_path(self):
        """樣品 → 小批量 → 量產 完整升版路徑。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_4.id,
                "bom_id": self.bom_1.id,
                "product_qty": 1.0,
                "mfg_custom_production_stage": "sample",
            },
        )
        mo.action_change_stage("pilot", reason="PP 試量產")
        mo.action_change_stage("mass", reason="客戶下單")
        self.assertEqual(mo.mfg_custom_production_stage, "mass")
        self.assertEqual(mo.mfg_custom_stage_log_count, 2)
        # 最新一筆在最前面（_order = timestamp desc）
        latest = mo.mfg_custom_stage_log_ids[0]
        self.assertEqual(latest.from_stage, "pilot")
        self.assertEqual(latest.to_stage, "mass")

    # ---- 03 樣品單關聯欄位（不啟用 plm_custom_feasibility） ---------------

    def test_20_sample_request_field_exists(self):
        """欄位 mfg_custom_sample_request_id 已建立（即使目標模組未裝）。"""
        field = self.env["mrp.production"]._fields.get("mfg_custom_sample_request_id")
        self.assertTrue(field, "欄位 mfg_custom_sample_request_id 應存在")
        self.assertEqual(field.comodel_name, "plm_custom.feasibility")
        # 此時 ref 應不可解析（模組未安裝）
        # 注意：Odoo 不會阻擋 comodel_name 寫入已宣告的字串，僅在實際 click 時才會錯。
