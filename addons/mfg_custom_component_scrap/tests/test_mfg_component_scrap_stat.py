# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.mrp.tests.common import TestMrpCommon


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgComponentScrapStat(TestMrpCommon):
    """測試 BOM 子件報廢統計模型。

    涵蓋：
    * 模型可被 ORM 載入
    * ``init()`` 可建立 SQL view
    * 建立 scrap 資料後，可依零件 / BOM / MO 搜尋
    * 報廢率、有效得料率公式正確
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 重建一個乾淨 BOM：1 件成品 = 2 件原料 A + 1 件原料 B
        cls.product_finish = cls.env["product.product"].create(
            {
                "name": "ScrapStatFinish",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.product_comp_a = cls.env["product.product"].create(
            {
                "name": "ScrapStatCompA",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.product_comp_b = cls.env["product.product"].create(
            {
                "name": "ScrapStatCompB",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.bom_scrap = cls.env["mrp.bom"].create(
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

        # 報廢原因標籤（為了測試 primary_reason_tag_id）
        cls.reason_damage = cls.env["stock.scrap.reason.tag"].create(
            {"name": "破損"},
        )
        cls.reason_defect = cls.env["stock.scrap.reason.tag"].create(
            {"name": "不良"},
        )

    def _make_confirmed_mo(self, qty=10.0):
        """建立並 confirm 一張 MO，回傳 record。"""
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.product_finish
        mo_form.bom_id = self.bom_scrap
        mo_form.product_qty = qty
        mo = mo_form.save()
        mo.action_confirm()
        return mo

    def _make_scrap_move(self, mo, component, qty, reason_tags=None):
        """建立一筆 ``stock.move(is_scrap=True, state='done')`` 報廢單。"""
        vals = {
            "name": f"Scrap-{component.name}",
            "product_id": component.id,
            "product_uom": component.uom_id.id,
            "product_uom_qty": qty,
            "product_qty": qty,
            "raw_material_production_id": mo.id,
            "is_scrap": True,
            "state": "done",
            "location_id": mo.location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_stock").id,
        }
        if reason_tags is not None:
            vals["scrap_reason_tag_ids"] = [Command.set(reason_tags.ids)]
        return self.env["stock.move"].create(vals)

    # ---- 01 模型載入 -----------------------------------------------------

    def test_01_model_loads(self):
        """模型可被 ORM 載入，且為 SQL view。"""
        model = self.env["mfg_custom.component.scrap.stat"]
        self.assertTrue(model)
        self.assertFalse(
            model._auto,
            "mfg_custom.component.scrap.stat 應為 SQL view（_auto=False）",
        )
        # 確保 _table 已註冊
        self.assertTrue(model._table)

    def test_02_model_has_expected_fields(self):
        """關鍵欄位已宣告。"""
        model = self.env["mfg_custom.component.scrap.stat"]
        expected = {
            "scrap_move_id",
            "production_id",
            "component_product_id",
            "finished_product_id",
            "bom_id",
            "bom_line_id",
            "scrapped_qty",
            "standard_qty",
            "actual_consumed_qty",
            "scrap_rate",
            "effective_yield",
            "scrap_date",
            "scrap_user_id",
            "scrap_reason_tag_ids",
            "primary_reason_tag_id",
        }
        missing = expected - set(model._fields)
        self.assertFalse(missing, f"缺少欄位：{missing}")

    # ---- 02 SQL view 建立 ------------------------------------------------

    def test_10_sql_view_creates(self):
        """init() 可建立 SQL view，不報錯。"""
        model = self.env["mfg_custom.component.scrap.stat"]
        # drop + create
        model.init()
        # 確認 PG 中真的有 view
        self.env.cr.execute(
            "SELECT 1 FROM pg_views WHERE viewname = %s",
            (model._table,),
        )
        self.assertTrue(
            self.env.cr.fetchone(),
            f"SQL view {model._table} 不存在",
        )

    # ---- 03 查詢 + 公式 --------------------------------------------------

    def test_20_scrap_move_visible_in_stat(self):
        """建立 scrap 資料後，stat 模型可查到。"""
        mo = self._make_confirmed_mo(qty=10.0)
        # 標準用量 = 2.0 * (10/1) = 20
        self._make_scrap_move(mo, self.product_comp_a, qty=2.0)

        # 重建 view（因為我們直接 create scrap move，沒有觸發 ORM 快取）
        self.env["mfg_custom.component.scrap.stat"].init()

        stats = self.env["mfg_custom.component.scrap.stat"].search(
            [("production_id", "=", mo.id)],
        )
        self.assertEqual(len(stats), 1, "應查到 1 筆報廢記錄")
        stat = stats[0]
        self.assertEqual(stat.component_product_id, self.product_comp_a)
        self.assertEqual(stat.scrapped_qty, 2.0)
        self.assertEqual(stat.standard_qty, 20.0)
        # scrap_rate = 2 / 20 * 100 = 10
        self.assertAlmostEqual(stat.scrap_rate, 10.0, places=2)
        # effective_yield = 100 - 10 = 90
        self.assertAlmostEqual(stat.effective_yield, 90.0, places=2)

    def test_21_scrap_rate_capped_when_no_standard(self):
        """當 BOM 子件不存在（BOM 沒抓到原料）時，scrap_rate = 0，yield = 100。"""
        mo = self._make_confirmed_mo(qty=5.0)
        # 故意報廢一個不在 BOM 內的產品
        orphan = self.env["product.product"].create(
            {
                "name": "ScrapStatOrphan",
                "type": "consu",
                "is_storable": True,
            },
        )
        self._make_scrap_move(mo, orphan, qty=3.0)

        self.env["mfg_custom.component.scrap.stat"].init()
        stat = self.env["mfg_custom.component.scrap.stat"].search(
            [("production_id", "=", mo.id), ("component_product_id", "=", orphan.id)],
        )
        self.assertEqual(len(stat), 1)
        # BOM 沒對應的 bom_line → standard_qty=0 → 報廢率 0、有效得料率 100
        self.assertEqual(stat.standard_qty, 0.0)
        self.assertEqual(stat.scrap_rate, 0.0)
        self.assertEqual(stat.effective_yield, 100.0)

    def test_22_actual_consumed_qty(self):
        """實際消耗：同 MO × 同產品的非報廢 stock.move(state='done') 加總。"""
        mo = self._make_confirmed_mo(qty=10.0)
        # 模擬消耗 5 件原料 A（非報廢）
        consume_move = self.env["stock.move"].create(
            {
                "name": "Consume-A",
                "product_id": self.product_comp_a.id,
                "product_uom": self.product_comp_a.uom_id.id,
                "product_uom_qty": 5.0,
                "product_qty": 5.0,
                "raw_material_production_id": mo.id,
                "is_scrap": False,
                "state": "done",
                "location_id": mo.location_src_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_stock").id,
            },
        )
        self.assertTrue(consume_move)
        # 建立 1 件 scrap
        self._make_scrap_move(mo, self.product_comp_a, qty=1.0)

        self.env["mfg_custom.component.scrap.stat"].init()
        stats = self.env["mfg_custom.component.scrap.stat"].search(
            [
                ("production_id", "=", mo.id),
                ("component_product_id", "=", self.product_comp_a.id),
            ],
        )
        # 應只有 1 筆（只有 scrap 會被收進 stat）
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats.actual_consumed_qty, 5.0)

    def test_23_scrap_reason_tag_related(self):
        """scrap_reason_tag_ids 透過 related 從 scrap_move_id 取得。"""
        mo = self._make_confirmed_mo(qty=10.0)
        scrap = self._make_scrap_move(
            mo,
            self.product_comp_b,
            qty=1.0,
            reason_tags=self.reason_damage | self.reason_defect,
        )
        self.env["mfg_custom.component.scrap.stat"].init()
        stat = self.env["mfg_custom.component.scrap.stat"].search(
            [("scrap_move_id", "=", scrap.id)],
        )
        self.assertEqual(len(stat), 1)
        # m2m tags
        self.assertEqual(
            set(stat.scrap_reason_tag_ids.ids),
            {self.reason_damage.id, self.reason_defect.id},
        )
        # primary = 第一個
        self.assertIn(
            stat.primary_reason_tag_id,
            self.reason_damage | self.reason_defect,
        )

    def test_24_search_by_component(self):
        """依零件搜尋。"""
        mo = self._make_confirmed_mo(qty=10.0)
        self._make_scrap_move(mo, self.product_comp_a, qty=1.0)
        self._make_scrap_move(mo, self.product_comp_b, qty=2.0)
        self.env["mfg_custom.component.scrap.stat"].init()

        only_a = self.env["mfg_custom.component.scrap.stat"].search(
            [("component_product_id", "=", self.product_comp_a.id)],
        )
        only_b = self.env["mfg_custom.component.scrap.stat"].search(
            [("component_product_id", "=", self.product_comp_b.id)],
        )
        self.assertEqual(len(only_a), 1)
        self.assertEqual(len(only_b), 1)
        self.assertEqual(only_a.scrapped_qty, 1.0)
        self.assertEqual(only_b.scrapped_qty, 2.0)
