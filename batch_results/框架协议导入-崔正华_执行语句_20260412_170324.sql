-- ========================================
-- 框架协议导入-崔正华 - 执行语句
-- 生成时间: 2026-04-12 17:03:24
-- 总计: 2 条语句
-- ========================================

-- 语句 1
UPDATE tphct02
SET item_id = '01871505',
    物料名称 = '螺钉',
    category = '370299',
    item_uom = 'EA',
    ops_remark = '72480 框架协议导入-崔正华'
WHERE bpo_line_id = 'test';

-- 语句 2
UPDATE tphct02
SET qty = '1',
    bpo_price = '3',
    tax_rate = '5',
    ops_remark = '72480 框架协议导入-崔正华'
WHERE bpo_line_id = 'test2';
