# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    """擴充 mrp.production：加入生產階段、得料率、樣品單關聯。"""

    _inherit = "mrp.production"

    # ---- 欄位 -------------------------------------------------------------

    mfg_custom_production_stage = fields.Selection(
        [
            ("sample", "樣品"),
            ("pilot", "小批量 / 試量產"),
            ("mass", "量產"),
        ],
        string="生產階段",
        default="mass",
        required=True,
        index=True,
        tracking=True,
        help="樣品 = 工程打樣；小批量 = 試量產/PP；量產 = 正式生產。",
    )
    mfg_custom_sample_request_id = fields.Reference(
        # 使用 Reference 而非 Many2one：避免 plm_custom_feasibility 模組互依賴
        selection=[("plm_custom.feasibility", "可行性評估單")],
        string="樣品評估單",
        help="若是樣品階段，可關聯一份可行性評估單（待 plm_custom_feasibility 模組安裝後即可使用）。",
    )
    mfg_custom_parent_production_id = fields.Many2one(
        "mrp.production",
        "上階 MO（量產由小批升版而來）",
        index=True,
        ondelete="set null",
        help="當此 MO 為量產、由小批量升版而來時記錄其來源。",
    )
    mfg_custom_yield_rate = fields.Float(
        "得料率 %",
        digits=(5, 2),
        tracking=True,
        compute="_compute_mfg_custom_yield_rate",
        store=True,
        help="= min(100, 實際產量 / 標準用量 * 100)。未 done 時為 0。",
    )
    mfg_custom_expected_yield_rate = fields.Float(
        "期望得料率 %",
        digits=(5, 2),
        default=98.0,
        help="期望得料率；若實際得料率低於此值，將以紅色標示於清單。",
    )
    mfg_custom_issue_count = fields.Integer(
        "問題点數",
        compute="_compute_mfg_custom_issue_count",
        help="此 MO 的問題点數（待 mfg_custom_issue 模組補上 mfg_custom.issue.production_id 後可自動反查）。",
    )
    mfg_custom_quality_check_count = fields.Integer(
        "品檢次數",
        compute="_compute_mfg_custom_quality_check_count",
        help="此 MO 的品檢次數（待 mfg_custom_quality 模組補上 mfg_custom.quality.check.production_id 後可自動反查）。",
    )
    mfg_custom_stage_log_ids = fields.One2many(
        "mrp.production.stage.log",
        "production_id",
        "階段變更日誌",
    )
    mfg_custom_stage_log_count = fields.Integer(
        "階段變更次數",
        compute="_compute_mfg_custom_stage_log_count",
    )

    # ---- 索引 -------------------------------------------------------------

    _mfg_custom_stage_idx = models.Index(
        "(mfg_custom_production_stage, state)",
    )

    # ---- 計算 -------------------------------------------------------------

    @api.depends(
        "state",
        "move_finished_ids.state",
        "move_finished_ids.quantity",
        "move_finished_ids.product_id",
        "move_raw_ids.state",
        "move_raw_ids.quantity",
        "product_qty",
        "bom_id",
    )
    def _compute_mfg_custom_yield_rate(self):
        """得料率 = 實際合格產量 / 標準原料消耗 * 100，上限 100。

        只在 ``state == 'done'`` 時計算；其餘情境顯示 0。
        """
        for production in self:
            if production.state != "done":
                production.mfg_custom_yield_rate = 0.0
                continue
            standard = production._mfg_custom_get_standard_consumption()
            produced = production._mfg_custom_get_produced_qty()
            if standard <= 0:
                # 沒有 BOM / 沒有原料消耗：視為 100%（純服務型工單）
                production.mfg_custom_yield_rate = 100.0 if produced > 0 else 0.0
                continue
            rate = (produced / standard) * 100.0
            production.mfg_custom_yield_rate = min(round(rate, 2), 100.0)

    def _mfg_custom_get_standard_consumption(self):
        """計算標準原料消耗（依 BOM 與 qty 推算）。"""
        self.ensure_one()
        if not self.bom_id:
            # 沒有 BOM：直接採用實際消耗
            return sum(
                self.move_raw_ids.filtered(lambda m: m.state == "done").mapped(
                    "quantity"
                ),
            )
        product_qty_in_bom_uom = self.product_uom_qty or self.product_qty
        if self.bom_id.product_qty:
            factor = product_qty_in_bom_uom / self.bom_id.product_qty
        else:
            factor = product_qty_in_bom_uom
        total = 0.0
        for line in self.bom_id.bom_line_ids:
            if line.product_id and line.product_id.type == "service":
                continue
            total += (line.product_qty or 0.0) * factor
        if total <= 0:
            # BOM 沒抓到原料時回退到實際消耗
            return sum(
                self.move_raw_ids.filtered(lambda m: m.state == "done").mapped(
                    "quantity"
                ),
            )
        return total

    def _mfg_custom_get_produced_qty(self):
        """計算實際合格產量（done 的 move_finished_ids 之產品產量）。"""
        self.ensure_one()
        done_moves = self.move_finished_ids.filtered(
            lambda m: m.state == "done" and m.product_id.id == self.product_id.id,
        )
        return sum(done_moves.mapped("quantity"))

    @api.depends()
    def _compute_mfg_custom_issue_count(self):
        """問題点計數：待 mfg_custom_issue 模組補上 mfg_custom.issue.production_id 後即可反查。"""
        for production in self:
            # 不在此模組強加 depends 連結 mfg_custom.issue，避免循環依賴
            production.mfg_custom_issue_count = 0

    @api.depends()
    def _compute_mfg_custom_quality_check_count(self):
        """品檢次數：待 mfg_custom_quality 模組補上 mfg_custom.quality.check.production_id 後即可反查。"""
        for production in self:
            production.mfg_custom_quality_check_count = 0

    @api.depends("mfg_custom_stage_log_ids")
    def _compute_mfg_custom_stage_log_count(self):
        for production in self:
            production.mfg_custom_stage_log_count = len(
                production.mfg_custom_stage_log_ids
            )

    # ---- 動作 -------------------------------------------------------------

    def action_change_stage(self, new_stage, reason=None):
        """變更生產階段並寫日誌。

        :param new_stage: 'sample' / 'pilot' / 'mass'
        :param reason: 變更原因（可選，會記在日誌的 reason 欄位）
        """
        valid = {k for k, _ in self._fields["mfg_custom_production_stage"].selection}
        if new_stage not in valid:
            raise UserError(
                self.env._(
                    "無效的生產階段：%s（應為 %s）", new_stage, ", ".join(sorted(valid))
                ),
            )
        Log = self.env["mrp.production.stage.log"]
        for production in self:
            if production.mfg_custom_production_stage == new_stage:
                continue
            Log.create(
                {
                    "production_id": production.id,
                    "from_stage": production.mfg_custom_production_stage,
                    "to_stage": new_stage,
                    "reason": reason or False,
                },
            )
            production.mfg_custom_production_stage = new_stage

    @api.model
    def _cron_recompute_mfg_custom_yield_rate(self):
        """每日 23:00 觸發：重算所有 done MO 的得料率。

        主要處理情境：done 後又做了 scrap / unbuild 造成數量變動。
        """
        productions = self.search([("state", "=", "done")])
        if productions:
            productions._compute_mfg_custom_yield_rate()
        return True

    # ---- override ---------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """若 vals 沒帶 production_stage，沿用 BOM 上的預設階段。"""
        for vals in vals_list:
            if "mfg_custom_production_stage" not in vals and vals.get("bom_id"):
                bom = self.env["mrp.bom"].browse(vals["bom_id"])
                if bom.mfg_custom_default_production_stage:
                    vals["mfg_custom_production_stage"] = (
                        bom.mfg_custom_default_production_stage
                    )
        records = super().create(vals_list)
        return records  # noqa: RET504

    @api.onchange("bom_id")
    def _onchange_bom_id_mfg_custom_stage(self):
        """切換 BOM 時，自動帶入 BOM 預設階段。"""
        for production in self:
            if (
                production.bom_id
                and production.bom_id.mfg_custom_default_production_stage
                and not production.mfg_custom_production_stage
            ):
                production.mfg_custom_production_stage = (
                    production.bom_id.mfg_custom_default_production_stage
                )

    # ---- smart button 動作 ------------------------------------------------

    def action_mfg_custom_view_stage_logs(self):
        """開啟此 MO 的階段變更日誌。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mfg_custom_production_stage.mrp_production_stage_log_action",
        )
        action["domain"] = [("production_id", "=", self.id)]
        action["context"] = {
            "default_production_id": self.id,
            "search_default_groupby_to_stage": 1,
        }
        return action

    def action_mfg_custom_view_issues(self):
        """問題点：待 mfg_custom_issue 模組補上 mfg_custom.issue.production_id 後即可正常運作。

        目前以 placeholder 形式回傳，避免使用者按了無反應。
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("問題点模組未安裝"),
                "message": self.env._(
                    "請先安裝 mfg_custom_issue 模組，才能查看問題点。",
                ),
                "type": "warning",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_mfg_custom_print_yield_report(self):
        """回傳「列印含良率」PDF report action。"""
        self.ensure_one()
        return self.env.ref(
            "mfg_custom_production_stage.action_mfg_mo_yield_report"
        ).report_action(self)

    def action_mfg_custom_view_quality_checks(self):
        """品檢：待 mfg_custom_quality 模組補上 mfg_custom.quality.check.production_id 後即可正常運作。"""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("品檢模組未安裝"),
                "message": self.env._(
                    "請先安裝 mfg_custom_quality 模組，才能查看品檢記錄。",
                ),
                "type": "warning",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
