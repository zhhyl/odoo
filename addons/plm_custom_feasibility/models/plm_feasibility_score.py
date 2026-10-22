# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PlmFeasibilityScore(models.Model):
    """可行性評估的評分明細.

    每個部門對同一張 ``feasibility`` 只能留下一筆記錄，
    並提供 0-10 分數、意見（Html）以及佐證附件。
    """

    _name = "plm_custom.feasibility.score"
    _description = "PLM Custom 可行性評分明細"
    _order = "feasibility_id, department, id"

    feasibility_id = fields.Many2one(
        "plm_custom.feasibility",
        "可行性評估",
        required=True,
        ondelete="cascade",
        index=True,
    )
    department = fields.Selection(
        [
            ("sales", "業務"),
            ("engineering", "工程"),
            ("production", "產線"),
            ("qa", "品保"),
            ("procurement", "採購"),
            ("legal", "法規"),
        ],
        string="部門",
        required=True,
        index=True,
    )
    reviewer_id = fields.Many2one(
        "res.users",
        "評分者",
        required=True,
        default=lambda self: self.env.user,
    )
    score = fields.Integer(
        "分數 (0-10)",
        required=True,
        help="0 = 完全不可行、10 = 完全可行。",
    )
    comment = fields.Html("意見")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="佐證附件",
        help="佐證此評分的附件（規格書、料況報告等）。",
    )
    company_id = fields.Many2one(
        "res.company",
        "公司",
        related="feasibility_id.company_id",
        store=True,
        index=True,
    )

    _score_dept_uniq = models.Constraint(
        "UNIQUE(feasibility_id, department)",
        "同一部門對同一張評估單只能評分一次。",
    )
    _score_dept_idx = models.Index("(department, reviewer_id)")

    # ------------------------------------------------------------------
    # 顯示輔助
    # ------------------------------------------------------------------

    @api.depends("department", "reviewer_id")
    def _compute_display_name(self):
        """顯示「部門中文名 / 評分者」。

        Odoo 20 已移除 ``name_get()``，顯示名稱改由 ``display_name``
        欄位計算，覆寫 ``_compute_display_name()`` 即可。
        """
        labels = {
            "sales": "業務",
            "engineering": "工程",
            "production": "產線",
            "qa": "品保",
            "procurement": "採購",
            "legal": "法規",
        }
        for rec in self:
            rec.display_name = rec.env._(
                "%(dept)s / %(user)s",
                dept=labels.get(rec.department, rec.department or ""),
                user=rec.reviewer_id.display_name or "",
            )

    # ------------------------------------------------------------------
    # 約束
    # ------------------------------------------------------------------

    @api.constrains("score")
    def _check_score(self):
        for rec in self:
            if not (0 <= rec.score <= 10):
                raise ValidationError(
                    self.env._(
                        "分數需介於 0 到 10 之間，目前為 %s",
                        rec.score,
                    )
                )

    @api.constrains("feasibility_id", "department")
    def _check_unique_department(self):
        """同一張評估單的同一部門只能有一筆評分（給出友善錯誤訊息）。"""
        for rec in self:
            if not rec.feasibility_id or not rec.department:
                continue
            duplicate = self.search_count([
                ("feasibility_id", "=", rec.feasibility_id.id),
                ("department", "=", rec.department),
                ("id", "!=", rec.id),
            ])
            if duplicate:
                raise ValidationError(
                    self.env._(
                        "評估單 %s 的「%s」部門只能有一筆評分。",
                        rec.feasibility_id.display_name,
                        rec.department,
                    )
                )

    @api.constrains("reviewer_id")
    def _check_reviewer_active(self):
        for rec in self:
            if not rec.reviewer_id.active:
                raise ValidationError(
                    self.env._(
                        "評分者 %s 已停用，請改派其他評分者",
                        rec.reviewer_id.display_name,
                    )
                )

    # ------------------------------------------------------------------
    # 覆寫：同步主檔五項分數欄位
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """建立評分：先擋住重複部門，再同步主檔分數欄位。"""
        # 先讓前幾筆待寫入的紀錄落地，否則重複檢查會漏掉尚未 flush 的資料
        self.flush_model()
        for vals in vals_list:
            if not vals.get("feasibility_id") or not vals.get("department"):
                continue
            if self.search_count([
                ("feasibility_id", "=", vals["feasibility_id"]),
                ("department", "=", vals["department"]),
            ]):
                raise ValidationError(
                    self.env._(
                        "同一張評估單的「%s」部門只能有一筆評分。",
                        vals["department"],
                    )
                )
        records = super().create(vals_list)
        records.mapped("feasibility_id")._sync_score_fields()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "score" in vals or "department" in vals:
            self.mapped("feasibility_id")._sync_score_fields()
        return result

    def unlink(self):
        feasibilities = self.mapped("feasibility_id")
        result = super().unlink()
        feasibilities._sync_score_fields()
        return result
