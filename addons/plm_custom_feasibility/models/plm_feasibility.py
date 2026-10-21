# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PlmFeasibility(models.Model):
    """跨部門可行性評估主檔.

    一張 ``feasibility`` 對應一份潛在訂單/客戶詢問的可行性評估結果。
    內含五個面向分數（產能 / 技術 / 料況 / 法規 / 風險），由各部門
    透過 ``plm_custom.feasibility.score`` 評分明細登錄分數。

    評估流程
    --------

    1. ``draft``        — 業務/PM 建立評估單，填入客戶/產品/數量/交期/目標價
    2. ``in_review``    — 透過 ``action_submit`` 送出，要求至少有 1 筆評分
    3. ``approved``     — 透過 ``action_approve`` 核准，要求五面向皆已評分
    4. ``rejected``     — 透過 ``action_reject`` 駁回
    5. ``cancelled``    — 透過 ``action_cancel`` 取消

    決策結論（``decision``）由五項分數加總後依門檻自動計算：

    * ``feasible``            — 總分 >= 80
    * ``feasible_with_risk``  — 60 <= 總分 < 80
    * ``infeasible``          — 總分 < 60
    """

    _name = "plm_custom.feasibility"
    _description = "PLM Custom 可行性評估"
    _inherit = ["mail.thread", "mfg_custom.approval.mixin"]
    _order = "id desc"
    _rec_name = "name"

    # ------------------------------------------------------------------
    # 業務欄位
    # ------------------------------------------------------------------

    name = fields.Char(
        "單號",
        default="New",
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("in_review", "評估中"),
            ("approved", "通過"),
            ("rejected", "不通過"),
            ("cancelled", "取消"),
        ],
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    source_model = fields.Selection(
        [
            ("sale.order", "銷售訂單"),
            ("sale.order.line", "銷售明細"),
            ("crm.lead", "CRM 機會"),
            ("manual", "手動建立"),
        ],
        string="來源模型",
        default="manual",
        required=True,
        help="建立本評估單的來源業務單據。",
    )
    source_id = fields.Integer(
        "來源單據 ID",
        index=True,
        help="對應來源模型的 res_id。",
    )

    partner_id = fields.Many2one(
        "res.partner",
        "客戶",
        required=True,
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        "產品",
        required=True,
        index=True,
    )
    product_qty = fields.Float(
        "預估數量",
        digits="Product Unit",
        default=1.0,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        "單位",
        related="product_id.uom_id",
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        "候選 BOM",
        domain="[('product_tmpl_id', '=', product_id.product_tmpl_id)]",
        help="候選的 BOM，僅顯示屬於選定產品模板的版本。",
    )
    requested_date = fields.Date("客戶要求交期")
    target_price = fields.Monetary(
        "客戶目標價",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        "幣別",
        default=lambda self: self.env.company.currency_id,
    )

    # ------------------------------------------------------------------
    # 評分彙總
    # ------------------------------------------------------------------

    score_ids = fields.One2many(
        "plm_custom.feasibility.score",
        "feasibility_id",
        "評分明細",
    )
    score_capacity = fields.Integer("產能分數 (0-10)", default=0)
    score_technical = fields.Integer("技術分數 (0-10)", default=0)
    score_material = fields.Integer("料況分數 (0-10)", default=0)
    score_regulatory = fields.Integer("法規分數 (0-10)", default=0)
    score_risk = fields.Integer("風險分數 (0-10)", default=0)
    score_total = fields.Float(
        "總分 (0-100)",
        compute="_compute_score_total",
        store=True,
    )
    decision = fields.Selection(
        [
            ("feasible", "可行"),
            ("feasible_with_risk", "可行但有風險"),
            ("infeasible", "不可行"),
        ],
        compute="_compute_decision",
        store=True,
    )

    # ------------------------------------------------------------------
    # 其他
    # ------------------------------------------------------------------

    user_id = fields.Many2one(
        "res.users",
        "負責業務",
        default=lambda self: self.env.user,
        tracking=True,
    )
    notes = fields.Text("備註")
    company_id = fields.Many2one(
        "res.company",
        "公司",
        default=lambda self: self.env.company,
        index=True,
    )

    _feasibility_state_idx = models.Index("(state, partner_id, product_id)")

    # ------------------------------------------------------------------
    # ORM 覆寫
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "plm_custom.feasibility"
                ) or "New"
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # 計算邏輯
    # ------------------------------------------------------------------

    @api.depends(
        "score_capacity",
        "score_technical",
        "score_material",
        "score_regulatory",
        "score_risk",
    )
    def _compute_score_total(self):
        """五項分數加總 × 2，最高 100。"""
        for rec in self:
            total = (
                rec.score_capacity
                + rec.score_technical
                + rec.score_material
                + rec.score_regulatory
                + rec.score_risk
            )
            rec.score_total = total * 2

    @api.depends("score_total")
    def _compute_decision(self):
        """依總分決定可行性結論。

        * >= 80 → feasible
        * 60-79 → feasible_with_risk
        * < 60  → infeasible
        """
        for rec in self:
            if rec.score_total >= 80:
                rec.decision = "feasible"
            elif rec.score_total >= 60:
                rec.decision = "feasible_with_risk"
            else:
                rec.decision = "infeasible"

    # ------------------------------------------------------------------
    # 內部輔助
    # ------------------------------------------------------------------

    def _sync_score_fields(self):
        """依 score_ids 同步主檔五個面向分數欄位。

        部門與面向的對應關係：

        * 產線 (production)   → 產能分數
        * 工程 (engineering)  → 技術分數
        * 採購 (procurement)  → 料況分數
        * 品保 (qa)           → 法規分數（QA 兼管法規/認證）
        * 業務 (sales)        → 風險分數（業務風險/客戶/付款）
        * 法規 (legal)        → 不在五項彙總中，僅供記錄（選填）
        """
        field_map = {
            "production": "score_capacity",
            "engineering": "score_technical",
            "procurement": "score_material",
            "qa": "score_regulatory",
            "sales": "score_risk",
        }
        for rec in self:
            values = {fname: 0 for fname in field_map.values()}
            for line in rec.score_ids:
                fname = field_map.get(line.department)
                if fname:
                    values[fname] = line.score
            rec.write(values)

    def _check_all_scores_filled(self):
        """檢查五面向是否皆已有評分。"""
        self.ensure_one()
        required_depts = {"sales", "engineering", "production", "qa", "procurement"}
        scored_depts = set(self.score_ids.mapped("department"))
        # legal（法規）為選填，於 mfg_custom_eco 串接時由法規群組補
        missing = required_depts - scored_depts
        if missing:
            labels = {
                "sales": "業務",
                "engineering": "工程",
                "production": "產線",
                "qa": "品保",
                "procurement": "採購",
            }
            missing_labels = sorted(labels[d] for d in missing)
            raise UserError(
                self.env._(
                    "仍有以下部門未評分，無法核准：%s",
                    "、".join(missing_labels),
                )
            )
        return True

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def action_submit(self):
        """草稿 → 評估中。

        需至少 1 筆評分記錄，否則提示「請先請相關部門評分」。
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    self.env._(
                        "僅有 draft 狀態可送出評估，目前狀態為 %s",
                        rec.state,
                    )
                )
            if not rec.score_ids:
                raise UserError(
                    self.env._("送出前請至少建立 1 筆評分明細")
                )
            rec.write({"state": "in_review"})
            rec.message_post(
                body=rec.env._("已送出評估，等待各部門完成評分。"),
                subtype_xmlid="plm_custom_feasibility.mt_plm_feasibility_state_changed",
            )

    def action_approve(self):
        """評估中 → 通過。

        需五個必要部門（業務 / 工程 / 產線 / 品保 / 採購）皆有評分。
        """
        for rec in self:
            if rec.state != "in_review":
                raise UserError(
                    self.env._(
                        "僅有 in_review 狀態可核准，目前狀態為 %s",
                        rec.state,
                    )
                )
            rec._check_all_scores_filled()
            rec.write({"state": "approved"})
            rec.message_post(
                body=rec.env._(
                    "評估通過，決策結論：%s",
                    dict(rec._fields["decision"].selection).get(rec.decision, ""),
                ),
                subtype_xmlid="plm_custom_feasibility.mt_plm_feasibility_state_changed",
            )

    def action_reject(self):
        """評估中 → 不通過。"""
        for rec in self:
            if rec.state != "in_review":
                raise UserError(
                    self.env._(
                        "僅有 in_review 狀態可駁回，目前狀態為 %s",
                        rec.state,
                    )
                )
            rec.write({"state": "rejected"})
            rec.message_post(
                body=rec.env._("評估不通過。"),
                subtype_xmlid="plm_custom_feasibility.mt_plm_feasibility_state_changed",
            )

    def action_cancel(self):
        """取消評估單（任何非結束狀態皆可）。"""
        for rec in self:
            if rec.state in ("approved", "rejected", "cancelled"):
                continue
            rec.write({"state": "cancelled"})
            rec.message_post(
                body=rec.env._("評估單已取消。"),
                subtype_xmlid="plm_custom_feasibility.mt_plm_feasibility_state_changed",
            )

    # ------------------------------------------------------------------
    # 顯示輔助
    # ------------------------------------------------------------------

    def name_get(self):
        result = []
        for rec in self:
            label = rec.name or ""
            if rec.product_id:
                label = f"{label} - {rec.product_id.display_name}"
            result.append((rec.id, label))
        return result
