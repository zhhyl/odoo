# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Base",
    "version": "20.0.1.1.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 350,
    "summary": "共用 mixin、群組、序號、mail subtype 入口（其他 MFG Custom 模組的前置）",
    "description": """
MFG Custom - Base
=================

為整個 mfg_custom_* 與 plm_custom_* 模組群提供：

* 抽象 mixin ``mfg_custom.model.mixin`` （含 mail.thread、company、code、active、tags）
* 共用安全群組（User / Manager / Engineering / Quality）
* 共用序號（``mfg_custom.sequence.mixin``）
* 共用 mail.message.subtype（狀態變更預設追蹤）

安裝此模組後，下游模組（mfg_custom_approval、mfg_custom_quality 等）皆可安全相依。
""",
    "depends": ["mail"],
    "data": [
        "security/mfg_custom_security.xml",
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "views/mfg_custom_tag_views.xml",
        "views/mfg_custom_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
