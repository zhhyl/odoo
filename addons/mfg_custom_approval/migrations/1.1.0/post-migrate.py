# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""把舊的 ``res_model``（技術模型名 字串）資料回填到新的 ``model_id`` 欄位。

20.0.1.0.0 → 20.0.1.1.0
=======================

* ``mfg_custom.approval.rule.res_model`` 改為由 ``model_id`` 帶出的 related 欄位，
  管理介面改以下拉選單選擇單據類型。
* ``mfg_custom.approval.step.approver_field`` / ``amount_field`` 改為由
  ``ir.model.fields`` 帶出的 related 欄位（避免管理員手打欄位名）。

舊值一律以原生 SQL 讀取，避免欄位型別變更後 ORM 已把舊值清空。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _read_old(cr, table, column, extra_where=""):
    """以原生 SQL 讀出舊欄位的值（欄位型別已變更時仍可取得原始資料）。"""
    cr.execute(
        f'SELECT id, "{column}" FROM "{table}" '
        f'WHERE "{column}" IS NOT NULL AND "{column}" != %s {extra_where}',
        ("",),
    )
    return cr.fetchall()


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Rule = env["mfg_custom.approval.rule"]
    Step = env["mfg_custom.approval.step"]
    IrModel = env["ir.model"]
    IrModelFields = env["ir.model.fields"]

    approvable = set(Rule._get_approvable_models())

    # --- rule: res_model 字串 → model_id -----------------------------------
    for rule_id, res_model in _read_old(cr, "mfg_custom_approval_rule", "res_model"):
        model = IrModel.search([("model", "=", res_model)], limit=1)
        if not model:
            _logger.warning(
                "mfg_custom_approval: 找不到模型 %s，規則 #%s 的 model_id 留空。",
                res_model,
                rule_id,
            )
            continue
        if res_model not in approvable:
            _logger.warning(
                "mfg_custom_approval: 模型 %s 尚未掛載簽核功能，規則 #%s 的 model_id 留空。",
                res_model,
                rule_id,
            )
            continue
        rule = Rule.browse(rule_id)
        if not rule.model_id:
            rule.model_id = model.id

    # --- step: approver_field / amount_field 字串 → ir.model.fields ---------
    for step_id, field_name in _read_old(
        cr, "mfg_custom_approval_step", "approver_field"
    ):
        step = Step.browse(step_id)
        if step.approver_field_id:
            continue
        if not step.rule_id.res_model:
            _logger.warning(
                "mfg_custom_approval: 關卡 #%s 的規則未指定 model_id，"
                "無法回填 approver_field（%s），請手動設定。",
                step_id,
                field_name,
            )
            continue
        field = IrModelFields.search(
            [("model", "=", step.rule_id.res_model), ("name", "=", field_name)],
            limit=1,
        )
        if field:
            step.approver_field_id = field.id

    for step_id, field_name in _read_old(
        cr, "mfg_custom_approval_step", "amount_field"
    ):
        step = Step.browse(step_id)
        if step.amount_field_id:
            continue
        if not step.rule_id.res_model:
            _logger.warning(
                "mfg_custom_approval: 關卡 #%s 的規則未指定 model_id，"
                "無法回填 amount_field（%s），請手動設定。",
                step_id,
                field_name,
            )
            continue
        field = IrModelFields.search(
            [("model", "=", step.rule_id.res_model), ("name", "=", field_name)],
            limit=1,
        )
        if field:
            step.amount_field_id = field.id
