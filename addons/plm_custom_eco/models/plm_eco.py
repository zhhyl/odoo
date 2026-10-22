# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PlmCustomEco(models.Model):
    """工程變更單 (Engineering Change Order)。"""

    _name = "plm_custom.eco"
    _description = "PLM Custom 工程變更單"
    _inherit = ["mail.activity.mixin", "mfg_custom.approval.mixin"]
    _order = "create_date desc"

    name = fields.Char(default="ECO/New", readonly=True, copy=False)
    code = fields.Char(default="New", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("impact_analysis", "影響分析"),
            ("pending_approval", "待簽核"),
            ("approved", "已核准"),
            ("rejected", "已駁回"),
            ("applied", "已套用"),
            ("cancelled", "取消"),
        ],
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    type = fields.Selection(
        [
            ("product", "產品變更"),
            ("process", "製程變更"),
            ("material", "材料變更"),
            ("tooling", "工治具變更"),
            ("document", "文件變更"),
        ],
        required=True,
    )
    origin = fields.Selection(
        [
            ("customer", "客戶要求"),
            ("internal", "內部改善"),
            ("supplier", "供應商通知"),
            ("issue", "問題点升級"),
            ("compliance", "法規要求"),
        ],
        required=True,
    )
    subject = fields.Char("主旨", required=True)
    source_issue_id = fields.Many2one(
        "mfg_custom.issue",
        "觸發問題点",
        ondelete="set null",
    )
    source_feasibility_id = fields.Many2one(
        "plm_custom.feasibility",
        "觸發可行性評估",
        ondelete="set null",
    )
    product_id = fields.Many2one(
        "product.product",
        "影響產品",
        required=True,
        index=True,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        "影響 BOM",
        required=True,
        ondelete="restrict",
        index=True,
    )
    from_version = fields.Char("變更前版本", required=True)
    to_version = fields.Char("變更後版本", required=True)
    old_bom_version_id = fields.Many2one(
        "mrp.bom.version",
        "舊版快照",
        readonly=True,
    )
    new_bom_version_id = fields.Many2one(
        "mrp.bom.version",
        "新版快照",
        readonly=True,
    )
    line_ids = fields.One2many(
        "plm_custom.eco.line",
        "eco_id",
        "影響清單",
    )
    attachment_ids = fields.One2many(
        "plm_custom.eco.attachment",
        "eco_id",
        "相關附件",
    )
    impact_summary = fields.Html("影響摘要")
    risk_level = fields.Selection(
        [("low", "低"), ("medium", "中"), ("high", "高"), ("critical", "關鍵")],
        default="medium",
    )
    estimated_cost = fields.Monetary(
        "預估變更成本",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    effective_date = fields.Date("預定生效日")
    applied_date = fields.Datetime("實際套用日")
    owner_id = fields.Many2one(
        "res.users",
        "ECO 負責人",
        default=lambda self: self.env.user,
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        "申請人",
        default=lambda self: self.env.user,
    )
    notes = fields.Text("備註")

    _eco_state_bom_idx = models.Index("(state, bom_id, effective_date)")

    @api.constrains("from_version", "to_version")
    def _check_versions(self):
        for eco in self:
            if eco.from_version == eco.to_version:
                raise ValidationError(
                    self.env._("變更前後版本不可相同：%s", eco.from_version)
                )

    def action_start_analysis(self):
        for eco in self:
            if eco.state != "draft":
                raise UserError(
                    self.env._("只有草稿狀態的 ECO 可以開始影響分析")
                )
            eco._auto_populate_lines()
            eco.state = "impact_analysis"
            eco.message_post(
                body=self.env._("ECO 進入影響分析階段"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def action_submit_approval(self):
        for eco in self:
            if eco.state != "impact_analysis":
                raise UserError(
                    self.env._("只有完成影響分析的 ECO 可送出簽核")
                )
            if not eco.line_ids:
                raise UserError(
                    self.env._("影響清單為空，請先執行影響分析")
                )
            # 交給通用簽核引擎：自動比對規則、建立簽核單、掛回本單
            eco.action_submit_for_approval()
            eco.write({"state": "pending_approval"})
            eco.message_post(
                body=self.env._("ECO 已送出簽核，等待核准"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def action_approve(self):
        """委派給簽核引擎核准「目前關卡」。

        ECO 的 ``state`` 只有在 **所有** 關卡都核准後，才會由
        ``_approval_on_approved()`` 改為 ``approved``。
        """
        self.action_approve_current_step()

    def action_reject(self):
        """委派給簽核引擎駁回「目前關卡」。"""
        self.action_reject_current_step(reason=self.env._("由 ECO 駁回"))

    # ------------------------------------------------------------------
    # 簽核引擎回呼（mixin hooks）
    # ------------------------------------------------------------------

    def _approval_on_approved(self):
        """所有簽核關卡皆通過時，把 ECO 改為已核准。"""
        for eco in self:
            if eco.state == "approved":
                continue
            eco.sudo().write({"state": "approved"})
            eco.sudo().message_post(
                body=self.env._("ECO 已核准"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def _approval_on_rejected(self):
        """簽核被駁回時，把 ECO 改為已駁回。"""
        for eco in self:
            if eco.state == "rejected":
                continue
            eco.sudo().write({"state": "rejected"})
            eco.sudo().message_post(
                body=self.env._("ECO 已駁回"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def _approval_on_cancelled(self):
        """簽核被取消時，把 ECO 退回影響分析階段。"""
        for eco in self:
            if eco.state != "pending_approval":
                continue
            eco.sudo().write({"state": "impact_analysis"})
            eco.sudo().message_post(
                body=self.env._("ECO 簽核已取消，退回影響分析"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def action_apply(self):
        for eco in self:
            if eco.state == "applied":
                raise UserError(self.env._("ECO 已套用過，請勿重複套用"))
            if eco.state != "approved":
                raise UserError(self.env._("只有已核准的 ECO 可以套用"))
            # 1. 凍結舊版快照
            if eco.bom_id:
                old_snap = self.env["mrp.bom.version"].create_from_bom(eco.bom_id)
                old_snap.write({
                    "reason": "eco",
                    "version": eco.from_version,
                })
                eco.old_bom_version_id = old_snap
                # 2. 升級 BOM 版本字串
                eco.bom_id.write({"plm_custom_version": eco.to_version})
                # 3. 建立新快照
                new_snap = self.env["mrp.bom.version"].create_from_bom(eco.bom_id)
                new_snap.write({
                    "reason": "eco",
                    "version": eco.to_version,
                })
                eco.new_bom_version_id = new_snap
            # 4. 升級附件版本
            for att_link in eco.attachment_ids.filtered("attachment_id"):
                att_link.attachment_id._mfg_custom_bump_version(reason="eco")
            eco.applied_date = fields.Datetime.now()
            eco.state = "applied"
            eco.message_post(
                body=self.env._(
                    "ECO 已套用：BOM 升至 %s", eco.to_version
                ),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_applied",
            )
            eco._notify_eco_applied()

    def _notify_eco_applied(self):
        """ECO 套用後，以電子郵件通知負責人。

        只在真正套用（BOM 升版）當下寄一封。
        """
        template = self.env.ref(
            "plm_custom_eco.mail_template_plm_eco_apply",
            raise_if_not_found=False,
        )
        if not template:
            return
        for eco in self:
            if not eco.owner_id or not eco.owner_id.email:
                continue
            template.send_mail(eco.id, force_send=False)

    def action_cancel(self):
        for eco in self:
            if eco.state == "applied":
                raise UserError(
                    self.env._("已套用的 ECO 不可取消，請另開新單處理")
                )
            eco.state = "cancelled"
            eco.message_post(
                body=self.env._("ECO 已取消"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def action_view_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "影響清單",
            "res_model": "plm_custom.eco.line",
            "view_mode": "list,form",
            "domain": [("eco_id", "=", self.id)],
            "context": {"default_eco_id": self.id},
        }

    def action_reset_to_draft(self):
        for eco in self:
            if eco.state == "applied":
                raise UserError(
                    self.env._("已套用的 ECO 不可重設為草稿")
                )
            eco.state = "draft"
            eco.message_post(
                body=self.env._("ECO 重設為草稿"),
                subtype_xmlid="plm_custom_eco.mt_plm_eco_state_changed",
            )

    def _auto_populate_lines(self):
        """自動建立影響清單。"""
        LineEnv = self.env["plm_custom.eco.line"]
        for eco in self:
            # 清空既有 line（避免重複）
            eco.line_ids.unlink()
            line_vals = []

            # 1. 找出所有未完成 SO（含此產品）
            sos = self.env["sale.order.line"].search([
                ("product_id", "=", eco.product_id.id),
                ("state", "in", ["draft", "sent", "sale"]),
            ])
            for line in sos:
                line_vals.append({
                    "eco_id": eco.id,
                    "impact_type": "sale",
                    "res_model": "sale.order.line",
                    "res_id": line.id,
                    "description": self.env._(
                        "銷售明細 %s 未交 %s %s",
                        line.order_id.name,
                        line.product_uom_qty,
                        line.product_uom_id.name,
                    ),
                })

            # 2. 找出庫存量
            quants = self.env["stock.quant"].search([
                ("product_id", "=", eco.product_id.id),
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
            ])
            for q in quants:
                line_vals.append({
                    "eco_id": eco.id,
                    "impact_type": "inventory",
                    "res_model": "stock.quant",
                    "res_id": q.id,
                    "description": self.env._(
                        "倉位 %s 庫存 %.2f",
                        q.location_id.display_name,
                        q.quantity,
                    ),
                })

            # 3. 找出未關 MO
            mos = self.env["mrp.production"].search([
                ("product_id", "=", eco.product_id.id),
                ("state", "in", ["confirmed", "progress", "to_close"]),
            ])
            for mo in mos:
                line_vals.append({
                    "eco_id": eco.id,
                    "impact_type": "production",
                    "res_model": "mrp.production",
                    "res_id": mo.id,
                    "description": self.env._(
                        "MO %s 預計 %s 開工",
                        mo.name,
                        mo.date_start,
                    ),
                })

            # 4. 找客戶規格附件（mfg_custom_attachment_version 標記為 customer_spec）
            docs = self.env["ir.attachment"].search([
                ("res_model", "=", "product.product"),
                ("res_id", "=", eco.product_id.id),
                ("mfg_custom_doc_type", "=", "customer_spec"),
                ("mfg_custom_doc_state", "in", ["draft", "released"]),
            ])
            for doc in docs:
                line_vals.append({
                    "eco_id": eco.id,
                    "impact_type": "document",
                    "res_model": "ir.attachment",
                    "res_id": doc.id,
                    "description": self.env._(
                        "規格附件 %s v%s",
                        doc.name,
                        doc.mfg_custom_version,
                    ),
                })

            if line_vals:
                LineEnv.create(line_vals)
