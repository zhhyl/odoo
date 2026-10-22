# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.fields import Domain
from odoo.exceptions import UserError


class IrAttachment(models.Model):
    """MFG / PLM 附件版本控管延伸.

    在 ``ir.attachment`` 既有邏輯（檔案儲存、ACL、chatter、bus）之上加入：

    * ``mfg_custom_version``      — 同 ``res_model + res_id + name`` 群組內的遞增版本號
    * ``mfg_custom_doc_type``     — 文件分類（客戶規格 / 圖面 / 承認書 / CoA / ...）
    * ``mfg_custom_doc_state``    — 受控狀態（草稿 / 審核中 / 已發行 / 已停用）
    * ``mfg_custom_tag_ids``      — 附件標籤（Many2many ``mfg_custom.attachment.tag``）
    * ``mfg_custom_superseded_by_id`` — 「被此版本取代」的反向連結

    自動行為
    --------

    * ``create``：當 vals 含 ``res_model``、``res_id``、``name`` 三項時，
      自動計算 ``mfg_custom_version = max(同群組版本) + 1``。
    * ``create``：若新增附件 ``mfg_custom_doc_state='released'``，
      自動將同群組（res_model+res_id+name）的舊版本切為 ``obsolete``，
      並把 ``mfg_custom_superseded_by_id`` 指向自己。
    * ``write``：當 ``mfg_custom_doc_state`` 變為 ``released`` 時，
      同樣將同群組其他 released/draft/in_review 切為 ``obsolete``。
    * ``_mfg_custom_bump_version()``：由 ECO 觸發的「跳版」輔助方法。
    """

    _inherit = "ir.attachment"

    DOC_TYPE_SELECTION = [
        ("customer_spec", "客戶規格書"),
        ("drawing", "圖面"),
        ("acknowledgement", "客戶承認書"),
        ("coa", "CoA 報告"),
        ("tool_drawing", "工治具圖"),
        ("internal", "內部文件"),
        ("other", "其他"),
    ]

    DOC_STATE_SELECTION = [
        ("draft", "草稿"),
        ("in_review", "審核中"),
        ("released", "已發行"),
        ("obsolete", "已停用"),
    ]

    mfg_custom_version = fields.Integer(
        "版本",
        default=1,
        readonly=True,
        tracking=True,
        help="同 res_model+res_id+name 群組內的遞增版本；首版為 1。",
    )
    mfg_custom_doc_type = fields.Selection(
        DOC_TYPE_SELECTION,
        string="文件類型",
        index=True,
        tracking=True,
        help="客戶規格書、圖面、承認書等業務用途分類。",
    )
    mfg_custom_doc_state = fields.Selection(
        DOC_STATE_SELECTION,
        string="文件狀態",
        default="draft",
        required=True,
        index=True,
        tracking=True,
        help="受控狀態：draft → in_review → released；被新發行版本取代後轉為 obsolete。",
    )
    mfg_custom_tag_ids = fields.Many2many(
        "mfg_custom.attachment.tag",
        string="標籤",
        help="自由標籤，方便篩選與群組。",
    )
    mfg_custom_superseded_by_id = fields.Many2one(
        "ir.attachment",
        string="被此版本取代",
        index=True,
        readonly=True,
        help="當自身由新版取代時，由 create / bump_version 反向連結到新版；新版清空自身。",
    )
    mfg_custom_version_reason = fields.Char(
        "版本說明",
        readonly=True,
        help="建立此版本的原因（例如由 ECO 跳版時的原因）。",
    )

    # 命名遵循「以底線開頭 + 描述性後綴」，與 mfg_custom_base 風格一致
    _mfg_doc_type_state_idx = models.Index("(mfg_custom_doc_type, mfg_custom_doc_state)")
    _mfg_res_idx = models.Index("(res_model, res_id, mfg_custom_doc_state)")

    # ---------------------------------------------------------------
    # CRUD 覆寫
    # ---------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """建立附件時自動分配版本號與處理 superseded_by.

        維持 base 既有 create 行為不變；於 ``super().create`` 之前預計算版本號，
        於 ``super().create`` 之後處理「released → 把同群組舊版改為 obsolete」的反向連結。
        """
        if not vals_list:
            return self.browse()

        # 預計算版本號：依 (res_model, res_id, name) 分組，每組獨立遞增
        version_map = self._mfg_custom_compute_next_versions(vals_list)
        # 在 vals_list 中出現多次的同 key，每多一筆就 +1
        seen_count: dict[tuple[str, int | bool, str], int] = {}

        for vals in vals_list:
            if "mfg_custom_version" in vals:
                continue
            key = (vals.get("res_model"), vals.get("res_id"), vals.get("name"))
            if not all(key):
                # 任一識別欄位缺漏（例：尚未掛到單據的暫存附件），沿用欄位預設值 1
                continue
            base = version_map.get(key, 1)
            offset = seen_count.get(key, 0)
            vals["mfg_custom_version"] = base + offset
            seen_count[key] = offset + 1

        records = super().create(vals_list)

        # 對剛建立的 released 附件，把同群組其他非自身附件標為 obsolete + superseded_by
        records._mfg_custom_auto_obsolete_predecessors()

        return records

    def write(self, vals):
        """寫入時若 doc_state 改為 released，觸發同群組舊版的 obsolete 處理."""
        result = super().write(vals)
        if "mfg_custom_doc_state" in vals and vals["mfg_custom_doc_state"] == "released":
            self._mfg_custom_auto_obsolete_predecessors()
        return result

    # ---------------------------------------------------------------
    # 業務方法
    # ---------------------------------------------------------------

    def _mfg_custom_bump_version(self, reason="eco"):
        """由 ECO 觸發的「跳版」輔助方法.

        為目前 recordset 中的每一筆附件建立一份新版本（同一份 binary 內容，
        res_model / res_id / name / doc_type 沿用，並把 state 重設為 ``draft``），
        然後把原附件的 ``mfg_custom_doc_state`` 設為 ``obsolete`` 並
        ``mfg_custom_superseded_by_id`` 指到新建的版本。

        :param reason: 觸發原因字串，記錄在新版的 chatter 訊息中。
        :returns: 新建立的附件 recordset（順序與 ``self`` 對應）。
        """
        if not self:
            return self.browse()

        new_vals_list = []
        for att in self:
            new_vals_list.append({
                "name": att.name,
                "res_model": att.res_model,
                "res_id": att.res_id,
                "type": att.type,
                "url": att.url,
                "raw": att.raw,
                "mfg_custom_doc_type": att.mfg_custom_doc_type,
                "mfg_custom_doc_state": "draft",
                "mfg_custom_version": att.mfg_custom_version + 1,
                "mfg_custom_version_reason": reason or False,
            })

        new_attachments = self.create(new_vals_list)

        # 把原附件指向新版，並標為 obsolete
        for old_att, new_att in zip(self, new_attachments):
            old_att.with_context(tracking_disable=True).write({
                "mfg_custom_superseded_by_id": new_att.id,
                "mfg_custom_doc_state": "obsolete",
            })
            # Odoo 20 的 ir.attachment 沒有 chatter（不繼承 mail.thread），
            # 因此以「版本說明」欄位記錄觸發原因（建立時已帶入），不使用 message_post。

        return new_attachments

    # ---------------------------------------------------------------
    # 內部輔助
    # ---------------------------------------------------------------

    def _mfg_custom_compute_next_versions(self, vals_list):
        """批次計算每筆 vals 應取得的下一版本號.

        規則：當 ``res_model`` 與 ``res_id`` 與 ``name`` 三者皆已填入，
        取 DB 中「同 res_model+res_id+name」內 ``mfg_custom_version`` 最大者 + 1。
        任一欄位缺漏（例如暫存附件尚未掛到單據）時，新版本號直接使用預設 1。

        :param vals_list: create 即將處理的 vals 串列（原樣會被讀，但不修改）
        :returns: {(res_model, res_id, name): next_version_int}
        """
        # 先把要查的群組挑出來
        groups = {
            (v.get("res_model"), v.get("res_id"), v.get("name"))
            for v in vals_list
            if v.get("res_model") and v.get("res_id") and v.get("name")
        }
        if not groups:
            return {}

        result = {}
        for res_model, res_id, name in groups:
            existing = self.search_read(
                [("res_model", "=", res_model), ("res_id", "=", res_id), ("name", "=", name)],
                ["mfg_custom_version"],
                order="mfg_custom_version desc",
                limit=1,
            )
            current_max = existing[0]["mfg_custom_version"] if existing else 0
            # 注意：要遞增，且若 vals_list 中本就有多筆同 key 也會在外部建立時
            # 一一加上 +1 之後的 offset — 此處先給最小可用的下一版即可。
            result[(res_model, res_id, name)] = (current_max or 0) + 1
        return result

    def _mfg_custom_auto_obsolete_predecessors(self):
        """對 recordset 中 doc_state='released' 的附件，把同群組其他附件轉為 obsolete.

        群組鍵：``(res_model, res_id, name)``，排除自身與已 obsolete 的記錄。
        同時將這些前代附件的 ``mfg_custom_superseded_by_id`` 指到自身。
        """
        by_group = defaultdict(list)
        for att in self.filtered(lambda a: a.mfg_custom_doc_state == "released"):
            if not att.res_model or not att.res_id or not att.name:
                continue
            by_group[(att.res_model, att.res_id, att.name)].append(att)

        for (res_model, res_id, name), new_att_list in by_group.items():
            new_ids = [a.id for a in new_att_list]
            domain = Domain([
                ("res_model", "=", res_model),
                ("res_id", "=", res_id),
                ("name", "=", name),
                ("id", "not in", new_ids),
                ("mfg_custom_doc_state", "!=", "obsolete"),
            ])
            predecessors = self.with_context(tracking_disable=True).search(domain)
            for predecessor in predecessors:
                predecessor.mfg_custom_superseded_by_id = new_att_list[0]
                predecessor.mfg_custom_doc_state = "obsolete"

    # ---------------------------------------------------------------
    # 便利動作（在 UI 可呼叫）
    # ---------------------------------------------------------------

    def action_mfg_custom_release(self):
        """使用者動作：把選中的草稿/審核中附件一次性切到 released."""
        eligible = self.filtered(lambda a: a.mfg_custom_doc_state in ("draft", "in_review"))
        if not eligible:
            raise UserError(self.env._("目前選取的附件皆不符合發行條件（需為草稿或審核中）。"))
        eligible.write({"mfg_custom_doc_state": "released"})
        return True

    def action_mfg_custom_revoke_release(self):
        """使用者動作：將 released / obsolete 退回到 draft（重新校圖流程用）."""
        eligible = self.filtered(lambda a: a.mfg_custom_doc_state in ("released", "obsolete"))
        if not eligible:
            raise UserError(self.env._("目前選取的附件皆不可退回草稿。"))
        # 清掉 superseded_by 反向連結，避免干擾下次 bump
        eligible.write({
            "mfg_custom_doc_state": "draft",
            "mfg_custom_superseded_by_id": False,
        })
        return True
