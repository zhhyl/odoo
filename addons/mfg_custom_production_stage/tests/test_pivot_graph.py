# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.mrp.tests.common import TestMrpCommon


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMrpProductionPivotGraph(TestMrpCommon):
    """測試 mrp.production 的良率分析 pivot / graph view 可正確載入並彙總資料。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # ---- 1) 成品 + 兩個 component，建立 BOM：1 件成品 = 3 件原料 ----
        cls.product_finish = cls.env["product.product"].create(
            {
                "name": "YieldTrendFinish",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.product_comp_a = cls.env["product.product"].create(
            {
                "name": "YieldTrendCompA",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.product_comp_b = cls.env["product.product"].create(
            {
                "name": "YieldTrendCompB",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.bom_yield = cls.env["mrp.bom"].create(
            {
                "product_id": cls.product_finish.id,
                "product_tmpl_id": cls.product_finish.product_tmpl_id.id,
                "product_qty": 1.0,
                "uom_id": cls.uom_unit.id,
                "type": "normal",
                "bom_line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product_comp_a.id,
                            "product_qty": 2.0,
                        },
                    ),
                    Command.create(
                        {
                            "product_id": cls.product_comp_b.id,
                            "product_qty": 1.0,
                        },
                    ),
                ],
            },
        )

    # ------------------------------------------------------------------
    # 工具方法：建立一個 done 的 MO，並設定產量/原料消耗以得到目標 yield
    # ------------------------------------------------------------------

    def _make_done_mo(self, qty=10.0, produced=10.0, stage="mass"):
        """建一個 done 的 MO，並依 produced / 原料消耗回算 yield。"""
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.product_finish
        mo_form.bom_id = self.bom_yield
        mo_form.product_qty = qty
        mo_form.mfg_custom_production_stage = stage
        mo = mo_form.save()
        mo.action_confirm()

        for move in mo.move_raw_ids:
            move.write(
                {
                    "state": "done",
                    "quantity": mo.product_qty * 3,  # 30 件原料（10 * (2+1)）
                },
            )
        finished = mo.move_finished_ids.filtered(
            lambda m: m.product_id == mo.product_id
        )
        finished.write({"state": "done", "quantity": produced})
        mo.write({"state": "done"})
        mo._compute_mfg_custom_yield_rate()
        return mo

    # ------------------------------------------------------------------
    # 01 建立 3 個不同階段 + 不同 yield 的 done MO
    # ------------------------------------------------------------------

    def test_01_create_three_done_mos(self):
        """建立 3 個 done MO（樣品 / 小批量 / 量產），yield 各不同。"""
        mo_sample = self._make_done_mo(qty=10.0, produced=5.0, stage="sample")
        mo_pilot = self._make_done_mo(qty=10.0, produced=8.0, stage="pilot")
        mo_mass = self._make_done_mo(qty=10.0, produced=10.0, stage="mass")

        # 預期 yield：5/30=16.67, 8/30=26.67, 10/30=33.33
        self.assertAlmostEqual(mo_sample.mfg_custom_yield_rate, 16.67, places=2)
        self.assertAlmostEqual(mo_pilot.mfg_custom_yield_rate, 26.67, places=2)
        self.assertAlmostEqual(mo_mass.mfg_custom_yield_rate, 33.33, places=2)

        # 三個 MO 都應為 done 狀態
        self.assertEqual(
            (mo_sample | mo_pilot | mo_mass).mapped("state"),
            ["done", "done", "done"],
        )

    # ------------------------------------------------------------------
    # 02 pivot view 可載入（fetch_fields 不丟 exception）
    # ------------------------------------------------------------------

    def test_02_pivot_view_loads(self):
        """良率分析 pivot view 應可成功載入，欄位都存在於 model。"""
        view = self.env.ref(
            "mfg_custom_production_stage.mrp_production_view_pivot_yield_analysis"
        )
        self.assertTrue(view, "pivot view 應已被宣告於 XML")
        self.assertEqual(view.type, "pivot")
        self.assertEqual(view.model, "mrp.production")

        # 取實際 arch 並確保欄位名正確
        arch = view.arch_db
        for expected_field in (
            "mfg_custom_production_stage",
            "date_finished",
            "product_id",
            "state",
            "mfg_custom_yield_rate",
            "product_uom_qty",
            "qty_producing",
        ):
            self.assertIn(expected_field, arch)

    # ------------------------------------------------------------------
    # 03 graph view 可載入
    # ------------------------------------------------------------------

    def test_03_graph_view_loads(self):
        """得料率走勢圖 graph view 應可成功載入。"""
        view = self.env.ref(
            "mfg_custom_production_stage.mrp_production_view_graph_yield_trend"
        )
        self.assertTrue(view, "graph view 應已被宣告於 XML")
        self.assertEqual(view.type, "graph")
        self.assertEqual(view.model, "mrp.production")

        arch = view.arch_db
        # line chart、月份 row、yield measure 都要在 arch 內
        self.assertIn('type="line"', arch)
        self.assertIn("date_finished", arch)
        self.assertIn("mfg_custom_yield_rate", arch)

    # ------------------------------------------------------------------
    # 04 良率分析 action 存在 + view_mode 正確
    # ------------------------------------------------------------------

    def test_04_yield_analysis_action(self):
        """新增的良率分析 action 應存在，且 view_mode 含 graph/pivot。"""
        action = self.env.ref(
            "mfg_custom_production_stage.mrp_production_action_yield_analysis"
        )
        self.assertTrue(action, "良率分析 action 應已宣告")
        self.assertEqual(action.res_model, "mrp.production")
        view_modes = action.view_mode.split(",")
        self.assertIn("graph", view_modes)
        self.assertIn("pivot", view_modes)
        # 預設啟用 filter_done
        self.assertEqual(action.context.get("search_default_filter_done"), 1)

    # ------------------------------------------------------------------
    # 05 原 group_by_stage action 不再含 graph/pivot
    # ------------------------------------------------------------------

    def test_05_group_by_stage_action_still_works(self):
        """原生產階段分析 action 應仍可用，只是移除 graph/pivot。"""
        action = self.env.ref(
            "mfg_custom_production_stage.mrp_production_action_group_by_stage"
        )
        self.assertTrue(action)
        view_modes = action.view_mode.split(",")
        self.assertNotIn("graph", view_modes)
        self.assertNotIn("pivot", view_modes)
