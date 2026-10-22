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
        # selection 以 callable 動態產生：目標模型未安裝時回傳空清單，
        # 避免讀寫此欄位時因 env["plm_custom.feasibility"] 找不到模型而拋 KeyError
        selection=lambda model: (
            [("plm_custom.feasibility", "可行性評估單")]
            if "plm_custom.feasibility" in model.env
            else []
        ),
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
        help=(
            "= min(100, 實際產出 / 依實際投入原料換算的理論產出 * 100)。"
            "未 done 時為 0。"
        ),
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
        help="此 MO 的問題点數（需安裝 mfg_custom_issue 模組，未安裝時為 0）。",
    )
    mfg_custom_quality_check_count = fields.Integer(
        "品檢次數",
        compute="_compute_mfg_custom_quality_check_count",
        help="此 MO 的品檢次數（需安裝 mfg_custom_quality 模組，未安裝時為 0）。",
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
        """得料率 = 實際產出 / 依實際投入原料換算的理論產出 * 100，上限 100。

        以 BOM 配比換算理論產出：若依 BOM 每件成品需 R 件原料，則投入 C 件
        原料理論上應產出 C / R 件成品；實際產出與理論值之比即為得料率。
        完美生產（產出與投入完全符合配比）時為 100%，少產或多耗原料時下降。

        只在 ``state == 'done'`` 時計算；其餘情境顯示 0。
        """
        for production in self:
            if production.state != "done":
                production.mfg_custom_yield_rate = 0.0
                continue
            produced = production._mfg_custom_get_produced_qty()
            expected = production._mfg_custom_get_expected_output()
            if expected <= 0:
                # 沒有 BOM / 沒有原料消耗：退而以「產出 / 計劃數量」計算
                planned = production.product_qty or 0.0
                rate = (produced / planned * 100.0) if planned else 0.0
                production.mfg_custom_yield_rate = min(round(rate, 2), 100.0)
                continue
            rate = (produced / expected) * 100.0
            production.mfg_custom_yield_rate = min(round(rate, 2), 100.0)

    def _mfg_custom_get_standard_consumption(self):
        """計算標準原料消耗（依 BOM 與計劃產量推算）。

        僅供顯示／參考用；得料率本身改以「實際投入」換算（見
        ``_mfg_custom_get_expected_output``）。
        """
        self.ensure_one()
        if not self.bom_id:
            # 沒有 BOM：直接採用實際消耗
            return self._mfg_custom_get_consumed_qty()
        product_qty_in_bom_uom = self.product_qty or 0.0
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
            return self._mfg_custom_get_consumed_qty()
        return total

    def _mfg_custom_get_consumed_qty(self):
        """實際消耗的原料數量（done 的原料 move 加總，換算為產品預設單位）。"""
        self.ensure_one()
        total = 0.0
        for move in self.move_raw_ids.filtered(lambda m: m.state == "done"):
            qty = move.quantity or 0.0
            product = move.product_id
            uom = product.uom_id
            if uom and move.uom_id and uom != move.uom_id:
                qty = move.uom_id._compute_quantity(qty, uom)
            total += qty
        return total

    def _mfg_custom_get_raw_ratio(self):
        """回傳 {原料 id: 每件成品需耗用的原料數量}（依 BOM 配比）。"""
        self.ensure_one()
        if not self.bom_id:
            return {}
        bom_qty = self.bom_id.product_qty or 1.0
        ratio = {}
        for line in self.bom_id.bom_line_ids:
            if not line.product_id or line.product_id.type == "service":
                continue
            ratio[line.product_id.id] = (line.product_qty or 0.0) / bom_qty
        return ratio

    def _mfg_custom_get_expected_output(self):
        """依實際投入的原料與 BOM 配比，換算理論上應產出的成品數量。

        以「實際投入的原料總量 / 每件成品所需的原料總量」換算：
        例如 BOM 每件成品需 3 件原料，實際投入 30 件 → 理論產出 10 件；
        多耗原料時理論產出提高（得料率下降），少耗原料則相反。
        """
        self.ensure_one()
        ratio = self._mfg_custom_get_raw_ratio()
        if not ratio:
            return 0.0
        consumed = 0.0
        for move in self.move_raw_ids.filtered(lambda m: m.state == "done"):
            if move.product_id.id not in ratio:
                # 非 BOM 內的原料不列入計算
                continue
            qty = move.quantity or 0.0
            product = move.product_id
            uom = product.uom_id
            if uom and move.uom_id and uom != move.uom_id:
                qty = move.uom_id._compute_quantity(qty, uom)
            consumed += qty
        total_ratio = sum(ratio.values())
        if not total_ratio or consumed <= 0:
            return 0.0
        return consumed / total_ratio

    def _mfg_custom_get_produced_qty(self):
        """計算實際合格產量（done 的 move_finished_ids 之產品產量）。"""
        self.ensure_one()
        done_moves = self.move_finished_ids.filtered(
            lambda m: m.state == "done" and m.product_id.id == self.product_id.id,
        )
        return sum(done_moves.mapped("quantity"))

    @api.depends()
    def _compute_mfg_custom_issue_count(self):
        """問題点計數：反查 mfg_custom.issue（模組未安裝時為 0）。

        本模組不依賴 mfg_custom_issue，因此以 ``in self.env`` 判斷模型是否存在，
        避免循環依賴；安裝後即自動取得真實數量，MO 表單的 smart button 也會啟用。

        以 ``sudo()`` 查詢：這是純技術性計數器，一般 MRP 使用者（未加入
        mfg_custom_base 群組）開啟 MO 表單時不應因此發生 AccessError。
        """
        Issue = self.env.get("mfg_custom.issue")
        if Issue is not None:
            Issue = Issue.sudo()
        for production in self:
            if Issue is None:
                production.mfg_custom_issue_count = 0
                continue
            production.mfg_custom_issue_count = Issue.search_count(
                [("production_id", "=", production.id)],
            )

    @api.depends()
    def _compute_mfg_custom_quality_check_count(self):
        """品檢次數：反查 mfg_custom.quality.check（模組未安裝時為 0）。

        本模組不依賴 mfg_custom_quality，判斷方式同上；
        網域與 mfg_custom_quality 的 ``_get_mfg_quality_check_domain`` 一致。

        同樣以 ``sudo()`` 查詢，避免一般 MRP 使用者開啟 MO 表單時發生 AccessError。
        """
        Check = self.env.get("mfg_custom.quality.check")
        if Check is not None:
            Check = Check.sudo()
        for production in self:
            if Check is None:
                production.mfg_custom_quality_check_count = 0
                continue
            production.mfg_custom_quality_check_count = Check.search_count(
                [("production_id", "=", production.id)],
            )

    @api.depends("mfg_custom_stage_log_ids")
    def _compute_mfg_custom_stage_log_count(self):
        for production in self:
            production.mfg_custom_stage_log_count = len(
                production.mfg_custom_stage_log_ids
            )

    # ---- 動作 -------------------------------------------------------------

    def action_change_stage(self, new_stage=None, reason=None):
        """變更生產階段並寫日誌。

        :param new_stage: 'sample' / 'pilot' / 'mass'；未指定時開啟「變更生產階段」視窗
        :param reason: 變更原因（可選，會記在日誌的 reason 欄位）
        """
        if not new_stage:
            # 由 MO 表單的「變更生產階段」按鈕呼叫：開啟視窗讓使用者挑選新階段
            self.ensure_one()
            return self._mfg_custom_get_stage_change_action()
        valid = {k for k, _ in self._fields["mfg_custom_production_stage"].selection}
        if new_stage not in valid:
            raise UserError(
                self.env._(
                    "無效的生產階段：%s（應為 %s）", new_stage, ", ".join(sorted(valid))
                ),
            )
        # 日誌統一由 write() 寫入，變更原因透過 context 傳遞
        productions = self.with_context(mfg_custom_stage_change_reason=reason or False)
        productions.write({"mfg_custom_production_stage": new_stage})
        return True

    def _mfg_custom_get_stage_change_action(self):
        """取得「變更生產階段」視窗的 action（由 action_change_stage 呼叫）。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mfg_custom_production_stage.mfg_production_stage_change_action",
        )
        action["context"] = {"default_production_id": self.id}
        return action

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

    def write(self, vals):
        """寫入時若生產階段有變動，自動補寫階段變更日誌。

        讓表單上的階段選擇器與「變更生產階段」按鈕都留下稽核紀錄；
        變更原因可由 context 的 ``mfg_custom_stage_change_reason`` 帶入。
        """
        new_stage = vals.get("mfg_custom_production_stage")
        old_stages = {}
        if new_stage:
            old_stages = {
                production.id: production.mfg_custom_production_stage
                for production in self
            }
        result = super().write(vals)
        if new_stage:
            self._mfg_custom_create_stage_logs(old_stages, new_stage)
        return result

    def _mfg_custom_create_stage_logs(self, old_stages, new_stage):
        """依階段變更前後值建立日誌（前後值相同者不建立）。"""
        reason = self.env.context.get("mfg_custom_stage_change_reason") or False
        # 以 sudo() 建立日誌：mrp.production.stage.log 的 ACL 僅開放建立權限給
        # mfg_custom_base.group_manager，一般 MRP 使用者變更階段時不應被擋下。
        # sudo() 不會改變目前使用者，user_id / create_uid 仍會記錄實際操作者。
        Log = self.env["mrp.production.stage.log"].sudo()
        for production in self:
            old_stage = old_stages.get(production.id)
            if not old_stage or old_stage == new_stage:
                continue
            if not isinstance(production.id, int):
                # 尚未寫入資料庫的暫存記錄（NewId）無法建立日誌
                continue
            Log.create(
                {
                    "production_id": production.id,
                    "from_stage": old_stage,
                    "to_stage": new_stage,
                    "reason": reason,
                },
            )

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
            ):
                # 欄位本身有預設值（mass），因此「非空」不能當成使用者已指定；
                # 選擇 BOM 時一律帶入 BOM 的預設階段。
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
        """開啟此 MO 的問題点清單。

        mfg_custom_issue 模組已安裝時，改用其提供的 action；
        未安裝時顯示提示訊息，避免使用者按了無反應。
        """
        self.ensure_one()
        if "mfg_custom.issue" in self.env:
            action = getattr(self, "action_view_mfg_custom_issues", None)
            if action is not None:
                return action()
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
        """開啟此 MO 的品檢單。

        mfg_custom_quality 模組已安裝時，改用其提供的 action_view_mfg_quality_checks；
        未安裝時顯示提示訊息（保持原本行為）。
        """
        self.ensure_one()
        if "mfg_custom.quality.check" in self.env:
            action = getattr(self, "action_view_mfg_quality_checks", None)
            if action is not None:
                return action()
            # 備援：直接開啟 mfg_custom_quality 的品檢單 action
            action = self.env["ir.actions.act_window"]._for_xml_id(
                "mfg_custom_quality.mfg_quality_check_action",
            )
            action["domain"] = [("production_id", "=", self.id)]
            action["context"] = {"default_production_id": self.id}
            return action
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
