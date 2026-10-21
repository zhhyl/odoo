# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Multi-level Approval",
    "version": "20.0.1.1.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 351,
    "summary": "通用多層簽核引擎（state machine + approver chain）",
    "description": """
MFG Custom - Multi-level Approval
=================================

通用多層簽核引擎，可掛載到任何業務模型（plm_custom.eco、sale.order、mrp.production 等）。
取代 Enterprise ``approvals`` 模組。

提供：

* 抽象 mixin ``mfg_custom.approval.mixin``（可由其他模型繼承）
* 簽核規則 ``mfg_custom.approval.rule``（含適用 model 與 domain）
* 簽核關卡 ``mfg_custom.approval.step``（支援 user / group / group_all / field 四種 approver_mode）
* 簽核申請 ``mfg_custom.approval.request``（state machine：draft/pending/approved/rejected/cancelled）
* 簽核紀錄 ``mfg_custom.approval.line``（每關卡的決策與意見）

安裝後即可在「MFG Custom > 設定 > 簽核規則」建立流程，
並讓 ``plm_custom.eco``、``sale.order`` 等模型透過繼承 mixin 取得簽核按鈕。
""",
    "depends": ["mfg_custom_base", "mail"],
    "data": [
        "security/mfg_approval_security.xml",
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "data/mail_template_data.xml",
        "views/mfg_approval_rule_views.xml",
        "views/mfg_approval_step_views.xml",
        "views/mfg_approval_request_views.xml",
        "views/mfg_approval_request_menus.xml",
        "views/mfg_approval_mixin_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
