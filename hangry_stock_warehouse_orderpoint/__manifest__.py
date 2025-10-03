{
    "name": "Test Hangry Github Issue Replenishment",
    "version": "18.0.1.0.0",
    "summary": "Contoh database population via odoo populate",
    "depends": ["stock"],
    "data": ["data/ir_cron.xml"],
    "license": "LGPL-3",
    "post_init_hook": "post_init_create_indexes",
    "author": "Faris Bassam",
    "installable": True,

}