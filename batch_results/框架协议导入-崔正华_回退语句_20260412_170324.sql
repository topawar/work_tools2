-- ========================================
-- 框架协议导入-崔正华 - 回退语句
-- 生成时间: 2026-04-12 17:03:24
-- 总计: 2 条语句
-- ========================================

-- 语句 1
UPDATE tphct02
SET item_id = '01605688',
    物料名称 = '蝶阀',
    category = '160401',
    item_uom = 'EA',
    ops_remark = ''
WHERE bpo_line_id = 'test';

-- 语句 2
UPDATE tphct02
SET qty = '2',
    bpo_price = '4',
    tax_rate = '6',
    ops_remark = ''
WHERE bpo_line_id = 'test2';
