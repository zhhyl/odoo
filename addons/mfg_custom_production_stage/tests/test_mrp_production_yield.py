# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.mrp.tests.common import TestMrpCommon


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMrpProductionYield(TestMrpCommon):
    """測試得料率計算與 cron 行為。"""

    # Odoo 20 的測試框架會以受限使用者執行測試（_test_user_groups），
    # 此處需補齊本模組測試會用到的權限：
    # - mfg_custom_base.group_user：可讀取 mfg_custom.quality.check
    # - base.group_system：ir.cron 僅系統管理員可讀（檢查 cron 是否已建立）
    _test_user_groups = (
        'mrp.group_mrp_user',
        'mrp.group_mrp_manager',
        'mfg_custom_base.group_user',
        'mfg_custom_base.group_manager',
        'base.group_system',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 重建一個乾淨的 BOM：1 件成品 = 2 件原料
        cls.product_finish = cls.env["product.product"].create(
            {
                "name": "YieldFinish",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.product_comp_a = cls.env["product.product"].create(
            {
                "name": "YieldCompA",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.product_comp_b = cls.env["product.product"].create(
            {
                "name": "YieldCompB",
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

    def _set_raw_moves_done(self, mo, factor=1.0):
        """把原料 move 標記為 done，數量依各原料的 BOM 需求（可乘 factor 模擬超耗）。"""
        for move in mo.move_raw_ids:
            move.write({
                "state": "done",
                "quantity": (move.product_uom_qty or 0.0) * factor,
            })

    def _make_confirmed_mo(self, qty=10.0):
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.product_finish
        mo_form.bom_id = self.bom_yield
        mo_form.product_qty = qty
        mo = mo_form.save()
        mo.action_confirm()
        return mo

    # ---- 01 未 done 時 yield = 0 -----------------------------------------

    def test_01_yield_zero_when_draft(self):
        """MO 為 draft 時，得料率應為 0。"""
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_finish.id,
                "bom_id": self.bom_yield.id,
                "product_qty": 10.0,
            },
        )
        self.assertEqual(mo.mfg_custom_yield_rate, 0.0)

    def test_02_yield_zero_when_confirmed(self):
        """MO 為 confirmed 時，得料率應為 0。"""
        mo = self._make_confirmed_mo()
        self.assertEqual(mo.state, "confirmed")
        self.assertEqual(mo.mfg_custom_yield_rate, 0.0)

    # ---- 02 done 後 yield 計算 ------------------------------------------

    def test_03_yield_computed_when_done(self):
        """MO 為 done 時，依實際投入原料換算理論產出並計算得料率。

        情境：計劃產 10 件，原料配比 2:1（每件成品需 3 件原料）；
        依計劃投入 30 件原料 → 理論產出 10 件，實際只產 9 件
        → 得料率 = 9 / 10 * 100 = 90%
        """
        mo = self._make_confirmed_mo(qty=10.0)
        # 直接寫入 state / 庫存動作以避免 full warehouse 流程：
        # 1) 把 move_raw_ids 標 done，數量依 BOM 需求（20 + 10 = 30）
        self._set_raw_moves_done(mo)
        # 2) 模擬產出：move_finished_ids 中與成品同 id 的標 done 且 quantity 9
        finished = mo.move_finished_ids.filtered(
            lambda m: m.product_id == mo.product_id
        )
        finished.write({"state": "done", "quantity": 9.0})
        # 3) 把 MO 標 done
        mo.write({"state": "done"})
        # 重算（手動觸發 compute 鏈）
        mo._compute_mfg_custom_yield_rate()
        # 期望得料率 = 9 / 10 * 100 = 90
        self.assertAlmostEqual(mo.mfg_custom_yield_rate, 90.0, places=2)

    def test_04_yield_full_when_perfect(self):
        """完美生產：計劃 10 件、產 10 件、原料 30 → yield = 100。"""
        mo = self._make_confirmed_mo(qty=10.0)
        # 依 BOM 需求投入原料（20 + 10 = 30 件）→ 理論產出 10 件
        self._set_raw_moves_done(mo)
        finished = mo.move_finished_ids.filtered(
            lambda m: m.product_id == mo.product_id
        )
        finished.write({"state": "done", "quantity": 10.0})
        mo.write({"state": "done"})
        mo._compute_mfg_custom_yield_rate()
        self.assertEqual(mo.mfg_custom_yield_rate, 100.0)

    def test_05_yield_capped_at_100(self):
        """得料率上限為 100（即使公式算出 >100）。"""
        mo = self._make_confirmed_mo(qty=10.0)
        # 原料只投入 20（10 + 10），依配比理論產出 15 件，實際產 10 件
        for move in mo.move_raw_ids:
            move.write({"state": "done", "quantity": 10.0})
        finished = mo.move_finished_ids.filtered(
            lambda m: m.product_id == mo.product_id
        )
        finished.write({"state": "done", "quantity": 10.0})
        mo.write({"state": "done"})
        mo._compute_mfg_custom_yield_rate()
        # 重點：上限 100，絕不超過
        self.assertLessEqual(mo.mfg_custom_yield_rate, 100.0)
        self.assertGreater(mo.mfg_custom_yield_rate, 0.0)

    # ---- 03 cron 重算 -----------------------------------------------------

    def test_10_cron_recompute_done_mo(self):
        """手動觸發 cron：已 done 的 MO 應被重算 yield。"""
        mo_done = self._make_confirmed_mo(qty=10.0)
        self._set_raw_moves_done(mo_done)
        finished = mo_done.move_finished_ids.filtered(
            lambda m: m.product_id == mo_done.product_id
        )
        finished.write({"state": "done", "quantity": 10.0})
        mo_done.write({"state": "done"})
        # 模擬 done 後有人改產量 → 9 件
        # yield 為 store 欄位且依賴 move 的數量，改完即時重算為 90%
        finished.write({"quantity": 9.0})
        self.assertAlmostEqual(mo_done.mfg_custom_yield_rate, 90.0, places=2)
        # 觸發 cron
        result = self.env["mrp.production"]._cron_recompute_mfg_custom_yield_rate()
        self.assertTrue(result)
        mo_done.invalidate_recordset()
        # 產出由 10 降為 9（理論產出仍為 10）→ 得料率 90%
        self.assertAlmostEqual(mo_done.mfg_custom_yield_rate, 90.0, places=2)

    def test_11_cron_recompute_no_done_mo(self):
        """沒有 done MO 時，cron 不應爆。"""
        # 確保環境中無 done MO
        self.env["mrp.production"].search([("state", "=", "done")]).write(
            {"state": "cancel"}
        )
        result = self.env["mrp.production"]._cron_recompute_mfg_custom_yield_rate()
        self.assertTrue(result)

    def test_12_cron_record_exists(self):
        """確認 cron 已建立。"""
        cron = self.env["ir.cron"].search(
            [("code", "=", "model._cron_recompute_mfg_custom_yield_rate()")],
            limit=1,
        )
        self.assertTrue(cron, "應已建立 cron 記錄")
        self.assertEqual(cron.interval_number, 1)
        self.assertEqual(cron.interval_type, "days")
